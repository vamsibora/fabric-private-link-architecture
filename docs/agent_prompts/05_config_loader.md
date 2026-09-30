# 05 — Metadata / configuration loader and run identity (spec §14, §40, phase 5)

```text
Context: 00_master_context.md. Reference: notebooks/bronze/models.py, config_loader.py,
run_manager.py.

models.py (frozen dataclasses):
- ColumnConfig, AnonymisationRule, ValidationRule, LoadConfig, EntityConfig, and
  FrameworkConfig (typed accessors plus safe defaults; anonymisation defaults ON).
- EntityConfig derives write_strategy (HISTORY / MERGE / REPLACE / APPEND), hash_columns
  (hash_flag, excluding PKs), watermark_target_column, and target_fqn / staging_fqn.

config_loader.py:
- One SELECT per control table, not per entity.
- assemble_entities() is pure: it merges column_mapping into columns and orders entities by
  processing_priority, then entity_id.
- validate_entity() reports:
  - MERGE/HISTORY without a PK, or a PK that is not an active column;
  - INCREMENTAL without watermark_column/type;
  - HISTORY without HASH change detection;
  - unknown anonymisation_rule_id;
  - an invalid failure_action or stage.
- Invalid metadata raises MetadataError (non-retryable), listing every problem.
- load_framework_config(cursor, environment); load_entities(cursor, entity_ids, entity_group).

run_manager.py:
- new_run_id() -> yyyyMMdd-HHmmss-XXXXXX; run_timestamp() -> yyyyMMddHHmmss (UTC).
- run_timestamp_from_run_id; entity_run_id(run_id, entity_id) -> <run_id>-E<id>.
- RunContext (environment upper-cased, run_timestamp validated; with_notebook_context() reads
  notebookutils.runtime.context and is a no-op outside Fabric).
The pipeline must build the identical run_id and run timestamp from pipeline().TriggerTime.

Tests: tests/bronze/test_config_loader.py and test_models_and_run_manager.py cover id formats, the
deterministic entity_run_id, composite keys, strategy derivation, every validation problem,
mapping merge and ordering, and fetch_dicts over a fake cursor.
Report: what you could NOT verify live.
```
