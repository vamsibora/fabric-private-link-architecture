"""Hash Engine: deterministic, metadata-driven record hashing for change
detection (spec section 52).

Algorithm: SHA-256 (hex, lower case) over the canonical string forms of
the entity's hash columns -- entity_column.hash_flag = 1, excluding primary
key columns and every framework technical column -- in ordinal_position
order, joined with the unit separator U+001F.

Canonicalisation rules (applied identically by the Spark expression and by
the pure-Python reference implementation used in tests):

  NULL          -> "\\N"   (a sentinel no real value renders to; keeps NULL
                           distinct from the empty string)
  STRING        -> the value as-is (no trimming, no case folding)
  TIMESTAMP     -> yyyy-MM-dd'T'HH:mm:ss.SSSSSS in the Spark session time
                   zone, which the framework pins to UTC (spark_timezone)
  DATE          -> yyyy-MM-dd
  BOOLEAN       -> "true" / "false"
  DECIMAL(p,s)  -> plain decimal string at the column's scale, no exponent
                   (Spark CAST(decimal AS STRING))
  integers      -> base-10 string
  DOUBLE/FLOAT  -> CAST AS STRING (may use exponent notation; avoid float
                   columns in hashes where possible)
  BINARY        -> lower-case hex

Hashes are computed AFTER anonymisation (anonymisation rules are required
to be deterministic, so change detection still works in lower
environments) and BEFORE technical columns are added.
"""

import hashlib
from datetime import date, datetime
from decimal import Decimal
from typing import Iterable, Sequence

from notebooks.bronze.models import ColumnConfig, EntityConfig
from notebooks.bronze.schema_manager import quote

NULL_SENTINEL = "\\N"
SEPARATOR = "\x1f"
HASH_COLUMN = "bronze_record_hash"


def _base_type(data_type: str) -> str:
    return data_type.strip().upper().split("(")[0]


def canonical_expression(column: str, data_type: str) -> str:
    """Spark SQL expression producing the canonical string for one column."""
    col = quote(column)
    base = _base_type(data_type)
    if base == "TIMESTAMP" or base == "TIMESTAMP_NTZ":
        rendered = f"date_format({col}, \"yyyy-MM-dd'T'HH:mm:ss.SSSSSS\")"
    elif base == "DATE":
        rendered = f"date_format({col}, 'yyyy-MM-dd')"
    elif base == "BOOLEAN":
        rendered = f"CASE WHEN {col} THEN 'true' ELSE 'false' END"
    elif base == "BINARY":
        rendered = f"lower(hex({col}))"
    else:
        rendered = f"CAST({col} AS STRING)"
    return f"CASE WHEN {col} IS NULL THEN '{NULL_SENTINEL}' ELSE {rendered} END"


def build_hash_expression(columns: Sequence[ColumnConfig]) -> str:
    """sha2(concat_ws(<US>, canon(c1), canon(c2), ...), 256). Every part is
    already NULL-safe, so concat_ws never silently drops a position."""
    if not columns:
        # No hash columns: every record hashes to the digest of the empty
        # string, i.e. "no business change is ever detected".
        return "sha2('', 256)"
    parts = ", ".join(canonical_expression(c.target_column, c.target_data_type) for c in columns)
    return f"sha2(concat_ws('\\u001F', {parts}), 256)"


def build_entity_hash_expression(entity: EntityConfig) -> str:
    return build_hash_expression(entity.hash_columns)


# --- pure-Python reference implementation ------------------------------------

def canonical_value(value, data_type: str) -> str:
    if value is None:
        return NULL_SENTINEL
    base = _base_type(data_type)
    if base in ("TIMESTAMP", "TIMESTAMP_NTZ"):
        if isinstance(value, datetime):
            return value.strftime("%Y-%m-%dT%H:%M:%S.%f")
        return str(value)
    if base == "DATE":
        return value.strftime("%Y-%m-%d") if isinstance(value, (date, datetime)) else str(value)
    if base == "BOOLEAN":
        return "true" if value else "false"
    if base == "BINARY":
        return bytes(value).hex()
    if base == "DECIMAL":
        scale = 0
        if "," in data_type:
            scale = int(data_type.split(",")[1].rstrip(") "))
        quantum = Decimal(1).scaleb(-scale)
        return format(Decimal(str(value)).quantize(quantum), "f")
    return str(value)


def compute_hash(values: Iterable, data_types: Iterable[str]) -> str:
    joined = SEPARATOR.join(canonical_value(v, t) for v, t in zip(values, data_types))
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()


def compute_record_hash(record: dict, entity: EntityConfig) -> str:
    columns = entity.hash_columns
    if not columns:
        return hashlib.sha256(b"").hexdigest()
    return compute_hash((record.get(c.target_column) for c in columns), (c.target_data_type for c in columns))


class HashEngine:
    """Spark adapter: adds bronze_record_hash (and the literal technical
    columns) to a DataFrame."""

    def add_hash(self, df, entity: EntityConfig):
        from pyspark.sql import functions as F

        return df.withColumn(HASH_COLUMN, F.expr(build_entity_hash_expression(entity)))

    def add_technical_columns(self, df, values: dict):
        from pyspark.sql import functions as F

        for name, value in values.items():
            df = df.withColumn(name, F.lit(value))
        return df
