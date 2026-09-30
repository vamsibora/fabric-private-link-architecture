# 11 — Bronze MERGE and history engine (spec §16–§18, §53)

```text
Context: 00_master_context.md. Reference: notebooks/bronze/merge_engine.py,
history_engine.py, dedup_engine.py.

Dedup (before the write):
- Current-state strategies keep one row per PK: latest by watermark, then by
  _bronze_ingest_seq.
- HISTORY and no-PK entities drop only exact duplicates.
- Duplicates removed are reported as rejected_row_count.

merge_engine (MERGE / APPEND / REPLACE):
- MERGE:
  - Delta MERGE on the (composite) PK.
  - Update only when bronze_record_hash differs, or the row was soft-deleted and has
    reappeared; change detection NONE updates every match. Insert new keys.
  - Never overwrite bronze_created_datetime.
  - Delete detection (FULL + delete_detection_enabled only): whenNotMatchedBySource ->
    bronze_record_status = 'DELETED' (a soft delete, never physical).
- APPEND: idempotent per entity run via replaceWhere bronze_entity_run_id = <id>.
- REPLACE: full overwrite (FULL, no key).
- parse_merge_metrics(operationMetrics): inserted, updated, deleted (not-matched-by-source
  updates count as deleted).

history_engine (HISTORY, source history, NOT SCD2):
- valid_from = the DATETIME watermark, else the ingestion time.
- Temporal filter vs the current row: keep a row only if it is newer, or at the same instant
  with a different hash. This makes a rerun a no-op.
- Collapse consecutive identical hashes, seeded with the current hash.
- valid_to = the next version's valid_from.
- ONE atomic MERGE over a staged union:
  - inserts: _mk_* keys NULL -> INSERT;
  - one close row per key: _mk_* = key -> UPDATE is_current = false,
    valid_to = the earliest new valid_from.
  The result is never zero or two current rows for a key.
- Document the limitation: late versions older than the current version are skipped.

Nothing here advances the watermark. The caller fails without committing it.

Tests: tests/bronze/test_merge_history_dedup.py cover
conditions and sets (composite keys), the matched condition per change detection, the soft
delete set, the replaceWhere literal escaping, metrics parsing, the history merge/insert
conditions, the temporal predicate, and the dedup mode/order.
Spark tests (delta-spark):
- initial load, then an unchanged rerun (0 updates);
- changed record -> 1 update (MERGE) or close + insert (HISTORY);
- A->B->A history;
- delete detection.
Report: what you could NOT verify live.
```
