"""Watermark Manager (spec section 54).

  1. read the last successful watermark (control.watermark)
  2. the pipeline passes it to source extraction (control.fn_active_entities
     builds the WHERE clause from the same stored value)
  3. capture the new maximum from the staged batch BEFORE anonymisation
  4. commit ONLY after the Bronze write and post-validation succeeded
  5. never move backwards; an empty batch keeps the old value
  6. record before/after in audit.entity_run

Canonical string forms stored in control.watermark.last_successful_watermark
(and understood by control.fn_active_entities):
  DATETIME  yyyy-MM-dd HH:mm:ss.ffffff (UTC, microseconds)
  NUMERIC   plain decimal string, no exponent
  STRING    the value itself

The commit is a single-row UPDATE guarded by the previously read value
(optimistic concurrency). 0 rows updated means another run moved the
watermark first -> WatermarkConflictError (never overwrite it).
"""

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Callable, Optional

from notebooks.bronze.error_manager import STAGE_WATERMARK, MetadataError, WatermarkConflictError
from notebooks.bronze.models import WATERMARK_DATETIME, WATERMARK_NUMERIC, WATERMARK_STRING, EntityConfig

_DATETIME_FORMAT = "%Y-%m-%d %H:%M:%S.%f"


def parse_watermark(value: Optional[str], watermark_type: str):
    """Canonical string -> comparable Python value (None stays None)."""
    if value is None or value == "":
        return None
    if watermark_type == WATERMARK_DATETIME:
        text = str(value).replace("T", " ")
        for fmt in (_DATETIME_FORMAT, "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
            try:
                return datetime.strptime(text[:26], fmt)
            except ValueError:
                continue
        raise MetadataError(f"Unparseable DATETIME watermark {value!r}", stage=STAGE_WATERMARK)
    if watermark_type == WATERMARK_NUMERIC:
        try:
            return Decimal(str(value))
        except InvalidOperation as ex:
            raise MetadataError(f"Unparseable NUMERIC watermark {value!r}", stage=STAGE_WATERMARK) from ex
    if watermark_type == WATERMARK_STRING:
        return str(value)
    raise MetadataError(f"Unknown watermark_type {watermark_type!r}", stage=STAGE_WATERMARK)


def format_watermark(value, watermark_type: str) -> Optional[str]:
    """Python/Spark value -> canonical string."""
    if value is None:
        return None
    if watermark_type == WATERMARK_DATETIME:
        if isinstance(value, str):
            value = parse_watermark(value, WATERMARK_DATETIME)
        if value.tzinfo is not None:
            value = value.astimezone(timezone.utc).replace(tzinfo=None)
        return value.strftime(_DATETIME_FORMAT)
    if watermark_type == WATERMARK_NUMERIC:
        return format(Decimal(str(value)).normalize(), "f")
    return str(value)


def resolve_watermark_after(before: Optional[str], batch_max, watermark_type: str) -> Optional[str]:
    """The watermark to commit: max(before, batch_max). Never moves
    backwards; an empty batch (batch_max None) keeps `before`."""
    if batch_max is None:
        return before
    candidate = format_watermark(batch_max, watermark_type)
    if before is None:
        return candidate
    return candidate if parse_watermark(candidate, watermark_type) > parse_watermark(before, watermark_type) else before


_SELECT_SQL = "SELECT last_successful_watermark FROM [control].[watermark] WHERE entity_id = ?"
_UPDATE_SQL = (
    "UPDATE [control].[watermark] SET last_successful_watermark = ?, last_run_id = ?, last_entity_run_id = ?, "
    "updated_datetime = ? WHERE entity_id = ? AND "
    "((last_successful_watermark IS NULL AND ? IS NULL) OR last_successful_watermark = ?)"
)
_INSERT_SQL = (
    "INSERT INTO [control].[watermark] (entity_id, last_successful_watermark, last_run_id, last_entity_run_id, "
    "updated_datetime) SELECT ?, ?, ?, ?, ? WHERE NOT EXISTS "
    "(SELECT 1 FROM [control].[watermark] WHERE entity_id = ?)"
)


class WatermarkManager:
    """pyodbc adapter over control.watermark in the Warehouse."""

    def __init__(self, connection_factory: Callable[[], object]):
        self._connection_factory = connection_factory

    def get(self, entity_id: int) -> Optional[str]:
        conn = self._connection_factory()
        try:
            cursor = conn.cursor()
            cursor.execute(_SELECT_SQL, entity_id)
            row = cursor.fetchone()
            return row[0] if row else None
        finally:
            conn.close()

    def commit(self, entity: EntityConfig, before: Optional[str], after: Optional[str],
               run_id: str, entity_run_id: str) -> bool:
        """Persist `after`. Returns False when there is nothing to change."""
        if after is None or after == before:
            return False
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        conn = self._connection_factory()
        try:
            cursor = conn.cursor()
            cursor.execute(_UPDATE_SQL, after, run_id, entity_run_id, now, entity.entity_id, before, before)
            if cursor.rowcount == 0:
                cursor.execute(_SELECT_SQL, entity.entity_id)
                existing = cursor.fetchone()
                if existing is None:
                    cursor.execute(_INSERT_SQL, entity.entity_id, after, run_id, entity_run_id, now, entity.entity_id)
                    return True
                raise WatermarkConflictError(
                    f"watermark for entity {entity.entity_id} changed concurrently "
                    f"(expected {before!r}, found {existing[0]!r}); not overwriting",
                    stage=STAGE_WATERMARK,
                )
            return True
        finally:
            conn.close()


def batch_max_watermark(df, entity: EntityConfig):
    """Spark: max of the watermark column in the staged batch (pre-anonymisation)."""
    if not entity.watermark_target_column:
        return None
    from pyspark.sql import functions as F

    return df.agg(F.max(F.col(entity.watermark_target_column)).alias("m")).collect()[0]["m"]
