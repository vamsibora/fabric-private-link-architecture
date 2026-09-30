# 07 — Staging Manager (spec §8–§9, §49, change 1: landing_enabled = FALSE)

```text
Context: 00_master_context.md. Reference: notebooks/bronze/staging_manager.py.

Staging is ephemeral; Bronze is persistent. Only staging is ever truncated.

landing_enabled = FALSE (source -> staging -> Bronze):
- The extract pipeline's Copy sink is LakehouseTableSink on staging.<table> with
  tableActionOption Overwrite (truncate + load in one commit). It adds
  additionalColumns _staging_run_id = run_id.
- The framework VERIFIES before use: every row carries this run_id (no stale or foreign rows),
  and the count equals the copy's rowsCopied (audit.entity_run.source_row_count).
  Otherwise it raises StagingIntegrityError.
- truncate() (Delta DELETE FROM, which keeps the schema) is the documented fallback if
  Overwrite proves unsuitable live.

landing_enabled = TRUE (landing -> staging -> Bronze):
- Read this run's landing JSON with an explicit all-STRING schema of the source columns. Do not
  infer: JSON omits null fields and inferred types drift.
- Stamp _staging_run_id and overwrite staging (overwriteSchema), then verify.

read(entity, run_id): filter to the run, apply column_mapping expressions or the source column,
CAST to target_data_type ONCE, and add _bronze_ingest_seq for deterministic dedup.
Never touch the final Bronze table.
Audit STAGING_VERIFIED / STAGING_LOADED_FROM_LANDING activities with row counts.

Tests: tests/bronze/test_landing_staging_schema.py covers the counts SQL, check_staging_counts (a
foreign row, a count mismatch, OK), projection (mapping, cast, case-insensitive source lookup),
the landing read schema, and missing_source_columns.
Spark test: overwrite, verify and read round-trip.
Report: what you could NOT verify live (Overwrite atomicity; additionalColumns on a Lakehouse sink).
```
