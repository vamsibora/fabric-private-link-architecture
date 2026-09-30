"""Schema Manager: Delta table definitions for Bronze and staging, driven
by control.entity_column, plus the framework technical columns (spec
section 41).

Bronze tables live in a schema-enabled Lakehouse (<target_schema>.<table>,
e.g. sqlserver.customer -- the same layout as the working Dev reference
lh_bronze_dev with rio.department). Staging tables live in the `staging`
schema. Source business columns keep their names; the framework only adds
bronze_* columns (and _staging_run_id in staging).

Evolution is additive only: missing columns are added with ALTER TABLE ...
ADD COLUMNS (the reference notebook's pattern); nothing is ever dropped or
retyped automatically.
"""

from typing import Iterable, List, Sequence, Set, Tuple

from notebooks.bronze.models import STAGING_RUN_ID_COLUMN, STRATEGY_HISTORY, EntityConfig

# Framework technical columns on EVERY Bronze table.
TECHNICAL_COLUMNS: Tuple[Tuple[str, str], ...] = (
    ("bronze_run_id", "STRING"),
    ("bronze_entity_run_id", "STRING"),
    ("bronze_created_datetime", "TIMESTAMP"),
    ("bronze_updated_datetime", "TIMESTAMP"),
    ("bronze_ingestion_datetime", "TIMESTAMP"),
    ("bronze_source_system", "STRING"),
    ("bronze_source_table", "STRING"),
    ("bronze_record_hash", "STRING"),
    ("bronze_record_status", "STRING"),   # ACTIVE | DELETED
)

# Only on HISTORY-strategy tables (source history, not business SCD2).
HISTORY_COLUMNS: Tuple[Tuple[str, str], ...] = (
    ("bronze_valid_from", "TIMESTAMP"),
    ("bronze_valid_to", "TIMESTAMP"),
    ("bronze_is_current", "BOOLEAN"),
)

TECHNICAL_COLUMN_NAMES = frozenset(name for name, _ in TECHNICAL_COLUMNS + HISTORY_COLUMNS) | {STAGING_RUN_ID_COLUMN}


def quote(identifier: str) -> str:
    """Spark SQL identifier quoting (backticks, embedded backticks doubled)."""
    return "`" + identifier.replace("`", "``") + "`"


def business_column_definitions(entity: EntityConfig) -> List[Tuple[str, str]]:
    return [(c.target_column, c.target_data_type) for c in entity.ordered_columns]


def bronze_column_definitions(entity: EntityConfig) -> List[Tuple[str, str]]:
    columns = business_column_definitions(entity) + list(TECHNICAL_COLUMNS)
    if entity.write_strategy == STRATEGY_HISTORY:
        columns += list(HISTORY_COLUMNS)
    return columns


def staging_column_definitions(entity: EntityConfig) -> List[Tuple[str, str]]:
    """Staging is SOURCE-shaped: source column names (as the copy activity
    writes them) plus the run marker the copy stamps on every row
    (additionalColumns). Mapping and casting to target names/types happens
    once, when staging is read (staging_manager.projection). The copy's
    Overwrite action may redefine this schema; that is expected."""
    return [(c.source_column, c.target_data_type) for c in entity.ordered_columns] + [(STAGING_RUN_ID_COLUMN, "STRING")]


def build_create_table_sql(table_fqn: str, columns: Sequence[Tuple[str, str]]) -> str:
    body = ",\n    ".join(f"{quote(name)} {data_type}" for name, data_type in columns)
    return f"CREATE TABLE IF NOT EXISTS {table_fqn} (\n    {body}\n) USING DELTA"


def build_create_schema_sql(schema: str) -> str:
    return f"CREATE SCHEMA IF NOT EXISTS {quote(schema)}"


def missing_columns(existing: Iterable[str], required: Sequence[Tuple[str, str]]) -> List[Tuple[str, str]]:
    present: Set[str] = {c.lower() for c in existing}
    return [(name, data_type) for name, data_type in required if name.lower() not in present]


def build_add_columns_sql(table_fqn: str, columns: Sequence[Tuple[str, str]]) -> str:
    definitions = ", ".join(f"{quote(name)} {data_type}" for name, data_type in columns)
    return f"ALTER TABLE {table_fqn} ADD COLUMNS ({definitions})"


class SchemaManager:
    """Spark adapter: ensures schemas/tables exist and carry every required column."""

    def __init__(self, spark):
        self.spark = spark

    def _ensure(self, schema: str, table_fqn: str, columns: Sequence[Tuple[str, str]]) -> List[str]:
        self.spark.sql(build_create_schema_sql(schema))
        self.spark.sql(build_create_table_sql(table_fqn, columns))
        existing = [f.name for f in self.spark.table(table_fqn).schema.fields]
        added = missing_columns(existing, columns)
        if added:
            self.spark.sql(build_add_columns_sql(table_fqn, added))
        return [name for name, _ in added]

    def ensure_bronze_table(self, entity: EntityConfig) -> List[str]:
        return self._ensure(entity.target_schema, entity.target_fqn, bronze_column_definitions(entity))

    def ensure_staging_table(self, entity: EntityConfig) -> List[str]:
        return self._ensure(entity.staging_schema, entity.staging_fqn, staging_column_definitions(entity))

    def ensure_entity_tables(self, entity: EntityConfig) -> dict:
        return {
            "staging_added": self.ensure_staging_table(entity),
            "bronze_added": self.ensure_bronze_table(entity),
        }
