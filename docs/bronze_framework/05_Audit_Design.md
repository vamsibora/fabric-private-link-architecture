# 05 — Audit Design (central Fabric SQL Database)

The `BronzeFrameworkAudit` Fabric SQL Database lives in the Audit / Operations
workspace, schema `audit`. **Every** ingestion workspace and environment
writes to it, so it is cross-workspace by design. Its source is under
`sql_database/audit/` and it is migrated by `migration_runner` target
`AUDIT_DB`.

The database uses the full SQL Server T-SQL surface: enforced PK/FK,
`DEFAULT`, `CHECK`, `IDENTITY`, `NVARCHAR` and nonclustered indexes. None of
these are available in the Fabric Warehouse.

## Correlation

```text
audit.run            run_id          yyyyMMdd-HHmmss-XXXXXX (pipeline expression or run_manager.new_run_id)
 └ audit.entity_run  entity_run_id   <run_id>-E<entity_id> (deterministic; retries bump attempt_number)
    ├ audit.activity    activity_id   IDENTITY
    ├ audit.error       error_id      IDENTITY
    ├ audit.validation  validation_id IDENTITY
    └ audit.file        file_id       IDENTITY
```

`run_id` and `entity_run_id` also appear in Bronze technical columns, landing
file names (through `run_timestamp`), `control.watermark` and the Warehouse
migration ledger (`run_id`).

## Tables (`ddl/10_tables`)

| Table | Grain | Key columns |
|---|---|---|
| `audit.run` | one per framework execution | framework_name, environment, workspace_id/name, pipeline_name/run_id, notebook_name, trigger_type/name, initiated_by, run_timestamp, entity_group, start/end, status (`STARTED`, `RUNNING`, `SUCCEEDED`, `PARTIAL_SUCCESS`, `FAILED`, `CANCELLED`), total/successful/failed/skipped entities, message |
| `audit.entity_run` | one per entity per run | entity_id, source_system/schema/table, target_schema/table, load_type, write_strategy, landing_enabled, landing_path, status (`STARTED`, `EXTRACTING`, `EXTRACTED`, `PROCESSING`, `SUCCEEDED`, `FAILED`, `SKIPPED`, `CANCELLED`), attempt_number, source/staging/inserted/updated/deleted/rejected/bronze row counts, watermark_before/after, error_message |
| `audit.activity` | one per event | activity_type (`COPY_COMPLETED`, `STAGING_VERIFIED`, `STAGING_LOADED_FROM_LANDING`, `VALIDATION_COMPLETED`, `DEDUPLICATION_COMPLETED`, `ANONYMISATION_COMPLETED`, `HASH_COMPLETED`, `<STRATEGY>_COMPLETED`, `WATERMARK_UPDATED`, `RETRY_SCHEDULED`, `SCHEMA_MIGRATION_COMPLETED`), activity_source (`PIPELINE`/`NOTEBOOK`), status, rows_affected, duration_ms |
| `audit.error` | one per error | error_stage, error_code (the original SQLSTATE:native / Spark error class / Fabric code), sanitised error_message, is_retryable, attempt_number, stack_trace |
| `audit.validation` | one per rule per entity run | validation_rule_id (NULL = built-in), rule, type, stage, status (`PASSED`, `FAILED`, `WARNING`, `IGNORED`), failure_action, severity, expected/actual value (counts only), failed_row_count |
| `audit.file` | one per landing file | container, file_path (unique with container), size, row_count, status (`CREATED`, `PROCESSED`, `FAILED`, `REPLAYED`), processed_run_id |
| `audit.schema_migration_history` | migration ledger for this database | same contract as `control.schema_migration_history` |

Indexes (`20_indexes/020_audit_indexes.sql`) cover run_id, entity_run_id,
source_system/source_table, status, start_datetime and environment.

## Stored procedures (`procs/`, repeatable `CREATE OR ALTER`)

| Procedure | Called by | Behaviour |
|---|---|---|
| `usp_start_run` | pipeline, `AuditManager.start_run` | Insert, or reopen as RUNNING when run_id exists (notebook in pipeline mode) |
| `usp_complete_run` | notebook, pipeline failure branch | `@status NULL` derives the status from entity_run. An explicit status only applies if the run is not already terminal, so the pipeline's FAILED never overwrites the notebook's result. Counts are always recomputed. |
| `usp_start_entity_run` | extract pipeline, replay | Insert, or on retry increment attempt_number and reset end/error |
| `usp_update_entity_run` | extract pipeline, notebook | EXTRACTED / PROCESSING / FAILED transitions. NULL params keep existing values. |
| `usp_complete_entity_run` | notebook | Final status, counts, committed watermark_after |
| `usp_log_activity` | both | Append an event; duration derived from timestamps |
| `usp_log_error` | both | Append an error (message truncated to 4000) |
| `usp_log_validation` | notebook | Append a validation result |
| `usp_log_file` | extract pipeline, notebook | Upsert a landing file by (container, path) |
| `usp_get_run_entities` | notebook | Entities of a run in a status (default EXTRACTED) |
| `usp_get_entity_baseline` | notebook | Last successful run for an entity in an environment (ROW_COUNT_ANOMALY baseline) |

Named-parameter `EXEC [audit].[usp_x] @a = ?, …` is used from Python
(`audit_manager._exec_sql`), so adding optional proc parameters never breaks
callers.

## Monitoring views (`views/`) and the spec §62 operator questions

| # | Question | View |
|---|---|---|
| 1 | What runs are executing? | `vw_run_summary` (`is_executing`) |
| 2 | Which entities failed? | `vw_entity_status` (status = FAILED), `vw_recent_errors` |
| 3 | Which entities succeeded? | `vw_entity_status` |
| 4 | What was the source row count? | `vw_entity_status.source_row_count` |
| 5 | What was the Bronze row count? | `vw_entity_status.bronze_row_count` |
| 6 | Which entities have not loaded recently? | `vw_watermark_status.is_not_loaded_recently` (> 24 h since last success) |
| 7 | What is the latest watermark? | `vw_watermark_status.latest_watermark` |
| 8 | Which entities repeatedly fail? | `vw_repeated_failures` (≥ 3 failures in 7 days) |
| 9 | Which validations are failing? | `vw_validation_failures` |
| 10 | Which pipelines are slow? | `vw_load_performance` (duration, rows/s, copy vs write ms) |
| 11 | Which sources have extraction problems? | `vw_recent_errors WHERE error_stage IN ('EXTRACT','LANDING')` |
| 12 | Which landing files were created? | `vw_landing_files` (plus `is_replayable`) |
| 13 | Which entities have stale watermarks? | `vw_watermark_status.is_watermark_stale` (unchanged across the last 5 successes) |

`vw_run_summary` also carries `error_count` and duration.
`vw_entity_status` shows the latest attempt per environment and entity.

## Audit manager boundaries (`notebooks/bronze/audit_manager.py`)

- **Fail fast** (raises `AuditConnectionError`): `start_run`,
  `start_entity_run`, `get_run_entities`. An untracked run is worse than no
  run.
- **Fail soft** (returns `bool`): every `log_*`, `update_*` and `complete_*`
  call. On failure it writes JSON to
  `Files/_framework_fallback/audit/<kind>/<uuid>.json` and logs at
  `CRITICAL`. With `audit_failure_is_critical = true`, it then raises
  `AuditCriticalError`.
- `audit_enabled = false` turns every call into a successful no-op.
- There is one pyodbc connection per thread (`threading.local`), with one
  reconnect-and-retry per call.
- **No sensitive values.** Messages pass through
  `error_manager.sanitise_message`, which redacts e-mails, 7+ digit runs and
  quoted literals. Validation rows hold counts only.

Sample data for exercising the views on DEV only:
`sql_database/audit/samples/900_sample_audit_records.sql`. It is not a
migration root, so run it by hand.

## Why audit is not in the Warehouse

Audit is append-heavy, needs enforced keys, point updates and indexes, and
serves operators across every workspace. Control metadata is
low-write configuration that is promoted with the code. Keeping them apart
means the Warehouse can be redeployed without touching operational history,
and one database answers questions about every workspace.
