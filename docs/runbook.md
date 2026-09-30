# CI/CD Runbook

Operational reference for running and troubleshooting the Fabric-native
deployment pipeline. For the *design* rationale, see `docs/cicd_pipeline.md`;
for the service principal setup, see `docs/service_principal_requirements.md`.
This page is commands and failure-mode fixes, not architecture.

Framework runbooks are in `docs/runbooks/`: platform setup, metadata
maintenance, operations procedures and framework changes.

## 1. Local development commands

Run these from the repo root.

```bash
# Install dependencies (pytest, build, msal, requests, pyodbc)
pip install -r requirements-dev.txt

# Full test suite (everything mocked -- no Fabric/Azure connection needed;
# tests marked `spark` skip automatically without Java/pyspark)
pytest -q

# Framework unit tests / Spark end-to-end tests
pytest tests/bronze -v
pytest -m spark -v

# Just the migration runner or connection tests
pytest tests/framework/test_migration_runner.py -v
pytest tests/framework/test_fabric_connection.py -v

# Just the CI script tests
pytest tests/ci/ -v
```

### Build the framework wheel locally (no upload)

Useful for confirming packaging still works after touching any migration
root (`warehouse/ddl/`, `warehouse/programmability/`, `warehouse/metadata/`,
`security/rls/`, `sql_database/audit/`) or `notebooks/`.

```bash
python -c "from scripts.ci.fabric_publish_environment_library import build_wheel; print(build_wheel())"
```

This copies every migration root into
`notebooks/framework/_bundled_repo/` (transient — cleaned up automatically,
even on failure), runs `python -m build --wheel`, and prints the path to the
resulting `.whl` in `dist/`. To inspect what actually got packaged:

```bash
python -c "import zipfile,sys; [print(n) for n in zipfile.ZipFile(sys.argv[1]).namelist()]" dist/fabric_medallion_framework-*.whl
```

### Sanity-check a CI script's argument parsing without calling Fabric

```bash
python -m scripts.ci.fabric_git_sync --help
python -m scripts.ci.fabric_run_item_job --help
python -m scripts.ci.fabric_deploy_pipeline_stage --help
python -m scripts.ci.fabric_publish_environment_library --help
python -m scripts.ci.verify_migration_state --help   # --env, --target warehouse|audit_db
```

All five must be invoked with `python -m scripts.ci.<name>` (not
`python scripts/ci/<name>.py`) — the module form is required for their
`from scripts.ci._fabric_api import ...` absolute imports to resolve.

## 2. One-time environment setup (manual, do once per environment)

Full checklist: `docs/service_principal_requirements.md`. Commands you'll
actually type:

```bash
# Verify the SPN can authenticate (run as the SPN, or after `az login` with
# a user that can impersonate it via federated identity in a test context)
az login --service-principal -u <client-id> -p <client-secret-or-cert> --tenant <tenant-id>
az account get-access-token --resource https://api.fabric.microsoft.com --query accessToken -o tsv
```

Against each environment's Warehouse SQL endpoint (run once, as a human
admin, via any T-SQL client — SSMS, Fabric's own query editor, sqlcmd):

```sql
CREATE USER [spn-fabric-medallion-cicd-shared] FROM EXTERNAL PROVIDER;
ALTER ROLE db_owner ADD MEMBER [spn-fabric-medallion-cicd-shared];
```

Run the same bootstrap against the central **audit SQL Database**
(`BronzeFrameworkAudit`), for the SPN and for the identity the migration
notebook runs as. Runtime identities (the notebook/pipeline identity of each
engineering workspace) instead need `GRANT EXECUTE ON SCHEMA::audit`. See
`docs/bronze_framework/security_review.md`.

Portal steps (no CLI equivalent as of current Fabric GA — do these in the
Fabric admin portal / workspace UI):
1. Enable "Service principals can use Fabric APIs" (Admin Portal → Tenant
   settings → Developer settings), scoped to a group containing only the SPN.
2. Add the SPN as **Member** on Dev (and UAT/Prod once created).
3. Create the Warehouse, Notebook, Data Pipeline, and Environment items in Dev.
4. Connect Dev's Git integration to this repo, branch `main`, folder `/fabric_items`.
5. Use "Commit to Git" once to capture Fabric's real `.platform` files.
6. Create the Deployment Pipeline object, assign Dev/UAT(/Prod) stages, grant
   the SPN a role on the pipeline object.

## 3. GitHub repo configuration

**Secrets** (Settings → Secrets and variables → Actions → Secrets):

| Name | Used by |
|---|---|
| `AZURE_TENANT_ID` | all `azure/login` steps |
| `AZURE_CLIENT_ID` | all `azure/login` steps |
| `DEV_WAREHOUSE_CONNECTION_STRING` / `DEV_AUDIT_DB_CONNECTION_STRING` | `deploy-dev`'s `verify_migration_state.py` (`--target warehouse` / `--target audit_db`) |
| `UAT_WAREHOUSE_CONNECTION_STRING` / `UAT_AUDIT_DB_CONNECTION_STRING` | `promote-uat`'s `verify_migration_state.py` |
| `PROD_WAREHOUSE_CONNECTION_STRING` / `PROD_AUDIT_DB_CONNECTION_STRING` | `promote-prod`'s `verify_migration_state.py` |

The workflow maps these onto the `WAREHOUSE_CONNECTION_STRING` /
`AUDIT_DB_CONNECTION_STRING` environment variables the script reads.

**Variables** (same page, Variables tab):

`DEV_WORKSPACE_ID`, `DEV_ENVIRONMENT_ID`, `DEV_PIPELINE_ITEM_ID`,
`UAT_WORKSPACE_ID`, `UAT_ENVIRONMENT_ID`, `UAT_PIPELINE_ITEM_ID`,
`PROD_WORKSPACE_ID`, `PROD_ENVIRONMENT_ID`, `PROD_PIPELINE_ITEM_ID`,
`DEPLOYMENT_PIPELINE_ID`, `DEPLOYMENT_STAGE_DEV_ID`,
`DEPLOYMENT_STAGE_UAT_ID`, `DEPLOYMENT_STAGE_PROD_ID`.

**GitHub Environments** (Settings → Environments): create `uat` and `prod`,
each with **required reviewers** turned on — this is what makes
`promote-uat`/`promote-prod` pause for manual approval. No federated
credential subject works without the matching Environment existing (see
`docs/service_principal_requirements.md` § 1).

## 4. Deployment flow (what actually happens)

1. Open a PR → `.github/workflows/pr-checks.yml` runs `pytest -q`. No Fabric
   access, nothing deployed.
2. Merge to `main` → `.github/workflows/cicd-pipeline.yml` runs:
   - `test`: pytest again (safety net).
   - `deploy-dev`: git-sync Dev → publish library to Dev → run schema
     migration against Dev → verify.
   - `promote-uat`: **waits for a required reviewer to approve** the `uat`
     GitHub Environment → Deployment Pipeline Dev→UAT → publish library to
     UAT → run schema migration against UAT → verify.
   - `promote-prod`: same, gated on the `prod` Environment, UAT→Prod.
3. A failure at any step stops that job; later jobs (`needs:`) don't run.
   Re-running the workflow (or pushing a fix) is safe — the migration runner
   is idempotent (§5 below covers why).

### Running a step manually (e.g. to unstick a stalled deploy)

You need an authenticated `az` session first (either `az login` as yourself
if you have SPN-equivalent rights, or `az login --service-principal ...`):

```bash
az login --service-principal -u <client-id> -p <client-secret> --tenant <tenant-id>

python -m scripts.ci.fabric_git_sync --workspace-id <dev-workspace-id>
python -m scripts.ci.fabric_publish_environment_library --workspace-id <dev-workspace-id> --environment-id <dev-environment-id>
python -m scripts.ci.fabric_run_item_job --workspace-id <dev-workspace-id> --item-id <dev-pipeline-item-id> --target-environment dev

AUDIT_DB_CONNECTION_STRING="<dev audit db connection string>" python -m scripts.ci.verify_migration_state --env dev --target audit_db
WAREHOUSE_CONNECTION_STRING="<dev connection string>" python -m scripts.ci.verify_migration_state --env dev --target warehouse
```

## 5. Why re-running is safe

`migration_runner.run_migrations()` only executes a CREATE-once script if
it's not already recorded as `SUCCEEDED` in the target's ledger
(`control.schema_migration_history` / `audit.schema_migration_history`), and
only re-applies a repeatable script (procs, views, functions, metadata) when
its checksum differs from the latest `SUCCEEDED` row. Running
the same deploy twice in a row applies zero new scripts the second time.
The one thing that is **not** safe: editing an already-`SUCCEEDED` DDL file.
Fabric Warehouse DDL is `CREATE`-only — the runner will never re-execute a
changed file, it will only flag the mismatch as checksum drift (§6.6). Add a
new numbered file instead.

## 6. Troubleshooting

### 6.1 `pytest` fails locally but passed in CI (or vice versa)

- Confirm `pip install -r requirements-dev.txt` actually ran — `msal` and
  `requests` are only in the dev requirements, not `requirements.txt`.
- Modules that touch `notebookutils` (`fabric_connection`, `audit_manager`,
  `landing_manager`, the `anonymisation_engine` resolver) import it lazily,
  but tests still stub it via `sys.modules.setdefault("notebookutils", ...)`.
  If you add a *new* test file that exercises those paths, copy that stub
  block in, or the import will fail with
  `ModuleNotFoundError: notebookutils`. (`utils_logging.py` has been removed;
  audit is `notebooks/bronze/audit_manager.py`.)
- Spark tests are skipped locally when Java plus `pyspark`/`delta-spark`
  aren't available. That is expected.

### 6.2 `python -m scripts.ci.<name>` fails with `ModuleNotFoundError: No module named 'scripts'`

You ran it as `python scripts/ci/fabric_git_sync.py` instead of
`python -m scripts.ci.fabric_git_sync` — the direct-script form doesn't put
the repo root on `sys.path`, so the absolute `from scripts.ci._fabric_api
import ...` import fails. Always use the `-m` form, and run it from the
repo root (GitHub Actions does this automatically via `working-directory`
defaulting to the checkout root).

### 6.3 `azure/login` step fails / `az account get-access-token` returns an auth error

- Most likely cause: the federated credential's subject claim doesn't match
  the job. Check `docs/service_principal_requirements.md` § 1 — `deploy-dev`
  needs `ref:refs/heads/main`, `promote-uat` needs `environment:uat`,
  `promote-prod` needs `environment:prod`. A mismatch (e.g. the GitHub
  Environment was renamed, or the workflow branch changed) breaks OIDC
  silently with a generic auth failure.
- Confirm `permissions: id-token: write` is still present at the workflow
  level in `cicd-pipeline.yml` — without it, GitHub won't mint the OIDC
  token the federated credential needs at all.
- If using the client-secret fallback instead of OIDC, confirm
  `AZURE_CLIENT_SECRET` hasn't expired (Entra secrets have a hard expiry).

### 6.4 `fabric_git_sync.py` hangs or times out

- Fabric's git integration is pull/API-triggered, not webhook-driven (see
  `docs/cicd_pipeline.md`) — if the workspace's Git connection itself is
  broken (disconnected, reconnected to a different branch/folder, or has
  unresolved conflicts requiring a manual resolution in the portal), the
  `updateFromGit` call will never reach a terminal state via the API alone.
  Open the workspace in the Fabric portal and check Git integration status
  directly — conflicts must be resolved there, not via this script.
- If it fails fast instead of hanging: check the SPN still has Member role
  on the workspace (role assignments can be removed by someone cleaning up
  workspace access without knowing CI depends on it).

### 6.5 `fabric_run_item_job.py` reports `Failed` with a `failureReason`

- The `failureReason` string comes straight from Fabric's job-instance API
  response and printed verbatim — read it first, it's usually specific
  (e.g. a notebook exception, a timeout, an auth failure inside the
  notebook itself).
- If the notebook failed on `from notebooks.framework import
  migration_runner`: the Environment's custom library publish
  (`fabric_publish_environment_library.py`) either didn't run before this
  step, or published successfully but the notebook's attached Environment
  wasn't updated — confirm the Notebook item is actually configured to use
  `CicdFramework.Environment` in the portal.
- If it failed partway through applying scripts: check
  `control.schema_migration_history` (Warehouse) or
  `audit.schema_migration_history` (audit DB) directly in that environment
  — the `FAILED` row's `ErrorMessage` column has the real T-SQL error. Fix
  the underlying DDL issue in a **new** numbered file (never edit the
  failed file's predecessor scripts), and re-run; the runner picks up
  exactly where it left off.
- If it failed on the very first script (schema doesn't exist yet, no
  ledger rows possible): check
  `Files/_framework_fallback/schema_migration/*.json` in the workspace's
  attached Lakehouse/storage for the fallback-logged JSON payload plus a
  `CRITICAL` line in the notebook's own run log.

### 6.6 Checksum drift warning (`audit.error`, error_code `CHECKSUM_DRIFT`)

Someone edited an already-`SUCCEEDED` DDL file on disk. The runner
deliberately does **not** re-execute it (Fabric DW DDL is `CREATE`-only —
re-running would just error, or worse, silently diverge from what's really
in the Warehouse). To resolve:
1. Revert the edit to the original file (restores the recorded checksum), **or**
   (Repeatable scripts never drift: editing them in place is the supported
   way to change procs, views, functions and metadata.)
2. If the change was intentional, express it as a **new** numbered DDL file
   (e.g. an `ALTER TABLE` in a new `035_...sql` or next-available prefix)
   instead of modifying history.

### 6.7 `fabric_publish_environment_library.py` — build or publish is slow/fails

- **Build step fails**: run the local build command from §1 directly to see
  the real `python -m build` output (the CI step's error message is
  truncated to whatever `subprocess.run(..., check=True)` surfaces).
- **Publish hangs**: Environment library publish operations can genuinely
  take several minutes — this is expected, not necessarily a bug (see
  `docs/cicd_pipeline.md` § Open risks). If it consistently times out past
  `poll_until`'s default 1800s window, the documented fallback is staging
  `.sql` files into a Lakehouse `Files/` area instead of an Environment
  library — revisit this design choice if publish latency becomes a
  recurring blocker.
- **Publish succeeds but the notebook still can't import the new code**: the
  Notebook may be attached to a cached/previous Environment session — a
  fresh job run (not a re-run of an already-warm session) is usually needed
  to pick up a newly published library version.

### 6.8 `fabric_deploy_pipeline_stage.py` fails or the promoted stage looks unchanged

- Confirm `--pipeline-id`/`--source-stage-id`/`--target-stage-id` match the
  `DEPLOYMENT_PIPELINE_ID`/`DEPLOYMENT_STAGE_*_ID` GitHub variables exactly
  — a stale ID after someone recreates the Deployment Pipeline object in
  the portal is the most common cause of a confusing 404/403 here.
- Remember **Warehouse schema is never promoted by this call** — only
  notebooks/pipelines/environments move via the Deployment Pipeline. If a
  schema change appears "missing" in UAT/Prod after a stage deploy, that's
  expected — it lands via the *separate* `fabric_run_item_job.py` step that
  runs right after in the same GitHub Actions job.

### 6.9 `verify_migration_state.py` reports `FAIL: N expected migration(s) not SUCCEEDED` (or `repeatable script(s) not applied at current checksum`)

- This means the schema migration step before it didn't actually finish
  applying everything — check the `fabric_run_item_job.py` step's job
  status/log for that same run first; this smoke test is a second opinion,
  not the primary failure signal.
- If it fails on a script that's genuinely a template
  (`security/rls/002_security_policy_template.sql`): confirm the
  `-- MIGRATION_RUNNER: SKIP` marker is still present — if someone removed
  it without actually binding a real table, the script is no longer
  treated as a template and becomes "expected to succeed", so it'll show up
  here as missing until it's either re-marked or genuinely bound and applied.

### 6.10 Manual approval on `promote-uat`/`promote-prod` never shows up for reviewers

- Confirm the `uat`/`prod` GitHub Environments actually have **required
  reviewers** configured (Settings → Environments) — without that, the job
  just runs immediately with no gate, which can look like "the approval
  step is missing" when really it never existed.
- Confirm the person expected to approve is actually listed as a required
  reviewer on that specific Environment (Environment-level, not repo-level
  collaborator access).

### 6.11 SQL-level permission errors (`CREATE TABLE`/`ALTER TABLE` denied)

The SPN's workspace Member role does not automatically grant Warehouse
T-SQL DDL rights. Re-run the one-time bootstrap from §2 against the
specific environment's Warehouse that's failing — this is the single most
common first-deploy blocker for a brand-new environment.
