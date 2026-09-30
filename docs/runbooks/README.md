# Runbooks

Step-by-step procedures for building, maintaining and operating the Bronze
framework. Design rationale lives in `docs/bronze_framework/`. These pages
cover only what to do, in order, and how to confirm each step worked.

| Runbook | Use it to |
|---|---|
| [01_platform_setup.md](01_platform_setup.md) | Create every Fabric/Azure artifact for a new environment (DEV, UAT, PROD), from empty workspace to first successful run |
| [02_metadata_maintenance.md](02_metadata_maintenance.md) | Maintain `control` metadata: add or change source systems, entities, columns, rules and configuration; retire entities |
| [03_operations_procedures.md](03_operations_procedures.md) | Day-2 procedures: run, replay, re-run, watermark reset, backfill, salt rotation, audit outage, adding an environment |
| [04_framework_changes.md](04_framework_changes.md) | Change the framework itself: control/audit DDL, procs and views, a new source type, releasing framework code |

## Rules that apply to every runbook

- **Production.** Never act on a PROD workspace, Warehouse, audit database
  or Storage Account without explicit, in-the-moment approval. This applies
  even when the same step was approved for DEV or UAT.
- **Source control.** Change artifacts through git: SQL under `warehouse/`
  and `sql_database/`, items under `fabric_items/`. Do not make ad-hoc portal
  edits that are not committed afterwards.
- **Secrets.** Never put a secret, key, password or connection string in a
  file, a metadata row, a pipeline parameter default or an audit row. Secrets
  live in Key Vault and in Fabric connections.
- **Validate before calling it done.** Every procedure ends with a
  verification step. Record its result in the change ticket.
- **Status.** None of these procedures has been executed against a live
  Fabric tenant yet (see `docs/bronze_framework/test_results.md`). Treat the
  first execution in DEV as a dry run, and correct the runbook where reality
  differs.
