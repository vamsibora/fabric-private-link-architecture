"""Configuration Loader: reads control.* from the Warehouse (pyodbc) and
assembles validated, immutable EntityConfig / FrameworkConfig objects.

One query per control table (not per entity), so loading hundreds of
entities is a fixed number of round-trips. assemble_entities() is pure and
unit tested; load_*() are thin cursor adapters.

Invalid metadata raises MetadataError (non-retryable): an entity whose
metadata is wrong must fail loudly rather than be guessed at.
"""

from collections import defaultdict
from typing import Dict, Iterable, List, Mapping, Optional, Sequence

from notebooks.bronze.error_manager import STAGE_METADATA, MetadataError
from notebooks.bronze.models import (
    ACTION_FAIL,
    ACTION_IGNORE,
    ACTION_WARN,
    CHANGE_DETECTION_HASH,
    CHANGE_DETECTION_NONE,
    LOAD_FULL,
    LOAD_INCREMENTAL,
    STAGE_POST,
    STAGE_PRE,
    WATERMARK_DATETIME,
    WATERMARK_NUMERIC,
    WATERMARK_STRING,
    AnonymisationRule,
    ColumnConfig,
    EntityConfig,
    FrameworkConfig,
    LoadConfig,
    ValidationRule,
)

Row = Mapping[str, object]

_ENTITY_SQL = (
    "SELECT e.entity_id, e.source_schema, e.source_table, e.target_schema, e.target_table, "
    "e.staging_schema, e.staging_table, e.entity_group, e.load_type, e.landing_enabled, "
    "e.history_required, e.merge_required, e.primary_key, e.watermark_column, e.watermark_type, "
    "e.change_detection_method, e.anonymisation_required, e.processing_priority, "
    "s.source_system_name, s.source_type "
    "FROM [control].[entity] e "
    "JOIN [control].[source_system] s ON s.source_system_id = e.source_system_id AND s.active_flag = 1 "
    "WHERE e.active_flag = 1"
)
_COLUMN_SQL = (
    "SELECT entity_id, source_column, target_column, ordinal_position, target_data_type, nullable_flag, "
    "primary_key_flag, watermark_flag, hash_flag, anonymisation_flag, anonymisation_rule_id "
    "FROM [control].[entity_column] WHERE active_flag = 1"
)
_MAPPING_SQL = (
    "SELECT entity_id, target_column, source_expression FROM [control].[column_mapping] WHERE active_flag = 1"
)
_LOAD_CONFIG_SQL = (
    "SELECT entity_id, retry_enabled, max_retry_count, retry_delay_seconds, delete_detection_enabled, "
    "row_count_anomaly_threshold_pct FROM [control].[load_configuration] WHERE active_flag = 1"
)
_VALIDATION_SQL = (
    "SELECT validation_rule_id, entity_id, rule_name, rule_type, column_name, expression, severity, "
    "failure_action, validation_stage FROM [control].[validation_rule] WHERE active_flag = 1"
)
_ANONYMISATION_SQL = (
    "SELECT anonymisation_rule_id, rule_name, rule_type, algorithm, parameters, salt_secret_name "
    "FROM [control].[anonymisation_rule] WHERE active_flag = 1"
)
_FRAMEWORK_SQL = (
    "SELECT config_key, config_value FROM [control].[framework_configuration] "
    "WHERE environment = ? AND active_flag = 1"
)

_VALID_WATERMARK_TYPES = {WATERMARK_DATETIME, WATERMARK_NUMERIC, WATERMARK_STRING}
_VALID_ACTIONS = {ACTION_FAIL, ACTION_WARN, ACTION_IGNORE}


def fetch_dicts(cursor, sql: str, *params) -> List[Dict[str, object]]:
    cursor.execute(sql, *params)
    names = [d[0] for d in cursor.description]
    return [dict(zip(names, row)) for row in cursor.fetchall()]


def _bool(value) -> bool:
    return bool(value) and str(value).strip().lower() not in {"0", "false"}


def _split_key(value: Optional[str]) -> tuple:
    if not value:
        return ()
    return tuple(part.strip() for part in str(value).split(",") if part.strip())


def validate_entity(entity: EntityConfig, anonymisation_rules: Mapping[int, AnonymisationRule]) -> List[str]:
    """Metadata consistency checks. Returns human-readable problems (empty = valid)."""
    problems: List[str] = []
    targets = {c.target_column for c in entity.columns}
    if not entity.columns:
        problems.append("no active entity_column rows")
    if entity.load_type not in {LOAD_FULL, LOAD_INCREMENTAL}:
        problems.append(f"load_type must be FULL or INCREMENTAL, got {entity.load_type!r}")
    if entity.write_strategy in {"MERGE", "HISTORY"} and not entity.primary_key:
        problems.append(f"{entity.write_strategy} requires a primary_key")
    for key in entity.primary_key:
        if key not in targets:
            problems.append(f"primary_key column {key!r} is not an active entity_column target_column")
    if entity.is_incremental:
        if not entity.watermark_column:
            problems.append("INCREMENTAL load requires watermark_column")
        if entity.watermark_type not in _VALID_WATERMARK_TYPES:
            problems.append(f"watermark_type must be one of {sorted(_VALID_WATERMARK_TYPES)}")
        if entity.watermark_column and entity.watermark_target_column not in targets:
            problems.append(f"watermark_column {entity.watermark_column!r} is not an active entity_column")
    if entity.change_detection_method not in {CHANGE_DETECTION_HASH, CHANGE_DETECTION_NONE}:
        problems.append(f"change_detection_method must be HASH or NONE, got {entity.change_detection_method!r}")
    if entity.history_required and entity.change_detection_method != CHANGE_DETECTION_HASH:
        problems.append("history_required needs change_detection_method = HASH")
    for column in entity.columns:
        if column.anonymisation_rule_id is not None and column.anonymisation_rule_id not in anonymisation_rules:
            problems.append(
                f"column {column.target_column!r} references unknown/inactive anonymisation_rule_id "
                f"{column.anonymisation_rule_id}"
            )
    for rule in entity.validation_rules:
        if rule.failure_action not in _VALID_ACTIONS:
            problems.append(f"validation rule {rule.rule_name!r} has invalid failure_action {rule.failure_action!r}")
        if rule.stage not in {STAGE_PRE, STAGE_POST}:
            problems.append(f"validation rule {rule.rule_name!r} has invalid validation_stage {rule.stage!r}")
    return problems


def assemble_entities(
    entity_rows: Iterable[Row],
    column_rows: Iterable[Row],
    mapping_rows: Iterable[Row] = (),
    load_rows: Iterable[Row] = (),
    validation_rows: Iterable[Row] = (),
    anonymisation_rules: Optional[Mapping[int, AnonymisationRule]] = None,
    strict: bool = True,
) -> List[EntityConfig]:
    """Pure assembly of EntityConfig objects from control-table rows, ordered
    by processing_priority then entity_id. strict=True raises MetadataError
    listing every problem across every entity."""
    anonymisation_rules = anonymisation_rules or {}
    mappings: Dict[int, Dict[str, str]] = defaultdict(dict)
    for row in mapping_rows:
        mappings[int(row["entity_id"])][str(row["target_column"])] = str(row["source_expression"])

    columns: Dict[int, List[ColumnConfig]] = defaultdict(list)
    for row in column_rows:
        entity_id = int(row["entity_id"])
        target = str(row["target_column"])
        columns[entity_id].append(
            ColumnConfig(
                source_column=str(row["source_column"]),
                target_column=target,
                ordinal_position=int(row["ordinal_position"]),
                target_data_type=str(row["target_data_type"]).upper(),
                nullable=_bool(row.get("nullable_flag", True)),
                is_primary_key=_bool(row.get("primary_key_flag")),
                is_watermark=_bool(row.get("watermark_flag")),
                is_hash=_bool(row.get("hash_flag", True)),
                anonymisation_rule_id=(
                    int(row["anonymisation_rule_id"])
                    if _bool(row.get("anonymisation_flag")) and row.get("anonymisation_rule_id") is not None
                    else None
                ),
                source_expression=mappings[entity_id].get(target),
            )
        )

    loads: Dict[int, LoadConfig] = {}
    for row in load_rows:
        threshold = row.get("row_count_anomaly_threshold_pct")
        loads[int(row["entity_id"])] = LoadConfig(
            retry_enabled=_bool(row.get("retry_enabled")),
            max_retry_count=int(row.get("max_retry_count") or 0),
            retry_delay_seconds=int(row.get("retry_delay_seconds") or 0),
            delete_detection_enabled=_bool(row.get("delete_detection_enabled")),
            row_count_anomaly_threshold_pct=float(threshold) if threshold is not None else None,
        )

    rules: Dict[int, List[ValidationRule]] = defaultdict(list)
    for row in validation_rows:
        rules[int(row["entity_id"])].append(
            ValidationRule(
                rule_id=int(row["validation_rule_id"]),
                rule_name=str(row["rule_name"]),
                rule_type=str(row["rule_type"]).upper(),
                column_name=row.get("column_name"),
                expression=row.get("expression"),
                severity=str(row.get("severity") or "MEDIUM").upper(),
                failure_action=str(row.get("failure_action") or ACTION_FAIL).upper(),
                stage=str(row.get("validation_stage") or STAGE_PRE).upper(),
            )
        )

    entities: List[EntityConfig] = []
    problems: List[str] = []
    for row in entity_rows:
        entity_id = int(row["entity_id"])
        watermark_type = row.get("watermark_type")
        entity = EntityConfig(
            entity_id=entity_id,
            source_system=str(row["source_system_name"]),
            source_type=str(row.get("source_type") or ""),
            source_schema=row.get("source_schema"),
            source_table=str(row["source_table"]),
            target_schema=str(row["target_schema"]),
            target_table=str(row["target_table"]),
            staging_schema=str(row["staging_schema"]),
            staging_table=str(row["staging_table"]),
            load_type=str(row["load_type"]).upper(),
            landing_enabled=_bool(row.get("landing_enabled")),
            history_required=_bool(row.get("history_required")),
            merge_required=_bool(row.get("merge_required")),
            primary_key=_split_key(row.get("primary_key")),
            watermark_column=row.get("watermark_column") or None,
            watermark_type=str(watermark_type).upper() if watermark_type else None,
            change_detection_method=str(row.get("change_detection_method") or CHANGE_DETECTION_HASH).upper(),
            anonymisation_required=_bool(row.get("anonymisation_required")),
            columns=tuple(sorted(columns.get(entity_id, []), key=lambda c: c.ordinal_position)),
            validation_rules=tuple(rules.get(entity_id, [])),
            load_config=loads.get(entity_id, LoadConfig()),
            entity_group=row.get("entity_group"),
            processing_priority=int(row.get("processing_priority") or 100),
        )
        entity_problems = validate_entity(entity, anonymisation_rules)
        if entity_problems:
            problems.extend(f"entity {entity_id} ({entity.source_system}.{entity.source_table}): {p}"
                            for p in entity_problems)
            if strict:
                continue
        entities.append(entity)

    if strict and problems:
        raise MetadataError("Invalid control metadata:\n  " + "\n  ".join(problems), stage=STAGE_METADATA)
    return sorted(entities, key=lambda e: (e.processing_priority, e.entity_id))


def assemble_anonymisation_rules(rows: Iterable[Row]) -> Dict[int, AnonymisationRule]:
    rules: Dict[int, AnonymisationRule] = {}
    for row in rows:
        rule_id = int(row["anonymisation_rule_id"])
        rules[rule_id] = AnonymisationRule(
            rule_id=rule_id,
            rule_name=str(row["rule_name"]),
            rule_type=str(row["rule_type"]).upper(),
            algorithm=row.get("algorithm"),
            parameters=AnonymisationRule.parse_parameters(row.get("parameters")),
            salt_secret_name=row.get("salt_secret_name"),
        )
    return rules


def load_framework_config(cursor, environment: str) -> FrameworkConfig:
    rows = fetch_dicts(cursor, _FRAMEWORK_SQL, environment.upper())
    return FrameworkConfig(environment=environment.upper(),
                           values={str(r["config_key"]): r["config_value"] for r in rows})


def load_anonymisation_rules(cursor) -> Dict[int, AnonymisationRule]:
    return assemble_anonymisation_rules(fetch_dicts(cursor, _ANONYMISATION_SQL))


def load_entities(
    cursor,
    entity_ids: Optional[Sequence[int]] = None,
    entity_group: Optional[str] = None,
    anonymisation_rules: Optional[Mapping[int, AnonymisationRule]] = None,
) -> List[EntityConfig]:
    """Active entities, optionally filtered. Filtering happens after the
    fixed set of table reads, so the query count stays constant."""
    if anonymisation_rules is None:
        anonymisation_rules = load_anonymisation_rules(cursor)
    wanted = {int(i) for i in entity_ids} if entity_ids else None
    entity_rows = [
        r for r in fetch_dicts(cursor, _ENTITY_SQL)
        if (wanted is None or int(r["entity_id"]) in wanted)
        and (entity_group is None or r.get("entity_group") == entity_group)
    ]
    if wanted:
        missing = wanted - {int(r["entity_id"]) for r in entity_rows}
        if missing:
            raise MetadataError(f"Requested entity id(s) not found or inactive: {sorted(missing)}",
                                stage=STAGE_METADATA)
    return assemble_entities(
        entity_rows,
        fetch_dicts(cursor, _COLUMN_SQL),
        fetch_dicts(cursor, _MAPPING_SQL),
        fetch_dicts(cursor, _LOAD_CONFIG_SQL),
        fetch_dicts(cursor, _VALIDATION_SQL),
        anonymisation_rules,
    )
