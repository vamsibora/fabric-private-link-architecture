# Fabric Data Platform Automation — Product Blueprint

**Working Product Name:** Fabric Data Platform Automation Platform (FDPA)  
**Version:** 1.0  
**Date:** 15 September 2026

## 1. Product Definition

> **Configure your data platform once. The product generates, deploys, executes and monitors the Fabric implementation.**

The product sits above Microsoft Fabric as a **metadata-driven control plane**.

```text
                    FDPA PRODUCT
                 +-------------------+
                 | Configuration     |
                 | Metadata          |
                 | Templates         |
                 | Rules             |
                 | Governance        |
                 | Monitoring        |
                 +---------+---------+
                           |
                    Fabric REST APIs
                           |
                           v
              +-------------------------+
              |    MICROSOFT FABRIC     |
              |       DATA PLANE        |
              +-------------------------+
              | Pipelines / Copy Jobs   |
              | Lakehouses              |
              | Warehouses              |
              | Notebooks / Spark      |
              | Semantic Models        |
              | OneLake                |
              +-------------------------+
```

**Key principle:** Your product = Control Plane; Microsoft Fabric = Data Plane.

---

## 2. Product Modules

| Module | Purpose | MVP |
|---|---|---:|
| Project Management | Manage data-platform projects | Yes |
| Source Discovery | Discover databases, tables and columns | Yes |
| Metadata Manager | Define ingestion/transformation rules | Yes |
| Ingestion Engine | Generate Fabric ingestion | Yes |
| Bronze Engine | Standardise raw data | Yes |
| Transformation Engine | Silver processing | Later |
| Data Quality Engine | Validation framework | Later |
| Gold/Analytics Engine | Facts and dimensions | Later |
| Operations & Monitoring | Runs, errors and metrics | Yes |
| Deployment & Governance | DEV/UAT/PROD | Later |

---

## 3. Project Management

```text
Project
 |
 +-- Environments
 |    +-- DEV
 |    +-- UAT
 |    +-- PROD
 |
 +-- Data Sources
 +-- Entities
 +-- Transformations
 +-- Data Quality Rules
 +-- Security Rules
 +-- Fabric Workspaces
```

The project is the primary isolation boundary for configuration, generated artefacts and operational history.

---

## 4. Source Discovery

Automatically discover where supported:

- Databases
- Schemas
- Tables
- Columns
- Data types
- Primary keys
- Foreign keys
- Candidate watermark columns
- Nullable columns
- Row counts where practical

Example:

```text
Database
  |
  +-- Schema
       |
       +-- Customer
       |    +-- CustomerID
       |    +-- Name
       |    +-- Email
       |    +-- ModifiedDate
       |
       +-- Product
       +-- Order
```

Discovery should create metadata candidates rather than blindly making design decisions. Users can override detected keys, watermarks and mappings.

---

## 5. Metadata Manager

The metadata layer is the **brain of the platform**.

```text
Entity
 |
 +-- Source
 +-- Target
 +-- Primary Key
 +-- Load Strategy
 +-- Watermark
 +-- History
 +-- Change Detection
 +-- Anonymisation
 +-- Validation
 +-- Lookup
 +-- Transformation
```

Example:

```yaml
entity: Customer

source:
  system: CRM
  schema: dbo
  table: Customer

target:
  layer: bronze
  table: Customer

load:
  type: incremental
  watermark: ModifiedDate

history:
  type: SCD2

anonymisation:
  enabled: true

quality:
  reject_null_primary_key: true
```

---

## 6. Metadata Database Schema

For the first product version, **Azure SQL Database** is a strong control-plane metadata store.

### Core tables

```text
product_project
product_environment
product_user
product_role

data_source
data_source_connection

entity
entity_column
entity_key
entity_relationship

load_configuration
watermark_configuration
history_configuration

transformation
transformation_step

lookup_definition
validation_rule
anonymisation_rule

fabric_workspace
fabric_item

deployment
deployment_item

pipeline_run
entity_run
data_quality_result
error_log
```

### product_project

```text
project_id
project_name
description
customer_id
status
created_datetime
created_by
```

### product_environment

```text
environment_id
project_id
environment_name
environment_type
fabric_workspace_id
is_active
```

Values:

```text
DEV
UAT
PROD
```

### data_source

```text
data_source_id
project_id
source_name
source_type
connection_id
database_name
server_name
schema_name
active_flag
```

Potential source types:

```text
SQL_SERVER
REST_API
SFTP
FILE
FABRIC
LOGICMONITOR
```

### entity

```text
entity_id
project_id
data_source_id
entity_name
source_schema
source_table
target_schema
target_table
target_layer
load_type
active_flag
```

### entity_column

```text
entity_column_id
entity_id
column_name
source_data_type
target_data_type
ordinal_position
nullable
is_business_key
is_watermark
is_sensitive
```

---

## 7. Load Configuration

```text
load_configuration
------------------
entity_id
load_type
watermark_column
last_successful_watermark
merge_required
deduplicate
parallel_group
batch_size
retry_count
```

Possible strategies:

```text
FULL
INCREMENTAL
CDC
APPEND
MERGE
API
FILE
```

Persist the last successful watermark only after successful processing.

---

## 8. History Configuration

```text
history_configuration
---------------------
entity_id
history_type
change_detection_type
hash_columns
effective_from_column
effective_to_column
current_flag_column
```

Values:

```text
CURRENT
SCD1
SCD2
SOURCE_HISTORY
```

Recommended responsibility:

- Bronze preserves source information/change evidence.
- Silver implements business history and SCD preparation.
- Gold exposes business-friendly SCD dimensions.

---

## 9. Data Quality Schema

```text
validation_rule
----------------
validation_rule_id
entity_id
column_name
rule_type
rule_expression
severity
failure_action
threshold
active_flag
```

Rule types:

```text
NOT_NULL
UNIQUE
REGEX
RANGE
LOOKUP
REFERENTIAL_INTEGRITY
CUSTOM_SQL
```

---

## 10. Anonymisation Schema

```text
anonymisation_rule
------------------
rule_id
entity_id
column_name
strategy
environment
salt_reference
enabled
```

Strategies:

```text
MASK
HASH
DETERMINISTIC_HASH
SYNTHETIC
NULLIFY
```

Example:

```text
Email
DEV  -> HASH
UAT  -> HASH
PROD -> NONE
```

Anonymisation should happen during Bronze loading for environments where source data must be protected. Secrets and salts should be held in Azure Key Vault rather than stored directly in metadata.

---

## 11. Fabric Artefact Registry

```text
fabric_item
-----------
fabric_item_id
project_id
environment_id
item_type
item_name
fabric_workspace_id
fabric_item_id
source_template_id
deployment_status
last_deployed_datetime
```

Example:

```text
Logical Entity:
Customer

Fabric Items:

Pipeline:
PL_Bronze_Customer

Notebook:
NB_Silver_Customer

Lakehouse:
LH_Bronze

Warehouse:
WH_Silver

Table:
bronze.Customer

Table:
silver.Customer
```

---

## 12. Ingestion Engine

```text
Metadata
   |
   v
Generation Engine
   |
   +--> Pipeline definition
   +--> Copy configuration
   +--> Bronze table definition
   +--> Metadata registration
   |
   v
Fabric REST API
   |
   v
Fabric
```

Use Fabric-native ingestion capabilities wherever practical rather than building a separate data-transfer engine.

Responsibilities:

- Full load
- Incremental load
- Watermark handling
- Retry
- Parallel execution
- RunId propagation
- Schema validation
- Source-to-target mapping
- Staging
- MERGE/APPEND
- Operational logging

---

## 13. Bronze Engine

```text
                 Source
                    |
                    v
             Fabric Copy Job
                    |
                    v
             Bronze Staging
                    |
          +---------+---------+
          |         |         |
       Validate   Hash    Anonymise
          |         |         |
          +---------+---------+
                    |
                    v
             MERGE / APPEND
                    |
                    v
             Bronze Delta
```

Generated objects:

```text
LH_Bronze
    |
    +-- Tables
    |     +-- customer
    |     +-- product
    |     +-- order
    |
    +-- _staging
    |
    +-- framework
          +-- run
          +-- entity_run
          +-- errors
```

**Bronze Framework != MERGE**

- Bronze Framework = reusable metadata-driven processing/orchestration.
- MERGE = one operation the framework may use to update a target.

Recommended Bronze columns:

```text
bronze_created_datetime
bronze_updated_datetime
bronze_run_id
bronze_source_system
bronze_source_table
bronze_record_hash
```

Practical pattern:

```text
Source
  ↓
Copy
  ↓
_staging
  ↓
Validate / Hash / Anonymise
  ↓
MERGE
  ↓
Bronze
```

---

## 14. Transformation Engine

Support three levels.

### Level 1 — Standard

```text
Rename
Cast
Trim
Null handling
Derived columns
Deduplication
```

### Level 2 — SQL

```text
Stored procedure
SQL view
SQL transformation
```

### Level 3 — Custom

```text
Notebook
Spark
Custom transformation
```

Example:

```text
Entity
  |
  v
Framework
  |
  +-- Validation
  +-- Lookup
  +-- Standard transformation
  |
  v
Custom Stored Procedure
  |
  v
Transformed Dataset
  |
  v
Framework
  |
  v
Silver Table
```

---

## 15. Data Quality Engine

```text
Bronze
  |
  v
DQ Engine
  |
  +---- PASS ----> Silver
  |
  +---- WARNING -> Silver + warning
  |
  +---- REJECT --> Reject table
  |
  +---- FAIL ----> Pipeline failure
```

Track:

```text
rule_id
entity
column
rule_type
severity
status
failed_count
run_id
```

Outcomes:

```text
PASS
WARNING
REJECT
FAIL
```

---

## 16. Gold Engine

```text
                Silver
                  |
       +----------+----------+
       |          |          |
    Customer    Product     Order
       |          |          |
       +----------+----------+
                  |
                  v
             Gold Model
                  |
       +----------+----------+
       |          |          |
 FactSales  DimCustomer DimProduct
```

Support:

```text
Generate Dimension
Generate SCD2 Dimension
Generate Fact
Generate Aggregation
```

---

## 17. Operations & Monitoring

### Dashboard

```text
Today's Runs

Total Runs          124
Successful          117
Failed                4
Running               3

Rows Processed    42.8M
```

### Entity view

```text
Customer     SUCCESS    250K
Product      SUCCESS     80K
Order        SUCCESS    4.2M
Invoice      FAILED     1.1M
```

### Run details

```text
Run ID
Pipeline
Entity
Start
End
Duration
Rows read
Rows inserted
Rows updated
Rows rejected
Status
Error
```

---

## 18. Error Handling

Standardise:

- Structured error capture
- Failed entity identification
- Error messages
- Retry
- Retry count
- Pipeline status
- Entity status
- Reprocessing
- Failed-record capture where appropriate

Example:

```text
Pipeline Run
  |
  +-- Customer       SUCCESS
  +-- Product        SUCCESS
  +-- Order          FAILED
  |                    |
  |                    +-- Retry
  |
  +-- Invoice        SUCCESS
```

Entity-level status should be maintained separately from overall run status so one independent failure does not necessarily block unrelated entities.

---

## 19. Fabric REST API Layer

Use a dedicated Fabric Adapter rather than scattering REST calls throughout the application.

```text
Product API
     |
     v
Fabric Adapter
     |
     +-- Workspace Service
     +-- Item Service
     +-- Pipeline Service
     +-- Lakehouse Service
     +-- Warehouse Service
     +-- Notebook Service
     +-- Semantic Model Service
     +-- Deployment Service
```

The adapter should handle:

- Authentication
- API versioning
- Pagination
- Long-running operations
- Polling
- Retry
- Throttling/backoff
- Error normalisation
- Fabric item IDs
- Definition payloads

### Important API areas

| Capability | Product use |
|---|---|
| Fabric REST API | Main automation interface |
| Workspace APIs | Create/list/manage workspaces |
| Item management APIs | Create/update/delete supported Fabric items |
| Definition APIs | Generate and deploy supported item definitions |
| Data Pipeline APIs | Generate ingestion/orchestration pipelines |
| Lakehouse APIs | Create/manage Lakehouses and supported table operations |
| Notebook APIs | Create/update/execute notebooks |
| Semantic Model APIs | Create/update semantic models |
| Deployment Pipeline APIs | Promote Fabric content between environments |

Fabric REST APIs support automation, permissions/scopes, throttling, long-running operations and pagination. Definition-based item APIs are particularly important for programmatic artefact generation.

---

## 20. Generated Fabric Artefacts

Given:

```text
Customer
Product
Order
```

Generate:

```text
Workspace
|
+-- Lakehouse
|   +-- LH_Bronze
|
+-- Warehouse
|   +-- WH_Silver
|   +-- WH_Gold
|
+-- Pipelines
|   +-- PL_Customer
|   +-- PL_Product
|   +-- PL_Order
|
+-- Notebooks
|   +-- NB_Customer
|   +-- NB_Order
|
+-- Semantic Model
|   +-- SM_Reporting
|
+-- Framework tables
    +-- run
    +-- entity_run
    +-- error
    +-- data_quality
```

Not every entity needs every artefact. Generation should be rule-driven.

---

## 21. Artefact Generation Strategy

Use a **Template Library** rather than dynamically generating all raw code.

```text
Template Library
       |
       +-- Bronze Pipeline Template
       +-- Incremental Pipeline Template
       +-- SCD2 Template
       +-- DQ Template
       +-- Lookup Template
       +-- Silver SQL Template
       +-- Gold Dimension Template
       +-- Gold Fact Template
       +-- Notebook Template
```

Metadata fills the template:

```text
Template
   +
Metadata
   |
   v
Generated Fabric Definition
```

Generation flow:

```text
Metadata
   |
   v
Validation
   |
   v
Template Selection
   |
   v
Definition Generator
   |
   v
Fabric API Adapter
   |
   v
Fabric Artefacts
   |
   v
Artefact Registry
```

---

## 22. UI Screens

### Dashboard

```text
Projects
Sources
Entities
Runs
Failures
Deployments
```

### Project

```text
ABC Data Platform

DEV     UAT     PROD

Sources
Entities
Pipelines
Data Quality
Security
Deployments
```

### Add Data Source

```text
Source Type
[ SQL Server ]

Server
Database
Authentication

[Test Connection]

[ Discover ]
```

### Entity Discovery

```text
dbo.Customer        ✓
dbo.Product         ✓
dbo.Order           ✓
dbo.Invoice         □

[ Add Selected Entities ]
```

### Entity Configuration

```text
Customer

Primary Key:
[ CustomerID ]

Load Type:
[ Incremental ]

Watermark:
[ ModifiedDate ]

History:
[ SCD2 ]

Anonymisation:
[ Enabled ]

[ Save ]
```

### Transformation Designer

```text
Customer
   |
   +-- Trim Name
   +-- Validate Email
   +-- Lookup Country
   +-- Hash Email
   +-- SCD2
```

### Generate

```text
Generate Platform

✓ Bronze
✓ Silver
✓ Gold
✓ Pipelines
✓ Data Quality
□ Semantic Model

[ Generate ]
```

### Deployment

```text
DEV
 |
 | Validate
 v
UAT
 |
 | Approval
 v
PROD

[ Deploy ]
```

### Operations

```text
Pipeline Runs

Customer      SUCCESS
Product       SUCCESS
Order         FAILED
Invoice       RUNNING
```

---

## 23. Deployment Architecture

### Enterprise/customer-hosted model

```text
                    Microsoft Entra ID
                           |
                           v
                   +---------------+
                   |   Product UI  |
                   +-------+-------+
                           |
                           v
                   +---------------+
                   |  Product API  |
                   +-------+-------+
                           |
            +--------------+---------------+
            |              |               |
            v              v               v
       Azure SQL       Key Vault       Service Bus
       Metadata         Secrets        Async Jobs
            |                              |
            +--------------+---------------+
                           |
                           v
                   Fabric REST APIs
                           |
            +--------------+---------------+
            |              |               |
            v              v               v
          DEV             UAT             PROD
        Fabric          Fabric          Fabric
```

### Initial deployment

```text
Frontend
   |
Azure App Service / Static Web App
   |
.NET Product API
   |
   +--> Azure SQL
   +--> Key Vault
   +--> Fabric APIs
```

Introduce Service Bus/Azure Functions later for asynchronous and long-running operations.

---

## 24. Security Architecture

Use Microsoft Entra ID.

```text
User
 |
 v
Entra ID
 |
 v
Product
 |
 v
Fabric
```

Maintain:

```text
Tenant
Customer
Project
User
Role
Permission
Environment
```

Roles:

```text
Platform Admin
Project Admin
Data Engineer
Data Analyst
Operations
Viewer
```

Principles:

- No credentials in source code.
- Use Key Vault for secrets.
- Use least-privilege Fabric permissions.
- Isolate customer/project configuration.
- Audit configuration and deployment changes.
- Use environment-specific security boundaries.
- Treat production deployment as a controlled operation.

---

## 25. Fabric Authentication

Support two principal patterns.

### Interactive/delegated access

Use user delegated permissions for:

- Initial setup
- Interactive discovery
- User-driven configuration
- Testing connections

### Application identity

Use a service principal or managed identity where supported for:

- Automated generation
- Deployment
- Background jobs
- Scheduled operations
- Monitoring

Exact permissions should be validated against the Fabric API being invoked because scopes and tenant settings vary by operation.

---

## 26. MVP Backlog

### Epic 1 — Product Foundation

- Create project
- Create environment
- User authentication
- Basic RBAC

### Epic 2 — Source Connections

- SQL Server connection
- Test connection
- Secure credentials
- Connection management

### Epic 3 — Discovery

- Discover databases
- Discover schemas
- Discover tables
- Discover columns
- Discover primary keys
- Candidate watermark detection

### Epic 4 — Metadata

- Entity configuration
- Column mappings
- Load configuration
- Watermark configuration

### Epic 5 — Fabric Workspace

- Select/create workspace
- Register workspace
- Fabric item registry

### Epic 6 — Bronze Generation

- Create Bronze Lakehouse
- Create staging structures
- Create target tables
- Generate audit columns

### Epic 7 — Pipeline Generation

- Generate Copy Pipeline
- Incremental logic
- MERGE logic
- Retry configuration
- Scheduling

### Epic 8 — Anonymisation

- Sensitive column identification
- Hash
- Mask
- Environment-specific rules

### Epic 9 — Execution

- Start pipeline
- Monitor pipeline
- Retrieve status
- Capture run information

### Epic 10 — Monitoring

- Run dashboard
- Entity dashboard
- Error dashboard
- Run history

### Epic 11 — Deployment

- DEV configuration
- UAT configuration
- PROD configuration
- Basic deployment workflow

### Epic 12 — Product Hardening

- Logging
- Audit
- API throttling
- Retry
- Security
- Error handling
- Automated tests

---

## 27. MVP User Journey

```text
1. Create Project

2. Connect SQL Server

3. Discover tables

4. Select:
       Customer
       Product
       Order

5. Configure:
       PK
       Watermark
       Incremental
       Anonymisation

6. Select:
       DEV Fabric Workspace

7. Click:
       Generate

8. Product creates:
       Lakehouse
       Tables
       Pipelines
       Metadata

9. Click:
       Run

10. Monitor:
       Customer     SUCCESS
       Product      SUCCESS
       Order        SUCCESS
```

### MVP success criterion

A customer can onboard a SQL Server database and generate a functioning Fabric Bronze ingestion implementation without manually building the framework artefacts.

---

## 28. Phased Implementation Plan

### Phase 0 — Architecture & Prototype

**Duration: 2–4 weeks**

Build:

- Product architecture
- Metadata model
- Fabric API adapter
- Authentication
- One SQL Server connection
- One Fabric workspace

Proof:

```text
SQL Server
   ↓
Product
   ↓
Fabric Pipeline
   ↓
Bronze Lakehouse
```

**Exit criterion:** The product automatically creates and runs one Fabric ingestion pipeline.

### Phase 1 — MVP Ingestion Platform

**Duration: 6–10 weeks**

Build:

- Project management
- SQL Server connections
- Source discovery
- Metadata management
- Bronze generation
- Incremental loading
- MERGE
- Audit columns
- RunId
- Logging
- Monitoring
- Basic anonymisation

**Deliverable:** A customer can onboard a SQL Server database without manually creating the Fabric ingestion framework.

### Phase 2 — Transformation Platform

**Duration: 6–10 weeks**

Add:

- Silver layer
- Standard transformations
- SQL transformations
- Stored procedures
- Lookups
- Validation
- Reject framework
- SCD1
- SCD2

```text
Source
  ↓
Bronze
  ↓
Validation
  ↓
Transformation
  ↓
Silver
```

### Phase 3 — Analytics Platform

**Duration: 6–10 weeks**

Add:

- Gold layer
- Fact generation
- Dimension generation
- SCD2 dimensions
- Aggregations
- Reporting Lakehouse
- Semantic model automation

```text
Bronze
   ↓
Silver
   ↓
Gold
   ↓
Reporting Lakehouse
   ↓
Direct Lake Semantic Model
```

### Phase 4 — Enterprise Platform

Add:

- Git integration
- Deployment automation
- Approval workflow
- Advanced RBAC
- Governance
- Audit
- Cost monitoring
- Performance recommendations
- Multi-project management
- Tenant isolation

### Phase 5 — Commercial Product

Add:

- Multi-tenancy
- Subscription management
- Usage limits
- Customer onboarding
- Tenant isolation
- Billing
- Product telemetry
- Support tooling

**Potential positioning:** Fabric Data Platform Automation.

---

## 29. Final Product Architecture

```text
┌───────────────────────────────────────────────────────────┐
│                     PRODUCT CONTROL PLANE                 │
├───────────────────────────────────────────────────────────┤
│ UI                                                        │
│ Project Management                                        │
│ Source Discovery                                          │
│ Metadata                                                  │
│ Transformation Designer                                   │
│ Data Quality                                              │
│ Security / Governance                                     │
│ Deployment                                                │
│ Monitoring                                                │
└────────────────────────────┬──────────────────────────────┘
                             │
                       Product API
                             │
                   Fabric API Adapter
                             │
┌────────────────────────────▼──────────────────────────────┐
│                     MICROSOFT FABRIC                      │
│                       DATA PLANE                           │
├───────────────────────────────────────────────────────────┤
│ Pipelines / Copy Jobs                                     │
│ Bronze Lakehouse                                          │
│ Silver Warehouse                                          │
│ Gold Warehouse                                            │
│ Spark / Notebooks                                         │
│ Reporting Lakehouse                                       │
│ Semantic Model / Power BI                                 │
└───────────────────────────────────────────────────────────┘
```

---

## 30. Strategic Product Principle

The product should **generate and orchestrate Fabric**, not compete with Fabric.

Fabric already provides:

- Data movement
- Spark
- Delta
- Lakehouse
- Warehouse
- OneLake
- Pipelines
- Semantic models
- Power BI integration
- Security
- Deployment capabilities

The product's value is:

**Automation + Metadata + Standards + Governance + Generation + Monitoring + Developer Experience**

That is what turns an internal Fabric framework into a potentially commercial product.

---

## 31. Recommended First Build

Start with:

```text
SQL Server
    |
    v
Source Discovery
    |
    v
Metadata
    |
    v
Incremental Configuration
    |
    v
Fabric Pipeline Generation
    |
    v
Bronze Lakehouse Generation
    |
    v
MERGE / Audit / RunId
    |
    v
Execution
    |
    v
Monitoring
```

**Do not start with the full Gold/Power BI automation vision.**

First prove automated ingestion. Then build transformation, analytics and enterprise capabilities around the same metadata foundation.

---

## 32. Product Design Principles

1. **Metadata first** — every generated artefact should be traceable back to metadata.
2. **Fabric native** — use Fabric capabilities instead of recreating them unnecessarily.
3. **Convention over configuration** — provide sensible defaults while allowing advanced overrides.
4. **Understandable generated code** — engineers should be able to inspect and troubleshoot generated artefacts.
5. **Extensibility without losing standardisation** — support custom SQL, stored procedures and notebooks as controlled extension points.
6. **Environment aware** — never hard-code DEV/UAT/PROD configuration.
7. **Operational by design** — RunId, logging, retries, metrics and error handling are part of every generated workload.
8. **Security by design** — credentials, PII and production access are first-class concerns.
9. **Incremental by default** — favour incremental processing when a reliable watermark or CDC mechanism exists.
10. **Generate, don't hand-code** — reduce repetitive Fabric engineering work.

---

## 33. Commercial Differentiators

The strongest differentiators are the combination of:

1. Fabric-native automation
2. Metadata-driven architecture
3. Automatic Bronze/Silver/Gold generation
4. Built-in SCD1/SCD2
5. Environment-aware anonymisation
6. Built-in data quality
7. Incremental/CDC framework
8. Operational monitoring
9. Deployment automation
10. Direct Lake/reporting accelerator
11. Reusable engineering standards
12. Low-code onboarding with an engineering escape hatch

### Product positioning

> **An automation and governance control plane for Microsoft Fabric data platforms.**

---

## 34. Suggested Technology Stack

| Component | Recommended technology |
|---|---|
| Frontend | React / Next.js |
| Backend | .NET / ASP.NET Core |
| Metadata database | Azure SQL Database |
| Secrets | Azure Key Vault |
| Identity | Microsoft Entra ID |
| Fabric integration | Fabric REST APIs |
| Async processing | Azure Service Bus + Azure Functions |
| Source control | GitHub or Azure DevOps |
| Deployment | Fabric Deployment Pipelines + CI/CD |
| Data platform | Microsoft Fabric |
| Analytics | Fabric Warehouse + Lakehouse |
| Reporting | Power BI / Direct Lake where supported |

.NET is a strong default for an enterprise Microsoft-focused product, while Python remains suitable for data-engineering components and custom transformation workloads.

---

## 35. Example End-to-End Product Flow

```text
                 USER
                   |
                   v
          +----------------+
          |   Product UI   |
          +-------+--------+
                  |
                  v
          +----------------+
          |   Metadata     |
          |    Engine      |
          +-------+--------+
                  |
          +-------+-------+
          |               |
          v               v
     Source Discovery   Rules
          |               |
          +-------+-------+
                  |
                  v
          +----------------+
          | Generation     |
          | Engine         |
          +-------+--------+
                  |
                  v
          +----------------+
          | Fabric API     |
          | Adapter        |
          +-------+--------+
                  |
                  v
        +----------------------+
        | Microsoft Fabric     |
        |                      |
        | Pipeline             |
        | Lakehouse            |
        | Warehouse            |
        | Notebook             |
        | Semantic Model       |
        +----------+-----------+
                   |
                   v
              Run / Monitor
                   |
                   v
              Product UI
```

---

## 36. Product Roadmap Summary

```text
                FABRIC DATA PLATFORM AUTOMATION

PHASE 0
Prototype
  |
  v
PHASE 1
Automated Ingestion
  |
  v
PHASE 2
Transformation + DQ + SCD
  |
  v
PHASE 3
Gold + Reporting
  |
  v
PHASE 4
Enterprise Governance + Deployment
  |
  v
PHASE 5
Commercial SaaS / Multi-Tenant Product
```

The recommended commercial strategy is to make **Phase 1 extremely strong**. If the product can turn a new SQL Server source into a standardised, monitored, incremental Fabric Bronze implementation in minutes rather than days, there is a clear foundation on which the rest of the platform can be built.
