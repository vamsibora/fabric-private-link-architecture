# Fabric Metadata-Driven Bronze Ingestion Framework

## Architecture, Metadata Model, Audit Framework and AI-Agent Build Prompts

---

# 1. Executive Summary

This document defines a metadata-driven Bronze ingestion framework for Microsoft Fabric.

The architecture provides:

- Secure/private engineering workloads
- Optional source landing layer
- Bronze Delta Lakehouse
- Metadata-driven ingestion
- Incremental/watermark processing
- Current-state and historical Bronze patterns
- Environment-based anonymisation
- Central cross-workspace Fabric SQL Database auditing
- Warehouse `control` schema for framework metadata
- Silver and Gold Warehouses
- Reporting workspace and Direct Lake semantic model
- AI-agent prompts for building the Bronze framework from scratch

The architecture deliberately separates:

1. **Landing** — optional raw source persistence
2. **Bronze** — durable source representation in Delta
3. **Control metadata** — configuration that drives the framework
4. **Audit** — operational execution history

The key architectural principle is:

> **Control metadata belongs in the Warehouse `control` schema. Audit history belongs in the central cross-workspace Fabric SQL Database.**

---

# 2. Overall Architecture

```text
                           ON-PREMISES
       ┌──────────────────────┬──────────────────────┐
       │                      │                      │
   SQL Server              Other DBs              APIs/SDKs
       │                      │                      │
       └──────────────────────┴──────────────────────┘
                              │
                       Gateway / VNet
                              │
                              ▼
                 ┌──────────────────────────┐
                 │ Fabric Pipeline / Copy   │
                 │ Job                      │
                 └────────────┬─────────────┘
                              │
                    Metadata-driven
                     Bronze ingestion
                              │
              ┌───────────────┴────────────────┐
              │                                │
              │ LANDING_ENABLED = TRUE         │
              │                                │
              ▼                                │
    ┌──────────────────────────────┐            │
    │ Azure Storage Account        │            │
    │ Landing                      │            │
    │                              │            │
    │ /source_system/              │            │
    │    /table_name/              │            │
    │       /table_name_           │            │
    │        yyyymmddhhss.json     │            │
    └──────────────┬───────────────┘            │
                   │                            │
                   ▼                            │
          Bronze Framework                      │
                   │                            │
              ┌────┴─────┐                      │
              │           │                      │
              ▼           ▼                      │
        Bronze Staging   Bronze Delta             │
        Lakehouse        Lakehouse                │
              │           │                      │
              └────┬──────┘                      │
                   │                             │
                   │ LANDING_ENABLED = FALSE     │
                   │                             │
                   ▼                             │
        Bronze Staging Tables                    │
        in Bronze Lakehouse                      │
        TRUNCATE before each run                 │
                   │                             │
                   └──────────────┬──────────────┘
                                  │
                                  ▼
                       ┌─────────────────────┐
                       │ Bronze Framework    │
                       │                     │
                       │ Validate            │
                       │ Deduplicate         │
                       │ Anonymise           │
                       │ Hash                │
                       │ Audit columns       │
                       │ MERGE / APPEND      │
                       │ Watermark            │
                       └──────────┬──────────┘
                                  │
                                  ▼
                    ┌────────────────────────┐
                    │ PRIVATE ENGINEERING    │
                    │ WORKSPACE              │
                    │                        │
                    │ Bronze Lakehouse       │
                    │        ↓               │
                    │ Silver Warehouse       │
                    │        ↓               │
                    │ Gold Warehouse         │
                    │                        │
                    │ control schema         │
                    │ ├ metadata             │
                    │ ├ watermark            │
                    │ ├ mappings              │
                    │ └ framework config     │
                    └───────────┬────────────┘
                                │
                                ▼
                 ┌──────────────────────────────┐
                 │ CROSS-WORKSPACE AUDIT        │
                 │ FABRIC SQL DATABASE          │
                 │                              │
                 │ audit.run                    │
                 │ audit.entity_run             │
                 │ audit.activity               │
                 │ audit.error                  │
                 │ audit.validation             │
                 └──────────────────────────────┘
                                │
                                ▼
                    ┌────────────────────────┐
                    │ REPORTING WORKSPACE    │
                    │                        │
                    │ Reporting Lakehouse    │
                    │        ↓               │
                    │ Direct Lake Semantic   │
                    │ Model                  │
                    │        ↓               │
                    │ Power BI               │
                    └────────────────────────┘
```

---

# 3. Architectural Components

| Component | Purpose | Persistent |
|---|---|---:|
| Optional Landing | Raw source-file persistence/replay | Configurable |
| Bronze Lakehouse | Durable Delta representation of source data | Yes |
| Warehouse `control` schema | Metadata/configuration/framework state | Yes |
| Central Fabric SQL Database | Cross-workspace operational audit | Yes |
| Silver Warehouse | Cleansed/transformed data | Yes |
| Gold Warehouse | Curated dimensional/fact data | Yes |
| Reporting Workspace | Semantic model and Power BI serving layer | Yes |

---

# 4. On-Premises Data Ingestion

For relational on-premises sources such as SQL Server, use:

```text
SQL Server
    ↓
Gateway / VNet
    ↓
Fabric Pipeline / Copy Job
    ↓
Bronze ingestion process
```

The preferred approach is:

> **Fabric Pipeline / Copy Job → Bronze**

rather than:

> SQL Server → Python → Bronze

Fabric-native Copy Jobs/Pipelines provide:

- Gateway integration
- Incremental/watermark extraction
- Parallel extraction
- Retry handling
- Monitoring
- Scheduling
- Metadata-driven execution
- Native SQL connectivity

Python should be used when it adds value, such as:

- LogicMonitor SDK
- ServiceNow API
- REST APIs
- Custom extraction logic
- Complex source-specific processing

---

# 5. Optional Landing Layer

The landing layer is configurable.

The framework must support:

```text
landing_enabled = TRUE
landing_enabled = FALSE
```

The setting should preferably be configurable at the source/entity level.

Example:

| Source | Table | Landing Enabled |
|---|---|---:|
| SQLServer | Customer | TRUE |
| SQLServer | Product | FALSE |
| ServiceNow | Incident | TRUE |
| LogicMonitor | Alert | FALSE |

This means the framework can use a landing layer only where it provides value.

---

# 6. Landing Enabled = TRUE

When:

```text
landing_enabled = TRUE
```

the Fabric Copy Job writes raw source data to a Storage Account.

Required format:

```text
<landing_root>/
    <source_system>/
        <table_name>/
            <table_name>_yyyymmddhhss.json
```

Example:

```text
landing/
    SQLServer/
        Customer/
            Customer_202609300812.json
```

Another example:

```text
landing/
    ServiceNow/
        Incident/
            Incident_202609300813.json
```

The timestamp must be generated by the ingestion framework/pipeline.

Recommended logical template:

```text
{landing_root}/
{source_system}/
{table_name}/
{table_name}_{run_timestamp}.json
```

Where:

```text
run_timestamp = yyyyMMddHHss
```

---

# 7. Purpose of the Optional Landing Layer

Landing is useful when there is a requirement for:

- Raw source archive
- Replay
- Source recovery
- Reprocessing without reconnecting to the source
- Troubleshooting
- Regulatory retention
- External raw-data sharing
- Decoupling source extraction from Bronze processing

However, landing should not be mandatory.

If none of these requirements exist, the framework can operate without a Storage Account landing layer.

---

# 8. Landing Enabled = FALSE

When:

```text
landing_enabled = FALSE
```

the Copy Job writes directly into staging tables in the Bronze Lakehouse.

Example:

```text
Bronze Lakehouse

staging
    ├── customer
    ├── product
    └── order
```

The staging table is ephemeral.

Before each run:

```text
TRUNCATE staging.customer
```

Then:

```text
Copy Job
    ↓
Bronze staging.customer
    ↓
Bronze Framework
    ↓
bronze.customer
```

The framework must ensure that staging is cleared before a new load.

---

# 9. Important Staging Rule

When:

```text
landing_enabled = FALSE
```

only the **staging table** is truncated.

The final Bronze table is not automatically truncated.

Correct:

```text
STAGING

TRUNCATE
   ↓
COPY
   ↓
PROCESS


BRONZE

MERGE / APPEND
   ↓
Persistent data
```

This allows incremental and historical Bronze processing.

---

# 10. Bronze Lakehouse

Bronze is based on Delta tables in a Fabric Lakehouse.

Bronze provides the durable technical representation of source data.

Typical framework-controlled technical columns:

```text
bronze_created_datetime
bronze_updated_datetime
bronze_run_id
bronze_source_system
bronze_source_table
bronze_record_hash
```

Additional columns may include:

```text
bronze_ingestion_datetime
bronze_is_current
bronze_valid_from
bronze_valid_to
bronze_record_status
```

depending on the Bronze strategy.

Source business columns should remain recognizable and should not be unnecessarily renamed.

---

# 11. Bronze Staging

If MERGE/upsert processing is required, use staging.

Example:

```text
Bronze Lakehouse

staging
    └── customer

bronze
    └── customer
```

Flow:

```text
Copy Job
    ↓
staging.customer
    ↓
Bronze Framework
    ├── Validate
    ├── Deduplicate
    ├── Anonymise
    ├── Calculate hash
    ├── Add technical columns
    └── MERGE / APPEND
           ↓
      bronze.customer
```

The framework, rather than the Copy Job, controls the final Bronze table processing.

---

# 12. Bronze Framework

The Bronze Framework is reusable metadata-driven processing logic.

It is not synonymous with `MERGE`.

The framework determines:

- Which entity to process
- Source connection
- Source table
- Target table
- Load type
- Primary key
- Watermark column
- Whether MERGE is required
- Whether history is required
- Change detection
- Anonymisation
- Validation
- Hashing
- Technical audit columns
- Error handling
- Run ID
- Logging
- Watermark updates
- Retry behaviour

`MERGE` is simply one operation performed by the framework.

---

# 13. Bronze Framework Processing Flow

```text
                  Framework Run
                       │
                       ▼
                Load Metadata
                       │
                       ▼
                Create Run ID
                       │
                       ▼
             Resolve Entity Config
                       │
                       ▼
          ┌────────────────────────┐
          │ Determine Landing Mode │
          └───────────┬────────────┘
                      │
             ┌────────┴────────┐
             │                 │
          TRUE                FALSE
             │                 │
             ▼                 ▼
       Storage Account    Bronze staging
          Landing             table
             │                 │
             └────────┬────────┘
                      ▼
                   Validate
                      │
                      ▼
                 Deduplicate
                      │
                      ▼
                 Anonymise
                      │
                      ▼
                Calculate Hash
                      │
                      ▼
             Add Technical Columns
                      │
                      ▼
            MERGE / APPEND / REPLACE
                      │
                      ▼
              Validate Result
                      │
                      ▼
              Update Watermark
                      │
                      ▼
               Audit Completion
```

---

# 14. Metadata-Driven Configuration

The framework must process hundreds of tables using metadata rather than creating a dedicated implementation for every entity.

Example configuration:

| Configuration | Customer |
|---|---|
| Source System | SQLServer |
| Source Schema | dbo |
| Source Table | Customer |
| Target Schema | bronze |
| Target Table | Customer |
| Load Type | Incremental |
| Primary Key | CustomerId |
| Watermark | ModifiedDate |
| Merge Required | Yes |
| History Required | Yes |
| Change Detection | Hash |
| Landing Enabled | TRUE |
| Anonymisation | Environment dependent |

---

# 15. Incremental Loading

Large tables should use incremental extraction whenever possible.

Example:

```text
SQL Server
     ↓
WHERE ModifiedDate > LastWatermark
     ↓
Landing / Staging
     ↓
Bronze Framework
     ↓
Change Detection / MERGE
```

Watermark state is stored in metadata:

```text
source_system
source_table
watermark_column
last_successful_watermark
```

The watermark must only advance after the entity has completed successfully.

Correct:

```text
Extract
  ↓
Process
  ↓
Validate
  ↓
Commit
  ↓
Update watermark
```

Incorrect:

```text
Extract
  ↓
Update watermark
  ↓
Process
```

---

# 16. Current-State Bronze

For entities where only the latest state is required:

```text
Copy
  ↓
Staging
  ↓
Validate
  ↓
Deduplicate
  ↓
MERGE
  ↓
Bronze current-state table
```

Example:

```text
bronze.customer
```

contains the current representation of each customer.

---

# 17. Historical Bronze

For entities that must preserve source history:

```text
Copy
  ↓
Landing / Staging
  ↓
Change Detection
  ↓
Append Changed Records
  ↓
Bronze Historical Table
```

Example:

```text
CustomerId | Address    | ModifiedDate
-----------|------------|-------------
100        | Birmingham | 2026-09-01
100        | Solihull   | 2026-09-10
```

Do not overwrite historical records if doing so would destroy information required downstream.

---

# 18. Bronze vs SCD Type 2

Bronze should not implement business SCD Type 2 logic.

Bronze represents source history.

Silver/Gold implements business dimensional history.

Example:

```text
BRONZE

CustomerId | Address    | ModifiedDate
-----------|------------|-------------
100        | Birmingham | 01-Sep
100        | Solihull   | 10-Sep
```

Gold:

```text
CustomerKey | CustomerId | Address    | EffectiveFrom | EffectiveTo | IsCurrent
------------|------------|------------|---------------|-------------|----------
1001        | 100        | Birmingham | 01-Sep        | 09-Sep      | 0
1057        | 100        | Solihull   | 10-Sep        | 9999-12-31  | 1
```

---

# 19. Environment-Based Anonymisation

Anonymisation should occur as data enters Bronze when required.

Example:

```text
PROD
    ↓
Real source data

UAT
    ↓
Anonymised data

DEV
    ↓
Anonymised data
```

The framework determines anonymisation from metadata.

Example:

```text
Customer.Email
    anonymisation_rule = HASH_EMAIL

Customer.Phone
    anonymisation_rule = MASK_PHONE
```

This prevents sensitive production data from flowing unrestricted into lower environments.

---

# 20. Warehouse Control Schema

Create a dedicated:

```sql
control
```

schema in the Warehouse.

The control schema contains configuration and runtime control metadata.

It does not contain detailed operational audit history.

Recommended structure:

```text
control
│
├── source_system
├── source_connection
├── entity
├── entity_column
├── load_configuration
├── watermark
├── anonymisation_rule
├── validation_rule
├── column_mapping
├── pipeline_configuration
└── framework_configuration
```

---

# 21. `control.source_system`

Recommended columns:

```text
source_system_id
source_system_name
source_type
description
active_flag
connection_reference
created_datetime
updated_datetime
```

Examples:

```text
SQLSERVER
SERVICENOW
LOGICMONITOR
ORACLE
POSTGRES
```

---

# 22. `control.entity`

This is the central metadata table.

Recommended columns:

```text
entity_id
source_system_id
source_schema
source_table
target_schema
target_table
active_flag
load_type
landing_enabled
history_required
merge_required
primary_key
watermark_column
watermark_type
change_detection_method
anonymisation_required
```

Example:

```text
entity_id             = 101
source_system         = SQLSERVER
source_schema         = dbo
source_table          = Customer
target_schema         = bronze
target_table          = Customer
load_type             = INCREMENTAL
landing_enabled       = TRUE
history_required      = TRUE
merge_required        = FALSE
primary_key           = CustomerId
watermark_column      = ModifiedDate
change_detection      = HASH
```

---

# 23. `control.entity_column`

Column-level metadata:

```text
entity_column_id
entity_id
source_column
target_column
ordinal_position
target_data_type
nullable_flag
primary_key_flag
watermark_flag
hash_flag
anonymisation_flag
anonymisation_rule_id
active_flag
```

This allows the framework to dynamically generate:

- SELECT lists
- Hash expressions
- Merge conditions
- Validation rules
- Anonymisation
- Target definitions
- Technical column handling

---

# 24. `control.watermark`

Runtime watermark state should be separate from entity configuration.

```text
entity_id
last_successful_watermark
last_run_id
updated_datetime
```

Only successful runs may update the watermark.

---

# 25. `control.anonymisation_rule`

Example:

```text
anonymisation_rule_id
rule_name
rule_type
algorithm
parameters
active_flag
```

Possible rule types:

```text
HASH
MASK
REDACT
TOKENIZE
NULLIFY
CUSTOM
```

---

# 26. `control.validation_rule`

Example:

```text
validation_rule_id
entity_id
rule_name
rule_type
column_name
expression
severity
failure_action
active_flag
```

Possible validations:

```text
PRIMARY_KEY_NULL
DUPLICATE_PRIMARY_KEY
COLUMN_MISSING
DATA_TYPE_MISMATCH
ROW_COUNT_ANOMALY
WATERMARK_INVALID
MANDATORY_COLUMN_NULL
```

---

# 27. Environment Configuration

Create:

```text
control.framework_configuration
```

Example:

| Configuration | DEV | UAT | PROD |
|---|---:|---:|---:|
| Landing enabled | Configurable | Configurable | Configurable |
| Anonymisation | TRUE | TRUE | FALSE |
| Audit enabled | TRUE | TRUE | TRUE |
| Fail on validation error | TRUE | TRUE | TRUE |
| Max parallel entities | 5 | 10 | 20 |

Environment behaviour must be configuration-driven rather than hard-coded.

---

# 28. Central Cross-Workspace Fabric SQL Database

Create a dedicated Fabric SQL Database for audit.

Example:

```text
Audit / Operations Workspace

Fabric SQL Database
    └── BronzeFrameworkAudit
```

All ingestion workspaces write audit records to this central database.

Example:

```text
Private Engineering Workspace
            │
            │
            ├──────────────┐
            │              │
            ▼              ▼
       Bronze run      Bronze run
            │              │
            └──────┬───────┘
                   ▼
       Central Fabric SQL Database
              BronzeFrameworkAudit
```

The audit database is therefore cross-workspace.

---

# 29. Audit Database Schema

Create:

```sql
audit
```

Recommended tables:

```text
audit.run
audit.entity_run
audit.activity
audit.error
audit.validation
```

Optionally:

```text
audit.watermark
audit.pipeline_run
audit.file
```

---

# 30. `audit.run`

One record per framework execution.

```text
run_id
framework_name
workspace_id
workspace_name
environment
start_datetime
end_datetime
status
trigger_type
trigger_name
initiated_by
total_entities
successful_entities
failed_entities
```

Example status values:

```text
STARTED
RUNNING
SUCCEEDED
PARTIAL_SUCCESS
FAILED
CANCELLED
```

---

# 31. `audit.entity_run`

One record per entity/table processed.

```text
run_id
entity_run_id
source_system
source_schema
source_table
target_table
load_type
landing_enabled
start_datetime
end_datetime
status
source_row_count
staging_row_count
inserted_row_count
updated_row_count
deleted_row_count
rejected_row_count
bronze_row_count
watermark_before
watermark_after
```

This is the primary operational audit table.

It allows operations teams to answer:

> What happened to Customer during run 12345?

---

# 32. `audit.activity`

Detailed framework events:

```text
run_id
entity_run_id
activity_id
activity_type
activity_name
start_datetime
end_datetime
status
message
rows_affected
duration_ms
```

Examples:

```text
COPY_STARTED
COPY_COMPLETED
VALIDATION_STARTED
VALIDATION_COMPLETED
DEDUPLICATION_COMPLETED
ANONYMISATION_COMPLETED
HASH_COMPLETED
MERGE_STARTED
MERGE_COMPLETED
WATERMARK_UPDATED
```

---

# 33. `audit.error`

Centralised errors:

```text
run_id
entity_run_id
error_id
error_datetime
error_stage
error_code
error_message
source_system
source_table
target_table
is_retryable
stack_trace
```

The framework should write the original error information wherever possible without losing the source-system error code.

---

# 34. `audit.validation`

Data-quality results:

```text
run_id
entity_run_id
validation_id
validation_rule
validation_type
status
expected_value
actual_value
failed_row_count
error_message
```

Example:

```text
PRIMARY_KEY_NULL
DUPLICATE_PRIMARY_KEY
WATERMARK_INVALID
COLUMN_MISSING
DATA_TYPE_MISMATCH
ROW_COUNT_ANOMALY
```

---

# 35. Why Audit Is Separate from Control

Do not create:

```text
Warehouse
    control
       ├── metadata
       ├── watermark
       ├── audit_run
       ├── audit_error
       └── audit_activity
```

Instead:

```text
Warehouse
    control
       ├── source_system
       ├── entity
       ├── entity_column
       ├── watermark
       ├── anonymisation_rule
       └── validation_rule


Central SQL Database
    audit
       ├── run
       ├── entity_run
       ├── activity
       ├── error
       └── validation
```

Architectural principle:

> **Control metadata defines what should happen. Audit data records what actually happened.**

---

# 36. End-to-End Processing

## Landing Enabled

```text
SQL Server
    ↓
Fabric Copy Job
    ↓
Storage Account
/source_system/table/table_yyyymmddhhss.json
    ↓
Bronze Framework
    ↓
Validation
    ↓
Deduplication
    ↓
Anonymisation
    ↓
Hash
    ↓
MERGE / APPEND
    ↓
Bronze Delta
    ↓
Update Watermark
    ↓
Central Audit SQL Database
```

## Landing Disabled

```text
SQL Server
    ↓
Fabric Copy Job
    ↓
TRUNCATE Bronze staging table
    ↓
Bronze staging table
    ↓
Bronze Framework
    ↓
Validation
    ↓
Deduplication
    ↓
Anonymisation
    ↓
Hash
    ↓
MERGE / APPEND
    ↓
Bronze Delta
    ↓
Update Watermark
    ↓
Central Audit SQL Database
```

---

# 37. Failure Handling

The framework should use transaction-like control around the logical processing stages.

Example:

```text
Run Started
    ↓
Entity Started
    ↓
Extract
    ↓
Stage
    ↓
Validate
    ↓
Transform
    ↓
Bronze Commit
    ↓
Validation
    ↓
Watermark Commit
    ↓
Entity Success
```

If Bronze processing fails:

```text
Entity Failed
    ↓
Do NOT update watermark
    ↓
Write audit.error
    ↓
Mark run/entity failed
```

If the landing file was successfully created but Bronze processing failed:

```text
Landing file remains available
        ↓
Replay / reprocess
```

This is one of the major benefits of making landing configurable.

---

# 38. Retry Strategy

Metadata should support:

```text
max_retry_count
retry_delay_seconds
retry_enabled
```

Recommended retry classification:

### Retryable

```text
Transient network error
Gateway timeout
Temporary service failure
Capacity/transient connectivity issue
```

### Non-retryable

```text
Schema mismatch
Invalid metadata
Missing primary key
Invalid SQL
Data type incompatibility
Invalid transformation
```

The framework should not blindly retry every error.

---

# 39. Parallel Processing

The framework should support controlled parallel entity execution.

Example:

```text
Run 100
   │
   ├── Customer
   ├── Product
   ├── Supplier
   ├── Order
   ├── Invoice
   └── ...
```

Maximum parallelism should be configurable:

```text
control.framework_configuration
    max_parallel_entities
```

The AI implementation should avoid uncontrolled fan-out.

---

# 40. Framework Run ID

Every framework execution must create a unique:

```text
run_id
```

Every entity execution must have:

```text
entity_run_id
```

These identifiers must propagate to:

- Landing metadata
- Bronze technical columns
- Audit tables
- Framework logs
- Error records
- Watermark updates

Example:

```text
run_id = 20260930-081200-ABC123

entity_run_id = 20260930-081201-XYZ001
```

---

# 41. Recommended Bronze Technical Columns

For every Bronze table:

```text
bronze_run_id
bronze_created_datetime
bronze_updated_datetime
bronze_source_system
bronze_source_table
bronze_record_hash
```

For historical Bronze entities:

```text
bronze_valid_from
bronze_valid_to
bronze_is_current
```

Only add historical columns where the configured Bronze behaviour requires them.

---

# 42. Framework Components

The implementation should be divided into reusable components.

```text
Bronze Framework
│
├── Configuration Loader
├── Run Manager
├── Source Extract Manager
├── Landing Manager
├── Staging Manager
├── Schema Manager
├── Validation Engine
├── Deduplication Engine
├── Anonymisation Engine
├── Hash Engine
├── Merge Engine
├── Historical Load Engine
├── Watermark Manager
├── Audit Manager
├── Error Manager
└── Orchestrator
```

---

# 43. Suggested Fabric Artefacts

The AI agent should create:

```text
Workspace
│
├── Bronze Lakehouse
│
├── Warehouse
│   └── control schema
│
├── Bronze Framework Notebook(s)
│
├── Metadata Initialisation Notebook
│
├── Bronze Orchestration Notebook
│
├── Fabric Pipeline(s)
│
└── Supporting configuration
```

Central audit area:

```text
Audit Workspace
│
└── Fabric SQL Database
    └── BronzeFrameworkAudit
        └── audit schema
```

Optional:

```text
Azure Storage Account
└── landing
```

---

# 44. AI-Agent Build Requirements

The AI agent must build the framework from scratch.

It should not create a bespoke pipeline for every table.

The implementation must be:

- Metadata-driven
- Idempotent
- Configurable
- Environment-aware
- Auditable
- Restartable
- Testable
- Modular
- Secure
- Capable of incremental processing

The agent must first create the framework and then demonstrate it using a sample entity.

---

# 45. AI-Agent Prompt 1 — Architecture Builder

Use the following prompt as the master prompt.

```text
You are a Microsoft Fabric data platform architect and senior Fabric data engineer.

Build a complete metadata-driven Bronze ingestion framework from scratch.

The framework must support:

1. Fabric Pipelines / Copy Jobs as the preferred extraction mechanism for relational sources.
2. Bronze Lakehouse using Delta tables.
3. Optional Storage Account landing layer controlled by metadata.
4. Bronze staging tables when landing is disabled.
5. Metadata-driven incremental ingestion.
6. Current-state Bronze processing.
7. Historical Bronze processing.
8. MERGE processing where configured.
9. Append/change-capture processing where history is required.
10. Environment-based anonymisation.
11. Column-level metadata.
12. Primary-key validation.
13. Duplicate detection.
14. Hash-based change detection.
15. Watermark processing.
16. Centralised cross-workspace audit in a Fabric SQL Database.
17. Warehouse control schema containing framework metadata.
18. Run-level and entity-level audit.
19. Retry and error handling.
20. Restartability and idempotency.

Do not create a bespoke implementation for every table.

Build a reusable framework capable of processing hundreds of entities.

Architecture:

Source systems
    ↓
Fabric Pipeline / Copy Job
    ↓
Optional Storage Account landing
    ↓
Bronze staging
    ↓
Bronze Framework
    ↓
Bronze Delta
    ↓
Silver Warehouse
    ↓
Gold Warehouse

Control metadata:

Warehouse
    └── control schema

Audit:

Central cross-workspace Fabric SQL Database
    └── audit schema

The framework must keep control metadata and audit history separate.

Control metadata defines what should happen.

Audit records what actually happened.

Before writing implementation code:

1. Inspect the target Fabric environment.
2. Identify available Lakehouse, Warehouse and SQL Database objects.
3. Identify connection constraints.
4. Identify notebook execution capabilities.
5. Identify pipeline/copy job capabilities.
6. State any Fabric feature limitations discovered.

Then produce an implementation plan.

Do not silently assume that a Fabric feature exists.

Where Fabric has multiple implementation options, choose the simplest production-supported option and document the reason.

All implementation must be modular and metadata-driven.
```

---

# 46. AI-Agent Prompt 2 — Create Control Metadata

```text
Implement the Warehouse metadata layer for the Bronze Framework.

Create a dedicated schema:

control

Create the following tables:

control.source_system
control.source_connection
control.entity
control.entity_column
control.watermark
control.anonymisation_rule
control.validation_rule
control.column_mapping
control.pipeline_configuration
control.framework_configuration

Requirements:

- Use surrogate numeric identifiers where appropriate.
- Add active/inactive flags.
- Add created_datetime and updated_datetime.
- Add environment-aware configuration where required.
- Add appropriate primary and unique keys.
- Add referential integrity logically through metadata.
- Avoid hard-coded entity-specific logic.
- Support multiple source systems.
- Support multiple schemas and tables.
- Support composite primary keys.
- Support multiple watermark types.
- Support landing_enabled at entity level.
- Support current-state and historical Bronze modes.
- Support configurable anonymisation.
- Support configurable validation rules.

Generate DDL first.

Then generate representative seed metadata.

Include at least:

SQLServer / dbo.Customer
SQLServer / dbo.Product
SQLServer / dbo.Order

Use realistic metadata values.

Document each metadata field.
```

---

# 47. AI-Agent Prompt 3 — Create Central Audit Database

```text
Build the central cross-workspace audit database for the Bronze Framework.

Use a Fabric SQL Database.

Create schema:

audit

Create:

audit.run
audit.entity_run
audit.activity
audit.error
audit.validation

Requirements:

- Every framework execution has run_id.
- Every entity execution has entity_run_id.
- Support multiple Fabric workspaces.
- Store workspace_id and workspace_name.
- Store environment.
- Store start/end timestamps.
- Store execution status.
- Store source and target information.
- Store row counts.
- Store watermark before and after.
- Store landing_enabled.
- Store activity-level events.
- Store validation results.
- Store errors.
- Support retryable/non-retryable errors.
- Make tables suitable for operational reporting.

Create indexes appropriate for:

run_id
entity_run_id
source_system
source_table
status
start_datetime
environment

Create sample audit records.

Do not place operational audit tables in the Warehouse control schema.
```

---

# 48. AI-Agent Prompt 4 — Implement Landing Manager

```text
Implement a reusable Landing Manager.

The Landing Manager must read:

landing_enabled

from control.entity.

When landing_enabled = TRUE:

Write source data to the configured Storage Account using:

{landing_root}/
{source_system}/
{table_name}/
{table_name}_{yyyyMMddHHss}.json

Requirements:

- Generate the timestamp from the framework run.
- Include run_id in framework metadata.
- Do not overwrite an existing landing file.
- Support replay.
- Return the landing path to the orchestrator.
- Write landing activity to central audit.
- Capture file size.
- Capture row count where available.
- Capture creation timestamp.
- Capture source/entity identifiers.

When landing_enabled = FALSE:

Do not write to the Storage Account.

Instead:

1. Truncate the configured Bronze staging table.
2. Copy the source data into staging.
3. Return the staging table to the orchestrator.

Make the implementation idempotent and restartable.
```

---

# 49. AI-Agent Prompt 5 — Implement Staging Manager

```text
Implement the Bronze Staging Manager.

When landing_enabled = FALSE:

1. Resolve target staging table from metadata.
2. Validate that the staging object exists.
3. Truncate staging before extraction.
4. Execute the Copy Job/source extraction.
5. Record source row count.
6. Record staging row count.
7. Record audit activity.
8. Fail safely if truncation or extraction fails.

When landing_enabled = TRUE:

The staging manager must consume the configured landing file and load it into Bronze staging before framework processing.

Do not truncate the final Bronze table.

Staging is ephemeral.

Bronze is persistent.

Support both:

landing → staging → Bronze

and:

source → staging → Bronze
```

---

# 50. AI-Agent Prompt 6 — Implement Validation Engine

```text
Implement a metadata-driven validation engine.

Validation rules are stored in:

control.validation_rule

Support at minimum:

- Primary key null
- Duplicate primary key
- Mandatory column null
- Missing column
- Data type mismatch
- Invalid watermark
- Row-count anomaly
- Custom validation expression

Each validation must return:

validation_id
rule_name
status
failed_row_count
expected_value
actual_value
error_message

Validation failures must support configurable actions:

WARN
FAIL
IGNORE

Write every validation result to:

central audit SQL Database
audit.validation

Do not hard-code validations for specific entities.
```

---

# 51. AI-Agent Prompt 7 — Implement Anonymisation Engine

```text
Implement a metadata-driven anonymisation engine.

Use:

control.anonymisation_rule

and:

control.entity_column

to determine which columns require anonymisation.

Support:

HASH
MASK
REDACT
TOKENIZE
NULLIFY
CUSTOM

Environment configuration must determine whether anonymisation is enabled.

Example:

DEV = anonymise
UAT = anonymise
PROD = preserve source values

The framework must never hard-code specific customer columns.

Anonymisation must occur before the final Bronze write.

Record the anonymisation activity in the central audit database.

Never log sensitive source values in the audit database.
```

---

# 52. AI-Agent Prompt 8 — Implement Hash and Change Detection

```text
Implement metadata-driven record hashing.

Use control.entity_column to determine columns participating in change detection.

Requirements:

- Produce deterministic hashes.
- Handle NULL consistently.
- Handle data type conversion consistently.
- Use a documented hashing algorithm.
- Avoid including framework-generated audit columns in the business hash.
- Support composite business keys.
- Support hash comparison between source/staging and Bronze.

Return:

record_hash

Use the hash for:

- Change detection
- Historical Bronze processing
- Avoiding unnecessary updates
- Incremental processing

Document the exact canonicalisation rules used before hashing.
```

---

# 53. AI-Agent Prompt 9 — Implement Bronze MERGE Engine

```text
Implement a reusable Bronze MERGE engine.

The engine must use metadata from:

control.entity
control.entity_column

Determine:

- Target table
- Primary key
- Change detection
- Update columns
- Insert columns
- Technical columns

Support:

1. Current-state MERGE.
2. Historical append/change capture.
3. Composite keys.
4. Hash-based change detection.

Do not implement SCD Type 2 business logic.

Bronze history is source history.

SCD Type 2 belongs downstream in Silver/Gold.

The MERGE engine must:

- Be idempotent.
- Return inserted count.
- Return updated count.
- Return deleted count where supported.
- Return rejected count.
- Write audit activity.
- Fail without advancing the watermark.
```

---

# 54. AI-Agent Prompt 10 — Implement Watermark Manager

```text
Implement a metadata-driven Watermark Manager.

Use:

control.watermark

Requirements:

1. Read the last successful watermark.
2. Pass it to source extraction.
3. Capture the new maximum watermark.
4. Do not update the stored watermark until Bronze processing succeeds.
5. Update the watermark atomically with the successful entity completion state where technically possible.
6. Record old and new watermark values in central audit.
7. Support datetime, numeric and string watermark types where appropriate.

Failure scenario:

If Bronze processing fails:

- preserve previous watermark
- mark entity failed
- write audit.error
- allow the entity to be retried

Never advance the watermark on failure.
```

---

# 55. AI-Agent Prompt 11 — Implement Audit Manager

```text
Implement the central Audit Manager.

Every framework run must:

1. Create audit.run.
2. Create audit.entity_run for every entity.
3. Write activity records.
4. Write validation records.
5. Write errors.
6. Complete the run with an overall status.

The Audit Manager must write to the central Fabric SQL Database.

Required correlation:

run_id
entity_run_id
activity_id
error_id
validation_id

Audit must work across multiple Fabric workspaces.

Capture:

workspace_id
workspace_name
environment
pipeline_name
notebook_name
source_system
source_table
target_table

Do not log sensitive source values.

Audit writes must not cause a successful Bronze load to become failed solely because a non-critical audit operation failed.

However, critical audit failures must be configurable.
```

---

# 56. AI-Agent Prompt 12 — Implement Orchestrator

```text
Implement the Bronze Framework Orchestrator.

The orchestrator must:

1. Start framework run.
2. Generate run_id.
3. Load active entities from control.entity.
4. Determine eligible entities.
5. Process entities using controlled parallelism.
6. For each entity:
   - create entity_run
   - resolve metadata
   - determine landing mode
   - extract data
   - stage data
   - validate
   - deduplicate
   - anonymise
   - calculate hash
   - process Bronze
   - validate Bronze result
   - update watermark
   - write audit
7. Continue processing independent entities after an entity failure where configured.
8. Complete the framework run.
9. Return overall status and summary.

Support:

SUCCESS
PARTIAL_SUCCESS
FAILED
CANCELLED

Do not advance watermarks for failed entities.
```

---

# 57. AI-Agent Prompt 13 — Build Fabric Pipelines

```text
Build the Fabric Pipeline/Copy Job orchestration required for the Bronze Framework.

Use metadata rather than creating one pipeline per table.

The pipeline must:

1. Read active entity metadata.
2. Resolve source configuration.
3. Resolve landing_enabled.
4. Execute source extraction.
5. Write either:
   - Storage Account landing, or
   - Bronze staging
6. Invoke Bronze Framework processing.
7. Capture run_id and entity_run_id.
8. Support controlled parallelism.
9. Handle retries.
10. Write central audit information.

Do not duplicate business logic between the pipeline and notebook.

Pipelines should orchestrate.

The Bronze Framework should process.

Metadata should determine behaviour.
```

---

# 58. AI-Agent Prompt 14 — Build Sample End-to-End Entity

```text
Demonstrate the completed framework using:

SQLServer
dbo.Customer

Configuration:

load_type = INCREMENTAL
primary_key = CustomerId
watermark_column = ModifiedDate
landing_enabled = TRUE
history_required = TRUE
change_detection_method = HASH
anonymisation = environment dependent

Demonstrate:

1. Initial load.
2. Incremental load.
3. New records.
4. Changed records.
5. Duplicate input.
6. Validation failure.
7. Processing failure.
8. Retry.
9. Watermark preservation after failure.
10. Successful watermark update.
11. Central audit records.
12. Landing file creation.
13. Bronze historical result.

Then demonstrate the same entity with:

landing_enabled = FALSE

Verify that:

- staging is truncated
- source data is loaded into staging
- Bronze processing succeeds
- no landing file is created
- audit records correctly show landing_enabled = FALSE
```

---

# 59. AI-Agent Prompt 15 — Testing Framework

```text
Create a comprehensive test framework for the Bronze ingestion architecture.

Test:

1. Initial full load.
2. Incremental load.
3. No-change incremental load.
4. New records.
5. Updated records.
6. Deleted records where supported/configured.
7. Duplicate source records.
8. Null primary keys.
9. Invalid data types.
10. Invalid watermark.
11. Landing enabled.
12. Landing disabled.
13. Landing file replay.
14. Bronze MERGE failure.
15. Validation failure.
16. Network/transient failure.
17. Retry.
18. Watermark rollback/preservation.
19. Anonymisation.
20. Hash change detection.
21. Historical Bronze.
22. Composite primary key.
23. Multiple concurrent entities.
24. Partial run failure.
25. Complete framework failure.
26. Audit database failure.

For every test verify:

- Expected Bronze state
- Expected staging state
- Expected landing state
- Expected watermark
- Expected audit records
- Expected run status
- Expected entity status

Produce a test results report.
```

---

# 60. AI-Agent Prompt 16 — Security Review

```text
Perform a security review of the complete Bronze Framework.

Review:

- Fabric workspace permissions
- Lakehouse permissions
- Warehouse permissions
- Storage Account permissions
- Fabric SQL Database permissions
- Gateway connectivity
- Secret/credential handling
- Environment separation
- Sensitive data handling
- Anonymisation
- Audit security
- Least privilege
- Network boundaries
- Private workspace configuration
- Reporting workspace separation

Do not place credentials in:

- notebooks
- metadata tables
- pipeline parameters
- source code
- audit tables

Use secure connection references/secrets.

Identify any Fabric networking limitations affecting cross-workspace access.

Produce:

1. Findings
2. Risk
3. Recommended remediation
4. Required configuration
```

---

# 61. AI-Agent Prompt 17 — Performance Review

```text
Perform a performance review of the Bronze Framework.

Assess:

- Copy Job parallelism
- Gateway throughput
- Source query performance
- Incremental extraction
- Landing file size
- JSON processing
- Bronze Delta writes
- MERGE performance
- Partitioning strategy
- File sizing
- Small-file management
- Concurrent entity processing
- Audit write volume
- SQL Database audit performance
- Warehouse metadata query performance

Do not recommend partitioning automatically.

Only introduce partitioning where query/write characteristics justify it.

Identify:

- Bottlenecks
- Scaling limits
- Recommended defaults
- Configuration parameters
```

---

# 62. AI-Agent Prompt 18 — Operational Monitoring

```text
Build operational monitoring for the Bronze Framework.

The monitoring solution must allow operators to answer:

1. What runs are executing?
2. Which entities failed?
3. Which entities succeeded?
4. What was the source row count?
5. What was the Bronze row count?
6. Which entities have not loaded recently?
7. What is the latest watermark?
8. Which entities repeatedly fail?
9. Which validations are failing?
10. Which pipelines are slow?
11. Which sources have extraction problems?
12. Which landing files were created?
13. Which entities have stale watermarks?

Use the central audit SQL Database as the operational source.

Create suitable views for:

audit.vw_run_summary
audit.vw_entity_status
audit.vw_recent_errors
audit.vw_watermark_status
audit.vw_validation_failures
audit.vw_load_performance
```

---

# 63. AI-Agent Prompt 19 — Documentation

```text
Generate complete technical documentation for the implemented Bronze Framework.

Create:

01_Architecture.md
02_Metadata_Model.md
03_Bronze_Framework.md
04_Landing_Design.md
05_Audit_Design.md
06_Incremental_Loading.md
07_Historical_Loading.md
08_Anonymisation.md
09_Validation.md
10_Error_Handling.md
11_Deployment.md
12_Operations.md
13_Troubleshooting.md
14_Testing.md

Include:

- Architecture diagrams
- Metadata definitions
- Processing flows
- Error flows
- Configuration examples
- Deployment dependencies
- Security model
- Operational procedures
- Recovery procedures
```

---

# 64. AI-Agent Prompt 20 — Deployment and CI/CD

```text
Prepare the Bronze Framework for:

DEV
UAT
PROD

The implementation must separate:

- Environment configuration
- Metadata
- Secrets
- Connection references
- Workspace identifiers
- Storage Account paths
- Audit database references

Do not hard-code DEV/UAT/PROD values into framework code.

Create deployment documentation covering:

1. Infrastructure creation.
2. Metadata deployment.
3. Notebook deployment.
4. Pipeline deployment.
5. Warehouse object deployment.
6. Audit SQL Database deployment.
7. Storage configuration.
8. Environment configuration.
9. Security configuration.
10. Smoke tests.
11. Rollback.

Ensure deployment is repeatable and idempotent.
```

---

# 65. AI-Agent Prompt 21 — Final Acceptance Test

```text
Act as the solution architect performing final acceptance testing.

Review the complete Bronze Framework against these requirements:

ARCHITECTURE
- Optional landing layer
- Bronze Lakehouse
- Warehouse control schema
- Central Fabric SQL Database audit
- Metadata-driven execution

LANDING
- landing_enabled TRUE
- landing_enabled FALSE
- Correct path format
- JSON output
- Replay capability

BRONZE
- Current-state
- Historical
- MERGE
- Append/change capture
- Technical columns
- Hash

INCREMENTAL
- Watermark
- Safe watermark update
- Retry
- Restartability

DATA QUALITY
- Primary key
- Duplicate detection
- Mandatory fields
- Schema validation
- Configurable validation actions

SECURITY
- Environment anonymisation
- No secrets in metadata
- No sensitive data in logs

AUDIT
- Run
- Entity
- Activity
- Error
- Validation
- Cross-workspace logging

OPERATIONS
- Retry
- Failure recovery
- Monitoring
- Performance

For every requirement return:

PASS
FAIL
PARTIAL

For failures provide:

- Evidence
- Root cause
- Required change

Do not mark a feature PASS merely because code exists.

Verify that it actually works end-to-end.
```

---

# 66. Recommended Implementation Sequence

The AI agent should build the framework in this order:

```text
Phase 1
Architecture
    ↓
Phase 2
Control schema
    ↓
Phase 3
Central audit SQL Database
    ↓
Phase 4
Bronze Lakehouse/staging
    ↓
Phase 5
Metadata loader
    ↓
Phase 6
Landing Manager
    ↓
Phase 7
Staging Manager
    ↓
Phase 8
Validation Engine
    ↓
Phase 9
Anonymisation Engine
    ↓
Phase 10
Hash Engine
    ↓
Phase 11
Bronze MERGE/History Engine
    ↓
Phase 12
Watermark Manager
    ↓
Phase 13
Audit Manager
    ↓
Phase 14
Orchestrator
    ↓
Phase 15
Fabric Pipelines/Copy Jobs
    ↓
Phase 16
Testing
    ↓
Phase 17
Security
    ↓
Phase 18
Performance
    ↓
Phase 19
Monitoring
    ↓
Phase 20
Deployment
```

---

# 67. Final Target Architecture

The final architecture is:

```text
                         SOURCE SYSTEMS
                              │
                              ▼
                   Fabric Pipeline / Copy
                              │
                              ▼
                    Metadata Configuration
                              │
                    ┌─────────┴─────────┐
                    │                   │
                    ▼                   ▼
             LANDING ENABLED       LANDING DISABLED
                    │                   │
                    ▼                   ▼
             Storage Account       Bronze Staging
               JSON Files           Lakehouse
                    │                   │
                    └─────────┬─────────┘
                              │
                              ▼
                    BRONZE FRAMEWORK
                              │
             ┌────────────────┼────────────────┐
             │                │                │
             ▼                ▼                ▼
         Validation      Anonymisation       Hash
             │                │                │
             └────────────────┼────────────────┘
                              │
                              ▼
                     MERGE / APPEND
                              │
                              ▼
                       BRONZE DELTA
                              │
                              ▼
                    SILVER WAREHOUSE
                              │
                              ▼
                     GOLD WAREHOUSE
                              │
                              ▼
                  REPORTING WORKSPACE
                              │
                              ▼
                    DIRECT LAKE MODEL
                              │
                              ▼
                       POWER BI


CONTROL PLANE
───────────────────────────────────────────────

Warehouse
   │
   └── control
       ├── source_system
       ├── source_connection
       ├── entity
       ├── entity_column
       ├── watermark
       ├── anonymisation_rule
       ├── validation_rule
       ├── column_mapping
       └── framework_configuration


AUDIT PLANE
───────────────────────────────────────────────

Central Fabric SQL Database
   │
   └── audit
       ├── run
       ├── entity_run
       ├── activity
       ├── error
       └── validation
```

---

# 68. Key Architectural Principles

1. **Landing is optional.**
2. `landing_enabled` is metadata-driven.
3. Landing files use:
   ```text
   source_system/table_name/table_name_yyyymmddhhss.json
   ```
4. When landing is disabled, Bronze staging tables are truncated before each run.
5. The final Bronze table is not truncated merely because landing is disabled.
6. Bronze is persistent Delta data.
7. Staging is ephemeral.
8. Control metadata lives in the Warehouse `control` schema.
9. Audit history lives in the central cross-workspace Fabric SQL Database.
10. `MERGE` is an operation, not the framework itself.
11. Incremental processing uses watermarks where available.
12. Watermarks only advance after successful processing.
13. Bronze can preserve source history.
14. Business SCD Type 2 logic belongs downstream.
15. Anonymisation can be environment-dependent.
16. Pipelines orchestrate; the Bronze Framework processes.
17. Metadata determines entity behaviour.
18. Every execution has a `run_id`.
19. Every entity execution has an `entity_run_id`.
20. The framework must be idempotent and restartable.
21. Errors must be centrally auditable.
22. Sensitive data must never be written into operational audit logs.
23. Environment-specific configuration must not be hard-coded.
24. The framework must support controlled parallelism.
25. The framework should be built once and reused across hundreds of entities.

---

# 69. Target Outcome

The resulting platform is a reusable Bronze ingestion product rather than a collection of individual pipelines.

```text
                METADATA
                   │
                   ▼
             ┌───────────┐
             │ Framework │
             └─────┬─────┘
                   │
       ┌───────────┼───────────┐
       │           │           │
       ▼           ▼           ▼
    Landing     Staging      Direct
       │           │           │
       └───────────┼───────────┘
                   ▼
                 Bronze
                   │
                   ▼
                Silver
                   │
                   ▼
                 Gold
                   │
                   ▼
               Reporting
```

The key result is a **configuration-driven ingestion platform** where adding a new source table primarily means adding metadata rather than developing a new ingestion implementation.

