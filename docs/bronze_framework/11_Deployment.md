# 11 — Deployment (DEV → UAT → PROD)

Nothing in framework code is environment-specific. Environment differences
come from:
- `control.framework_configuration` and `control.source_connection` rows
  (keyed by environment)
- pipeline/notebook parameters: `warehouse_connection_string`,
  `audit_connection_string`, `key_vault_uri`, `environment`, bound per stage
  through Deployment Pipeline rules or a Variable Library
- Fabric connection and item bindings (the placeholders in
  `fabric_items/README.md`).

Secrets are never in code, metadata, parameters or audit. Key Vault holds
salts, and Fabric connections or gateways hold source credentials.

**Never deploy to PROD without explicit, in-the-moment approval.** The CI
`promote-prod` job is gated by the `prod` GitHub Environment's required
reviewers.

## Deployment order

```text
1 infrastructure      workspaces, Lakehouse (schema-enabled), Warehouse, audit SQL DB, ADLS, Key Vault, connections
2 audit SQL Database  migration_runner AUDIT_DB   (schema, tables, indexes, procs, views)
3 Warehouse           migration_runner WAREHOUSE  (control DDL, SECURITY/RLS, fn_active_entities)
4 metadata            migration_runner WAREHOUSE  warehouse/metadata (repeatable, same run as 3)
5 MetadataInitialisation notebook  (staging + Bronze Delta tables)
6 pipelines/notebooks  git sync (Dev) / Deployment Pipeline (UAT, PROD), then bind placeholders
7 smoke test
```

Steps 2–4 are one `SchemaMigration.DataPipeline` run. It calls the
`SchemaMigrationRunner` notebook, which migrates the audit database first and
then the Warehouse, auditing the Warehouse migration as a run.

## 1. Infrastructure creation (manual, once per environment)

- **Private engineering workspace:** a Bronze Lakehouse with **schemas
  enabled**, the Warehouse (`control`, `SECURITY`), and the `CicdFramework`
  Environment.
- **Audit / Operations workspace:** one Fabric SQL Database,
  `BronzeFrameworkAudit`, shared by all ingestion workspaces. Decide whether
  there is one per environment or one shared database with an `environment`
  column. The schema supports both; per-environment is recommended.
- **ADLS Gen2** account with a `landing` container, private endpoint, and
  lifecycle policy.
- **Key Vault** with secret `bronze-anonymisation-salt` (DEV/UAT: a distinct
  random value per environment).
- **On-premises data gateway** plus a Fabric connection to the SQL Server
  source.
- **Fabric connections:** source SQL Server, ADLS landing, audit SQL Database
  (cross-workspace), and the InvokePipeline connection.
- A OneLake shortcut `Files/landing` in the Bronze Lakehouse, pointing to the
  landing container.

## 2. Metadata deployment

`warehouse/metadata/*.sql` is repeatable. It is re-applied when the checksum
changes, and is idempotent (delete then insert the owned ids, in a
transaction). Two tables hold **runtime or environment-owned** rows that
metadata scripts only ever insert when missing, and never delete or update:
- `control.watermark`
- `control.source_connection`.

Set the environment-specific connection values (`fabric_connection_id`,
`gateway_name`, `database_name`) with the operator procedure in
[runbooks/02_metadata_maintenance.md](../runbooks/02_metadata_maintenance.md) §
Environment connection values. Never put real ids in a seed script.

Step-by-step creation of every artifact is in
[runbooks/01_platform_setup.md](../runbooks/01_platform_setup.md).

## 3. Notebook deployment

`fabric_items/notebooks/*` are thin wrappers. Code ships as the wheel built by
`scripts/ci/fabric_publish_environment_library.py`. It bundles
`notebooks.framework` and `notebooks.bronze`, plus `warehouse/ddl`,
`warehouse/programmability`, `warehouse/metadata`, `security/rls` and
`sql_database/audit`. Attach the Bronze Lakehouse (as default) and the
`CicdFramework` Environment to each notebook in each workspace.

## 4. Pipeline deployment

Dev gets pipelines through git sync of `/fabric_items`. UAT and PROD get them
through a Deployment Pipeline stage deploy. After the first sync:
- bind each `00000000-…-a00N` connection and `…-b00N` artifact placeholder
- confirm that `notebookId`/`pipelineId` references resolved to the right
  items
- set deployment rules for the three connection-string/URI parameters.

## 5. Warehouse object deployment

The `migration_runner` `WAREHOUSE` target:
- CREATE-once: `warehouse/ddl/**`, then `security/rls/*`
- repeatable: `warehouse/programmability/**`, then `warehouse/metadata/**`.

The ledger is `control.schema_migration_history`. Never edit an applied
CREATE-once file. Add a new numbered file instead.

## 6. Audit SQL Database deployment

The `AUDIT_DB` target:
- CREATE-once: `sql_database/audit/ddl/**`
- repeatable: `procs/**`, then `views/**`.

The ledger is `audit.schema_migration_history`. `samples/` is never applied
automatically.

## 7. Storage configuration

- Container name = `framework_configuration.landing_container`.
- Shortcut path = `landing_lakehouse_path` (default `Files/landing`).
- Folder layout is created by the Copy activity:
  `<source_system>/<table>/<table>_<yyyyMMddHHmmss>.json`.

## 8. Environment configuration

Edit `warehouse/metadata/020_framework_configuration.sql` (per-environment
rows) and redeploy. Typical per-environment differences:
- `anonymisation_enabled` (false only in PROD)
- `max_parallel_entities` (5/10/20)
- `landing_globally_enabled`.

## 9. Security configuration

See [security_review.md](security_review.md) → Required configuration:
workspace roles, SQL users and grants on the Warehouse and the audit
database, ADLS RBAC, Key Vault access, and the gateway.

## 10. Smoke tests

1. `python -m scripts.ci.verify_migration_state --env <env> --target audit_db`
   and `--target warehouse`. These check that every CREATE-once script
   SUCCEEDED, every repeatable script is at its current checksum, and nothing
   is FAILED.
2. Run `MetadataInitialisation` and check that every staging and Bronze table
   exists.
3. Run `BronzeOrchestrator` with `entity_group = reference` (Territory: FULL,
   staging path), then `sales`.
4. Query `audit.vw_run_summary`, `vw_entity_status`, `vw_landing_files` and
   `vw_recent_errors` for the run.

## 11. Rollback

| What | How |
|---|---|
| Notebooks / pipelines | Redeploy the previous commit (Dev: revert and git sync; UAT/PROD: Deployment Pipeline redeploy of the previous stage content) |
| Framework wheel | Republish the previous wheel version to the Environment |
| Repeatable SQL (procs, views, `fn_active_entities`, metadata) | Revert the file and redeploy. The runner re-applies it because the checksum changed. |
| CREATE-once DDL | Roll **forward** with a new numbered script (`ALTER`/`DROP`). Fabric DW DDL is not transactional across files, and the runner never re-runs applied scripts. |
| Bronze data | Delta time travel (`RESTORE TABLE … TO VERSION AS OF n`), then reset `control.watermark` to the value recorded in `audit.entity_run.watermark_before` for the restored run |
| Watermark | `UPDATE control.watermark SET last_successful_watermark = '<value>'` using audit history. Record the manual change. |

Deployment is repeatable: re-running the migration pipeline applies nothing
new, and re-running metadata scripts is idempotent.
