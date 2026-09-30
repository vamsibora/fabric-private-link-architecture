# 04 — Bronze Lakehouse, staging and Schema Manager (spec §10–§11, §41, phase 4)

```text
Context: 00_master_context.md. Reference: notebooks/bronze/schema_manager.py,
fabric_items/notebooks/MetadataInitialisation.Notebook/notebook-content.py.

Build the Schema Manager for a SCHEMA-ENABLED Bronze Lakehouse
(<target_schema>.<table>, e.g. sqlserver.customer, the same layout as the reference
lh_bronze_dev rio.department).

- Bronze table = business columns (entity_column target names/types, in ordinal order) plus
  the technical columns bronze_run_id, bronze_entity_run_id, bronze_created_datetime,
  bronze_updated_datetime, bronze_ingestion_datetime, bronze_source_system,
  bronze_source_table, bronze_record_hash, bronze_record_status.
  Add bronze_valid_from, bronze_valid_to and bronze_is_current ONLY for the HISTORY strategy.
- Staging table staging.<source_system>_<table> is SOURCE-shaped: source column names plus
  _staging_run_id STRING. Mapping and casting happen once, when staging is read.
- Pure builders: CREATE SCHEMA IF NOT EXISTS; CREATE TABLE IF NOT EXISTS ... USING DELTA;
  missing_columns; ALTER TABLE ADD COLUMNS. Evolution is additive only: never drop or retype.
  Quote identifiers with backticks.
- SchemaManager(spark).ensure_entity_tables(entity).
- The MetadataInitialisation notebook (Fabric notebook-content.py format; no hard-coded
  Lakehouse ids in META) runs it for every active entity.

Tests: tests/bronze/test_landing_staging_schema.py covers DDL text, history-only columns, the
source-shaped staging layout, and missing-column detection that ignores case.
Add a Spark test (@pytest.mark.spark) that creates the tables in a local Delta catalog.
Report: what you could NOT verify live (schema-enabled Lakehouse; default-Lakehouse resolution
of schema.table).
```
