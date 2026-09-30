# Context Prompt — Metadata-Driven Bronze Ingestion Framework

> Paste this file's content as context at the start of a session on this repo.
> Treat it as authoritative unless you spot a mismatch; if you do, re-read that
> specific file, not the whole repo. Design rationale lives in
> `docs/bronze_framework/01–14` and `docs/control_framework.md`. Load those only
> when you need the reasoning. The target spec is
> `docs/Fabric_Metadata_Driven_Bronze_Ingestion_Framework.md`.

## What exists

```
warehouse/ddl/00_schemas      001 CREATE SCHEMA [control] (lowercase), 002 [SECURITY]
warehouse/ddl/05_meta         050 control.schema_migration_history (Warehouse ledger)
warehouse/ddl/10_control      010-020 control tables (see below)
warehouse/ddl/20_security     020 SECURITY.UserAccess
warehouse/ddl/30_constraints  030 all PK/FK/UNIQUE, NOT ENFORCED
warehouse/programmability     100 control.fn_active_entities (repeatable, CREATE OR ALTER)
warehouse/metadata            seed metadata (repeatable, idempotent; README has id ranges)
security/rls                  001 predicate fn, 002 policy TEMPLATE (MIGRATION_RUNNER: SKIP)
sql_database/audit/ddl        audit schema, ledger, tables run/entity_run/activity/error/validation/file, indexes
sql_database/audit/procs      usp_* (repeatable) -- the ONLY write path for pipelines and notebooks
sql_database/audit/views      vw_* monitoring views (repeatable)
sql_database/audit/samples    DEV-only sample data (not a migration root)
notebooks/framework           fabric_connection.py, migration_runner.py (targets WAREHOUSE + AUDIT_DB)
notebooks/bronze              the framework: models, config_loader, run_manager, landing/staging/schema
                              managers, validation/dedup/anonymisation/hash/merge/history engines,
                              watermark_manager, audit_manager, error_manager, orchestrator, bootstrap
fabric_items/                 Dev git-sync root: BronzeOrchestrator + BronzeExtractSqlServerEntity +
                              SchemaMigration pipelines; BronzeFramework, MetadataInitialisation,
                              SchemaMigrationRunner notebooks; CicdFramework environment (.platform incl.)
scripts/ci/*.py               Fabric REST helpers; verify_migration_state --target warehouse|audit_db
tests/                        pytest, all Fabric deps mocked; Spark tests marked `spark` (skip w/o Java)
docs/agent_prompts/           per-phase AI-agent build prompts
```

`notebooks/framework/utils_logging.py` and the PascalCase `CONTROL` tables
(IngestionConfig, PipelineRun, TableRun, ErrorLog, Quarantine) were
**removed**. They were never deployed. Audit now lives in the SQL Database.

## Control schema (Warehouse, metadata only)

- `source_system`, `source_connection` (per-environment references, no
  secrets)
- `entity`: landing_enabled, history_required, merge_required, primary_key
  (comma list), watermark_column/type, change_detection_method,
  anonymisation_required, staging/target names, entity_group,
  processing_priority
- `entity_column`: source→target, Spark type, pk/watermark/hash/anonymisation
  flags
- `load_configuration`: retry, source_query_override with `{watermark}`,
  source_filter, delete detection, anomaly threshold
- `watermark`: runtime state, committed only on success
- `anonymisation_rule`, `validation_rule`, `column_mapping`
- `pipeline_configuration`, `framework_configuration` (key/value per
  environment)

Write strategy is derived: history → HISTORY, merge → MERGE, FULL → REPLACE,
else APPEND.

## Audit (Fabric SQL Database, cross-workspace)

- Correlation: `run_id` = `yyyyMMdd-HHmmss-XXXXXX`, and `entity_run_id` =
  `<run_id>-E<entity_id>`.
- Tables: `audit.run`, `entity_run`, `activity`, `error`, `validation`,
  `file`, `schema_migration_history`.
- Pipelines and `audit_manager.AuditManager` both call the same `usp_*`
  procs.

## Key decisions to preserve

- **Control vs audit split:** control defines, audit records. Never put
  audit tables in the Warehouse.
- **Landing:** `<container>/<source_system>/<table>/<table>_<yyyyMMddHHmmss>.json`.
  Files are never overwritten. With landing off, staging is Copy-Overwritten
  with `_staging_run_id` and verified. The Bronze table is never truncated.
- **Watermark** advances only after the Bronze write and POST validation
  succeed. The UPDATE is guarded by the old value.
- **Idempotent writes:**
  - MERGE is hash-guarded.
  - HISTORY uses a temporal filter and one atomic MERGE.
  - APPEND uses replaceWhere on entity_run_id.
  - REPLACE is a full overwrite.
- **Fail-fast vs fail-soft audit:** start_run, start_entity_run and
  get_run_entities raise. All other writes return bool, fall back to
  `Files/_framework_fallback/audit/`, and escalate only if
  `audit_failure_is_critical`.
- **Retries** are only for retryable errors (`error_manager.is_retryable`).
  Unknown errors are non-retryable.
- **Fabric DW T-SQL limits:** no NVARCHAR/DATETIME/DEFAULT/CHECK/SEQUENCE,
  constraints are `NOT ENFORCED` and added last, one batch per file, no `GO`.
- **Control ids** are explicit BIGINTs (identical across environments), not
  IDENTITY. The audit DB uses full T-SQL.
- **Migrations:** CREATE-once scripts are never re-run (drift is warned).
  Repeatable roots (programmability, metadata, procs, views) re-apply on a
  checksum change. The audit DB migrates before the Warehouse.
- **No hard-coded endpoints/ids:** connection strings and the Key Vault URI
  are parameters. Fabric item connection/artifact ids are placeholders
  (`fabric_items/README.md`).
- **Token audience** defaults to `"pbi"` (proven in the Dev reference
  notebook). It is configurable via `sql_token_audience` /
  `audit_sql_token_audience`.
- **Fabric item syntax** follows the working Dev reference items in
  `ito_dp_fabric_dev/rio`.
- **RLS unchanged:** `SECURITY.fn_SecurityPredicate` via `USER_NAME()`. The
  policy template is unbound until Gold facts exist.

## Validation status

`pytest -q` passes with mocks. Spark end-to-end tests skip without Java.
**Nothing has been deployed or run against a live Fabric workspace**, and
the CI/CD path is unvalidated end to end. See
`docs/bronze_framework/01_Architecture.md` § Verify live before production.
