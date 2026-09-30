# 10 — Hash and change detection (spec §52)

```text
Context: 00_master_context.md. Reference: notebooks/bronze/hash_engine.py.

- bronze_record_hash = SHA-256 hex over the canonical strings of EntityConfig.hash_columns:
  hash_flag = 1, excluding PKs and every technical column, in ordinal order, joined with
  U+001F.
- Canonicalisation, documented in the module and in docs/bronze_framework:
  - NULL -> "\N"
  - STRING -> as-is (no trim, no case folding)
  - TIMESTAMP -> yyyy-MM-dd'T'HH:mm:ss.SSSSSS (session time zone pinned to UTC via
    spark_timezone)
  - DATE -> yyyy-MM-dd
  - BOOLEAN -> true/false
  - DECIMAL -> a plain string at the column's scale
  - integers -> base 10
  - BINARY -> lower-case hex
  - DOUBLE/FLOAT -> CAST AS STRING (discouraged)
- build_hash_expression (Spark SQL: sha2(concat_ws(U+001F, NULL-safe parts), 256)), plus a
  pure-Python reference compute_hash / compute_record_hash with identical rules.
- Use it for MERGE "update only if the hash differs", HISTORY version detection, and
  no-change incremental loads.
- HashEngine.add_hash and add_technical_columns are the only pyspark touchpoints.

Tests: tests/bronze/test_hash_engine.py covers:
- determinism;
- NULL vs "" distinction;
- column order sensitivity;
- PK and technical columns excluded;
- decimal scale and timestamp formats;
- the expression text.
Spark test: the Spark hash equals compute_record_hash for the same rows.
Report: what you could NOT verify live.
```
