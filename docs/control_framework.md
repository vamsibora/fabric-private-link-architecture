# Control, Audit & Security Framework

Design rationale for the metadata plane (`warehouse/`), the audit plane
(`sql_database/audit/`), the audit writer
(`notebooks/bronze/audit_manager.py`) and Row-Level Security (`security/rls/`).
Table-by-table reference: [bronze_framework/02_Metadata_Model.md](bronze_framework/02_Metadata_Model.md)
and [bronze_framework/05_Audit_Design.md](bronze_framework/05_Audit_Design.md).

## Two planes

| Plane | Store | Holds | Changes |
|---|---|---|---|
| Control | Fabric Warehouse, schema `control` | Source systems, connections (references), entities, columns, load config, watermarks, anonymisation/validation rules, mappings, pipeline/framework config | Deployed as code (`warehouse/metadata/`); watermarks updated by the framework on success |
| Audit | Central Fabric SQL Database `BronzeFrameworkAudit`, schema `audit` | run, entity_run, activity, error, validation, file | Append/point-update at runtime from every workspace |

Control metadata defines what should happen. Audit records what actually
happened.

The previous design kept `PipelineRun`/`TableRun`/`ErrorLog`/`Quarantine` in a
PascalCase `CONTROL` schema inside the Warehouse, written by `utils_logging.py`.
It was retired before any deployment, for two reasons: audit must be shared
across workspaces, and it needs enforced keys and indexes that Fabric DW
lacks. The lowercase `control` schema is a distinct schema, because Fabric DW
identifiers are case-sensitive.

## Fabric Warehouse constraints reflected in the DDL

- Use `VARCHAR` (UTF-8) and `DATETIME2(6)`. Do not use `NVARCHAR`,
  `DATETIME`, `MONEY`, `DEFAULT`, `CHECK` or `SEQUENCE`.
- There is no inline PK/FK/UNIQUE. They are added in `30_constraints/` via
  `ALTER TABLE … NOT ENFORCED`, after all tables exist.
- `IDENTITY` is preview, BIGINT-only and has no `IDENTITY_INSERT`.

Deploy order: `00_schemas` → `05_meta` → `10_control` → `20_security` →
`30_constraints` → `security/rls` → `programmability` → `metadata`. This is
handled by `migration_runner` (`WAREHOUSE` target).

The audit database is full SQL Server T-SQL and uses enforced PK/FK,
`DEFAULT`, `CHECK`, `IDENTITY` and indexes.

## Key strategy

| Tables | Key | Why |
|---|---|---|
| control.* config tables | Explicit `BIGINT` set by metadata scripts (id ranges in `warehouse/metadata/README.md`) | Metadata is promoted DEV → UAT → PROD, so ids must be identical everywhere. IDENTITY can't guarantee that, and has no IDENTITY_INSERT in Fabric DW. |
| control.watermark | entity_id | One runtime row per entity |
| control/audit `schema_migration_history` | `UNIQUEIDENTIFIER` from Python | Written before or while the ledger bootstraps |
| audit.run / audit.entity_run | Caller-generated strings (`yyyyMMdd-HHmmss-XXXXXX`, `<run_id>-E<entity_id>`) | Known before any insert, so they can be threaded into landing paths, Bronze columns and child rows. entity_run_id is deterministic, so pipeline and notebook address the same row. |
| audit.activity/error/validation/file | `BIGINT IDENTITY` | Append-only children; never referenced before insert |

## Audit writer boundaries (`audit_manager.py`)

| Call | On failure | Rationale |
|---|---|---|
| `start_run`, `start_entity_run`, `get_run_entities` | **Fail fast**: raise `AuditConnectionError` | An untracked run, or not knowing what was extracted, is worse than aborting loudly, especially in a framework that governs anonymisation. |
| `update_entity_run`, `complete_entity_run`, `complete_run`, `log_activity`, `log_error`, `log_validation`, `log_file`, `previous_row_count` | **Fail soft**: return `False` (or None) | These run inside except/finally blocks around real work. Raising could mask the real exception or fail a Bronze load that succeeded. On failure they write JSON to `Files/_framework_fallback/audit/<kind>/` and log at `CRITICAL`. `audit_failure_is_critical = true` escalates to `AuditCriticalError` after the fallback write. |

Other behaviour:
- Writes go only through `audit.usp_*`, with named parameters. Pipelines use
  the same procedures.
- There is one pyodbc connection per thread, and a reconnect on failure.
- Nothing written contains source values: messages are sanitised, and
  validation results are counts only.

Connection: pyodbc plus `notebookutils.credentials.getToken(<audience>)` via
`SQL_COPT_SS_ACCESS_TOKEN` (`fabric_connection.get_connection_notebookutils`).
The default audience is `"pbi"`. It is configurable
(`sql_token_audience`, `audit_sql_token_audience`), and the value for the
audit DB is unverified live. Connection strings are always caller-supplied
parameters.

## Row-Level Security (unchanged)

- `security/rls/001_security_predicate_function.sql`:
  `SECURITY.fn_SecurityPredicate(@RegionKey, @CountryKey, @BusinessUnitKey)`,
  checking `SECURITY.UserAccess` for `USER_NAME()`. It uses `USER_NAME()`, not
  `SESSION_CONTEXT`, because Fabric SQL endpoints are per-user Entra
  pass-through.
- `002_security_policy_template.sql` is unbound
  (`-- MIGRATION_RUNNER: SKIP`) until Gold fact/dimension tables with those
  keys exist.
- NULL in a UserAccess key column is a wildcard for that dimension.
- RLS is bypassed for workspace Admin/Member/Contributor, so always test
  connected as the target user.

## Anonymisation

The rules are now **executed** by `notebooks/bronze/anonymisation_engine.py`
as data enters Bronze. They are gated per environment by
`framework_configuration.anonymisation_enabled`. See
[bronze_framework/08_Anonymisation.md](bronze_framework/08_Anonymisation.md).

## Verification

1. `pytest -q`. It is fully mocked and needs no Fabric connection.
2. Deploy via `SchemaMigration.DataPipeline` in Dev (audit DB, then the
   Warehouse), then run
   `python -m scripts.ci.verify_migration_state --target audit_db|warehouse`.
3. Run `sql_database/audit/samples/900_sample_audit_records.sql` against DEV
   only, and query the `audit.vw_*` views.
4. **Not yet done:** none of the DDL, procs or views have been applied to a
   live Warehouse or SQL Database.
