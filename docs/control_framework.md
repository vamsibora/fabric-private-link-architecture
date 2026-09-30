# Control & Security Framework

Foundational metadata-driven framework for the Fabric Warehouse: ingestion configuration, pipeline/table run tracing, error/quarantine handling, and Row-Level Security. This document explains the design decisions behind `warehouse/ddl/`, `security/rls/`, and `notebooks/framework/utils_logging.py`.

## Schemas and tables

### CONTROL

| Table | Purpose |
|---|---|
| `IngestionConfig` | One row per source object -> target table mapping. Drives what the ingestion framework loads and how (`LoadType`: FULL / INCREMENTAL / CDC, `WatermarkColumn`). |
| `AnonymizationRule` | Defines *what* should be anonymized for a source column (`RuleType`, `RuleParameters`, `SaltKeyVaultSecret`). See [Anonymization scope](#anonymization-scope) below. |
| `PipelineRun` | Top tier of the tracing hierarchy — one row per pipeline/notebook invocation. |
| `TableRun` | Middle tier — one row per table processed within a `PipelineRun`. |
| `ErrorLog` | Written by `utils_logging.log_error()`; may attach to a `PipelineRunID` and/or `TableRunID`. |
| `Quarantine` | Rows rejected during a `TableRun` (failed data quality checks), held for inspection/replay rather than dropped. |

### SECURITY

| Table | Purpose |
|---|---|
| `UserAccess` | Source of truth for RLS. Grants a `UserPrincipalName` access to a `RegionKey`/`CountryKey`/`BusinessUnitKey` combination. `NULL` on any key column is a wildcard for that dimension. |

## Fabric Warehouse constraints reflected in the DDL

- No `NVARCHAR`/`DATETIME`/`MONEY` — use `VARCHAR` (UTF-8 collation) and `DATETIME2(6)`.
- No `DEFAULT` or `CHECK` constraints at all — audit columns (`CreatedDate`, etc.) are populated by the calling code, never by the table definition.
- No inline `PRIMARY KEY`/`FOREIGN KEY`/`UNIQUE` in `CREATE TABLE` — added afterward via `ALTER TABLE ... ADD CONSTRAINT ... NOT ENFORCED` (see `warehouse/ddl/30_constraints/`), and only once every referenced table exists.
- `IDENTITY` is a preview feature, `BIGINT`-only, and can't be added retroactively.
- No `CREATE SEQUENCE`.

Deploy order: `00_schemas/` → `10_control/` → `20_security/` → `30_constraints/` (constraints last, since FKs need their target tables to already exist).

## Key strategy: IDENTITY vs GUID

| Tables | Key | Why |
|---|---|---|
| `IngestionConfig`, `AnonymizationRule`, `UserAccess` | `BIGINT IDENTITY(1,1)` | Low-concurrency, admin/CI-managed metadata — sequential, human-readable keys are appropriate. |
| `PipelineRun`, `TableRun`, `ErrorLog`, `Quarantine` | `UNIQUEIDENTIFIER`, generated in Python (`uuid.uuid4()`) before insert | High-concurrency, append-heavy logging tables (many parallel table loads insert at once). The ID must be known *before* the row is written so it can be threaded into child rows (e.g. `TableRunID` passed to `end_table_run()`) without a round-trip identity lookup, and without depending on the preview `IDENTITY` feature for the tables where lineage integrity matters most. |

## Tracing hierarchy

```
ExecutionID (correlation GUID; no dedicated table — carried on PipelineRun/ErrorLog,
             sourced from the orchestrating Data Pipeline's own RunId, or minted
             fresh by start_pipeline_run() when a notebook runs standalone)
   └── PipelineRun [PipelineRunID]   one row per pipeline/notebook invocation
          └── TableRun [TableRunID]  one row per table processed in that run
                 ├── ErrorLog        0..n, may reference PipelineRunID and/or TableRunID
                 └── Quarantine      0..n, references TableRunID
```

Multiple `TableRun` rows share one `PipelineRunID` when a pipeline fans out over `IngestionConfig` (e.g. a parallel `ForEach`) — this is safe under concurrency because each `TableRun` insert is an independent row.

## `utils_logging.py` design

**Connection**: `pyodbc`, authenticated with an Entra access token from `notebookutils.credentials.getToken("https://database.windows.net/.default")`, passed via the `SQL_COPT_SS_ACCESS_TOKEN` connection attribute. Fabric Warehouse tables aren't writable from Spark directly, and the SQL endpoint is Entra-only — this reuses the notebook's own run-as identity with no extra secret management. The connection string itself is always passed in by the caller (resolved from config), never hardcoded in the module.

**Exception boundaries** (deliberately not uniform):

| Function | On failure | Rationale |
|---|---|---|
| `start_pipeline_run`, `start_table_run` | Fail fast — raises `ControlConnectionError` | If the opening row can't be written, the run is untracked. Proceeding silently would create an unaudited run, which is worse than aborting loudly — especially in a framework that also governs anonymization/PII handling. |
| `end_pipeline_run`, `end_table_run`, `log_error` | Fail soft — never raises, returns `bool` | These are called from `except`/`finally` blocks around the caller's real business logic. If they raised, they could mask the original exception or leave a run stuck in `RUNNING` forever. On failure they fall back to writing a JSON line under `Files/_framework_fallback/` in the Lakehouse (via `notebookutils.fs`, independent of Warehouse reachability), then log at `CRITICAL` as a last resort. |

## Row-Level Security

- `security/rls/001_security_predicate_function.sql` — `SECURITY.fn_SecurityPredicate(@RegionKey, @CountryKey, @BusinessUnitKey)`, a schema-bound inline table-valued function that checks `EXISTS` against `SECURITY.UserAccess` for the calling user.
- **`USER_NAME()` rather than `SESSION_CONTEXT`**: Fabric Warehouse SQL endpoint connections are per-user Entra pass-through — there's no trusted pooled middle tier that could `SET SESSION_CONTEXT` on behalf of an end user — so `USER_NAME()` reliably identifies the caller with no extra plumbing.
- `security/rls/002_security_policy_template.sql` — the `CREATE SECURITY POLICY` statement is delivered as a commented template, since no fact/dimension tables exist yet in this repo. Once a table with `RegionKey`/`CountryKey`/`BusinessUnitKey` columns exists, uncomment and bind it; use the `ALTER SECURITY POLICY ... ADD FILTER PREDICATE` pattern for each additional table.
- **NULL-as-wildcard**: a `NULL` on any `UserAccess` key column means that user sees all values on that dimension. This is a convention enforced by the predicate function's logic, not by the database — document it wherever `UserAccess` rows are maintained.
- **Testing**: RLS is bypassed for workspace Admin/Member/Contributor roles. Always test connected *as* the target user.

## Anonymization scope

`CONTROL.AnonymizationRule` only defines *what* should be anonymized (source column, rule type, parameters, and a reference to the Key Vault secret holding the salt — never the raw salt value itself). It does not execute anything. The anonymization engine itself — reading active rules for a `SourceSystem`/`SourceTable`, resolving `SaltKeyVaultSecret`, and applying the hash/mask/tokenize/nullify/encrypt transform during Bronze → Silver — is out of scope for this framework and should be tracked as a separate follow-up module.

## Verification

1. Deploy DDL in order via the Fabric SQL endpoint (one batch per script, no `GO`): `00_schemas/` → `10_control/` → `20_security/` → `30_constraints/` → `security/rls/001_security_predicate_function.sql`. Confirm via `INFORMATION_SCHEMA.TABLES`/`COLUMNS` and, after RLS, `sys.security_predicates`.
2. Insert one sample row per `CONTROL` table through the full parent/child chain (`PipelineRun` → `TableRun` → `ErrorLog`/`Quarantine`) and confirm joins resolve. Insert 2+ `SECURITY.UserAccess` rows for different principals and confirm `fn_SecurityPredicate` filters as expected when queried as each principal.
3. Run `pytest tests/framework/test_utils_logging.py` — fully mocked, no live Fabric connection required.
4. Live `pyodbc`/`notebookutils` integration can only be exercised inside an actual Fabric notebook against a dev Warehouse; this has not been verified in this session since no Fabric connection is available here.
