# Service Principal Requirements — Fabric CI/CD

This is a standalone operational/security deliverable for whoever provisions
the Entra service principal (SPN) the GitHub Actions CI/CD pipeline
(`.github/workflows/cicd-pipeline.yml`) uses to talk to Fabric. Hand this
page to a Fabric/Entra admin — it does not assume they've read the rest of
this repo.

## Suggested name

**`spn-fabric-medallion-cicd-shared`** — one SPN shared across Dev, UAT, and
Prod to start, matching the current single-branch/single-Deployment-Pipeline
design (see `docs/cicd_pipeline.md`).

**Hardening path for later**: once Prod is live, split into
`spn-fabric-medallion-cicd-dev`, `spn-fabric-medallion-cicd-uat`,
`spn-fabric-medallion-cicd-prod` so a compromised Dev credential (or a bug in
the `deploy-dev` job) can't reach Prod. Not required for the initial rollout.

## 1. Entra App Registration

- Create one App Registration backing the SPN(s) above.
- **Prefer federated credentials over a client secret** — nothing long-lived
  to leak or rotate. Add one federated credential per GitHub OIDC subject the
  workflow actually uses:
  - `repo:vamsibora/fabric_medallion_architecture:ref:refs/heads/main` — the
    `deploy-dev` job (runs on every push to `main`, no GitHub Environment).
  - `repo:vamsibora/fabric_medallion_architecture:environment:uat` — the
    `promote-uat` job.
  - `repo:vamsibora/fabric_medallion_architecture:environment:prod` — the
    `promote-prod` job.
- **Fallback**: if federated credentials aren't available yet in this
  tenant, create a client secret, store it as the GitHub Actions repo secret
  `AZURE_CLIENT_SECRET`, and use MSAL's confidential-client secret flow
  instead of `azure/login@v2`'s OIDC path. Rotate it on a schedule if you go
  this route.

## 2. Fabric tenant setting

Enable **"Service principals can use Fabric APIs"** in the Fabric Admin
Portal → Tenant settings → Developer settings. Scope it to a security group
containing **only** this SPN — not tenant-wide — so no other SPN in the
tenant inherits Fabric API access as a side effect.

## 3. Fabric workspace role assignments

Add the SPN as **Member** (not just Contributor) on each workspace:

| Workspace | Why Member specifically |
|---|---|
| Dev | Needed for git `updateFromGit`, publishing the `CicdFramework.Environment` custom library, and running the `SchemaMigration.DataPipeline` job. |
| UAT | Same — the pipeline publishes the library and runs the migration job here too, after Deployment Pipeline stage-deploy. |
| Prod | Same, added once the Prod workspace exists. |

There is **no Graph-style `Workspace.ReadWrite.All` app permission** to
grant for the Fabric REST API surface — as of current GA, Fabric authorizes
calls by the caller's **workspace role**, not by declared Graph API
permissions. "Assign the SPN Member on each workspace" *is* the permission
grant here, not a prerequisite to one.

## 4. Deployment Pipeline role assignment

Separately from workspace membership, assign the SPN **Admin or
Contributor** directly on the Deployment Pipeline object itself (once
created — see `docs/cicd_pipeline.md` § Order of Implementation):

```
POST /v1/deploymentPipelines/{pipelineId}/roleAssignments
```

A Deployment Pipeline is not a workspace, so this is a distinct
authorization surface from the workspace role assignments above — both are
required.

## 5. SQL-level Warehouse permissions

Workspace Member role does **not** automatically grant full DDL rights on a
Fabric Warehouse's T-SQL surface. As a guaranteed one-time bootstrap **per
environment** (Dev now; UAT and Prod when their Warehouses exist), have a
human admin connect to each Warehouse's SQL endpoint as an admin and run:

```sql
CREATE USER [spn-fabric-medallion-cicd-shared] FROM EXTERNAL PROVIDER;
ALTER ROLE db_owner ADD MEMBER [spn-fabric-medallion-cicd-shared];
```

If `db_owner` is considered too broad for a CI identity, use a narrower
custom role instead — grant `CREATE SCHEMA`, `CREATE TABLE`, `ALTER` on the
`CONTROL` and `SECURITY` schemas, plus `SELECT`/`INSERT`/`UPDATE` on
`CONTROL.*` (the migration runner only ever needs DDL on those two schemas
and DML on the `CONTROL.SchemaMigrationHistory` ledger and other `CONTROL`
tables via `utils_logging`).

This step **cannot be automated by the CI pipeline itself** — the pipeline
has no permissions on the Warehouse until this bootstrap runs, so it must be
done manually before the first `deploy-dev` run.

## Summary checklist

- [ ] Entra App Registration created, named `spn-fabric-medallion-cicd-shared`
- [ ] Federated credentials added for `ref:refs/heads/main`, `environment:uat`, `environment:prod` (or a client secret stored as `AZURE_CLIENT_SECRET` as fallback)
- [ ] "Service principals can use Fabric APIs" enabled, scoped to a group containing only this SPN
- [ ] SPN added as Member on Dev workspace (UAT/Prod once they exist)
- [ ] SPN assigned a role on the Deployment Pipeline object (once created)
- [ ] `CREATE USER ... FROM EXTERNAL PROVIDER` + role grant run against Dev's Warehouse (UAT/Prod once they exist)
- [ ] GitHub repo secrets/variables created: tenant ID, client ID, workspace IDs, item IDs, deployment pipeline/stage IDs
- [ ] GitHub Environments `uat` and `prod` created with required reviewers configured
