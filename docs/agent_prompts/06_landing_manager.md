# 06 — Landing Manager (spec §5–§7, §48, change 1: landing_enabled = TRUE)

```text
Context: 00_master_context.md. Reference: notebooks/bronze/landing_manager.py.

When landing_enabled is TRUE (entity flag AND the environment's landing_globally_enabled):
- Path, relative to the landing container:
  <source_system>/<table_name>/<table_name>_<yyyyMMddHHmmss>.json
  - The timestamp is the RUN timestamp (RunContext.run_timestamp), NOT wall-clock per file.
  - Reject unsafe path segments (anything but [A-Za-z0-9_.-]) and a timestamp that is not
    14 digits.
- Never overwrite:
  - The pipeline checks with Get Metadata (exists) and then Fail(LANDING_FILE_EXISTS).
  - LandingManager.assert_not_exists raises LandingFileExistsError (non-retryable).
- Spark path = <landing_lakehouse_path>/<relative> (default Files/landing). This is a OneLake
  shortcut to the private ADLS container, the reference nb_landing_bronze pattern.
- Record every file in audit.file via audit.usp_log_file: container, path, name, size,
  row_count, created; status CREATED (pipeline), then PROCESSED or FAILED (framework).
- Replay:
  - list_replayable(entity, since_run_ts) returns the entity's files oldest first, with the
    run timestamp parsed from the file name.
  - Replaying a file never re-extracts from the source.
- Return the resolved path to the orchestrator. Prefer the path the pipeline recorded in
  audit.entity_run.landing_path.
When landing_enabled is FALSE, write nothing to the Storage Account (see 07).

Tests: tests/bronze/test_landing_staging_schema.py (fake fs) covers path and name format, the
timestamp guard, unsafe segments, the exists guard, replay ordering and filtering, and the
recorded-path preference.
Report: what you could NOT verify live (the shortcut to a private-endpoint ADLS account;
Get Metadata "exists").
```
