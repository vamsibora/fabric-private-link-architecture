# 02 — Metadata Model (Warehouse `control` schema)

The `control` schema holds **configuration and runtime control state only**.
Operational audit history lives in the audit SQL Database
([05_Audit_Design.md](05_Audit_Design.md)).

- DDL is in `warehouse/ddl/10_control/010–020`. Constraints are in
  `30_constraints/030_control_security_constraints.sql`, all `NOT ENFORCED`.
- Seed data is in `warehouse/metadata/`.
- The pipeline-facing function is in `warehouse/programmability/`.

## Fabric Warehouse DDL rules

- Use `VARCHAR` (UTF-8 collation) and `DATETIME2(6)`. Do not use `NVARCHAR`,
  `DATETIME`, `DEFAULT`, `CHECK` or `SEQUENCE`.
- PK/FK/UNIQUE constraints are added afterwards with
  `ALTER TABLE … ADD CONSTRAINT … NOT ENFORCED`. The seed scripts and
  framework code maintain integrity.
- Identifiers are case-sensitive, so the schema is lowercase `control`,
  distinct from the retired `CONTROL`.
- Ids are explicit `BIGINT`s, not `IDENTITY` (see the id ranges below).
- Every table has `active_flag` (except `watermark`),
  `created_datetime`/`created_by` and `updated_datetime`/`updated_by`.

## Tables

### `control.source_system`
| Column | Meaning |
|---|---|
| source_system_id | Explicit id (1–99) |
| source_system_name | e.g. `SQLServer`; used in landing paths `<source_system_name>/<table>/…` and `bronze_source_system` |
| source_type | `SQLSERVER`, `ORACLE`, `POSTGRES`, `SERVICENOW`, `LOGICMONITOR`, `REST`. It picks the extract child pipeline (only SQLSERVER is implemented). |
| description | Free text |
| bronze_schema | Default Bronze Lakehouse schema for the source (e.g. `sqlserver`) |
| connection_reference | Logical name, resolved per environment in `source_connection` |

### `control.source_connection`

Environment-owned: seed scripts only insert missing rows, and never update or delete them.
Operators set `fabric_connection_id`, `gateway_name` and `database_name` per environment
([RB-02](../runbooks/02_metadata_maintenance.md) § Environment connection values).
At run time, `fabric_connection_id` is the Fabric connection GUID the extract Copy binds to
(a parameterised connection), and `database_name` is passed as `source_database`. Both are
returned by `fn_active_entities` (`source_connection_id`, `source_database`).
Per-environment connection **references**. No credential is ever stored.
| Column | Meaning |
|---|---|
| source_connection_id | `<source_system_id>*10 + env` (DEV=1, UAT=2, PROD=3) |
| source_system_id | FK to source_system |
| environment | DEV / UAT / PROD |
| connection_reference | Matches `source_system.connection_reference` |
| fabric_connection_id | Fabric connection GUID (an identifier, not a secret). Seeded `NULL` and set per environment by an operator. |
| gateway_name | On-premises / VNet gateway name |
| database_name | Source database, passed to the Copy activity as `source_database` |
| auth_type | `FABRIC_CONNECTION`, `MANAGED_IDENTITY` or `KEY_VAULT_SECRET` |
| key_vault_secret_name | Secret **name** only |

### `control.entity`
The central table: one row per ingested source table.
| Column | Meaning |
|---|---|
| entity_id | Explicit id (100–9999) |
| source_system_id | FK to source_system |
| source_schema, source_table | Source object. `source_table` is also the landing `<table_name>`. |
| target_schema, target_table | Bronze Lakehouse table |
| staging_schema, staging_table | Staging table, normally `staging.<source>_<table>` |
| entity_group | Optional scheduling filter (pipeline parameter `entity_group`) |
| load_type | `FULL` or `INCREMENTAL` |
| landing_enabled | 1 = Storage Account JSON landing; 0 = copy straight to staging |
| history_required | 1 means the HISTORY write strategy |
| merge_required | 1 means the MERGE write strategy |
| primary_key | Comma-separated; composite keys supported (`OrderId,OrderLineNumber`) |
| watermark_column, watermark_type | Required for INCREMENTAL. Type is `DATETIME`, `NUMERIC` or `STRING`. |
| change_detection_method | `HASH` or `NONE` (HISTORY requires HASH) |
| anonymisation_required | Entity has anonymised columns |
| processing_priority | Lower runs first |

The **write strategy is derived** (`models.EntityConfig.write_strategy`):
`history_required` → HISTORY; else `merge_required` → MERGE; else FULL →
REPLACE; else APPEND.

### `control.entity_column`
| Column | Meaning |
|---|---|
| entity_column_id | `<entity_id>*100 + ordinal` |
| entity_id | FK to entity |
| source_column, target_column | Source name (as staged) and Bronze name |
| ordinal_position | Column order: select list, DDL and hash order |
| source_data_type | Informational |
| target_data_type | Spark SQL type (`INT`, `STRING`, `DECIMAL(18,2)`, `TIMESTAMP`, …) |
| nullable_flag | Informational; use `MANDATORY_COLUMN_NULL` rules to enforce |
| primary_key_flag | Informational; `entity.primary_key` is authoritative |
| watermark_flag | Marks the watermark column |
| hash_flag | Participates in `bronze_record_hash`. PKs and technical columns are always excluded. |
| anonymisation_flag, anonymisation_rule_id | Column is anonymised with that rule |

### `control.load_configuration`
One active row per entity (id = entity_id).
| Column | Meaning |
|---|---|
| retry_enabled, max_retry_count, retry_delay_seconds | Framework-side retry of **retryable** errors, with linear back-off |
| source_query_override | Replaces the generated query. `{watermark}` is substituted with the watermark literal, or a floor value when none exists. |
| source_filter | Extra predicate ANDed onto the generated query |
| delete_detection_enabled | FULL + MERGE only: soft-delete keys missing from the extract |
| row_count_anomaly_threshold_pct | Threshold for `ROW_COUNT_ANOMALY` (NULL = not evaluated) |

### `control.watermark`
Runtime state, one row per entity. It is written **only** by
`WatermarkManager.commit` after a successful Bronze write and
post-validation.
| Column | Meaning |
|---|---|
| entity_id | PK |
| last_successful_watermark | Canonical string: `yyyy-MM-dd HH:mm:ss.ffffff`, a plain decimal, or the string |
| last_run_id, last_entity_run_id | Which run committed it |
| updated_datetime | UTC |

Metadata scripts only `INSERT … WHERE NOT EXISTS` into this table, so they
never reset a watermark.

### `control.anonymisation_rule`
| Column | Meaning |
|---|---|
| anonymisation_rule_id | 1–999 |
| rule_name | e.g. `HASH_EMAIL`, `MASK_PHONE` |
| rule_type | `HASH`, `MASK`, `REDACT`, `TOKENIZE`, `NULLIFY` or `CUSTOM` |
| algorithm | e.g. `EMAIL`, `SHA2_256`, `PARTIAL` |
| parameters | JSON object (see [08_Anonymisation.md](08_Anonymisation.md)) |
| salt_secret_name | Key Vault secret **name** |

### `control.validation_rule`
| Column | Meaning |
|---|---|
| validation_rule_id | `<entity_id>*10 + n` |
| entity_id, rule_name, rule_type | Rule type is one of the eight in [09_Validation.md](09_Validation.md) |
| column_name | Target column, where applicable |
| expression | CUSTOM: a Spark SQL predicate every row must satisfy |
| severity | LOW / MEDIUM / HIGH / CRITICAL |
| failure_action | FAIL / WARN / IGNORE |
| validation_stage | PRE (staged batch) or POST (after the Bronze write) |

### `control.column_mapping`
| Column | Meaning |
|---|---|
| column_mapping_id | `<entity_id>*100 + n` |
| entity_id, target_column | Which target column |
| source_expression | Spark SQL over the staged row, e.g. `CAST(ModifiedDate AS TIMESTAMP)`. It is applied once in `staging_manager.projection`, then cast to `target_data_type`. |

### `control.pipeline_configuration`
Key/value per `(pipeline_name, environment)`, for example `copy_timeout`.

### `control.framework_configuration`
Key/value per environment. The keys and their typed accessors are on
`models.FrameworkConfig`.

| Key | DEV | UAT | PROD | Meaning |
|---|---|---|---|---|
| anonymisation_enabled | true | true | false | Apply anonymisation rules |
| audit_enabled | true | true | true | Write audit |
| fail_on_validation_error | true | true | true | FAIL rules fail the entity |
| max_parallel_entities | 5 | 10 | 20 | Notebook thread pool size |
| continue_on_entity_failure | true | true | true | Keep processing other entities |
| audit_failure_is_critical | false | false | false | Escalate fail-soft audit failures |
| landing_globally_enabled | true | true | true | Environment switch ANDed with entity flag |
| landing_container | landing | landing | landing | ADLS container |
| landing_lakehouse_path | Files/landing | … | … | OneLake shortcut path |
| sql_token_audience | pbi | pbi | pbi | Warehouse token audience |
| audit_sql_token_audience | pbi | pbi | pbi | Audit DB token audience (verify live) |
| spark_timezone | UTC | UTC | UTC | Spark session TZ for hashing and watermarks |

Environment **endpoints** (connection strings, Key Vault URI, workspace ids)
are deliberately **not** stored here. They are pipeline and notebook
parameters.

## `control.fn_active_entities(@environment, @entity_group)`

`warehouse/programmability/100_control_fn_active_entities.sql` is an inline
TVF and the only source for the pipeline Lookup. It returns one row per
active entity with:
- identifiers, target and staging names
- effective `landing_enabled`, `landing_container` and `landing_folder`
  (`<source_system>/<table>`)
- `source_database`, the `last_successful_watermark` and retry settings
- `source_query`: the fully resolved extraction query.

The generated query is `SELECT <[col], … in ordinal order> FROM
[schema].[table]`, plus `WHERE [wm] > <literal>` for INCREMENTAL entities with
a stored watermark, and ANDed with `source_filter` when set. The watermark
literal depends on the type:
- DATETIME: `CAST('…' AS DATETIME2(7))`. This is safe against `datetime`
  columns, which reject more than 3 fractional digits in an implicit cast.
- NUMERIC: unquoted.
- STRING: quoted, with embedded quotes doubled.

The function is a repeatable script (`CREATE OR ALTER`), re-applied when its
checksum changes.

## Seeded example entities

| id | Entity | Load | Landing | Strategy | Notes |
|---|---|---|---|---|---|
| 101 | dbo.Customer | INCREMENTAL (ModifiedDate) | yes | HISTORY | Email `HASH_EMAIL`, Phone `MASK_PHONE`; spec §58 demo entity |
| 102 | dbo.Product | INCREMENTAL | no | MERGE | FAIL rules on ListPrice and ProductName |
| 103 | dbo.Order | INCREMENTAL | yes | MERGE | composite PK (OrderId, OrderLineNumber) |
| 104 | dbo.Territory | FULL | no | MERGE + delete detection | ROW_COUNT_ANOMALY FAIL at 80% |

## Id-range convention (`warehouse/metadata/README.md`)

| Table | Range |
|---|---|
| source_system | 1–99 |
| source_connection | `<source_system_id>*10 + env` (DEV=1, UAT=2, PROD=3) |
| entity | 100–9999 |
| entity_column | `<entity_id>*100 + ordinal` |
| load_configuration | = entity_id |
| anonymisation_rule | 1–999 |
| validation_rule | `<entity_id>*10 + n` |
| column_mapping | `<entity_id>*100 + n` |
| framework_configuration / pipeline_configuration | DEV 1000s, UAT 2000s, PROD 3000s |

Metadata scripts are idempotent. Each deletes then inserts only the ids it
owns, in one transaction. To add a table, add a new numbered script, e.g.
`105_entity_<source>_<table>.sql`.
