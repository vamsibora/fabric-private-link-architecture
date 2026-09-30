# 14 — Testing

## Layers

| Layer | Where | Needs | Runs in CI |
|---|---|---|---|
| Unit (pure logic): SQL/expression builders, classification, roll-ups, path building, watermark ordering | `tests/bronze/test_*.py`, `tests/framework/`, `tests/ci/` | Python only; `notebookutils`/pyodbc mocked | yes (`pytest -q`) |
| Adapter (fakes): orchestrator chain, audit manager boundaries, watermark commit SQL | `tests/bronze/test_orchestrator.py`, `test_audit_manager.py`, `test_watermark_manager.py` | Python only | yes |
| Spark end-to-end: real Delta MERGE/history/validation on a local Spark session | `tests/bronze/test_spark_end_to_end.py` (`@pytest.mark.spark`) | `pyspark` + `delta-spark` + **Java** | only where Java exists; **skipped** otherwise |
| Item structure: pipeline JSON / `.platform` / notebook source shape vs the `rio` reference; no non-placeholder GUIDs | `tests/fabric_items/test_fabric_items.py` | Python only | yes |
| Live Fabric: the pipeline end to end | Dev workspace, manual (spec §65 / agent prompt 21) | Fabric Dev | **not done**; required before UAT |

Commands:

```bash
pytest -q                      # everything available locally
pytest -m spark -v             # Spark end-to-end (skips without Java)
pytest tests/bronze -v
```

> The live layer has not been exercised. Passing unit and adapter tests do
> not prove the Fabric-specific behaviour listed under "Verify live" in
> [01_Architecture.md](01_Architecture.md).

## Spec §59 scenario coverage

Test file names are as laid out in `tests/bronze/`. "spark" means covered
with real Delta tables in `test_spark_end_to_end.py`, which is skipped when
Java is unavailable. Re-check this table against `pytest --collect-only`
after changing tests.

| # | Scenario | Covered by |
|---|---|---|
| 1 | Initial full load | spark; `test_merge_history_dedup.py` (REPLACE/MERGE builders) |
| 2 | Incremental load | `test_watermark_manager.py` (resolve/commit); spark |
| 3 | No-change incremental load | `test_merge_history_dedup.py` (hash-guarded matched condition); `test_merge_history_dedup.py` (temporal filter); spark (re-run is a no-op) |
| 4 | New records | spark; `test_merge_history_dedup.py` (insert values) |
| 5 | Updated records | `test_hash_engine.py` (business change detected); spark |
| 6 | Deleted records (configured) | `test_merge_history_dedup.py` (delete detection only for FULL + MERGE, soft-delete set, metric parsing); spark |
| 7 | Duplicate source records | `test_validation_engine.py` (DUPLICATE_PRIMARY_KEY SQL); `test_merge_history_dedup.py` (mode/order); spark |
| 8 | Null primary keys | `test_validation_engine.py` (PRIMARY_KEY_NULL built-in, FAIL) |
| 9 | Invalid data types | `test_validation_engine.py` (DATA_TYPE_MISMATCH try_cast); `test_error_manager.py` (DATATYPE_MISMATCH non-retryable) |
| 10 | Invalid watermark | `test_validation_engine.py` (WATERMARK_INVALID incl. older-than-stored); `test_watermark_manager.py` (unparseable → MetadataError) |
| 11 | Landing enabled | `test_landing_staging_schema.py` (path format, yyyyMMddHHmmss); `test_orchestrator.py` (landing branch); `tests/fabric_items/test_fabric_items.py` (Copy → JsonSink) |
| 12 | Landing disabled | `test_landing_staging_schema.py` (verify counts/foreign rows); `test_orchestrator.py` (staging branch, no landing file logged) |
| 13 | Landing file replay | `test_landing_staging_schema.py` (replayable ordering, no-overwrite guard) |
| 14 | Bronze MERGE failure | `test_orchestrator.py` (write-stage failure → FAILED, watermark unchanged) |
| 15 | Validation failure | `test_orchestrator.py` (FAIL rule blocks, WARN/IGNORE do not); `test_validation_engine.py` (status mapping) |
| 16 | Network/transient failure | `test_error_manager.py` (SQL error numbers/SQLSTATEs/patterns retryable) |
| 17 | Retry | `test_error_manager.py` (`with_retry` back-off, limits); `test_orchestrator.py` (retry then success, RETRY_SCHEDULED) |
| 18 | Watermark rollback/preservation | `test_orchestrator.py` (failed entity: no commit, watermark_after = before); `test_watermark_manager.py` (never backwards, conflict) |
| 19 | Anonymisation | `test_anonymisation_engine.py` (every rule type, env gating, salt resolution once, no salt → MetadataError) |
| 20 | Hash change detection | `test_hash_engine.py` |
| 21 | Historical Bronze | `test_merge_history_dedup.py` (merge/insert conditions, temporal predicate); spark (versions, is_current, idempotent re-run) |
| 22 | Composite primary key | `test_config_loader.py`, `test_models_and_run_manager.py`, `test_merge_history_dedup.py` |
| 23 | Multiple concurrent entities | `test_orchestrator.py` (bounded pool, per-entity isolation) |
| 24 | Partial run failure | `test_orchestrator.py` (`rollup_status` PARTIAL_SUCCESS; continue_on_entity_failure) |
| 25 | Complete framework failure | `test_orchestrator.py` (all failed → FAILED; stop-on-failure → CANCELLED) |
| 26 | Audit database failure | `test_audit_manager.py` (fail-fast raises, fail-soft falls back, critical escalation, disabled no-op) |

Cross-artifact contracts (not in §59): `test_sql_contracts.py` checks audit proc names and parameters against `audit_manager.py` and every pipeline stored-procedure activity, Fabric DW T-SQL limits, metadata scripts never resetting watermarks, `fn_active_entities` columns used by the pipeline, and no secrets or hard-coded endpoints. Latest results: [test_results.md](test_results.md).

Metadata/migration coverage (not in §59): `test_config_loader.py`, and
`tests/framework/test_migration_runner.py` (targets, repeatable roots,
bootstrap, drift, halt on failure). `tests/ci/test_verify_migration_state.py`
covers the `--target` smoke test.

## For every live scenario, verify

- Bronze state
- staging state
- landing state (`audit.vw_landing_files`)
- watermark (`control.watermark` vs `audit.entity_run.watermark_after`)
- audit rows (run, entity_run, activity, error, validation)
- run status and entity status.

This checklist feeds the spec §65 final acceptance test (agent prompt 21).
Record results as PASS / FAIL / PARTIAL with evidence.
