# Context Prompt — Phase 1: CONTROL/SECURITY Framework Scaffold

> Paste this file's content as context at the start of a session working on this repo.
> It is meant to stand in for reading the actual DDL/Python files — treat it as
> authoritative unless you spot a mismatch (then re-read the specific file, not the whole repo).
> Full design rationale (why, not just what) lives in `docs/control_framework.md` — load that
> only if you need the reasoning behind a decision, not for routine extension work.

## What exists (repo: `fabric_medallion_architecture`, branch `feature/framework`)

Greenfield metadata-driven framework for a Microsoft Fabric Warehouse. Nothing existed before
Phase 1 except `README.md`/`.gitignore` — every convention below was established in this phase.

```
warehouse/ddl/00_schemas/    001, 002        CREATE SCHEMA CONTROL, SECURITY
warehouse/ddl/05_meta/       050             CONTROL.SchemaMigrationHistory (migration ledger)
warehouse/ddl/10_control/    010-015         one table each, see schema below
warehouse/ddl/20_security/   020             SECURITY.UserAccess
warehouse/ddl/30_constraints/030             all PK/FK/UNIQUE, added last, all NOT ENFORCED
security/rls/                001, 002        predicate function + policy TEMPLATE (marked MIGRATION_RUNNER: SKIP, unbound)
notebooks/framework/utils_logging.py         5 functions, see signatures below
notebooks/framework/fabric_connection.py     shared notebookutils/SPN token + pyodbc connection helpers
notebooks/framework/migration_runner.py      ledger-driven DDL/RLS applier (see docs/cicd_pipeline.md)
scripts/ci/*.py                              GitHub Actions helper scripts (Fabric REST API calls)
tests/framework/, tests/ci/                  pytest, all Fabric deps mocked -- see `pytest -q`
docs/control_framework.md                    full rationale doc (schema tables, design tradeoffs)
docs/cicd_pipeline.md                        CI/CD design + runbook (Phase 2)
docs/service_principal_requirements.md       SPN naming/permissions deliverable for a Fabric/Entra admin
.github/workflows/pr-checks.yml, cicd-pipeline.yml   PR gate; deploy-dev -> promote-uat -> promote-prod
fabric_items/                                Fabric git-sync root (notebook/pipeline/environment item defs)
conftest.py, notebooks/__init__.py, notebooks/framework/__init__.py   pytest import plumbing
```

Deploy order matters: `00_schemas` → `05_meta` → `10_control` → `20_security` → `30_constraints` → `security/rls/001`.
Each `.sql` file is exactly one T-SQL batch (no `GO`) — deploy one file per call. In practice this ordering
and safe re-run behavior is handled by `notebooks/framework/migration_runner.py`, not run by hand.

## Schema (columns only — see the actual `.sql` file for exact types if writing new DDL against these)

- **CONTROL.IngestionConfig** (BIGINT IDENTITY PK): SourceSystem, SourceSchema, SourceObject, TargetSchema, TargetTable, LoadType, WatermarkColumn, IsAnonymizationEnabled, IsActive, +audit(CreatedDate/By, ModifiedDate/By)
- **CONTROL.AnonymizationRule** (BIGINT IDENTITY PK): SourceSystem, SourceTable, ColumnName, RuleType, RuleParameters (JSON text), SaltKeyVaultSecret (secret name/URI, never raw), IsActive, +audit
- **CONTROL.PipelineRun** (GUID PK = PipelineRunID): ExecutionID (GUID), PipelineName, SourceSystem, StartTime, EndTime, Status, TriggerType, ParametersJson, RowsProcessed, CreatedDate, ModifiedDate
- **CONTROL.TableRun** (GUID PK = TableRunID): PipelineRunID (FK), IngestionConfigID (FK, nullable), SourceSystem, TargetTable, StartTime, EndTime, Status, WatermarkValueStart/End, RowsRead/Inserted/Updated/Quarantined, CreatedDate, ModifiedDate
- **CONTROL.ErrorLog** (GUID PK = ErrorID): ExecutionID, PipelineRunID (FK, nullable), TableRunID (FK, nullable), SourceSystem, TargetTable, ErrorSeverity, ErrorMessage, ErrorDetails (stack trace), SourceStage, CreatedDate
- **CONTROL.Quarantine** (GUID PK = QuarantineID): TableRunID (FK, nullable), SourceSystem, TargetTable, RecordKey, RawRecordJson, QuarantineReason, ErrorID (FK), IsReprocessed, CreatedDate, ReprocessedDate
- **SECURITY.UserAccess** (BIGINT IDENTITY PK): UserPrincipalName, SecurityRole, RegionKey/CountryKey/BusinessUnitKey (INT, **NULL = wildcard**), IsActive, +audit

Tracing hierarchy: `ExecutionID` (no table, correlation GUID on PipelineRun/ErrorLog) → `PipelineRun` → `TableRun` → `ErrorLog`/`Quarantine`.

## Key decisions to preserve when extending

- **Key strategy**: config/access tables (`IngestionConfig`, `AnonymizationRule`, `UserAccess`) use `BIGINT IDENTITY(1,1)`. Run/log tables (`PipelineRun`, `TableRun`, `ErrorLog`, `Quarantine`) use `UNIQUEIDENTIFIER` generated in **Python** (`uuid.uuid4()`) before insert — keep this split for any new CONTROL table (config-like → IDENTITY, append-heavy log-like → GUID-from-Python).
- **Fabric Warehouse T-SQL limits** (apply to any new DDL): no `NVARCHAR`/`DATETIME`/`MONEY`/`DEFAULT`/`CHECK`/`CREATE SEQUENCE`; no inline PK/FK/UNIQUE in `CREATE TABLE` (add via `ALTER TABLE ... NOT ENFORCED` after all referenced tables exist); `IDENTITY` is preview-only, `BIGINT`-only, can't be added retroactively. Use `VARCHAR` + UTF-8 collation, `DATETIME2(6)`.
- **RLS**: filters via `USER_NAME()` (not `SESSION_CONTEXT` — no pooled middle tier in Fabric's per-user Entra pass-through model). `security/rls/002_security_policy_template.sql` is deliberately unbound (commented out) — no fact/dim tables exist yet. When one does, uncomment and bind `[SECURITY].[fn_SecurityPredicate](RegionKey, CountryKey, BusinessUnitKey)` to it.
- **`utils_logging.py` exception boundary** (do not flatten this to one style): `start_pipeline_run`/`start_table_run` fail fast (raise `ControlConnectionError`) — an untracked run start is worse than aborting. `end_pipeline_run`/`end_table_run`/`log_error` fail soft (never raise, return `bool`, fall back to `Files/_framework_fallback/` JSON + `logger.critical`) — they run inside `except`/`finally` and must never mask the caller's real exception.
- **Connection**: `pyodbc` + `notebookutils.credentials.getToken("https://database.windows.net/.default")` via `SQL_COPT_SS_ACCESS_TOKEN`. Warehouse tables aren't Spark-writable; connection string is always caller-supplied (config-resolved), never hardcoded.

## Function signatures (`notebooks/framework/utils_logging.py`)

```python
start_pipeline_run(connection_string, pipeline_name, execution_id=None, source_system=None,
                    trigger_type="SCHEDULED", parameters=None) -> str  # PipelineRunID, raises ControlConnectionError
end_pipeline_run(connection_string, pipeline_run_id, status, rows_processed=None) -> bool
start_table_run(connection_string, pipeline_run_id, source_system, target_table,
                ingestion_config_id=None, watermark_value_start=None) -> str  # TableRunID, raises ControlConnectionError
end_table_run(connection_string, table_run_id, status, rows_read=None, rows_inserted=None,
              rows_updated=None, rows_quarantined=None, watermark_value_end=None) -> bool
log_error(connection_string, error_message, severity="ERROR", execution_id=None, pipeline_run_id=None,
          table_run_id=None, source_system=None, target_table=None, source_stage=None, exception=None) -> bool
```

## CI/CD (Phase 2)

A Fabric-native hybrid CI/CD deployment pipeline now exists — see
`docs/cicd_pipeline.md` for the full design and `docs/
service_principal_requirements.md` for the SPN setup it depends on. Summary:
GitHub Actions runs pytest as a PR gate and drives Fabric REST API calls
(git sync, schema-migration job runs, Deployment Pipeline stage promotion)
via a service principal; a `CONTROL.SchemaMigrationHistory` ledger
(`warehouse/ddl/05_meta/050_...`) and `notebooks/framework/
migration_runner.py` apply pending DDL/RLS scripts idempotently per
environment. Fabric workspace items (`fabric_items/`) and the actual
Dev/UAT/Prod workspace provisioning are still pending manual setup — see
`docs/cicd_pipeline.md` § Order of implementation.

## Explicitly out of scope (do not assume it exists)

- No anonymization **execution** engine — `AnonymizationRule` only stores config. Building the engine (resolve `SaltKeyVaultSecret`, apply transform Bronze→Silver) is a separate future phase.
- No fact/dimension tables anywhere in the repo yet — the RLS policy has nothing real to bind to.
- No bronze/silver/gold notebooks — control-plane scaffolding only.
- No actual Fabric workspace items committed yet (`fabric_items/` is designed but not populated) — Dev workspace git-connection, UAT/Prod workspace provisioning, and the Deployment Pipeline object are manual prerequisites not yet completed (see `docs/cicd_pipeline.md`).

## Validation status

`pytest -q` passes (49/49, fully mocked — pyodbc/notebookutils/msal/Fabric REST calls). DDL has **not** been
deployed against a live Fabric Warehouse in any session — no Fabric connection was available. Verify against a
real dev Warehouse before treating the DDL as production-ready (see `docs/control_framework.md` § Verification).
The CI/CD pipeline (`docs/cicd_pipeline.md`) is similarly unvalidated end-to-end — its manual prerequisites
(SPN, workspace git-connection, Deployment Pipeline object) have not been completed in any session.
