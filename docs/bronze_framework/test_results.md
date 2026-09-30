# Test results report

Spec §59 asks for a test results report. This file records what was actually
run and what was not. Scenario-to-test mapping is in
[14_Testing.md](14_Testing.md).

**Run date:** 2026-09-30. **Where:** local Windows workstation, Python 3.11.9,
pytest 9.1.1, pyspark 3.5.2 installed, **no Java runtime**.
**Command:** `pytest -q -rs`

**Result: 290 passed, 1 skipped, 0 failed.**

| File | Tests | Result |
|---|---:|---|
| tests/bronze/test_anonymisation_engine.py | 14 | passed |
| tests/bronze/test_audit_manager.py | 10 | passed |
| tests/bronze/test_config_loader.py | 7 | passed |
| tests/bronze/test_error_manager.py | 19 | passed |
| tests/bronze/test_hash_engine.py | 8 | passed |
| tests/bronze/test_landing_staging_schema.py | 17 | passed |
| tests/bronze/test_merge_history_dedup.py | 11 | passed |
| tests/bronze/test_models_and_run_manager.py | 14 | passed |
| tests/bronze/test_orchestrator.py | 20 | passed |
| tests/bronze/test_sql_contracts.py | 66 | passed |
| tests/bronze/test_validation_engine.py | 16 | passed |
| tests/bronze/test_watermark_manager.py | 6 | passed |
| tests/bronze/test_spark_end_to_end.py | 4 (module) | **skipped: Java is required for Spark tests** |
| tests/ci/* (6 files) | 31 | passed |
| tests/fabric_items/test_fabric_items.py | 32 | passed |
| tests/framework/test_fabric_connection.py | 6 | passed |
| tests/framework/test_migration_runner.py | 13 | passed |

Other checks run on the same date:

- **Wheel build** (`build_wheel()`). This succeeded. The wheel contains
  `notebooks/bronze` (18 modules) and the bundled migration roots:
  `warehouse/ddl` (16), `warehouse/programmability` (1), `warehouse/metadata`
  (7), `security/rls` (2) and `sql_database/audit` (29, including the
  dev-only `samples/`, which is not a migration root). The transient
  `_bundled_repo/` was removed afterwards.
- **Workflow YAML** (`.github/workflows/*.yml`). Both files parse. They have
  not been run on GitHub.

## What the green run proves

The following is proven:

- Metadata assembly, validation and the write-strategy derivation.
- The id, run-timestamp and landing-path formats, and the never-overwrite
  guard.
- Staging integrity checks, and SQL/expression generation for validation,
  anonymisation, hashing, MERGE and history.
- Watermark ordering and guarded commits.
- Error classification and retry.
- The audit fail-fast / fail-soft boundaries.
- The orchestrator's processing order, and failure handling that preserves
  the watermark.
- Bounded parallelism and the run-status roll-up.
- Contracts between the Python, the pipelines and the SQL (proc names,
  parameters and required parameters, the `fn_active_entities` columns),
  the Fabric DW T-SQL limits and the no-secrets rule.
- Pipeline and notebook structure against the working `rio` reference shapes.

## What it does NOT prove

- **Spark/Delta behaviour.** `test_spark_end_to_end.py` covers real MERGE,
  history versioning, idempotent replay, landing JSON reads, staging
  integrity, validation-failure isolation and soft deletes. It was **never
  executed**, because no Java runtime was available. Run it on a machine with
  Java 17:
  `pip install "pyspark==3.5.*" "delta-spark==3.2.*" && pytest -m spark -v`.
  The `spark-tests` job in `.github/workflows/pr-checks.yml` runs it and is
  set to `continue-on-error` until it has passed once.
- **Anything live in Fabric.** No DDL, procedure, function, pipeline or
  notebook has been deployed or executed against a Fabric workspace, Warehouse,
  SQL Database, Lakehouse or Storage Account. See "Verify live before
  production" in [01_Architecture.md](01_Architecture.md) and agent prompt 21
  (`docs/agent_prompts/21_deployment_final_acceptance.md`) for the acceptance
  run that is still outstanding.
