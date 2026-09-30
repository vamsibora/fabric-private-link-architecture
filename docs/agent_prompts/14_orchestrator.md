# 14 — Orchestrator (spec §13, §37, §39, §56)

```text
Context: 00_master_context.md. Reference: notebooks/bronze/orchestrator.py, bootstrap.py,
fabric_items/notebooks/BronzeFramework.Notebook/notebook-content.py.

Modes:
- PIPELINE: the run was started by the pipeline. audit.usp_start_run is called again
  (idempotent). Process exactly the entities that usp_get_run_entities(run_id, 'EXTRACTED')
  returns (work_items_from_audit).
- REPLAY: a NEW run reprocesses existing landing files of an earlier run timestamp, or the
  latest file per entity, without touching the source.

Per entity (process_entity / _process_once), with each step tagged by stage:
1. staging: load from landing (TRUE) or verify copied staging (FALSE)
2. ensure the Bronze table
3. read the typed rows
4. PRE validation (blocking -> ValidationFailedError)
5. batch max watermark
6. dedup
7. anonymise
8. hash + technical columns
9. write (HISTORY -> history_engine, else merge_engine)
10. POST validation
11. watermark commit
12. audit complete SUCCEEDED with counts
Retry retryable errors per load_configuration. Any failure -> audit.error, entity FAILED,
watermark_after = the previous value, landing file FAILED. Nothing advances.

run():
- ThreadPoolExecutor(max_parallel_entities); no uncontrolled fan-out.
- continue_on_entity_failure off -> entities not yet started are CANCELLED.
- rollup_status: SUCCEEDED / PARTIAL_SUCCESS / FAILED / CANCELLED, mirroring
  usp_complete_run.
- Complete the audit run and return a RunSummary (to_dict).

bootstrap.build_framework:
- Takes parameters only: environment, the Warehouse and audit connection strings,
  key_vault_uri, run ids.
- Loads config and entities, applies landing_globally_enabled, and sets the Spark time zone.
- Fails if anonymisation is needed and there is no key_vault_uri.
The notebook raises when the status is not SUCCEEDED, so pipeline monitoring shows it.

Tests: tests/bronze/test_orchestrator.py (fake services, no Spark) covers:
- the success path's call order and counts;
- validation failure: no write, no watermark;
- a write failure keeping the watermark;
- a retryable error retried then succeeding;
- a non-retryable error not retried;
- landing vs staging paths;
- parallel entities with one failure -> PARTIAL_SUCCESS;
- cancellation;
- rollup;
- work items from audit rows.
Report: what you could NOT verify live.
```
