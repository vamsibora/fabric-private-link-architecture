# Microsoft Fabric Data Engineering Framework

## 1. Target Architecture

The recommended production architecture uses two primary workspaces:

- **Private Data Workspace** — engineering, ingestion, Bronze, Silver, Gold and operational control data.
- **Reporting / Consumption Workspace** — reporting-facing serving data, semantic models and Power BI reports.

Because Direct Lake has constraints around private-link-enabled workspaces and Warehouse consumption, the recommended pattern introduces a **Gold Serving Lakehouse** in the reporting workspace when Direct Lake is required.

```text
                         SOURCE SYSTEMS
                              |
                              v
                    +---------------------+
                    |    MASTER PIPELINE  |
                    +----------+----------+
                               |
                     Metadata + Run Logging
                               |
                               v
============================================================
                 PRIVATE DATA WORKSPACE
============================================================

                    BRONZE LAKEHOUSE
                       Delta Tables
                           |
                           | Spark
                           v
                    SILVER WAREHOUSE
                           |
                           | SQL / Stored Procedures
                           v
                     GOLD WAREHOUSE
                           |
                      Warehouse RLS
                           |
                           | Controlled publication
                           v
============================================================
                 REPORTING WORKSPACE
============================================================

                GOLD SERVING LAKEHOUSE
                           |
                      Direct Lake
                           v
                 POWER BI SEMANTIC MODEL
                           |
                    Semantic Model RLS
                           |
                           v
                    POWER BI REPORTS
```

## 2. Workspace Structure

### Private Data Workspace

Example:

```text
FAB-DATA-PRD
```

Contains:

```text
LH_BRONZE
WH_SILVER
WH_GOLD
PL_MASTER
PL_BRONZE
PL_SILVER
PL_GOLD
PL_PUBLISH
NB_BRONZE_GENERIC
NB_SILVER_GENERIC
NB_VALIDATION
NB_UTILITIES
CONTROL schema
SECURITY schema
```

This workspace should be restricted to the data engineering/platform team and service identities.

### Reporting Workspace

Example:

```text
FAB-REPORTING-PRD
```

Contains:

```text
LH_GOLD_SERVING
SEM_SALES
SEM_FINANCE
SEM_CUSTOMER
RPT_EXECUTIVE
RPT_SALES
RPT_FINANCE
```

Consumers receive access to this workspace/app rather than the private data workspace.

> Avoid calling this a "public workspace". "Reporting / Consumption Workspace" is a better security term because public can imply anonymous internet access.

---

# 3. Medallion Architecture

```text
BRONZE
  |
  | Raw / minimally transformed
  v
SILVER
  |
  | Cleaned / validated / conformed
  v
GOLD
  |
  | Reporting-ready
  v
SEMANTIC MODEL
```

## Bronze

Bronze is implemented as a Fabric Lakehouse using Delta tables.

Characteristics:

- Source-aligned
- Minimal transformation
- Full and incremental loads
- Audit columns
- Source metadata
- Batch/run tracking
- Raw record retention
- Optional quarantine/error area

Example:

```text
LH_BRONZE
|
+-- bronze.Customer
+-- bronze.Product
+-- bronze.SalesOrder
+-- bronze.SalesOrderLine
```

Recommended technical columns:

```text
RecordHash
SourceSystem
SourceTable
BatchID
PipelineRunID
PipelineName
LoadDateTime
IsDeleted
OperationType
```

---

# 4. Metadata-Driven Bronze Framework

Create central metadata/control tables.

```text
CONTROL
|
+-- SourceSystem
+-- SourceObject
+-- IngestionConfig
+-- ColumnConfig
+-- Watermark
+-- PipelineConfig
```

## CONTROL.IngestionConfig

Example:

| Column | Example |
|---|---|
| SourceSystem | ERP |
| SourceSchema | dbo |
| SourceTable | Customer |
| TargetLakehouse | LH_BRONZE |
| TargetTable | Customer |
| LoadType | INCREMENTAL |
| WatermarkColumn | ModifiedDate |
| PrimaryKey | CustomerID |
| IsActive | 1 |
| Notebook | NB_BRONZE_GENERIC |
| PartitionColumn | ModifiedDate |
| SourceConnection | ERP_SQL |

The pipeline:

```text
Read metadata
     |
     v
Filter active objects
     |
     v
ForEach source table
     |
     v
Execute generic Spark notebook
     |
     v
Write Delta Bronze
     |
     v
Update watermark
     |
     v
Log result
```

No table-specific pipeline should be required for standard ingestion.

---

# 5. Generic Bronze Spark Notebook

Use one reusable Spark notebook.

Conceptual implementation:

```python
def ingest_bronze(config):

    source = config["source"]
    target = config["target"]
    load_type = config["load_type"]
    watermark = config["watermark"]

    df = read_source(
        source=source,
        load_type=load_type,
        watermark=watermark
    )

    df = add_audit_columns(df)

    write_delta(
        df,
        target=target,
        mode=load_type
    )

    return {
        "rows_read": rows_read,
        "rows_written": rows_written,
        "status": "SUCCESS"
    }
```

The actual implementation should additionally handle:

- Schema evolution
- Retry
- Source connection failures
- Duplicate records
- Deletes/CDC
- Watermark management
- Logging
- Exception propagation

---

# 6. Silver Warehouse Framework

Silver is implemented in the Warehouse.

Responsibilities:

- Data cleansing
- Data type conversion
- Data validation
- Lookups
- Reference data
- Business rules
- Deduplication
- SCD processing
- Conformance
- Surrogate key assignment

Example:

```text
WH_SILVER
|
+-- silver.Customer
+-- silver.Product
+-- silver.Employee
+-- silver.Store
+-- silver.Sales
```

---

# 7. Silver Metadata Framework

Recommended metadata:

```text
CONTROL
|
+-- SilverTable
+-- SilverColumn
+-- Transformation
+-- Lookup
+-- Validation
+-- Mapping
+-- BusinessRule
+-- Dependency
```

## CONTROL.SilverTable

```text
TableID
SourceTable
TargetTable
LoadType
PrimaryKey
BusinessKey
SCDType
IsActive
LoadSequence
```

## CONTROL.Lookup

```text
LookupID
TargetTable
TargetColumn
LookupTable
LookupColumn
ReturnColumn
DefaultValue
IsMandatory
```

Example:

```text
Customer.CountryCode
       |
       v
Lookup Country
       |
       v
DimCountry.CountryKey
```

---

# 8. Metadata-Driven Validation

Create:

```text
CONTROL.Validation
```

Example columns:

```text
ValidationID
TableName
ColumnName
RuleType
RuleExpression
Severity
Threshold
IsActive
```

Example rules:

```text
CustomerID IS NOT NULL
Email LIKE '%@%'
SalesAmount >= 0
OrderDate <= ShipDate
CountryCode EXISTS IN DimCountry
```

Severity levels:

```text
WARNING
DATA_QUALITY_ERROR
TECHNICAL_ERROR
FATAL_ERROR
```

The framework should support configurable thresholds.

Example:

```text
0-1% invalid     -> WARNING
1-5% invalid     -> DATA QUALITY ERROR
>5% invalid      -> FAIL
```

Thresholds should be metadata-driven rather than hard-coded.

---

# 9. Quarantine

Invalid records should not simply be discarded.

Create:

```text
CONTROL.Quarantine
```

Suggested columns:

```text
PipelineRunID
TableRunID
TableName
RecordKey
ValidationID
ValidationMessage
SourceRecord
DetectedDateTime
```

This enables operational analysis such as:

> Why did 327 customer records fail today's load?

---

# 10. Gold Warehouse

Gold is reporting-ready and should normally use a star schema.

Example:

```text
WH_GOLD
|
+-- dim.Customer
+-- dim.Product
+-- dim.Date
+-- dim.Store
+-- dim.Employee
|
+-- fact.Sales
+-- fact.SalesTarget
+-- fact.Inventory
```

Example:

```text
                     DimDate
                        |
                        |
DimCustomer ---- FactSales ---- DimProduct
                        |
                        |
                    DimStore
                        |
                        |
                   DimEmployee
```

The semantic model should generally consume the Gold model rather than raw Silver tables.

---

# 11. Run ID and Logging Framework

Use three levels of identifiers.

```text
ExecutionID
    |
    +-- PipelineRunID
            |
            +-- TableRunID
```

Example:

```text
ExecutionID:
20260906-060001-ABC123

PipelineRunID:
20260906-060001-ABC123-BRONZE

TableRunID:
20260906-060001-ABC123-BRONZE-CUSTOMER
```

This provides end-to-end traceability.

---

# 12. Control Tables

Recommended operational tables:

```text
CONTROL
|
+-- PipelineRun
+-- ActivityRun
+-- TableRun
+-- ErrorLog
+-- Watermark
+-- Batch
+-- DataQualityResult
+-- Quarantine
```

## PipelineRun

```text
PipelineRunID
PipelineName
PipelineType
StartDateTime
EndDateTime
Status
TriggeredBy
ParentRunID
ErrorMessage
```

## TableRun

```text
PipelineRunID
TableRunID
SourceTable
TargetTable
StartDateTime
EndDateTime
RowsRead
RowsInserted
RowsUpdated
RowsDeleted
Status
ErrorMessage
```

---

# 13. Exception Handling

Recommended pattern:

```text
START
  |
  v
Create Run ID
  |
  v
Read Metadata
  |
  v
Execute Table
  |
  +-------------------+
  |                   |
SUCCESS              ERROR
  |                   |
  v                   v
Update Log       Capture Exception
                      |
                      v
                 Error Log
                      |
                      v
                Mark FAILED
                      |
                      +------+
                             |
                             v
                      Update Pipeline
                             |
                             v
                            END
```

Every framework component should:

1. Generate or receive a Run ID.
2. Write a STARTED event.
3. Execute work.
4. Capture row counts.
5. Capture duration.
6. Capture warnings/errors.
7. Write SUCCESS or FAILED.
8. Propagate fatal exceptions to the parent pipeline.

---

# 14. Pipeline Hierarchy

Recommended structure:

```text
PL_MASTER
|
+-- PL_PRECHECK
|
+-- PL_BRONZE
|     |
|     +-- NB_BRONZE_GENERIC
|
+-- PL_SILVER
|     |
|     +-- NB_VALIDATE
|     +-- NB_LOOKUP
|     +-- NB_TRANSFORM
|     +-- NB_SCD
|
+-- PL_GOLD
|     |
|     +-- Stored Procedures
|
+-- PL_SECURITY
|
+-- PL_PUBLISH
|
+-- PL_POSTCHECK
```

The Master pipeline should be responsible for orchestration, not business transformations.

---

# 15. Dependency Management

Use:

```text
CONTROL.Dependency
```

Example:

| ParentTable | ChildTable |
|---|---|
| DimDate | FactSales |
| DimCustomer | FactSales |
| DimProduct | FactSales |
| DimStore | FactSales |

This allows the framework to calculate execution order.

For example:

```text
DimDate
   |
DimCustomer
   |
DimProduct
   |
DimStore
   |
   v
FactSales
```

---

# 16. Incremental Loading

The metadata framework should support at least:

### Full

```text
Source
  |
  v
Bronze
```

### Incremental

```text
Last Watermark
      |
      v
Source WHERE ModifiedDate > watermark
      |
      v
Bronze MERGE
```

### CDC

Where supported:

```text
INSERT
UPDATE
DELETE
```

The metadata determines which strategy is used.

---

# 17. Warehouse Row-Level Security

Create a central security mapping table.

```text
SECURITY.UserAccess
```

Example:

| UserPrincipalName | SecurityRole | RegionKey | CountryKey | BusinessUnitKey |
|---|---|---|---|---|
| user1@company.com | RegionalManager | UK | ALL | ALL |
| user2@company.com | CountryManager | UK | GB | ALL |
| admin@company.com | Administrator | ALL | ALL | ALL |

Use Warehouse RLS/security policies to restrict rows.

Conceptually:

```text
SECURITY.UserAccess
        |
        v
Warehouse Security Policy
        |
        v
Gold Fact/Dimension Tables
```

The Warehouse should be treated as an independent security boundary.

---

# 18. Semantic Model RLS

Use the same logical security model in Power BI.

```text
SECURITY.UserAccess
        |
        v
DimUser / DimSecurity
        |
        v
DimRegion
        |
        v
FactSales
```

Example DAX pattern:

```DAX
[UserPrincipalName] =
    USERPRINCIPALNAME()
```

Avoid maintaining unrelated security mappings in multiple systems.

The preferred approach is:

```text
                 SECURITY.UserAccess
                         |
              +----------+----------+
              |                     |
              v                     v
        Warehouse RLS        Semantic Model RLS
```

This provides defence in depth.

---

# 19. Direct Lake Architecture

If Direct Lake is mandatory, use a reporting-serving Lakehouse.

```text
PRIVATE WORKSPACE
-----------------

Bronze Lakehouse
      |
      v
Silver Warehouse
      |
      v
Gold Warehouse
      |
      | Controlled publication
      v

REPORTING WORKSPACE
-------------------

Gold Serving Lakehouse
      |
      | Direct Lake
      v
Semantic Model
      |
      v
Power BI Reports
```

The Gold Warehouse remains the authoritative relational Gold layer.

The Gold Serving Lakehouse is a reporting-serving projection/copy.

Only tables needed for reporting should normally be published.

Example:

```text
Gold Warehouse
|
+-- FactSales ---------> LH FactSales
+-- DimCustomer --------> LH DimCustomer
+-- DimProduct ---------> LH DimProduct
+-- DimDate ------------> LH DimDate
+-- DimStore -----------> LH DimStore
```

This avoids copying unnecessary data.

---

# 20. Important Private-Link / Direct Lake Consideration

The following requirements create an architectural constraint:

```text
Private-link-enabled workspace
+
Warehouse Gold
+
Direct Lake semantic model
```

Do not assume that a Direct Lake semantic model can directly consume data hosted inside a private-link-restricted workspace.

The reporting/semantic layer should therefore be explicitly separated from the restricted engineering/data workspace.

The current Fabric private-link architecture has limitations around semantic models and restricted workspace scenarios. Validate the exact capabilities against the Fabric configuration in your tenant before production implementation.

Recommended principle:

> Keep sensitive engineering/storage resources private, and publish only the required reporting-serving data to the reporting domain.

---

# 21. Gold Serving Strategy

Do not blindly duplicate all Gold data.

Publish only the required reporting objects:

```text
WH_GOLD
   |
   +-- FactSales
   +-- DimCustomer
   +-- DimProduct
   +-- DimDate
   +-- DimStore
           |
           v
LH_GOLD_SERVING
           |
           v
Direct Lake Semantic Model
```

The Gold Warehouse remains the system of record for the curated relational model.

---

# 22. Security Model

Use layered security:

```text
Fabric Workspace Security
          +
Warehouse RLS
          +
Semantic Model RLS
          +
Power BI App / Report Permissions
```

Recommended access model:

```text
DATA ENGINEERS
    |
    v
Private Data Workspace

REPORT DEVELOPERS
    |
    v
Reporting Workspace

BUSINESS USERS
    |
    v
Power BI App
```

Business users should not receive direct access to the private workspace.

---

# 23. Dev / Test / Production

Recommended environments:

```text
DEV
|
+-- FAB-DATA-DEV
+-- FAB-REPORTING-DEV

TEST
|
+-- FAB-DATA-TEST
+-- FAB-REPORTING-TEST

PROD
|
+-- FAB-DATA-PROD
+-- FAB-REPORTING-PROD
```

Promotion:

```text
DEV
 |
 v
TEST
 |
 v
PROD
```

Use Git/source control and Fabric deployment mechanisms.

Metadata should be environment-independent where possible.

Example:

```text
ConnectionAlias = ERP_SQL
```

rather than hard-coding production server names in notebooks or pipelines.

---

# 24. Recommended Repository Structure

```text
/FabricDataPlatform
|
+-- pipelines/
|
+-- notebooks/
|   +-- bronze/
|   +-- silver/
|   +-- dq/
|   +-- utilities/
|
+-- sql/
|   +-- silver/
|   +-- gold/
|   +-- security/
|   +-- procedures/
|
+-- metadata/
|
+-- semantic-model/
|
+-- deployment/
|
+-- documentation/
```

---

# 25. Operational Monitoring

Build an internal monitoring report using:

```text
CONTROL.PipelineRun
CONTROL.TableRun
CONTROL.ErrorLog
CONTROL.DataQualityResult
CONTROL.Quarantine
```

Example dashboard:

```text
Today's Loads
------------------------------
Pipeline Success          98%
Pipeline Failure           2%

Tables Loaded             247
Rows Processed       1.82B

Average Duration       14 min

DQ Failures                3
Quarantined Rows        1284
```

Drill-down:

```text
Pipeline
   |
   v
Table
   |
   v
Run
   |
   v
Error
   |
   v
Failed Record
```

---

# 26. Framework Components

The complete framework can be divided into eight reusable components:

| Component | Purpose |
|---|---|
| 01 Control Framework | Metadata and configuration |
| 02 Ingestion Framework | Source → Bronze |
| 03 Spark Framework | Bronze → Silver processing |
| 04 DQ Framework | Validation and quarantine |
| 05 Warehouse Framework | Silver → Gold |
| 06 Security Framework | Warehouse and Power BI RLS |
| 07 Publishing Framework | Gold → reporting serving layer |
| 08 Monitoring Framework | Logging and operational dashboard |

Core design principle:

> **Pipelines orchestrate. Metadata controls. Spark transforms. Warehouse SQL models. Security controls access. Semantic models serve users.**

---

# 27. End-to-End Processing Flow

```text
SOURCE
  |
  v
MASTER PIPELINE
  |
  +--> Create ExecutionID
  |
  +--> Read metadata
  |
  v
BRONZE LAKEHOUSE
  |
  | Generic Spark ingestion
  |
  v
SILVER WAREHOUSE
  |
  +--> Validation
  +--> Cleansing
  +--> Lookup
  +--> Business Rules
  +--> SCD
  |
  v
GOLD WAREHOUSE
  |
  +--> Star schema
  +--> Warehouse RLS
  |
  v
GOLD SERVING LAKEHOUSE
  |
  +--> Reporting-only projection
  |
  v
DIRECT LAKE SEMANTIC MODEL
  |
  +--> Semantic Model RLS
  |
  v
POWER BI REPORTS
  |
  v
BUSINESS USERS
```

---

# 28. Recommended Final Architecture

```text
                         SOURCE SYSTEMS
                              |
                              v
                    +---------------------+
                    |    MASTER PIPELINE  |
                    +----------+----------+
                               |
                  +------------+------------+
                  |                         |
                  v                         v
             METADATA                    LOGGING
                  |                         |
                  +------------+------------+
                               |
                               v

================================================================
                    FAB-DATA-PROD
                  PRIVATE WORKSPACE
================================================================

                 +----------------------+
                 |   BRONZE LAKEHOUSE   |
                 |       Delta          |
                 +----------+-----------+
                            |
                         Spark
                            |
                            v
                 +----------------------+
                 |   SILVER WAREHOUSE   |
                 | Validation / Lookup  |
                 | Cleansing / SCD      |
                 +----------+-----------+
                            |
                           SQL
                            |
                            v
                 +----------------------+
                 |    GOLD WAREHOUSE    |
                 |   Star Schema        |
                 |   Warehouse RLS      |
                 +----------+-----------+
                            |
                   Controlled Publish
                            |
                            v

================================================================
                  FAB-REPORTING-PROD
                  REPORTING WORKSPACE
================================================================

                 +----------------------+
                 | GOLD SERVING         |
                 | LAKEHOUSE            |
                 +----------+-----------+
                            |
                       Direct Lake
                            |
                            v
                 +----------------------+
                 | POWER BI SEMANTIC    |
                 | MODEL                |
                 |                      |
                 | Semantic RLS         |
                 +----------+-----------+
                            |
                            v
                 +----------------------+
                 | POWER BI REPORTS     |
                 +----------------------+
```

## Final design recommendation

For your requirements, the strongest production pattern is:

**Bronze**
- Private workspace
- Lakehouse
- Delta
- Generic Spark ingestion
- Metadata-driven

**Silver**
- Private workspace
- Warehouse
- Metadata-driven transformations
- Lookups
- Validations
- SCD
- Data-quality quarantine

**Gold**
- Private workspace
- Warehouse
- Star schema
- Warehouse-level RLS

**Reporting**
- Separate reporting workspace
- Gold Serving Lakehouse
- Direct Lake semantic model
- Semantic-model RLS
- Power BI reports

**Cross-cutting**
- Metadata framework
- ExecutionID / PipelineRunID / TableRunID
- Central logging
- Exception handling
- Data-quality framework
- Dependency management
- Watermarks
- Git/source control
- DEV/TEST/PROD promotion
- Operational monitoring

This architecture gives you a reusable Fabric engineering framework rather than a collection of individual pipelines. It also keeps the private data boundary separate from the reporting/Direct Lake consumption boundary.
