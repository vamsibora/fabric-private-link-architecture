# Fabric-Native CI/CD Deployment Pipeline

End-to-end design and runbook for rolling out warehouse schema changes and
other Fabric artifacts (notebooks, data pipelines, environments) across
Dev → UAT → Prod. For the service-principal setup this depends on, see
`docs/service_principal_requirements.md`.

## Why this exists

Fabric's native Deployment Pipelines promote most workspace items (notebooks,
data pipelines, environments, semantic models, reports) between stages, but
**do not** promote Fabric Warehouse schema/data between stages as of current
GA. `warehouse/ddl/` is also `CREATE`-only T-SQL with no built-in tracking of
what's already been applied. This repo's migration ledger
(`CONTROL.SchemaMigrationHistory`) and runner (`notebooks/framework/
migration_runner.py`) exist specifically to fill that gap — re-verify the
Warehouse-promotion limitation against current Microsoft Learn docs
periodically, since Fabric iterates quickly here; if it's since been added,
this custom mechanism may be simplifiable.

## Orchestration model (hybrid)

- **GitHub Actions** runs pytest as a fast, Fabric-independent PR gate
  (`.github/workflows/pr-checks.yml`), and drives deployment via Fabric REST
  API calls made through a service principal (`.github/workflows/
  cicd-pipeline.yml`).
- **GitHub Actions never opens a direct DDL connection** to a Warehouse
  endpoint. The one exception is `scripts/ci/verify_migration_state.py`, a
  read-only post-deploy smoke test.
- The actual schema migration always executes **inside Fabric**, as a
  Notebook item run via a Data Pipeline job, so it runs with the notebook's
  own identity against the target Warehouse.

## Branch / promotion strategy

Only the **Dev** workspace is git-connected (to `main`, root folder
`/fabric_items`). **UAT and Prod are not git-connected** — they receive
content solely via Fabric's native Deployment Pipeline "deploy" action. This
is Microsoft's recommended pattern and avoids branch-per-environment drift.

## Components

| Component | Path | Purpose |
|---|---|---|
| Migration ledger | `warehouse/ddl/05_meta/050_control_schemamigrationhistory.sql` | Tracks which DDL/RLS scripts have been applied per environment. |
| Migration runner | `notebooks/framework/migration_runner.py` | Applies pending scripts in order; safe to re-run; halts on failure. |
| Shared connection helpers | `notebooks/framework/fabric_connection.py` | notebookutils-token and SPN-token pyodbc connections. |
| Fabric Notebook | `fabric_items/notebooks/SchemaMigrationRunner.Notebook/` | Thin wrapper: `start_pipeline_run` → `run_migrations` → `end_pipeline_run`/`log_error`. |
| Fabric Data Pipeline | `fabric_items/pipelines/SchemaMigration.DataPipeline/` | One Notebook activity; `TargetEnvironment` parameter; Warehouse connection swapped per stage via a deployment rule. |
| Fabric Environment | `fabric_items/environments/CicdFramework.Environment/` | Hosts the custom library (wheel) so the notebook can `import migration_runner`. |
| CI helper scripts | `scripts/ci/*.py` | Fabric REST API calls: git sync, library publish, job run, stage deploy, smoke test. |
| Workflows | `.github/workflows/pr-checks.yml`, `.github/workflows/cicd-pipeline.yml` | PR gate; deploy-dev → promote-uat → promote-prod. |

## Shipping runner code + SQL into Fabric

`scripts/ci/fabric_publish_environment_library.py` copies `warehouse/ddl/`
and `security/rls/` into `notebooks/framework/_bundled_repo/` (mirroring
their repo-relative layout — setuptools can only package files inside the
package tree), builds a wheel via `python -m build`, and publishes it as a
custom library to the target environment's `CicdFramework.Environment`. The
notebook then calls `migration_runner.discover_scripts()` against that
bundled path.

**Fallback** if library-publish operations (which can take several minutes)
prove too slow or flaky in practice: stage the `.sql` files into a Lakehouse
`Files/` area instead and have the notebook read from there.

## GitHub Actions workflows

**`pr-checks.yml`** (`pull_request → main`): checkout → setup-python →
`pip install -r requirements-dev.txt` → `pytest -q`. No secrets, no Fabric
access.

**`cicd-pipeline.yml`** (`push → main`, `permissions: id-token: write` for
OIDC):

| Job | GH Environment | Steps |
|---|---|---|
| `test` | — | pytest safety net |
| `deploy-dev` | none | `azure/login` (OIDC) → `fabric_git_sync.py` → `fabric_publish_environment_library.py` → `fabric_run_item_job.py` (runs `SchemaMigration.DataPipeline` against Dev) → `verify_migration_state.py --env dev` |
| `promote-uat` | `uat` (required reviewers) | `fabric_deploy_pipeline_stage.py` (Dev→UAT) → publish library to UAT → run migration pipeline against UAT → `verify_migration_state.py --env uat` |
| `promote-prod` | `prod` (required reviewers) | same shape, UAT→Prod |

Manual approval gates need no custom code — a job declaring
`environment: uat`/`prod` with required reviewers configured in repo
Settings → Environments auto-pauses for approval.

**Git sync note**: Fabric's git integration is pull/API-triggered, not
webhook-driven, in current GA behavior — a plain `git push` does not by
itself sync the Dev workspace. `fabric_git_sync.py` calls `git/status` then
`git/updateFromGit` explicitly and polls to completion. Re-verify this
against current Fabric docs before relying on it in production.

## Order of implementation / rollout

1. **Manual prerequisites** — see `docs/service_principal_requirements.md`
   in full: Entra App Registration + federated credentials, Fabric tenant
   setting, SPN workspace roles, Deployment Pipeline role, one-time SQL
   `CREATE USER ... FROM EXTERNAL PROVIDER` bootstrap per environment,
   GitHub secrets/variables, GitHub `uat`/`prod` Environments with required
   reviewers.
2. **Pure-code scaffolding** (this repo's Python/SQL/tests/workflows) — no
   Fabric access needed, fully testable locally via `pytest -q`.
3. **Fabric workspace items in Dev** — create Warehouse (confirm it exists
   first)/Notebook/Data Pipeline/Environment skeletons in the portal;
   connect Dev's Git integration to `/fabric_items` on `main`; use "Commit
   to Git" once to capture real `.platform` files into the repo.
4. **`deploy-dev` only** — validate manually first (`verify_migration_state.py
   --env dev` by hand) before trusting the automated job; confirm a second
   push to `main` is a safe no-op.
5. **Deployment Pipeline + UAT stage** — create the pipeline object, add
   UAT as the second stage, grant the SPN a role on it; exercise
   `deploy-dev → promote-uat` fully before Prod exists at all.
6. **Prod stage** — create last, only after a clean UAT cycle. Treat the
   first real Prod run as go-live, supervised, not a test.

## Ongoing rule for schema changes

Every future schema change is a **new numbered file** under
`warehouse/ddl/`. **Never edit an already-`SUCCEEDED` DDL file** — Fabric DW
DDL is `CREATE`-only and non-idempotent, so the migration runner will never
re-execute it; it will only flag the checksum drift as a warning. This must
be treated as a hard rule, not just something the drift check happens to
catch.

## Open risks (re-verify at implementation/maintenance time)

- Fabric Warehouse git-sync / Deployment Pipeline schema support may change —
  re-check current docs; this entire custom mechanism exists because of a
  current limitation.
- Git integration push-vs-pull semantics may change.
- The wheel-published-to-Environment-library approach is this repo's own
  design choice, not a Microsoft-prescribed pattern — watch publish latency.
- `NOT ENFORCED` constraints mean the ledger's `UNIQUE(ScriptPath)` doesn't
  stop the application layer from double-inserting — correctness is
  entirely in `migration_runner.py`'s pending-set logic.
- Exact Fabric REST API paths used by `scripts/ci/*.py` should be
  double-checked against current Microsoft Learn docs — the surface is
  still evolving.
