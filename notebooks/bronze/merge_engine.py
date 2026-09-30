"""Merge Engine: current-state Bronze writes (spec section 53).

  MERGE    Delta MERGE on the (composite) primary key. A matched row is
           updated only when its bronze_record_hash differs (or it was
           soft-deleted and has reappeared), so re-running the same batch
           changes nothing -- idempotent. bronze_created_datetime is never
           overwritten. With delete detection (FULL loads only), target rows
           missing from the source are soft-deleted:
           bronze_record_status = 'DELETED'. Nothing is physically deleted.
  APPEND   insert-only; idempotent per entity run via replaceWhere on
           bronze_entity_run_id (a retry replaces its own earlier attempt,
           never duplicates it).
  REPLACE  full overwrite of the Bronze table (FULL loads, no key).

This is Bronze source representation only -- no business SCD2 logic (that
belongs in Silver/Gold). HISTORY writes live in history_engine.

Clause builders are pure and unit tested; MergeEngine is the Spark adapter.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Mapping, Optional, Sequence

from notebooks.bronze.models import (
    CHANGE_DETECTION_HASH,
    LOAD_FULL,
    STRATEGY_APPEND,
    STRATEGY_MERGE,
    STRATEGY_REPLACE,
    EntityConfig,
)
from notebooks.bronze.schema_manager import quote

STATUS_ACTIVE = "ACTIVE"
STATUS_DELETED = "DELETED"

# Technical columns refreshed on every write of a row.
_REFRESHED_TECHNICAL = (
    "bronze_run_id",
    "bronze_entity_run_id",
    "bronze_updated_datetime",
    "bronze_ingestion_datetime",
    "bronze_source_system",
    "bronze_source_table",
    "bronze_record_hash",
    "bronze_record_status",
)


@dataclass(frozen=True)
class WriteMetrics:
    inserted: int = 0
    updated: int = 0
    deleted: int = 0
    rejected: int = 0


def technical_column_values(entity: EntityConfig, run_id: str, entity_run_id: str,
                            ingestion_datetime: datetime) -> Dict[str, object]:
    """Literal values for the technical columns added to every incoming row
    (bronze_record_hash is added separately by the hash engine)."""
    return {
        "bronze_run_id": run_id,
        "bronze_entity_run_id": entity_run_id,
        "bronze_created_datetime": ingestion_datetime,
        "bronze_updated_datetime": ingestion_datetime,
        "bronze_ingestion_datetime": ingestion_datetime,
        "bronze_source_system": entity.source_system,
        "bronze_source_table": entity.source_table,
        "bronze_record_status": STATUS_ACTIVE,
    }


def build_merge_condition(primary_key: Sequence[str], target: str = "t", source: str = "s") -> str:
    if not primary_key:
        raise ValueError("MERGE requires a primary key")
    return " AND ".join(f"{target}.{quote(c)} = {source}.{quote(c)}" for c in primary_key)


def build_matched_condition(entity: EntityConfig, target: str = "t", source: str = "s") -> Optional[str]:
    """Update only real changes. NONE change detection updates every match."""
    if entity.change_detection_method != CHANGE_DETECTION_HASH:
        return None
    return (f"{target}.`bronze_record_hash` <> {source}.`bronze_record_hash` "
            f"OR {target}.`bronze_record_status` <> '{STATUS_ACTIVE}' "
            f"OR {target}.`bronze_record_hash` IS NULL")


def build_update_set(entity: EntityConfig, source: str = "s") -> Dict[str, str]:
    columns = {c: f"{source}.{quote(c)}" for c in entity.business_columns if c not in entity.primary_key}
    columns.update({c: f"{source}.{quote(c)}" for c in _REFRESHED_TECHNICAL})
    return columns


def build_insert_values(columns: Sequence[str], source: str = "s") -> Dict[str, str]:
    return {c: f"{source}.{quote(c)}" for c in columns}


def build_soft_delete_set(run_id: str, entity_run_id: str) -> Dict[str, str]:
    return {
        "bronze_record_status": f"'{STATUS_DELETED}'",
        "bronze_updated_datetime": "current_timestamp()",
        "bronze_run_id": f"'{run_id}'",
        "bronze_entity_run_id": f"'{entity_run_id}'",
    }


def delete_detection_applies(entity: EntityConfig) -> bool:
    return (entity.write_strategy == STRATEGY_MERGE and entity.load_type == LOAD_FULL
            and entity.load_config.delete_detection_enabled)


def build_append_replace_where(entity_run_id: str) -> str:
    return "bronze_entity_run_id = '" + entity_run_id.replace("'", "''") + "'"


def parse_merge_metrics(metrics: Mapping[str, object]) -> WriteMetrics:
    """Delta MERGE operationMetrics -> WriteMetrics. Soft deletes are
    'not matched by source' UPDATES, so they are counted as deleted, not
    as updated."""
    def _int(key: str) -> int:
        try:
            return int(metrics.get(key) or 0)
        except (TypeError, ValueError):
            return 0

    by_source = _int("numTargetRowsNotMatchedBySourceUpdated")
    matched_updated = _int("numTargetRowsMatchedUpdated") or max(_int("numTargetRowsUpdated") - by_source, 0)
    return WriteMetrics(
        inserted=_int("numTargetRowsInserted"),
        updated=matched_updated,
        deleted=by_source + _int("numTargetRowsDeleted"),
    )


class MergeEngine:
    """Spark adapter for MERGE / APPEND / REPLACE."""

    def __init__(self, spark):
        self.spark = spark

    def _last_operation_metrics(self, table_fqn: str) -> Mapping[str, object]:
        from delta.tables import DeltaTable

        row = DeltaTable.forName(self.spark, table_fqn).history(1).collect()[0]
        return row["operationMetrics"] or {}

    def write(self, df, entity: EntityConfig, run_id: str, entity_run_id: str) -> WriteMetrics:
        strategy = entity.write_strategy
        if strategy == STRATEGY_MERGE:
            return self.merge(df, entity, run_id, entity_run_id)
        if strategy == STRATEGY_APPEND:
            return self.append(df, entity, entity_run_id)
        if strategy == STRATEGY_REPLACE:
            return self.replace(df, entity)
        raise ValueError(f"MergeEngine does not handle write strategy {strategy!r}")

    def merge(self, df, entity: EntityConfig, run_id: str, entity_run_id: str) -> WriteMetrics:
        from delta.tables import DeltaTable

        target_columns = [f.name for f in self.spark.table(entity.target_fqn).schema.fields]
        insert_columns = [c for c in target_columns if c in df.columns]
        builder = (
            DeltaTable.forName(self.spark, entity.target_fqn).alias("t")
            .merge(df.alias("s"), build_merge_condition(entity.primary_key))
            .whenMatchedUpdate(condition=build_matched_condition(entity), set=build_update_set(entity))
            .whenNotMatchedInsert(values=build_insert_values(insert_columns))
        )
        if delete_detection_applies(entity):
            builder = builder.whenNotMatchedBySourceUpdate(
                condition=f"t.`bronze_record_status` = '{STATUS_ACTIVE}'",
                set=build_soft_delete_set(run_id, entity_run_id),
            )
        builder.execute()
        return parse_merge_metrics(self._last_operation_metrics(entity.target_fqn))

    def append(self, df, entity: EntityConfig, entity_run_id: str) -> WriteMetrics:
        target_columns = [f.name for f in self.spark.table(entity.target_fqn).schema.fields]
        rows = df.count()
        (df.select(*[c for c in target_columns if c in df.columns])
           .write.format("delta").mode("overwrite")
           .option("replaceWhere", build_append_replace_where(entity_run_id))
           .saveAsTable(entity.target_fqn))
        return WriteMetrics(inserted=rows)

    def replace(self, df, entity: EntityConfig) -> WriteMetrics:
        target_columns = [f.name for f in self.spark.table(entity.target_fqn).schema.fields]
        rows = df.count()
        (df.select(*[c for c in target_columns if c in df.columns])
           .write.format("delta").mode("overwrite").saveAsTable(entity.target_fqn))
        return WriteMetrics(inserted=rows)
