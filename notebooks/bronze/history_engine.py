"""Historical Load Engine: Bronze SOURCE history (spec sections 17-18).

Bronze keeps every distinct version of a source record:

    CustomerId | Address    | ModifiedDate | bronze_valid_from | bronze_valid_to | bronze_is_current
    100        | Birmingham | 2026-09-01   | 2026-09-01        | 2026-09-10      | false
    100        | Solihull   | 2026-09-10   | 2026-09-10        | NULL            | true

This is source history, not business SCD Type 2 (no surrogate keys, no
business effective-dating rules) -- that belongs downstream in Silver/Gold.

Algorithm per batch (already validated, deduplicated, anonymised, hashed):

1. bronze_valid_from = the watermark value (DATETIME watermarks), else the
   entity run's ingestion time.
2. Temporal filter against the current Bronze version of each key: keep a
   row only if it is newer than the current version, or at the same
   instant with a different hash. Rows at or before the current version
   were already processed -- this makes re-running a batch a no-op.
3. Collapse consecutive identical hashes per key (ordered by valid_from,
   then ingestion order), seeding the comparison with the current Bronze
   hash, so a "touch" that changed no hashed column is not a new version.
4. valid_to = next version's valid_from; the last version is current.
5. ONE atomic Delta MERGE over a staged union:
      - insert rows (merge-key columns NULL -> never match -> INSERT)
      - one close row per affected key (merge-key = key, valid_from = the
        earliest new version) -> matches the current row -> UPDATE
        is_current = false, valid_to = that instant.
   Closing and inserting in one MERGE means a crash can never leave a key
   with zero or two current rows.

Late-arriving versions older than the current Bronze version are skipped
(documented limitation of watermark-ordered source history).
"""

from typing import Dict, List, Sequence

from notebooks.bronze.models import WATERMARK_DATETIME, EntityConfig
from notebooks.bronze.merge_engine import WriteMetrics, parse_merge_metrics
from notebooks.bronze.schema_manager import quote

MERGE_KEY_PREFIX = "_mk_"


def merge_key_columns(primary_key: Sequence[str]) -> List[str]:
    return [f"{MERGE_KEY_PREFIX}{c}" for c in primary_key]


def build_history_merge_condition(primary_key: Sequence[str], target: str = "t", source: str = "s") -> str:
    if not primary_key:
        raise ValueError("HISTORY requires a primary key")
    keys = " AND ".join(
        f"{target}.{quote(c)} = {source}.{quote(mk)}" for c, mk in zip(primary_key, merge_key_columns(primary_key))
    )
    return f"{keys} AND {target}.`bronze_is_current` = true"


def build_insert_condition(primary_key: Sequence[str], source: str = "s") -> str:
    return " AND ".join(f"{source}.{quote(mk)} IS NULL" for mk in merge_key_columns(primary_key))


def build_close_set(source: str = "s") -> Dict[str, str]:
    return {
        "bronze_is_current": "false",
        "bronze_valid_to": f"{source}.`bronze_valid_from`",
        "bronze_updated_datetime": f"{source}.`bronze_updated_datetime`",
    }


def build_temporal_keep_predicate(current_from: str = "_cur_valid_from", current_hash: str = "_cur_hash") -> str:
    """Step 2: keep rows newer than the current version (or same instant, different hash)."""
    return (f"{current_from} IS NULL OR bronze_valid_from > {current_from} "
            f"OR (bronze_valid_from = {current_from} AND bronze_record_hash <> {current_hash})")


def valid_from_source(entity: EntityConfig) -> str:
    """'watermark' when versions are dated by the source watermark, else 'ingestion'."""
    if entity.watermark_target_column and entity.watermark_type == WATERMARK_DATETIME:
        return "watermark"
    return "ingestion"


class HistoryEngine:
    """Spark adapter for the HISTORY write strategy."""

    def __init__(self, spark):
        self.spark = spark

    def write(self, df, entity: EntityConfig, ingestion_datetime) -> WriteMetrics:
        from delta.tables import DeltaTable
        from pyspark.sql import Window
        from pyspark.sql import functions as F

        from notebooks.bronze.dedup_engine import INGEST_SEQ_COLUMN

        pk = list(entity.primary_key)
        if valid_from_source(entity) == "watermark":
            df = df.withColumn("bronze_valid_from", F.col(entity.watermark_target_column).cast("timestamp"))
        else:
            df = df.withColumn("bronze_valid_from", F.lit(ingestion_datetime).cast("timestamp"))
        if INGEST_SEQ_COLUMN not in df.columns:
            df = df.withColumn(INGEST_SEQ_COLUMN, F.monotonically_increasing_id())

        current = (self.spark.table(entity.target_fqn)
                   .filter(F.col("bronze_is_current") == F.lit(True))
                   .select(*pk, F.col("bronze_record_hash").alias("_cur_hash"),
                           F.col("bronze_valid_from").alias("_cur_valid_from")))
        candidates = df.join(current, on=pk, how="left").filter(F.expr(build_temporal_keep_predicate()))

        ordering = Window.partitionBy(*pk).orderBy(F.col("bronze_valid_from"), F.col(INGEST_SEQ_COLUMN))
        candidates = (candidates
                      .withColumn("_prev_hash", F.coalesce(F.lag("bronze_record_hash").over(ordering), F.col("_cur_hash")))
                      .filter(F.col("_prev_hash").isNull() | (F.col("_prev_hash") != F.col("bronze_record_hash"))))

        ordering = Window.partitionBy(*pk).orderBy(F.col("bronze_valid_from"), F.col(INGEST_SEQ_COLUMN))
        versions = (candidates
                    .withColumn("bronze_valid_to", F.lead("bronze_valid_from").over(ordering))
                    .withColumn("bronze_is_current", F.col("bronze_valid_to").isNull())
                    .drop("_prev_hash", "_cur_hash", "_cur_valid_from", INGEST_SEQ_COLUMN))

        target_columns = [f.name for f in self.spark.table(entity.target_fqn).schema.fields]
        insert_columns = [c for c in target_columns if c in versions.columns]
        inserts = versions.select(*insert_columns)
        for mk in merge_key_columns(pk):
            inserts = inserts.withColumn(mk, F.lit(None).cast("string"))
        closes = (versions.groupBy(*pk)
                  .agg(F.min("bronze_valid_from").alias("bronze_valid_from"),
                       F.max("bronze_updated_datetime").alias("bronze_updated_datetime")))
        for column, mk in zip(pk, merge_key_columns(pk)):
            closes = closes.withColumn(mk, F.col(column).cast("string"))
        staged = inserts.unionByName(closes.drop(*pk), allowMissingColumns=True)
        # Cast merge keys back to the key types so the join is type-exact.
        key_types = {f.name: f.dataType for f in versions.schema.fields if f.name in pk}
        for column, mk in zip(pk, merge_key_columns(pk)):
            staged = staged.withColumn(mk, F.col(mk).cast(key_types[column]))

        (DeltaTable.forName(self.spark, entity.target_fqn).alias("t")
         .merge(staged.alias("s"), build_history_merge_condition(pk))
         .whenMatchedUpdate(set=build_close_set())
         .whenNotMatchedInsert(condition=build_insert_condition(pk),
                               values={c: f"s.{quote(c)}" for c in insert_columns})
         .execute())

        row = DeltaTable.forName(self.spark, entity.target_fqn).history(1).collect()[0]
        metrics = parse_merge_metrics(row["operationMetrics"] or {})
        # For history, "updated" = previous versions closed.
        return WriteMetrics(inserted=metrics.inserted, updated=metrics.updated, deleted=0)
