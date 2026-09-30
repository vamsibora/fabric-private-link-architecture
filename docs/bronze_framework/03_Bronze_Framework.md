# 03 — Bronze Framework

The framework is the `notebooks.bronze` Python package. It is shipped as a
wheel in the `CicdFramework` Environment and invoked by the thin
`BronzeFramework` notebook. `MERGE` is one operation it can perform; it is not
the framework itself.

## Entry points (`bootstrap.py`)

```python
framework = build_framework(spark, environment, warehouse_connection_string,
                            audit_connection_string, run_id=..., run_timestamp=...,
                            key_vault_uri=..., pipeline_name=..., pipeline_run_id=...,
                            trigger_type=..., entity_group=..., entity_ids=...)
framework.run_pipeline_mode()          # entities the pipeline reported EXTRACTED
framework.replay(landing_run_timestamp=None, entity_ids=None)   # reprocess landing files
```

`build_framework` does the following:
1. Loads `framework_configuration`, anonymisation rules and active entities
   in one Warehouse connection.
2. Applies `landing_globally_enabled` to every entity.
3. Sets `spark.sql.session.timeZone`.
4. Builds the `RunContext`, adding workspace and notebook identity from
   `notebookutils.runtime.context`.
5. Creates the `AuditManager`, using `audit_sql_token_audience`.
6. Wires every engine into `orchestrator.FrameworkServices`.

If anonymisation is enabled and no `key_vault_uri` is supplied, it fails fast.

## Per-entity processing (`orchestrator._process_once`)

```text
 1 STAGING    landing on : Files/landing/<src>/<tbl>/<tbl>_<ts>.json → staging (overwrite)
              landing off: verify staging only holds this run's rows and matches rowsCopied
 2 WRITE      ensure the Bronze table and technical columns exist
 3 read       staging rows for run_id → project/cast to target columns, add _bronze_ingest_seq
 4 VALIDATION PRE rules → audit.validation; FAIL-action failures stop here
 5 WATERMARK  batch max of the watermark column (BEFORE anonymisation)
 6 VALIDATION deduplicate (rejected_row_count = rows removed)
 7 ANONYMISE  if anonymisation_enabled AND entity.anonymisation_required
 8 HASH       bronze_record_hash + literal technical columns
 9 WRITE      MERGE | HISTORY | APPEND | REPLACE → inserted / updated / deleted
10 VALIDATION POST rules against the Bronze table
11 WATERMARK  commit max(before, batch max); never backwards; only now
12 audit      usp_complete_entity_run SUCCEEDED; landing file → PROCESSED
```

Each step runs inside `_Stage(...)`, which tags any escaping exception with
its stage, so `audit.error.error_stage` is always set.

`process_entity` wraps the chain in `error_manager.with_retry` using
`load_configuration`: only retryable errors are retried, with linear
back-off. On final failure it:
- writes `audit.error`
- completes the entity FAILED with `watermark_after = watermark_before` (the
  watermark is unchanged)
- marks the landing file FAILED, so it stays replayable.

## Run-level orchestration (`orchestrator.run`)

- A `ThreadPoolExecutor(max_workers=min(max_parallel_entities, n))` runs work
  items in priority order. There is no unbounded fan-out.
- `continue_on_entity_failure = false` means the first failure cancels items
  that have not started. They are recorded as `CANCELLED`.
- `rollup_status` mirrors `audit.usp_complete_run`:
  - no failures → `SUCCEEDED`
  - only failures → `FAILED`
  - both → `PARTIAL_SUCCESS`
  - cancellations in an otherwise clean run → `CANCELLED`
- The notebook raises unless the run status is `SUCCEEDED`, so pipeline
  monitoring shows the failure. The audit row already holds the precise
  status.

## Technical columns (`schema_manager.TECHNICAL_COLUMNS`)

| Column | Value |
|---|---|
| bronze_run_id / bronze_entity_run_id | Run identity |
| bronze_created_datetime | First insert (never overwritten by MERGE) |
| bronze_updated_datetime | Last change |
| bronze_ingestion_datetime | This entity run's ingestion instant |
| bronze_source_system / bronze_source_table | Lineage |
| bronze_record_hash | [Hash engine](06_Incremental_Loading.md#change-detection) |
| bronze_record_status | `ACTIVE` or `DELETED` (soft delete) |
| bronze_valid_from / bronze_valid_to / bronze_is_current | HISTORY tables only |

Source business columns keep their names. Schema evolution is **additive**:
missing columns are added with `ALTER TABLE … ADD COLUMNS`, and nothing is
dropped or retyped automatically.

## Write strategies

| Strategy | When | Behaviour | Idempotency |
|---|---|---|---|
| MERGE | `merge_required` | Delta MERGE on the PK. Updates only when the hash differs or the row was soft-deleted. Inserts new keys. Optional soft delete (`whenNotMatchedBySourceUpdate`) for FULL loads. | Same batch twice changes nothing |
| HISTORY | `history_required` | See [07_Historical_Loading.md](07_Historical_Loading.md) | Temporal filter makes a re-run a no-op |
| APPEND | INCREMENTAL, no flags | `overwrite` + `replaceWhere bronze_entity_run_id = '<id>'` | A retry replaces its own earlier attempt |
| REPLACE | FULL, no flags | Full overwrite | Naturally idempotent |

Bronze never implements business SCD Type 2. That belongs in Silver/Gold.
