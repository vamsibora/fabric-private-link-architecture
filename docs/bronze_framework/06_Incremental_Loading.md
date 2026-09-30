# 06 — Incremental Loading

## Watermark lifecycle

```text
control.watermark.last_successful_watermark  (e.g. 2026-09-29 23:59:59.000000)
        │  fn_active_entities builds:  WHERE [ModifiedDate] > CAST('…' AS DATETIME2(7))
        ▼
Copy (extract only rows after the watermark) ─► landing / staging
        ▼
Framework: batch_max = MAX(watermark column) on the staged batch  (BEFORE anonymisation)
        ▼
validate → dedup → anonymise → hash → Bronze write → POST validate
        ▼
after = max(before, batch_max)   (never backwards; empty batch keeps before)
WatermarkManager.commit(): UPDATE … WHERE entity_id = ? AND last_successful_watermark = <before>
        ▼
audit.entity_run.watermark_before / watermark_after
```

The rules:

- **Only successful entities advance the watermark.** The commit is the last
  processing step. On any failure, `audit.entity_run.watermark_after` is set
  to the unchanged `watermark_before`.
- **Optimistic concurrency.** The UPDATE is guarded by the previously read
  value. Zero rows updated with an existing row means another run moved it,
  which raises `WatermarkConflictError` (non-retryable, never overwritten). A
  missing row is inserted.
- **Types** (`watermark_manager`) and their canonical stored form:
  - DATETIME: `yyyy-MM-dd HH:mm:ss.ffffff`, UTC, microseconds. Spark's
    session time zone is pinned by `spark_timezone`.
  - NUMERIC: a plain decimal with no exponent. It is compared as `Decimal`.
  - STRING: the value itself, compared lexically.
- `WATERMARK_INVALID` validation fails rows whose watermark is NULL or older
  than the stored watermark.
- The extraction predicate is `>`, as in the spec. Rows committed at exactly
  the watermark instant after extraction are a known trade-off of
  timestamp-based watermarks. If a source needs `>=`, set
  `load_configuration.source_query_override` with `{watermark}`. All write
  strategies are idempotent, so re-reading boundary rows is safe.

The metadata deploy never resets a watermark. Seeds only
`INSERT … WHERE NOT EXISTS`. To reload an entity from scratch, set
`last_successful_watermark = NULL` deliberately (see
[12_Operations.md](12_Operations.md)).

## Change detection

`hash_engine`: `bronze_record_hash = sha2(concat_ws(U+001F, canon(c1), …), 256)`
over `entity_column.hash_flag = 1` columns in ordinal order. Primary keys and
all technical columns are excluded.

| Type | Canonical form |
|---|---|
| NULL | `\N` sentinel (distinct from the empty string) |
| STRING | As-is (no trim, no case fold) |
| TIMESTAMP | `yyyy-MM-dd'T'HH:mm:ss.SSSSSS` in the session TZ (UTC) |
| DATE | `yyyy-MM-dd` |
| BOOLEAN | `true` / `false` |
| DECIMAL(p,s) | Plain decimal at scale s |
| integers | Base-10 |
| DOUBLE/FLOAT | `CAST AS STRING` (may use an exponent; avoid in hashes) |
| BINARY | Lower-case hex |

`hash_engine.canonical_value` / `compute_hash` is a pure-Python reference
implementation of the same rules, used by the tests. The seeded entities keep
the watermark column out of the hash (`hash_flag = 0`), so a "touch" that
changes only `ModifiedDate` is not a business change.

The hash is used in three places:
- MERGE updates only when the hash differs.
- HISTORY versions a key only when its hash changes.
- The history temporal filter uses it for idempotency.

## Full loads

`load_type = FULL` has no watermark. With `merge_required` the strategy is
MERGE. Optional `delete_detection_enabled` soft-deletes keys missing from the
extract (`bronze_record_status = 'DELETED'`), and a key that returns is
revived. Without flags, the strategy is REPLACE, a full overwrite.
