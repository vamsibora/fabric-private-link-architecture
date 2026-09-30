# 16 — Sample end-to-end entity (spec §58)

```text
Context: 00_master_context.md. Entity: SQLServer dbo.Customer (control.entity 101,
warehouse/metadata/101_entity_sqlserver_customer.sql):
INCREMENTAL on ModifiedDate, landing_enabled = TRUE, HISTORY, HASH, Email (HASH_EMAIL) and
Phone (MASK_PHONE) anonymised where the environment enables it.

Demonstrate each scenario, first as a pytest -m spark scenario (local Delta; fake audit and
fake watermark store), then in DEV if access exists:
 1 initial load            2 incremental load         3 new records
 4 changed records         5 duplicate input          6 validation failure (WATERMARK_INVALID FAIL)
 7 processing failure      8 retry (TransientError)   9 watermark preserved after failure
10 watermark advanced      11 audit rows (run, entity_run, activity, validation, error, file)
12 landing file created as landing/SQLServer/Customer/Customer_<yyyyMMddHHmmss>.json, never overwritten
13 Bronze history: close + insert, exactly one current row per key
Then repeat with landing_enabled = FALSE (a metadata override in the test, or
landing_globally_enabled = false):
- staging overwritten, and only this run's _staging_run_id present;
- rows loaded;
- Bronze succeeds;
- no landing file;
- audit.entity_run.landing_enabled = 0.

Files: tests/bronze/test_spark_end_to_end.py (spark marker), plus a DEV runbook
section in docs/bronze_framework/16_Sample_Entity.md with the exact pipeline parameters and the
audit queries to check.
Report: each scenario PASS/FAIL with evidence, and what you could NOT verify live.
```
