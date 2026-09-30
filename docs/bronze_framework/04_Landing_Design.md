# 04 — Landing Design

Landing is **optional and metadata-driven**. It is controlled per entity by
`control.entity.landing_enabled`, and per environment by
`framework_configuration.landing_globally_enabled`. The effective value is
`entity AND global`. It is computed in `control.fn_active_entities` for the
pipeline, and in `bootstrap.build_framework` for the notebook.

Use landing when you need a raw archive, replay without reconnecting to the
source, regulatory retention, troubleshooting, or decoupling extraction from
Bronze processing. Otherwise leave it off.

## landing_enabled = TRUE

```text
SQL Server ─ Copy (JsonSink, setOfObjects) ─► ADLS Gen2
   <container>/<source_system>/<table>/<table>_<yyyyMMddHHmmss>.json
   e.g. landing/SQLServer/Customer/Customer_20260930081205.json
                       │  OneLake shortcut  (Files/landing → container)
                       ▼
BronzeFramework: spark.read.json(schema = every source column as STRING)
   → staging.<table> (overwrite) + _staging_run_id → Bronze
```

Path format:

- **container** is `framework_configuration.landing_container` (default
  `landing`), which is the Copy sink `fileSystem`.
- **folder** is `<source_system_name>/<source_table>`
  (`landing_manager.landing_folder`, and `fn_active_entities.landing_folder`).
- **file** is `<source_table>_<run_timestamp>.json`. The timestamp is the
  framework run's `yyyyMMddHHmmss`, taken from `pipeline().TriggerTime`, so
  every file in a run shares it and a file name identifies its run. Minutes
  are included deliberately. The spec's `yyyymmddhhss` would collide within
  the hour.
- Path segments are validated (`[A-Za-z0-9_.-]`, no `.`/`..`), so metadata
  cannot escape the folder.

**Never overwrite.** Before copying, the extract pipeline runs Get Metadata
(`exists`). If the file exists it runs a Fail activity (`LANDING_FILE_EXISTS`),
writes `audit.error`, and sets `entity_run` to FAILED. In the notebook,
`LandingManager.assert_not_exists` enforces the same rule.
`audit.file (file_container, file_path)` is unique.

**Audit.** After a successful copy the pipeline calls:
- `audit.usp_log_file` with status `CREATED`, `dataWritten` bytes and
  `rowsCopied`
- `usp_log_activity COPY_COMPLETED`
- `usp_update_entity_run EXTRACTED` with `landing_path` and
  `source_row_count`.

The framework then marks the file `PROCESSED` on success, or `FAILED` so it
stays replayable.

**Reading.** `StagingManager.load_from_landing` reads with an explicit
all-STRING schema of the entity's source columns. It does not infer the
schema, because JSON omits null fields and inferred types drift between
files. Typing happens once, in `projection()`, through `column_mapping`
expressions and `target_data_type`.

## landing_enabled = FALSE

```text
SQL Server ─ Copy (LakehouseTableSink, tableActionOption = Overwrite,
                   additionalColumns _staging_run_id = run_id) ─► staging.<table>
BronzeFramework: verify staging → Bronze
```

- **Only the staging table is truncated.** Overwrite replaces the table
  contents in one Delta commit. The Bronze table is never truncated.
- `StagingManager.verify` requires every staging row to carry this run's
  `_staging_run_id`, and the count to equal the copy's `rowsCopied`. Any
  mismatch raises `StagingIntegrityError` (non-retryable), so stale data from
  a failed earlier copy is never processed.
- If Overwrite semantics prove unsuitable live, use the documented
  alternative: `StagingManager.truncate()` (`DELETE FROM staging.<t>`) before
  an Append copy.

## Replay

Landing files remain after a Bronze failure. `Framework.replay()` (notebook
`mode = REPLAY`, with an optional `replay_run_timestamp`) does the following:
1. Lists `Files/landing/<src>/<tbl>/` (`LandingManager.list_replayable`,
   oldest first).
2. Picks the requested run's file, or else the latest.
3. Starts a **new** run and entity runs marked `EXTRACTED` with that
   `landing_path`.
4. Processes them normally.

The source is not contacted. `audit.vw_landing_files.is_replayable` lists
`CREATED`/`FAILED` files.

## Storage account

- ADLS Gen2 with a hierarchical namespace, one `landing` container per
  environment, behind a **private endpoint**.
- Fabric reaches it through a Fabric connection (Copy sink) and a OneLake
  shortcut (Spark read). Use trusted workspace access or the workspace
  identity, not account keys. See [security_review.md](security_review.md).
- Retention and lifecycle management are storage-account policies. They are
  not implemented by the framework.
