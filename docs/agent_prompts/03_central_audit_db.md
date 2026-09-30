# 03 — Central cross-workspace audit database (spec §28–§35, §47, change 2)

```text
Context: 00_master_context.md. Reference implementation: sql_database/audit/**.

Build the audit plane in the Fabric SQL Database "BronzeFrameworkAudit" (Audit/Operations
workspace), schema [audit]. Every ingestion workspace writes here. Full SQL Server T-SQL.

DDL (CREATE-once, sql_database/audit/ddl/):
  00_schemas/001  CREATE SCHEMA [audit]
  05_meta/050     audit.schema_migration_history (same column contract as the Warehouse ledger)
  10_tables:
    run         run_id VARCHAR(64) PK (caller-generated), framework_name, environment,
                workspace_id/name, pipeline_name/run_id, notebook_name, trigger_type/name,
                initiated_by, run_timestamp CHAR(14), entity_group, start/end, status
                CHECK (STARTED, RUNNING, SUCCEEDED, PARTIAL_SUCCESS, FAILED, CANCELLED),
                total/successful/failed/skipped_entities
    entity_run  entity_run_id VARCHAR(80) PK = <run_id>-E<entity_id>, FK run; source/target,
                load_type, write_strategy, landing_enabled, landing_path, status
                CHECK (STARTED, EXTRACTING, EXTRACTED, PROCESSING, SUCCEEDED, FAILED, SKIPPED,
                CANCELLED), attempt_number, source/staging/inserted/updated/deleted/rejected/
                bronze row counts, watermark_before/after, error_message
    activity    IDENTITY id, run/entity_run FKs, activity_type, activity_source PIPELINE|NOTEBOOK,
                status, rows_affected, duration_ms
    error       IDENTITY id, error_stage, error_code (original source code), error_message,
                is_retryable, attempt_number, stack_trace
    validation  IDENTITY id, validation_rule_id, rule, type, stage, status
                CHECK (PASSED, FAILED, WARNING, IGNORED), expected/actual, failed_row_count
    file        landing files: container + file_path UNIQUE, size, row_count, status
                CHECK (CREATED, PROCESSED, FAILED, REPLAYED), processed_run_id
  20_indexes: run_id, entity_run_id, source_system, source_table, status, start_datetime,
              environment.

Procs (repeatable, one CREATE OR ALTER PROCEDURE per file, sql_database/audit/procs/):
  usp_start_run           idempotent: reopens an existing run_id as RUNNING
  usp_complete_run        @status NULL -> derive from entity_run; an explicit status never
                          overwrites a terminal one
  usp_start_entity_run    upsert; a retry increments attempt_number
  usp_update_entity_run   intermediate status; NULL params keep existing values
  usp_complete_entity_run
  usp_log_activity, usp_log_error, usp_log_validation
  usp_log_file            upsert on (container, path)
  usp_get_run_entities    entities of a run in a given status
  usp_get_entity_baseline last SUCCEEDED run, excluding the current run
Pipelines and notebooks both write ONLY through these procs.

Migration runner: the AUDIT_DB target (once: sql_database/audit/ddl; repeatable: procs, views).
Dev-only sample data: sql_database/audit/samples/900_sample_audit_records.sql (not a migration
root).

Never put audit tables in the Warehouse control schema. Never store source data values.

Tests (mocked): the AUDIT_DB target discovers ddl -> procs -> views; every proc file holds
exactly one CREATE OR ALTER PROCEDURE; every table has a PK.
Report: what you could NOT verify live (cross-workspace connectivity, private link /
outbound access protection, token audience).
```
