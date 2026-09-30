# 08 — Validation Engine (spec §26, §50)

```text
Context: 00_master_context.md. Reference: notebooks/bronze/validation_engine.py.

- Rules come from control.validation_rule (stage PRE or POST), plus built-ins unless the entity
  overrides the same rule_type:
  PRIMARY_KEY_NULL (FAIL), DUPLICATE_PRIMARY_KEY (WARN, because dedup resolves it; this keeps
  it visible), COLUMN_MISSING (FAIL, checked against the source-shaped staging columns),
  DATA_TYPE_MISMATCH (FAIL, every non-STRING column; a column-specific rule adds to it and does
  not replace it).
- Type checks run on the RAW staging rows (staging_manager.read_raw), never on the cast frame:
  Spark's non-ANSI CAST silently NULLs bad values. Fail a row when the raw value is NOT NULL and
  its conversion (try_cast, or the column_mapping expression) is NULL.
- The engine is shared by entity threads: keep it stateless (pass raw_df per call).
- Supported: PRIMARY_KEY_NULL, DUPLICATE_PRIMARY_KEY, MANDATORY_COLUMN_NULL, COLUMN_MISSING,
  DATA_TYPE_MISMATCH (try_cast), WATERMARK_INVALID (NULL, or older than the stored watermark
  on INCREMENTAL), ROW_COUNT_ANOMALY (vs audit.usp_get_entity_baseline, threshold from
  load_configuration), CUSTOM (a Spark SQL predicate every row must satisfy).
- SQL generation is pure: build_rule_sql(rule, entity, view, previous_watermark, raw_view)
  returns a single failed_row_count.
- Each result: validation_rule_id, rule_name, rule_type, stage, status
  (PASSED/FAILED/WARNING/IGNORED), failure_action, severity, failed_row_count, expected_value,
  actual_value, error_message. Counts only, never row values.
- Actions:
  - FAIL blocks the entity when fail_on_validation_error is on (ValidationFailedError,
    non-retryable).
  - WARN is recorded and processing continues.
  - IGNORE is recorded as IGNORED and never blocks.
- Write every result to audit.validation via usp_log_validation. Nothing entity-specific is
  hard-coded.

Tests: tests/bronze/test_validation_engine.py covers the SQL for each rule type (composite PK),
built-in override behaviour, status mapping per action, blocking_failures honouring the config
switch, the row-count anomaly maths (previous 0 / None), and missing columns.
Spark test: rules evaluated against a small DataFrame.
Report: what you could NOT verify live.
```
