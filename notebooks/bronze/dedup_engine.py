"""Deduplication Engine.

  Current-state strategies (MERGE / APPEND / REPLACE with a primary key):
      keep ONE row per primary key -- the latest by watermark column, then
      by ingestion order (_bronze_ingest_seq, assigned when staging is read).
      MERGE requires a single source row per key; this guarantees it.

  HISTORY strategy:
      several rows per key are legitimate source history, so only exact
      duplicates (every business column equal) are removed.

  No primary key: exact duplicates are removed.
"""

from typing import List, Tuple

from notebooks.bronze.models import STRATEGY_HISTORY, EntityConfig

INGEST_SEQ_COLUMN = "_bronze_ingest_seq"


def dedup_mode(entity: EntityConfig) -> str:
    if entity.write_strategy == STRATEGY_HISTORY or not entity.primary_key:
        return "EXACT"
    return "LATEST_PER_KEY"


def latest_per_key_order(entity: EntityConfig) -> List[Tuple[str, str]]:
    """(column, direction) ordering inside each key partition; row 1 wins."""
    order = []
    if entity.watermark_target_column:
        order.append((entity.watermark_target_column, "desc_nulls_last"))
    order.append((INGEST_SEQ_COLUMN, "desc"))
    return order


class DedupEngine:
    """Spark adapter. Returns (df, duplicates_removed)."""

    def deduplicate(self, df, entity: EntityConfig):
        from pyspark.sql import Window
        from pyspark.sql import functions as F

        before = df.count()
        if dedup_mode(entity) == "EXACT":
            result = df.dropDuplicates(list(entity.business_columns))
        else:
            ordering = []
            for column, direction in latest_per_key_order(entity):
                ordering.append(F.col(column).desc_nulls_last() if direction == "desc_nulls_last"
                                else F.col(column).desc())
            window = Window.partitionBy(*[F.col(c) for c in entity.primary_key]).orderBy(*ordering)
            result = (df.withColumn("_bronze_rn", F.row_number().over(window))
                      .filter(F.col("_bronze_rn") == 1)
                      .drop("_bronze_rn"))
        after = result.count()
        return result, before - after
