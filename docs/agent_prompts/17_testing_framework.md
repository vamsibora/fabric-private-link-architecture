# 17 — Testing framework (spec §59)

```text
Context: 00_master_context.md. Existing tests: tests/framework, tests/ci, tests/bronze,
tests/fabric_items.

Cover all 26 spec §59 cases:
 1 full load, 2 incremental, 3 no-change incremental, 4 new, 5 updated,
 6 deleted (FULL + delete detection), 7 duplicates, 8 null PK, 9 invalid types,
10 invalid watermark, 11 landing on, 12 landing off, 13 landing replay,
14 MERGE failure, 15 validation failure, 16 transient failure, 17 retry,
18 watermark preservation, 19 anonymisation, 20 hash change detection,
21 historical Bronze, 22 composite PK, 23 concurrent entities,
24 partial run failure, 25 complete framework failure, 26 audit DB failure (fail-soft vs fail-fast).

For every case assert: the Bronze state, the staging state, the landing state, the watermark,
the audit records (via a recording fake of AuditManager's proc calls), the run status and the
entity status.

Layout:
- Pure/mocked tests run in `pytest -q` (the CI gate).
- Spark/Delta tests are marked @pytest.mark.spark, registered in pyproject/pytest config, and
  skip automatically when Java or pyspark/delta-spark is missing. Put shared fixtures in
  tests/bronze/conftest.py (local SparkSession with Delta, UTC time zone).
- Keep the notebookutils stub pattern in every test that imports runtime modules.

Produce docs/bronze_framework/14_Testing.md with a results table
(case -> test id -> PASS/FAIL/SKIPPED) from the actual run. Quote the pytest summary lines.
Report: what you could NOT verify live.
```
