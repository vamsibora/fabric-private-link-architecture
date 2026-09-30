"""Typed, immutable views of the control-schema metadata.

Everything the framework does is driven by these objects; no module
hard-codes entity-specific behaviour.
"""

import json
from dataclasses import dataclass, field
from typing import Dict, Mapping, Optional, Tuple

# --- enumerations (string constants mirror the control-schema values) -------

LOAD_FULL = "FULL"
LOAD_INCREMENTAL = "INCREMENTAL"

STRATEGY_MERGE = "MERGE"
STRATEGY_HISTORY = "HISTORY"
STRATEGY_APPEND = "APPEND"
STRATEGY_REPLACE = "REPLACE"

WATERMARK_DATETIME = "DATETIME"
WATERMARK_NUMERIC = "NUMERIC"
WATERMARK_STRING = "STRING"

CHANGE_DETECTION_HASH = "HASH"
CHANGE_DETECTION_NONE = "NONE"

ACTION_FAIL = "FAIL"
ACTION_WARN = "WARN"
ACTION_IGNORE = "IGNORE"

STAGE_PRE = "PRE"
STAGE_POST = "POST"

# Technical column framework-internal to staging: which run wrote the row.
STAGING_RUN_ID_COLUMN = "_staging_run_id"


@dataclass(frozen=True)
class ColumnConfig:
    source_column: str
    target_column: str
    ordinal_position: int
    target_data_type: str
    nullable: bool = True
    is_primary_key: bool = False
    is_watermark: bool = False
    is_hash: bool = True
    anonymisation_rule_id: Optional[int] = None
    source_expression: Optional[str] = None  # from control.column_mapping


@dataclass(frozen=True)
class AnonymisationRule:
    rule_id: int
    rule_name: str
    rule_type: str
    algorithm: Optional[str] = None
    parameters: Mapping[str, object] = field(default_factory=dict)
    salt_secret_name: Optional[str] = None

    @staticmethod
    def parse_parameters(raw: Optional[str]) -> Dict[str, object]:
        if not raw:
            return {}
        value = json.loads(raw)
        if not isinstance(value, dict):
            raise ValueError("anonymisation_rule.parameters must be a JSON object")
        return value


@dataclass(frozen=True)
class ValidationRule:
    rule_id: Optional[int]  # None for built-in rules
    rule_name: str
    rule_type: str
    column_name: Optional[str] = None
    expression: Optional[str] = None
    severity: str = "MEDIUM"
    failure_action: str = ACTION_FAIL
    stage: str = STAGE_PRE


@dataclass(frozen=True)
class LoadConfig:
    retry_enabled: bool = False
    max_retry_count: int = 0
    retry_delay_seconds: int = 30
    delete_detection_enabled: bool = False
    row_count_anomaly_threshold_pct: Optional[float] = None


@dataclass(frozen=True)
class EntityConfig:
    entity_id: int
    source_system: str
    source_type: str
    source_schema: Optional[str]
    source_table: str
    target_schema: str
    target_table: str
    staging_schema: str
    staging_table: str
    load_type: str
    landing_enabled: bool
    history_required: bool
    merge_required: bool
    primary_key: Tuple[str, ...]
    watermark_column: Optional[str]
    watermark_type: Optional[str]
    change_detection_method: str
    anonymisation_required: bool
    columns: Tuple[ColumnConfig, ...]
    validation_rules: Tuple[ValidationRule, ...] = ()
    load_config: LoadConfig = LoadConfig()
    entity_group: Optional[str] = None
    processing_priority: int = 100

    @property
    def write_strategy(self) -> str:
        if self.history_required:
            return STRATEGY_HISTORY
        if self.merge_required:
            return STRATEGY_MERGE
        if self.load_type == LOAD_FULL:
            return STRATEGY_REPLACE
        return STRATEGY_APPEND

    @property
    def is_incremental(self) -> bool:
        return self.load_type == LOAD_INCREMENTAL

    @property
    def target_fqn(self) -> str:
        return f"`{self.target_schema}`.`{self.target_table}`"

    @property
    def staging_fqn(self) -> str:
        return f"`{self.staging_schema}`.`{self.staging_table}`"

    @property
    def target_name(self) -> str:
        """Unquoted schema.table, for audit/log display."""
        return f"{self.target_schema}.{self.target_table}"

    @property
    def ordered_columns(self) -> Tuple[ColumnConfig, ...]:
        return tuple(sorted(self.columns, key=lambda c: c.ordinal_position))

    @property
    def business_columns(self) -> Tuple[str, ...]:
        return tuple(c.target_column for c in self.ordered_columns)

    @property
    def hash_columns(self) -> Tuple[ColumnConfig, ...]:
        """Columns in the business hash: hash_flag set, never a PK (the key
        identifies the record, it is not a change) and never a technical
        column."""
        return tuple(c for c in self.ordered_columns if c.is_hash and not c.is_primary_key)

    @property
    def watermark_target_column(self) -> Optional[str]:
        """The target-side name of the watermark column."""
        if not self.watermark_column:
            return None
        for c in self.columns:
            if c.is_watermark or c.source_column == self.watermark_column:
                return c.target_column
        return self.watermark_column

    def column(self, target_column: str) -> Optional[ColumnConfig]:
        for c in self.columns:
            if c.target_column == target_column:
                return c
        return None


# --- framework configuration --------------------------------------------------

_TRUE = {"true", "1", "yes", "y"}


@dataclass(frozen=True)
class FrameworkConfig:
    """control.framework_configuration for one environment, with typed
    accessors and defaults. Known keys:

      anonymisation_enabled       bool  apply anonymisation rules
      audit_enabled               bool  write to the central audit database
      fail_on_validation_error    bool  FAIL-action rules fail the entity
      max_parallel_entities       int   bounded entity concurrency
      continue_on_entity_failure  bool  keep going after an entity fails
      audit_failure_is_critical   bool  non-critical audit write failures fail the run
      landing_globally_enabled    bool  ANDed with entity.landing_enabled
      landing_container           str   ADLS container holding landing files
      landing_lakehouse_path      str   Lakehouse OneLake shortcut to the container
      sql_token_audience          str   token audience for the Warehouse
      audit_sql_token_audience    str   token audience for the audit SQL Database
      spark_timezone              str   Spark session time zone
    """

    environment: str
    values: Mapping[str, Optional[str]] = field(default_factory=dict)

    def get(self, key: str, default: Optional[str] = None) -> Optional[str]:
        value = self.values.get(key)
        return default if value is None or value == "" else value

    def get_bool(self, key: str, default: bool) -> bool:
        value = self.get(key)
        return default if value is None else value.strip().lower() in _TRUE

    def get_int(self, key: str, default: int) -> int:
        value = self.get(key)
        return default if value is None else int(value)

    @property
    def anonymisation_enabled(self) -> bool:
        # Safe default: anonymise unless the environment explicitly says not to.
        return self.get_bool("anonymisation_enabled", True)

    @property
    def audit_enabled(self) -> bool:
        return self.get_bool("audit_enabled", True)

    @property
    def fail_on_validation_error(self) -> bool:
        return self.get_bool("fail_on_validation_error", True)

    @property
    def max_parallel_entities(self) -> int:
        return max(1, self.get_int("max_parallel_entities", 4))

    @property
    def continue_on_entity_failure(self) -> bool:
        return self.get_bool("continue_on_entity_failure", True)

    @property
    def audit_failure_is_critical(self) -> bool:
        return self.get_bool("audit_failure_is_critical", False)

    @property
    def landing_globally_enabled(self) -> bool:
        return self.get_bool("landing_globally_enabled", True)

    @property
    def landing_container(self) -> str:
        return self.get("landing_container", "landing")

    @property
    def landing_lakehouse_path(self) -> str:
        return self.get("landing_lakehouse_path", "Files/landing").rstrip("/")

    @property
    def sql_token_audience(self) -> Optional[str]:
        return self.get("sql_token_audience")

    @property
    def audit_sql_token_audience(self) -> Optional[str]:
        return self.get("audit_sql_token_audience", self.sql_token_audience)

    @property
    def spark_timezone(self) -> str:
        return self.get("spark_timezone", "UTC")
