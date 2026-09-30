# RB-04 — Changing the framework itself

This runbook covers changes to the framework: schema, procedures, pipelines
and Python. Metadata-only changes are RB-02. Every change goes through a
branch, a pull request (`pr-checks`: `pytest -q`, a wheel build, and Spark
tests where Java is available), then DEV, UAT and PROD through `cicd-pipeline`.

## Which kind of SQL file am I changing?

| Folder | Kind | Rule |
|---|---|---|
| `warehouse/ddl/**`, `security/rls/*`, `sql_database/audit/ddl/**` | **CREATE-once** | **Never edit a file that has been applied** in any environment. Add a new, higher-numbered file (for example `warehouse/ddl/40_changes/040_add_entity_owner.sql`). Editing an applied file is only reported as checksum drift; it is never re-run. |
| `warehouse/programmability/**`, `sql_database/audit/procs/**`, `sql_database/audit/views/**` | **Repeatable** (`CREATE OR ALTER`) | Edit in place. It is re-applied when its checksum changes. |
| `warehouse/metadata/**` | Repeatable data | RB-02. |
| `warehouse/checks/**`, `sql_database/audit/samples/**`, `*.sql.template` | Not migrated | Run by hand only. |

**Fabric Warehouse T-SQL limits** apply to every file under `warehouse/`,
and the contract tests enforce them:
- no `NVARCHAR`, `DATETIME`, `DEFAULT`, `CHECK`, `IDENTITY`, `SEQUENCE` or `GO`
- constraints are added only as `ALTER TABLE … ADD CONSTRAINT … NOT ENFORCED`
- one batch per file.

The audit database is full SQL Server T-SQL, but it also has one batch per
file, and one procedure or view per file.

## Add a column to a control table

1. Add a new file, `warehouse/ddl/40_changes/0NN_control_<table>_<column>.sql`:
   ```sql
   ALTER TABLE [control].[entity] ADD owner_group VARCHAR(100) NULL;
   ```
   New columns must be nullable: existing rows have no value, and Fabric DW
   has no DEFAULT.
2. If `fn_active_entities` or `config_loader` should read the column, update
   them. Both files are repeatable or code.
3. Update the seed scripts that insert into the table. Their column lists
   must include the new column, or it stays NULL.
4. Update `02_Metadata_Model.md`, then continue with the standard deploy.

**Verify:** `verify_migration_state --target warehouse` prints OK, and the new
file appears in `control.schema_migration_history`.

## Change or add an audit procedure or view

1. Edit or add the file in `sql_database/audit/procs/` or `views/`
   (`CREATE OR ALTER`).
2. **Parameter changes must stay backwards compatible.** Pipelines and
   notebooks from the previous release may still call the procedure during a
   rollout. Add new parameters with a default, and never remove or rename one
   in the same release as its callers change.
3. Update every caller:
   - `notebooks/bronze/audit_manager.py`
   - the `SqlServerStoredProcedure` activities in
     `fabric_items/pipelines/*/pipeline-content.json`.

   `tests/bronze/test_sql_contracts.py` fails if any caller passes an unknown
   parameter or omits a required one.
4. For a new view, add it to the operator table in `05_Audit_Design.md`.

## Add a source type (Oracle, PostgreSQL, REST, …)

The orchestrator pipeline routes each entity by `source_type` in
`SwitchSourceType`. The processing notebook is source-agnostic: it only
needs staging or a landing file.

1. **Extract pipeline.** Copy
   `fabric_items/pipelines/BronzeExtractSqlServerEntity.DataPipeline` to
   `BronzeExtract<Type>Entity.DataPipeline`.
   - Keep the same parameters and every audit activity.
   - Change only the Copy source: the source type, the connection
     placeholder, and the query shape.
   - Give the new `.platform` a new `logicalId` (`python -c "import uuid;
     print(uuid.uuid4())"`).
   - Add a new placeholder GUID (for example `…a005`) to
     `fabric_items/README.md` and to the placeholder set in
     `tests/fabric_items/test_fabric_items.py`.
2. **Route it.** In `BronzeOrchestrator.DataPipeline`, add a case to
   `SwitchSourceType` whose `value` is the new `source_type`, invoking the new
   pipeline with the same parameters as the SQLSERVER case.
3. **Source query.** `fn_active_entities` builds a T-SQL-style
   `SELECT [col] FROM [schema].[table] WHERE …`. If the source needs a
   different dialect, either:
   - use `load_configuration.source_query_override`, per entity, with
     `{watermark}`, or
   - extend the function with a `CASE ss.source_type` branch.
4. **API sources (no Copy connector).** Extract in a notebook activity that
   writes the same outputs as a copy:
   - with landing on: the landing file `<container>/<source_system>/<table>/<table>_<ts>.json`
   - with landing off: overwrite `staging.<table>` with `_staging_run_id`
   - then `audit.usp_update_entity_run` EXTRACTED with `source_row_count`.

   Nothing downstream changes.
5. **Metadata.** Add the `source_system` row with the new `source_type`
   (RB-02 § *Add a source system*).
6. **Tests.** Run `pytest -q`: item-structure checks, placeholder checks, and
   the stored-procedure contracts for the new pipeline's activities.
7. **Verify in DEV** with one entity, with landing on and with landing off.

## Change framework Python (`notebooks/bronze`, `notebooks/framework`)

1. Keep the pattern: pure builders plus thin Spark or pyodbc adapters, with
   pyspark imported lazily inside the adapters.
   - Adapters shared across entity threads must stay stateless (see
     `ValidationEngine.run`).
2. Add or adjust tests in `tests/bronze/`. Add a `@pytest.mark.spark` test for
   anything that depends on Delta or Spark semantics.
3. Release:
   - Merging to `main` publishes the wheel to the DEV Environment (this
     takes minutes).
   - A notebook picks up the new library on its **next fresh session**, not
     in an already-warm one.
   - Bump `version` in `pyproject.toml` for any behaviour change, so the
     running version is identifiable.
4. Changes that alter results (hashing, canonicalisation, projection,
   validation built-ins) re-version data exactly like the metadata changes in
   RB-02's change-impact table. Announce them.

## Change a pipeline or notebook item

- **Recommended:** edit in the DEV workspace portal, then *Commit to Git*,
  review the JSON diff, and run `pytest tests/fabric_items`.
- **Alternative:** edit the JSON in git and let the sync apply it, keeping the
  structure of the `rio` reference items.
- Never commit real connection ids, workspace ids or connection strings.
  The placeholder test fails if you do.
- Notebooks stay thin wrappers. Put logic in the package, where it is
  tested.

## Staging truncate alternative

If live testing shows that the copy's `LakehouseTableSink`
`tableActionOption: Overwrite` does not truncate atomically, add a notebook
step before `CopyToStaging` that calls
`StagingManager(spark).truncate(entity)`, and switch the copy to append.
Keep the `_staging_run_id` stamp and the framework's integrity check.

## Drop a Bronze column or table (data change)

The framework never drops anything automatically. With approval:
1. Deactivate the column or entity in metadata first (RB-02), and deploy.
2. In a notebook, run `ALTER TABLE <schema>.<table> DROP COLUMN <col>`. This
   needs Delta column mapping enabled on the table; check first. Or
   `DROP TABLE`, after taking a copy if retention requires one.
3. Record it in the ticket. Downstream Silver/Gold owners must sign off.

## Rollback

| Change | Roll back by |
|---|---|
| Repeatable SQL | Revert the file and redeploy |
| CREATE-once SQL | Forward fix with a new numbered file |
| Python | Revert, or republish the previous wheel version to the Environment |
| Pipelines / notebooks | Revert and git sync (DEV); redeploy previous stage content (UAT/PROD) |
