# 21 — Deployment, CI/CD and final acceptance (spec §64, §65)

```text
Context: 00_master_context.md. Reference: docs/cicd_pipeline.md, scripts/ci/*,
.github/workflows/*.

PART A: deployment (DEV -> UAT -> PROD)
- Separate:
  - environment configuration (control.framework_configuration rows per environment);
  - metadata (warehouse/metadata);
  - secrets (Key Vault);
  - connection references (Fabric connections, placeholders in fabric_items);
  - workspace ids and endpoints (GitHub variables, Variable Library / deployment rules);
  - storage paths;
  - audit DB references.
  No DEV/UAT/PROD values in framework code.
- CI:
  - pr-checks.yml runs pytest -q.
  - cicd-pipeline.yml, per stage:
    1. git sync (Dev) / Deployment Pipeline promote (UAT, PROD);
    2. publish the wheel (bundles every migration root);
    3. run SchemaMigration (audit DB, then the Warehouse);
    4. verify_migration_state.py --target audit_db and --target warehouse;
    5. MetadataInitialisation;
    6. smoke test.
  - UAT and PROD are gated by GitHub Environment reviewers.
- Write docs/bronze_framework/11_Deployment.md covering:
  1. infrastructure (Lakehouse schema-enabled, Warehouse, SQL DB, ADLS + shortcut, gateway,
     Key Vault);
  2. metadata;
  3. notebooks;
  4. pipelines;
  5. Warehouse objects;
  6. the audit SQL DB;
  7. storage;
  8. environment configuration;
  9. security (SQL users, EXECUTE grants, RBAC);
  10. smoke tests;
  11. rollback (forward-fix DDL; revert repeatable scripts; restore watermarks from audit
      watermark_after).
  Deployment must be repeatable and idempotent.
- Never deploy to UAT or PROD without explicit confirmation in the moment.

PART B: final acceptance, as the solution architect
For each requirement, return PASS / FAIL / PARTIAL with evidence: a test id, an audit query
result, or a file:line. For FAIL/PARTIAL, give the root cause and the required change.
- ARCHITECTURE: optional landing; Bronze Lakehouse; Warehouse control schema; central SQL DB
  audit; metadata-driven.
- LANDING: TRUE; FALSE; path format <source_system>/<table>/<table>_<yyyyMMddHHmmss>.json;
  JSON; replay; no overwrite.
- BRONZE: current-state; historical; MERGE; append/change capture; technical columns; hash.
- INCREMENTAL: watermark; safe update; retry; restartability.
- DATA QUALITY: PK; duplicates; mandatory; schema; configurable actions.
- SECURITY: environment anonymisation; no secrets in metadata; no sensitive data in logs.
- AUDIT: run; entity; activity; error; validation; cross-workspace logging.
- OPERATIONS: retry; recovery; monitoring; performance.
Do not mark PASS just because code exists: it must be shown working end-to-end. Anything only
proven by mocked tests is PARTIAL until a DEV run confirms it.
Report: the acceptance table, and what you could NOT verify live.
```
