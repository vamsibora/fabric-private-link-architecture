# 02 — Control metadata in the Warehouse (spec §20–§27, §46, change 3)

```text
Context: 00_master_context.md. Reference implementation: warehouse/ddl/10_control/*,
warehouse/ddl/30_constraints/030_control_security_constraints.sql,
warehouse/programmability/100_control_fn_active_entities.sql, warehouse/metadata/*.

Build the Warehouse metadata layer in schema [control] (lowercase).

DDL (CREATE-once, one table per file, Fabric DW limits):
  00_schemas/001  CREATE SCHEMA [control]
  05_meta/050     control.schema_migration_history
                  (migration_id, script_path, script_category, checksum, status, run_id,
                   duration_ms, error_message, applied_by, created_datetime)
  10_control/010..020, one table per file:
    source_system (source_system_name drives landing paths; bronze_schema)
    source_connection (per-environment references only: fabric_connection_id, gateway_name,
      database_name, auth_type, key_vault_secret_name -- NEVER credentials)
    entity (every spec §22 column, plus staging_schema, staging_table, entity_group,
      processing_priority; primary_key is a comma list for composite keys;
      watermark_type DATETIME|NUMERIC|STRING)
    entity_column (spec §23; target_data_type is a Spark SQL type)
    load_configuration (retry_enabled, max_retry_count, retry_delay_seconds,
      source_query_override with a {watermark} token, source_filter, delete_detection_enabled,
      row_count_anomaly_threshold_pct)
    watermark (runtime state: entity_id, last_successful_watermark VARCHAR canonical,
      last_run_id, last_entity_run_id)
    anonymisation_rule (salt_secret_name = Key Vault secret NAME)
    validation_rule (failure_action FAIL|WARN|IGNORE, validation_stage PRE|POST)
    column_mapping (Spark SQL source_expression per target_column)
    pipeline_configuration, framework_configuration (environment, config_key, config_value)
  30_constraints: PK/UNIQUE/FK, all NOT ENFORCED, added last.
  Every table carries active_flag, created/updated datetime and _by; ids are explicit BIGINTs.

Programmability (repeatable, CREATE OR ALTER):
  control.fn_active_entities(@environment, @entity_group) returns one row per active entity:
  - the resolved source_query: the column list from entity_column, the watermark predicate
    [col] > <literal> (DATETIME -> CAST('...' AS DATETIME2(7)); NUMERIC unquoted; STRING
    quoted), source_filter, or the override with {watermark} replaced;
  - landing_enabled AND the environment's landing_globally_enabled; landing_container;
    landing_folder = <source_system>/<table>;
  - staging target, source_database and the retry settings.

Seed metadata (repeatable, warehouse/metadata/*.sql, one transaction, scoped DELETE by owned
ids + INSERT; the watermark via INSERT ... WHERE NOT EXISTS only):
  SQLServer dbo.Customer   entity 101  INCREMENTAL, landing ON, HISTORY, HASH,
                                       Email/Phone anonymised
  SQLServer dbo.Product    entity 102  INCREMENTAL, landing OFF, MERGE
  SQLServer dbo.Order      entity 103  composite key (OrderId, OrderLineNumber), landing ON, MERGE
  optional: dbo.Territory  entity 104  FULL, MERGE, delete detection
  framework_configuration for DEV/UAT/PROD:
    anonymisation_enabled true/true/false; max_parallel_entities 5/10/20; audit_enabled;
    fail_on_validation_error; continue_on_entity_failure; audit_failure_is_critical;
    landing_globally_enabled; landing_container; landing_lakehouse_path; sql_token_audience;
    audit_sql_token_audience; spark_timezone.
  Document every field and the id ranges in warehouse/metadata/README.md.
  No endpoints, connection strings or Key Vault URIs.

Migration runner: WAREHOUSE target = once roots warehouse/ddl, security/rls; repeatable roots
warehouse/programmability, warehouse/metadata. Ledger: control.schema_migration_history.

Tests (mocked): tests/framework/test_migration_runner.py covers
- order: once roots, then repeatable;
- bootstrap buffering before the ledger exists;
- a repeatable script re-applied on a checksum change;
- checksum drift warned, never re-run.
Add a test that every metadata script inserting into control.watermark uses WHERE NOT EXISTS.

Report: what you could NOT verify live (CREATE OR ALTER FUNCTION, STRING_AGG WITHIN GROUP,
APPLY, and transactions in Fabric DW).
```
