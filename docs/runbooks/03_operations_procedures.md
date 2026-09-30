# RB-03 — Operations procedures

These are the step-by-step versions of the procedures in
[12_Operations.md](../bronze_framework/12_Operations.md). Symptom-driven
diagnosis is in [13_Troubleshooting.md](../bronze_framework/13_Troubleshooting.md).

Every query here runs in the central audit database unless it says
*Warehouse*. Any procedure that changes data or state in UAT or PROD needs
approval at the time; record it in the change ticket.

## Run the framework

| Goal | How |
|---|---|
| Scheduled run | Schedule `BronzeOrchestrator` with `environment`, `trigger_type = SCHEDULED`, and optionally `entity_group` (one schedule per group). |
| Run one group now | Trigger `BronzeOrchestrator` manually with `entity_group`. |
| Process landing files without the source | Replay (below). |

After any run:
```sql
SELECT * FROM audit.vw_run_summary WHERE run_id = '<run_id>';
SELECT entity_id, source_table, status, source_row_count, inserted_row_count, updated_row_count,
       deleted_row_count, rejected_row_count, watermark_before, watermark_after, error_message
FROM audit.entity_run WHERE run_id = '<run_id>' ORDER BY entity_id;
```

## Replay landing files

Use this when a landing-enabled entity failed after its file was written, or
when Bronze must be rebuilt from retained files.

1. List the replayable files:
   ```sql
   SELECT file_path, file_created_datetime, row_count, status
   FROM audit.vw_landing_files
   WHERE entity_id = <id> AND environment = '<ENV>' AND is_replayable = 1
   ORDER BY file_created_datetime;
   ```
2. Run the `BronzeFramework` notebook manually with these parameters:
   - `mode = REPLAY`
   - `entity_ids = <id>`
   - `replay_run_timestamp = <the 14-digit timestamp from the file name>`, or
     empty for the latest file
   - `environment`, `warehouse_connection_string`, `audit_connection_string`,
     `key_vault_uri`.
3. Check that the new run (`trigger_type = REPLAY`) SUCCEEDED and the file is
   now `PROCESSED`.
4. **MERGE entities: replay files in timestamp order**, oldest first, one
   notebook run per file. Replaying an older file after a newer one moves
   current state backwards. HISTORY entities skip versions that are already
   older than the current one.

## Re-run after a failure

1. Find the cause:
   `SELECT * FROM audit.vw_recent_errors WHERE run_id = '<run_id>';`
   Use `error_stage` and `error_code` with 13_Troubleshooting.
2. Fix it: the source, a connection, the metadata (RB-02) or the code (RB-04).
3. Re-trigger `BronzeOrchestrator` for the entity's group, or replay if the
   entity is landing-enabled and its file exists.

The failed entity's watermark never advanced, and every write strategy is
safe to re-run, so there is no clean-up step.

## Reset a watermark (full reload of an incremental entity)

1. Record the current value in the ticket:
   ```sql
   -- Warehouse
   SELECT * FROM control.watermark WHERE entity_id = <id>;
   ```
2. Check the write strategy. **APPEND entities duplicate rows on reload**:
   truncate the Bronze table first, or delete the reloaded range. MERGE,
   HISTORY and REPLACE are safe.
3. Reset it:
   ```sql
   -- Warehouse
   UPDATE control.watermark
   SET last_successful_watermark = NULL, last_run_id = NULL, last_entity_run_id = NULL,
       updated_datetime = SYSUTCDATETIME()
   WHERE entity_id = <id>;
   ```
4. Run the entity's group. Expect `source_row_count` to cover the whole source
   table.

## Backfill from a point in time

To re-extract changes since a date, without reloading everything, set the
watermark to that date instead of NULL. Use the canonical format for the
entity's `watermark_type`:

| watermark_type | Format | Example |
|---|---|---|
| DATETIME | `yyyy-MM-dd HH:mm:ss.ffffff` (UTC) | `2026-09-01 00:00:00.000000` |
| NUMERIC | plain number | `1048576` |
| STRING | the value | `K-000900` |

```sql
-- Warehouse
UPDATE control.watermark SET last_successful_watermark = '2026-09-01 00:00:00.000000',
       updated_datetime = SYSUTCDATETIME()
WHERE entity_id = <id>;
```

The same caveats apply as for a reset: APPEND duplicates rows. For HISTORY,
versions older than the current Bronze version are skipped, not back-filled.

## Rotate the anonymisation salt (DEV / UAT)

Rotating the salt changes every anonymised value. That changes every hash, so
the next load of each key updates it (MERGE) or writes a new version
(HISTORY). Plan it deliberately.

1. Agree the timing with Bronze consumers in that environment.
2. Add a new version of the Key Vault secret `bronze-anonymisation-salt`.
3. Optionally, reset the watermark of the anonymised entities, so every key
   is re-anonymised in one run rather than only as keys change.
4. Run the entities, and check `audit.vw_entity_status`. `updated_row_count`
   close to the table size is expected.

PROD normally has `anonymisation_enabled = false`, so rotation there has no
data effect. Never copy a salt between environments.

## Landing file already exists (`LANDING_FILE_EXISTS`)

The pipeline refuses to overwrite a landing file. This means two runs got the
same run timestamp (to the second), or a run was re-triggered with the same
run id.
1. Confirm the existing file is in `audit.vw_landing_files`, and check its
   status.
2. If it is `CREATED`/`FAILED`, **replay** it rather than re-extracting.
3. Otherwise just trigger a new pipeline run. It gets a new run timestamp.

Never delete a landing file to "make room". It is the raw record of that
extract.

## Staging integrity error (`STAGING_INTEGRITY`)

Staging held rows from another run, or its row count did not match the copy.
1. Check `audit.activity` for the entity run's `COPY_COMPLETED`
   `rows_affected`.
2. Common causes:
   - Two runs of the same entity overlapped. Avoid overlapping schedules for
     the same `entity_group`.
   - The copy's Overwrite table action did not truncate.
3. Re-run the entity. If it recurs, use the documented alternative: an
   explicit `staging_manager.truncate()` before the copy (RB-04).

## Audit database outage

Behaviour during the outage:
- Runs **fail fast** at start (`AUDIT_UNAVAILABLE`); nothing is loaded
  unaudited.
- Events that fail mid-run are written to
  `Files/_framework_fallback/audit/<kind>/*.json` in the Bronze Lakehouse, and
  the load itself continues.

After recovery:
1. List the fallback files in the Lakehouse, from a notebook:
   `notebookutils.fs.ls("Files/_framework_fallback/audit")`.
2. Review them. Each file has the procedure name, its parameters and the
   `run_id`. Re-apply the important ones (for example `complete_entity_run`)
   by calling the same `audit.usp_*` procedure with those parameters.
3. Move the processed files to `Files/_framework_fallback/archive/<date>/`.
4. Close stuck runs:
   ```sql
   EXEC audit.usp_complete_run @run_id = '<run_id>';   -- derives the status from entity_run rows
   ```

## Add an environment

Follow [RB-01](01_platform_setup.md) completely. Then check that
`020_framework_configuration.sql` and `010_source_system.sql` contain rows for
the new environment code, and add them if they don't (RB-02). If the code is
not DEV/UAT/PROD, extend the id ranges in `warehouse/metadata/README.md`.

## Housekeeping (monthly)

| Task | How |
|---|---|
| Bronze file compaction | Notebook: `OPTIMIZE <schema>.<table>` for large or frequently merged tables (see performance_review.md) |
| Bronze old-file removal | `VACUUM <schema>.<table> RETAIN 168 HOURS`. Keep at least the time-travel window you rely on for rollback. |
| Staging | Nothing to do; it is overwritten every run |
| Landing retention | The storage lifecycle policy. Check it is still applied. |
| Audit growth | Archive or delete `audit.activity` rows older than the agreed retention. Keep `run`, `entity_run`, `error`, `validation` and `file` longer. |
| Fallback files | Should be empty; investigate anything present |
| Metadata health | Run `warehouse/checks/metadata_health_checks.sql` |
