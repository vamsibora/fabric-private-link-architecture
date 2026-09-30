# RB-01 — Platform setup (one environment)

This runbook creates every artifact the Bronze framework needs for one
environment, and ends with a first successful run. Run it for DEV first,
end to end. Repeat for UAT and then PROD. PROD needs explicit approval at the
time.

Estimated effort: about 1 day for DEV (first time), and a few hours for each
later environment.

**Names used below** are a suggested convention. Replace `<env>` with
`dev` / `uat` / `prod`.

| Artifact | Suggested name |
|---|---|
| Engineering workspace | `ws-<env>-bronze-engineering` |
| Audit / operations workspace | `ws-<env>-operations` (one per environment, recommended) |
| Bronze Lakehouse | `lh_bronze_<env>` (**schemas enabled**) |
| Warehouse | `wh_control_<env>` |
| Audit SQL Database | `BronzeFrameworkAudit` |
| Environment item | `CicdFramework` |
| ADLS Gen2 account / container | `st<org><env>landing` / `landing` |
| Key Vault / salt secret | `kv-<org>-<env>-bronze` / `bronze-anonymisation-salt` |

## 0. Prerequisites and identities

Decide these before creating anything, and record them in the change ticket.

| Identity | Used by | Needs |
|---|---|---|
| CI/CD service principal (`docs/service_principal_requirements.md`) | GitHub Actions: git sync, library publish, migration run, stage deploy, verify | Workspace Member on the engineering and operations workspaces; `db_owner` on the Warehouse and the audit database (migrations) |
| Pipeline / notebook runtime identity | `BronzeOrchestrator`, `BronzeFramework`, `MetadataInitialisation` | Workspace Contributor on engineering; Warehouse `SELECT` on `control`, `INSERT, UPDATE` on `control.watermark`; audit DB `EXECUTE` on schema `audit`; Key Vault Secrets User; storage read/write on `landing` |
| Operators group | Monitoring | audit DB `SELECT` on the `audit.vw_*` views; Viewer on the workspaces |

> **Verify live:** which identity a scheduled pipeline's notebook activity
> runs as. It is the pipeline owner, or the workspace identity if one is
> configured. The SQL grants below must go to *that* identity.

Other prerequisites:
- A Fabric capacity assigned to both workspaces.
- The tenant setting *Service principals can use Fabric APIs*, scoped to the
  CI group.
- *Users can create Fabric items*, and SQL database enabled for the tenant.

## 1. Workspaces

1. Create `ws-<env>-bronze-engineering` and `ws-<env>-operations`, and assign
   the capacity to both.
2. Add the role assignments from §0.
3. If the private-network design requires it, enable workspace private link
   or outbound access protection now. Note that outbound protection **blocks**
   the cross-workspace audit connection and the storage/Key Vault access,
   unless managed private endpoints are created for them (step 6c). See
   `docs/bronze_framework/security_review.md`.

**Verify:** both workspaces show the capacity, and the CI service principal
appears in the Manage access list of each.

## 2. Bronze Lakehouse

1. In the engineering workspace, create a Lakehouse `lh_bronze_<env>`, with
   **Lakehouse schemas** enabled at creation. This cannot be enabled later.
2. Leave schemas empty. `MetadataInitialisation` creates `staging` and one
   schema per source (for example `sqlserver`).

**Verify:** the Lakehouse explorer shows a *Schemas* node with `dbo`.

## 3. Warehouse

1. In the engineering workspace, create the Warehouse `wh_control_<env>`.
2. Copy its SQL connection string (Settings, SQL endpoint). It becomes
   `warehouse_connection_string`:
   `Driver={ODBC Driver 18 for SQL Server};Server=<endpoint>;Database=wh_control_<env>;Encrypt=yes;`
   Contains no credentials; the token is supplied at run time.
3. Grant access. Run in the Warehouse SQL editor as an admin, once per
   identity:
   ```sql
   CREATE USER [<ci-spn-name>] FROM EXTERNAL PROVIDER;
   ALTER ROLE db_owner ADD MEMBER [<ci-spn-name>];

   CREATE USER [<runtime-identity>] FROM EXTERNAL PROVIDER;
   -- after the first migration has created the control schema (step 9):
   GRANT SELECT ON SCHEMA::control TO [<runtime-identity>];
   GRANT INSERT, UPDATE ON control.watermark TO [<runtime-identity>];
   ```

**Verify:** `SELECT name FROM sys.database_principals WHERE type IN ('E','X');`
lists both identities.

## 4. Central audit SQL Database

1. In `ws-<env>-operations`, create a SQL database `BronzeFrameworkAudit`.
2. Copy its connection string. It becomes `audit_connection_string`, in the
   same shape as step 3.
3. Grant access in its query editor:
   ```sql
   CREATE USER [<ci-spn-name>] FROM EXTERNAL PROVIDER;
   ALTER ROLE db_owner ADD MEMBER [<ci-spn-name>];

   CREATE USER [<runtime-identity>] FROM EXTERNAL PROVIDER;   -- one per engineering workspace identity
   CREATE USER [<operators-group>] FROM EXTERNAL PROVIDER;
   -- after the first migration has created the audit schema (step 9):
   GRANT EXECUTE ON SCHEMA::audit TO [<runtime-identity>];
   GRANT SELECT ON SCHEMA::audit TO [<operators-group>];   -- or per view: audit.vw_*
   ```

**Verify:** as the runtime identity (for example from a scratch notebook in
the engineering workspace), open a pyodbc connection with
`notebooks.framework.fabric_connection.get_connection_notebookutils(cs, "pbi")`
and run `SELECT 1`. If `pbi` fails, try
`https://database.windows.net/.default`. Record the audience that works in
`framework_configuration.audit_sql_token_audience`
(`warehouse/metadata/020_framework_configuration.sql`) for this environment.

## 5. Storage account (landing) and Key Vault

1. Create an ADLS Gen2 account (hierarchical namespace **on**) with public
   network access **disabled**, and a container `landing`. If you choose a
   different name, change `landing_container` in
   `020_framework_configuration.sql`.
2. Add a lifecycle policy for `landing/` retention, for example cool after 30
   days and delete after the regulatory retention period.
3. Grant the runtime identity and the landing Fabric connection's identity
   *Storage Blob Data Contributor* on the container.
4. Enable *trusted workspace access* for the engineering workspace, or a
   private endpoint (see step 6c).
5. Create Key Vault `kv-<org>-<env>-bronze`, and a secret
   `bronze-anonymisation-salt` with a long random value, **distinct per
   environment**. Grant the runtime identity *Key Vault Secrets User*.
   `key_vault_uri` = `https://kv-<org>-<env>-bronze.vault.azure.net/`.

**Verify:** the container exists and is not publicly reachable. The secret is
readable from a scratch notebook:
`notebookutils.credentials.getSecret("<key_vault_uri>", "bronze-anonymisation-salt")`.
Print only its length, never the value.

## 6. Gateway, connections and shortcut

a. **Source connection.** Install or register the on-premises data gateway
   (or VNet gateway) that can reach the SQL Server. Create a Fabric connection
   *SQL Server* through that gateway, using a **read-only** source login. Note
   its connection id: this is placeholder `…a001`.

b. **Landing connection.** Create a Fabric connection of type *Azure Data Lake
   Storage Gen2* to the account from step 5 (placeholder `…a002`).

c. **Audit connection.** Create a Fabric connection to `BronzeFrameworkAudit`
   (placeholder `…a003`). If outbound access protection is on, create managed
   private endpoints from the engineering workspace to the audit database,
   ADLS and Key Vault first.

d. **Invoke-pipeline connection.** Create the connection used by
   `InvokePipeline` (placeholder `…a004`), the same kind as the working
   `rio/pl_invoke_audit` item.

e. **Landing shortcut.** In `lh_bronze_<env>`, go to Files, New shortcut, ADLS
   Gen2, and pick the `landing` container, using the connection from (b). Name
   the shortcut `landing` so that the path is `Files/landing`
   (`landing_lakehouse_path`).

f. Share the four connections with the runtime identity and the CI service
   principal only.

**Verify:** the Lakehouse shows `Files/landing`. Uploading a test file to the
container makes it visible there. Delete the test file afterwards.

## 7. Environment item and framework wheel

1. In the engineering workspace, create an Environment `CicdFramework`
   (DEV: git sync creates it from `fabric_items/environments/`).
2. Publish the framework wheel. CI does this. To do it by hand:
   ```bash
   python -m scripts.ci.fabric_publish_environment_library --workspace-id <ws-id> --environment-id <env-item-id>
   ```
   The wheel bundles `notebooks.framework`, `notebooks.bronze` and every
   migration SQL root.

**Verify:** Environment, Custom libraries shows
`fabric_medallion_framework-*.whl`, and the publish state is *Success*.

## 8. Fabric items (pipelines and notebooks)

- **DEV:** connect workspace git integration to this repo, branch `main`,
  folder `/fabric_items`, then run *Update from Git*. CI also runs
  `scripts/ci/fabric_git_sync.py`.
- **UAT / PROD:** create the Fabric Deployment Pipeline once (stages Dev, UAT,
  Prod), then deploy stage to stage. CI runs
  `scripts/ci/fabric_deploy_pipeline_stage.py`. UAT and PROD are never
  git-connected.

After the items exist in the workspace:
1. Open every pipeline and bind the placeholders listed in
   `fabric_items/README.md`:
   - `…a001`–`…a004`: the connections from step 6.
   - `…b001`: the Warehouse and its SQL endpoint in `LookupActiveEntities`.
   - `…b002`: the Lakehouse in `CopyToStaging`.
2. Check that every `TridentNotebook` / `InvokePipeline` activity points at the
   right item. `notebookId` and `pipelineId` were committed as logical ids.
3. For each notebook (`BronzeFramework`, `MetadataInitialisation`,
   `SchemaMigrationRunner`), attach `lh_bronze_<env>` as the **default
   Lakehouse** and `CicdFramework` as the Environment.
4. Bind the environment parameters, using deployment rules or a Variable
   Library. **Never** commit the values:

   | Parameter | Items | Value |
   |---|---|---|
   | `environment` / `TargetEnvironment` | BronzeOrchestrator / SchemaMigration | `DEV` / `UAT` / `PROD` |
   | `warehouse_connection_string` | BronzeOrchestrator, SchemaMigration | step 3 |
   | `audit_connection_string` | BronzeOrchestrator, SchemaMigration | step 4 |
   | `key_vault_uri` | BronzeOrchestrator | step 5 |

5. In DEV only: *Commit to Git* once, so Fabric rewrites any ids it resolved.
   Review the diff and make sure no real connection strings were committed.
   `pytest tests/fabric_items` fails if a non-placeholder GUID appears.

**Verify:** each pipeline opens without *invalid connection* warnings, and a
*Validate* on each pipeline passes.

## 9. First schema migration

Run the `SchemaMigration` pipeline (CI step: `fabric_run_item_job.py`). It
migrates the **audit database first**, then the Warehouse:
- control DDL
- `SECURITY`/RLS
- `fn_active_entities`
- seed metadata.

**Verify:**
```bash
AUDIT_DB_CONNECTION_STRING="<cs>" python -m scripts.ci.verify_migration_state --env <env> --target audit_db
WAREHOUSE_CONNECTION_STRING="<cs>" python -m scripts.ci.verify_migration_state --env <env> --target warehouse
```
Both must print `OK`. Then finish the deferred grants in steps 3 and 4
(`GRANT … ON SCHEMA::control` / `::audit`).

## 10. Environment metadata

1. Set this environment's connection values in `control.source_connection`,
   following RB-02 § *Environment connection values*.
2. Review `020_framework_configuration.sql` for this environment. Check:
   - `anonymisation_enabled` is `false` **only** in PROD
   - `max_parallel_entities`
   - `landing_globally_enabled`
   - the token audiences found in step 4.
3. Run `warehouse/checks/metadata_health_checks.sql`. Every check must return
   no rows. Query 15 shows the source query each entity will run.

## 11. Create the Bronze tables

Run the `MetadataInitialisation` notebook with `environment` and
`warehouse_connection_string`.

**Verify:** the Lakehouse contains `staging.sqlserver_*` and `sqlserver.*`
tables. The HISTORY entity (`sqlserver.customer`) has `bronze_valid_from`,
`bronze_valid_to` and `bronze_is_current`.

## 12. Smoke test

1. Trigger `BronzeOrchestrator` with `entity_group = reference`. This runs
   Territory only: a FULL load through the staging path.
2. Then trigger it with `entity_group = sales`. Customer and Order go through
   landing; Product goes through staging.
3. In the audit database, check:
   ```sql
   SELECT TOP 5 * FROM audit.vw_run_summary ORDER BY start_datetime DESC;
   SELECT * FROM audit.vw_entity_status WHERE environment = '<ENV>';
   SELECT * FROM audit.vw_landing_files WHERE environment = '<ENV>';
   SELECT * FROM audit.vw_recent_errors WHERE environment = '<ENV>';
   ```
   Expect `SUCCEEDED` runs, `landing_enabled = 1` rows with a file in
   `vw_landing_files`, and no errors.
4. Trigger the same group again. It should be a no-op incremental run: no
   Bronze changes, and the watermark stays the same.
5. Record the results as PASS / FAIL against
   `docs/agent_prompts/21_deployment_final_acceptance.md`.

## Rollback of a failed setup

Everything above is additive. For a failed migration, see
`docs/runbook.md` §6.5. For bad metadata, revert the script and redeploy
(RB-02). Workspace items and infrastructure can be deleted and recreated;
nothing in the framework depends on their ids except the bindings in step 8.
