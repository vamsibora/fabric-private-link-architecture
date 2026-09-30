# 07 — Historical Loading

`history_required = 1` selects the HISTORY strategy (`history_engine.py`).
Bronze keeps **source history**: every distinct version of a source record.

```text
CustomerId | Address    | ModifiedDate | bronze_valid_from | bronze_valid_to | bronze_is_current
100        | Birmingham | 2026-09-01   | 2026-09-01        | 2026-09-10      | false
100        | Solihull   | 2026-09-10   | 2026-09-10        | NULL            | true
```

This is **not** business SCD Type 2. There are no surrogate keys and no
business effective-dating rules. Dimensional history (CustomerKey,
EffectiveFrom/To, IsCurrent) is built downstream in Silver/Gold from these
rows.

## Algorithm

The input batch has already been validated, deduplicated (exact duplicates
only, since several versions per key are legitimate), anonymised and hashed.

1. **valid_from** is the watermark value for DATETIME watermarks. Otherwise
   it is the entity run's ingestion instant.
2. **Temporal filter** against the current Bronze row per key. Keep a row if
   there is no current row, or it is newer than the current version, or it
   has the same instant but a different hash. Anything at or before the
   current version was already processed, which makes re-running a batch a
   no-op.
3. **Collapse** consecutive identical hashes per key, ordered by valid_from
   then ingestion order. The first comparison is seeded with the current
   Bronze hash, so an unchanged record is not re-versioned.
4. **valid_to** is the next version's valid_from. The last version of each
   key is `bronze_is_current = true`.
5. **One atomic Delta MERGE** over a staged union:
   - Insert rows carry NULL merge-key columns (`_mk_<pk>`), so they never
     match and are inserted.
   - One close row per affected key carries the key and the earliest new
     valid_from. It matches the current row (`t.pk = s._mk_pk AND
     t.bronze_is_current`) and sets `is_current = false`,
     `valid_to = <earliest new valid_from>`.

   Closing and inserting in one commit means a crash can never leave a key
   with zero or two current rows.

Metrics: `inserted` is new versions; `updated` is previous versions closed.

## Limitations

- Late-arriving versions older than the current Bronze version are skipped.
- HISTORY requires a primary key and `change_detection_method = HASH`
  (`config_loader.validate_entity`).
- Delete detection is not applied to HISTORY entities.
