# 12 — Operations

Operators work from the central audit database. The views are described in
[05_Audit_Design.md](05_Audit_Design.md).

## Daily checks

```sql
-- runs in the last day
SELECT * FROM audit.vw_run_summary WHERE start_datetime >= DATEADD(DAY, -1, SYSUTCDATETIME()) ORDER BY start_datetime DESC;
-- current state of every entity
SELECT * FROM audit.vw_entity_status WHERE environment = 'PROD' ORDER BY status, source_table;
-- stale / not loaded
SELECT * FROM audit.vw_watermark_status WHERE is_not_loaded_recently = 1 OR is_watermark_stale = 1;
-- repeated failures, failing validations
SELECT * FROM audit.vw_repeated_failures;
SELECT * FROM audit.vw_validation_failures WHERE created_datetime >= DATEADD(DAY, -1, SYSUTCDATETIME());
```

## Running

- **Scheduled:** trigger `BronzeOrchestrator` with `environment` and,
  optionally, `entity_group`.
- **Manual subset:** set `entity_group`, or run the `BronzeFramework`
  notebook with `entity_ids` in REPLAY mode for landing entities.
- Adding a table means adding a numbered `warehouse/metadata/1xx_entity_*.sql`
  script, deploying (SchemaMigration), then running `MetadataInitialisation`.
  No pipeline changes are needed.

## Replay from landing (no source connection)

Use this after a Bronze-side failure of a landing-enabled entity whose file
exists.
1. `SELECT * FROM audit.vw_landing_files WHERE entity_id = 101 AND is_replayable = 1;`
2. Run the `BronzeFramework` notebook with:
   - `mode = REPLAY`
   - `entity_ids = 101`
   - `replay_run_timestamp` = the file's timestamp. Leave it empty for the
     latest file.
   - the connection-string / `key_vault_uri` parameters.
3. This creates a new run (`trigger_type = REPLAY`). The file status becomes
   `PROCESSED` on success.

Replaying an older file after a newer one has already been processed is
safe for HISTORY: the temporal filter skips already-processed versions. For
MERGE entities, it can move current state backwards, so replay files in
timestamp order.

## Re-run after failure

The watermark never advanced for a failed entity, and every write strategy is
idempotent. Fix the cause, then re-trigger the pipeline (for the entity's
group), or replay if the entity is landing-enabled. A retry of the same
`run_id` reopens the same `entity_run` row and increments `attempt_number`.

## Resetting a watermark (full reload of an incremental entity)

1. Check `audit.vw_watermark_status` and record the current value in the
   change ticket.
2. Run:
   ```sql
   UPDATE control.watermark
   SET last_successful_watermark = NULL, last_run_id = NULL, last_entity_run_id = NULL,
       updated_datetime = SYSUTCDATETIME()
   WHERE entity_id = <id>;
   ```
3. Run the entity. MERGE and HISTORY are idempotent, so existing Bronze rows
   are not duplicated.

Never run this against PROD without explicit approval.

## Stale watermark

`is_watermark_stale = 1` means the watermark has not moved across the last 5
successful runs. Check `source_row_count` in `vw_entity_status`:
- 0 rows: the source may genuinely be quiet, or the source watermark column
  is not being maintained.
- Rows arriving but the watermark not moving: check the `WATERMARK_INVALID`
  results, and that `entity.watermark_column` is the column the source
  updates.

## Fallback audit files

When the audit database is unreachable, fail-soft events are written to
`Files/_framework_fallback/audit/<kind>/*.json` in the Bronze Lakehouse, and
migration failures before the ledger exists go to
`Files/_framework_fallback/schema_migration/`. Review and archive these after
any audit outage. They are the only record of those events.

## Housekeeping

- Delta `OPTIMIZE` and `VACUUM` on Bronze tables, on a schedule (see
  [performance_review.md](performance_review.md)).
- Landing retention through the storage lifecycle policy.
- Audit retention: archive or delete old `audit.activity` rows periodically.
  This is not automated.
