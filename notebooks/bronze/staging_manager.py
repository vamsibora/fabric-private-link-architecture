"""Staging Manager: ephemeral Bronze Lakehouse staging (spec sections 8-9, 49).

Staging is ephemeral; Bronze is persistent. Only the STAGING table is ever
truncated -- the final Bronze table never is.

  landing_enabled = FALSE  (source -> staging -> Bronze)
      The extract pipeline's Copy activity writes to staging.<table> with
      table action OVERWRITE (truncate + load in one atomic Delta commit)
      and stamps every row with _staging_run_id = run_id
      (additionalColumns). The framework then VERIFIES staging before
      using it: every row must carry this run's id and the count must match
      the copy's rowsCopied. A stale or foreign row fails the entity rather
      than being processed.

  landing_enabled = TRUE   (landing -> staging -> Bronze)
      The framework reads this run's landing JSON (through the OneLake
      shortcut) with an explicit all-STRING schema of the entity's source
      columns (no inference: JSON omits null fields, and inferred types
      drift between files), stamps _staging_run_id and OVERWRITES staging.

Staging is always SOURCE-shaped. read() applies control.column_mapping
expressions and casts to entity_column.target_data_type exactly once, so
both paths produce identical typed business columns.

truncate() is the explicit alternative (Delta DELETE keeps the schema) if
the copy's Overwrite action is ever unsuitable.
"""

from typing import Dict, List, Optional, Tuple

from notebooks.bronze.error_manager import STAGE_STAGING, StagingIntegrityError
from notebooks.bronze.models import STAGING_RUN_ID_COLUMN, EntityConfig
from notebooks.bronze.schema_manager import quote


def build_staging_counts_sql(entity: EntityConfig, run_id: str) -> str:
    literal = "'" + run_id.replace("'", "\\'") + "'"
    return (f"SELECT COUNT(*) AS total_rows, "
            f"SUM(CASE WHEN {quote(STAGING_RUN_ID_COLUMN)} = {literal} THEN 1 ELSE 0 END) AS run_rows "
            f"FROM {entity.staging_fqn}")


def build_truncate_sql(entity: EntityConfig) -> str:
    return f"DELETE FROM {entity.staging_fqn}"


def check_staging_counts(total_rows: int, run_rows: int, expected_rows: Optional[int]) -> List[str]:
    """Problems with staging content (empty list = OK)."""
    problems = []
    if total_rows != run_rows:
        problems.append(f"staging holds {total_rows - run_rows} row(s) from another run")
    if expected_rows is not None and run_rows != expected_rows:
        problems.append(f"staging holds {run_rows} row(s) for this run but the copy reported {expected_rows}")
    return problems


def projection(entity: EntityConfig, available_columns: List[str]) -> List[Tuple[str, str]]:
    """(target_column, Spark SQL expression) for reading landing/staging
    rows into business columns: column_mapping expression when configured,
    else the source column, cast to the target data type."""
    available = {c.lower(): c for c in available_columns}
    result = []
    for column in entity.ordered_columns:
        if column.source_expression:
            expression = column.source_expression
        else:
            source = available.get(column.source_column.lower(), column.source_column)
            expression = quote(source)
        result.append((column.target_column, f"CAST({expression} AS {column.target_data_type})"))
    return result


def landing_read_schema_ddl(entity: EntityConfig) -> str:
    """Explicit JSON read schema: every source column as STRING."""
    return ", ".join(f"{quote(c.source_column)} STRING" for c in entity.ordered_columns)


def missing_source_columns(entity: EntityConfig, present_columns: List[str]) -> List[str]:
    present = {c.lower() for c in present_columns}
    return [c.source_column for c in entity.ordered_columns if c.source_column.lower() not in present]


class StagingManager:
    """Spark adapter."""

    def __init__(self, spark):
        self.spark = spark

    def truncate(self, entity: EntityConfig) -> None:
        self.spark.sql(build_truncate_sql(entity))

    def verify(self, entity: EntityConfig, run_id: str, expected_rows: Optional[int] = None) -> int:
        row = self.spark.sql(build_staging_counts_sql(entity, run_id)).collect()[0]
        total, run_rows = int(row["total_rows"] or 0), int(row["run_rows"] or 0)
        problems = check_staging_counts(total, run_rows, expected_rows)
        if problems:
            raise StagingIntegrityError(f"{entity.staging_fqn}: " + "; ".join(problems), stage=STAGE_STAGING)
        return run_rows

    def load_from_landing(self, entity: EntityConfig, landing_path: str, run_id: str) -> int:
        from pyspark.sql import functions as F

        raw = self.spark.read.format("json").schema(landing_read_schema_ddl(entity)).load(landing_path)
        staged = raw.withColumn(STAGING_RUN_ID_COLUMN, F.lit(run_id))
        (staged.write.format("delta").mode("overwrite").option("overwriteSchema", "true")
         .saveAsTable(entity.staging_fqn))
        return self.verify(entity, run_id)

    def read_raw(self, entity: EntityConfig, run_id: str):
        """This run's staged rows exactly as staged (source-shaped), for
        schema and type validation before any cast."""
        from pyspark.sql import functions as F

        return self.spark.table(entity.staging_fqn).filter(F.col(STAGING_RUN_ID_COLUMN) == F.lit(run_id))

    def read(self, entity: EntityConfig, run_id: str):
        """This run's staged rows as business columns (typed via projection),
        with an ingestion-order sequence for deterministic deduplication."""
        from pyspark.sql import functions as F

        from notebooks.bronze.dedup_engine import INGEST_SEQ_COLUMN

        df = self.spark.table(entity.staging_fqn).filter(F.col(STAGING_RUN_ID_COLUMN) == F.lit(run_id))
        mapped = [F.expr(expression).alias(target) for target, expression in projection(entity, df.columns)]
        return df.select(*mapped).withColumn(INGEST_SEQ_COLUMN, F.monotonically_increasing_id())
