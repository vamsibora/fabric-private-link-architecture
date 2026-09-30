# 01 — Architecture

A metadata-driven Bronze ingestion framework for Microsoft Fabric. Adding a
source table means adding metadata rows (`warehouse/metadata/`), not writing a
new pipeline or notebook.

> **Validation status.** Everything here is repo code tested with mocks. No
> part of it has been deployed to, or run against, a live Fabric workspace.
> The "Verify live before production" list at the end must be worked through
> in Dev first.

## The three architectural changes

| # | Change | Where it lives |
|---|---|---|
| 1 | **Optional landing layer.** `control.entity.landing_enabled` (ANDed with `framework_configuration.landing_globally_enabled`). TRUE: the Copy writes JSON to an ADLS Gen2 landing container at `<source_system>/<table>/<table>_<yyyyMMddHHmmss>.json`. FALSE: the Copy writes to a Bronze Lakehouse staging table, which is truncated/overwritten on every run. | `notebooks/bronze/landing_manager.py`, `staging_manager.py`, `BronzeExtractSqlServerEntity.DataPipeline` |
| 2 | **Central cross-workspace audit Fabric SQL Database** (`BronzeFrameworkAudit`, schema `audit`). Every ingestion workspace writes run, entity, activity, error, validation and landing-file audit here, through stored procedures. | `sql_database/audit/`, `notebooks/bronze/audit_manager.py` |
| 3 | **Warehouse `control` schema** holding only framework metadata: source systems, connections, entities, columns, load config, watermarks, anonymisation/validation rules, mappings, pipeline/framework config. | `warehouse/ddl/10_control/`, `warehouse/metadata/`, `warehouse/programmability/` |

The key principle: **control metadata defines what should happen (Warehouse),
and audit records what actually happened (SQL Database).** The old
PascalCase `CONTROL` schema, whose `PipelineRun`/`TableRun`/`ErrorLog` tables
held audit rows inside the Warehouse, was never deployed. It has been
retired.

## Overall flow

```text
                     SOURCE SYSTEMS (SQL Server via gateway)
                                   │
                                   ▼
        ┌──────────────── BronzeOrchestrator.DataPipeline ───────────────┐
        │ SetRunId / SetRunTimestamp  (from pipeline().TriggerTime)      │
        │ audit.usp_start_run                                            │
        │ Lookup control.fn_active_entities(@environment, @entity_group) │
        │ ForEach entity (batchCount 20) ─ Switch source_type            │
        │    └─ SQLSERVER → BronzeExtractSqlServerEntity.DataPipeline    │
        │ BronzeFramework notebook (after ForEach Completed)             │
        └────────────────────────────────────────────────────────────────┘
                                   │
                ┌──────────────────┴───────────────────┐
                │ landing_enabled = TRUE               │ landing_enabled = FALSE
                ▼                                      ▼
     Get Metadata exists? → Fail              Copy → Lakehouse staging.<table>
     Copy → ADLS JSON                         (table action Overwrite,
     landing/<src>/<tbl>/<tbl>_<ts>.json       _staging_run_id stamped)
     audit.usp_log_file (CREATED)                       │
                │                                       │
                └──────── audit.entity_run = EXTRACTED ─┘
                                   │
                                   ▼
                  BronzeFramework notebook (notebooks.bronze)
      stage → schema → read → validate PRE → watermark max → dedup →
      anonymise → hash → MERGE | HISTORY | APPEND | REPLACE →
      validate POST → commit watermark → audit
                                   │
                                   ▼
       Bronze Lakehouse <target_schema>.<table> (Delta)  → Silver → Gold

CONTROL PLANE  Warehouse  control.*          (metadata + watermark state)
AUDIT PLANE    Fabric SQL Database audit.*   (cross-workspace, all runs)
```

## Components

| Component | Module / item | Responsibility |
|---|---|---|
| Configuration Loader | `config_loader.py` | Read `control.*` (one query per table), validate, build `EntityConfig`/`FrameworkConfig` |
| Run Manager | `run_manager.py` | `run_id` (`yyyyMMdd-HHmmss-XXXXXX`), `entity_run_id` (`<run_id>-E<entity_id>`), run timestamp |
| Landing Manager | `landing_manager.py` | Landing paths, the no-overwrite guard, replayable file listing |
| Staging Manager | `staging_manager.py` | Verify copied staging, load landing JSON into staging, project to target types |
| Schema Manager | `schema_manager.py` | Delta DDL plus technical columns; additive evolution only |
| Validation Engine | `validation_engine.py` | Built-in and metadata rules, FAIL/WARN/IGNORE |
| Deduplication Engine | `dedup_engine.py` | Latest row per key, or exact duplicates for HISTORY |
| Anonymisation Engine | `anonymisation_engine.py` | Deterministic, environment-gated rules |
| Hash Engine | `hash_engine.py` | SHA-256 over canonicalised hash columns |
| Merge Engine | `merge_engine.py` | MERGE / APPEND / REPLACE, soft-delete detection |
| Historical Load Engine | `history_engine.py` | Source-history versions in one atomic MERGE |
| Watermark Manager | `watermark_manager.py` | Read, compute, and commit the watermark only on success |
| Audit Manager | `audit_manager.py` | Stored-procedure writes, fail-fast vs fail-soft |
| Error Manager | `error_manager.py` | Exception types, retryable classification, sanitisation, retry loop |
| Orchestrator | `orchestrator.py`, `bootstrap.py` | Bounded-parallel per-entity processing, run roll-up |

## Decisions

### Pipeline extracts, one notebook processes the whole run

Pipelines only orchestrate extraction. They contain no business logic, and
every audit write goes through the same `audit.usp_*` procedures the notebook
uses. After the ForEach, **one** `BronzeFramework` notebook activity processes
every entity that audit shows as `EXTRACTED` for the run. It uses a
`ThreadPoolExecutor(max_parallel_entities)` (5/10/20 for DEV/UAT/PROD). This
avoids paying Spark session start-up once per entity, and keeps concurrency a
metadata setting rather than a pipeline constant.

### Pipeline Copy activities, not Copy Jobs

The reference Copy Job `cj_department_landing` (CDC,
`SnapshotPlusIncremental`) writes a **fixed** file name (`department.json`).
It cannot be parameterised per entity or per run, so it cannot produce
`<table>_<yyyyMMddHHmmss>.json` or be driven by metadata. The framework
therefore uses a pipeline `Copy` activity in the shape of the working
reference `pl_data_delta_load`: an expression `sqlReaderQuery`, and a
`JsonSink` with `@concat(...)` `fileSystem`/`folderPath`/`fileName`. Copy Job
remains an optional per-source alternative only.

### Landing timestamp format `yyyyMMddHHmmss`

The spec's literal `yyyymmddhhss` has no minutes, so two runs in the same hour
would produce the same name, and files must never be overwritten. The
framework uses `yyyyMMddHHmmss`, derived from `pipeline().TriggerTime` (the
same instant as the `run_id`). The pipeline also refuses to write if the file
already exists (Get Metadata → Fail).

### SQL token audience `pbi`

In the working Dev reference notebook `nb_landing_bronze`, pyodbc connected
to a Warehouse with `notebookutils.credentials.getToken("pbi")`, while the
`https://database.windows.net` audience hit internal 500 errors.
`fabric_connection.DEFAULT_NOTEBOOK_TOKEN_AUDIENCE` is therefore `"pbi"`. It
can be overridden through `framework_configuration.sql_token_audience` and
`audit_sql_token_audience`. The audit-database audience is **unverified**.

### Lakehouse layout

Bronze is a **schema-enabled** Lakehouse with one schema per source
(`sqlserver.customer`), following the reference `lh_bronze_dev`
(`rio.department`). Staging is a shared `staging` schema holding
source-shaped tables (`staging.sqlserver_customer`).

### Control ids

Control-table ids are explicit `BIGINT`s set by metadata scripts, not
`IDENTITY`. That keeps them identical across DEV, UAT and PROD, which
metadata promotion needs. It also avoids preview-only `IDENTITY` in Fabric
DW, which has no `IDENTITY_INSERT`.

## Workspaces

```text
Private Engineering Workspace (per environment)
  ├─ Bronze Lakehouse (schema-enabled)  staging.*, <source>.*,  Files/landing → ADLS shortcut
  ├─ Warehouse                          control.*, SECURITY.*
  ├─ BronzeOrchestrator / BronzeExtractSqlServerEntity / SchemaMigration pipelines
  ├─ BronzeFramework / MetadataInitialisation / SchemaMigrationRunner notebooks
  └─ CicdFramework Environment          framework wheel
Audit / Operations Workspace
  └─ Fabric SQL Database BronzeFrameworkAudit   audit.*
Azure Storage Account (ADLS Gen2, private endpoint)
  └─ container "landing"
Reporting Workspace
  └─ Reporting Lakehouse → Direct Lake semantic model → Power BI
```

## Verify live before production

These have not been confirmed against a real Fabric tenant:

1. **ForEach `batchCount` is static** (20) and not expression-driven. Actual
   processing concurrency comes from `max_parallel_entities` in the notebook.
   Check that 20 concurrent Copy activities are acceptable for the gateway.
2. **`SqlServerStoredProcedure` against a Fabric SQL Database** over a
   cross-workspace connection. Fallback: a Script activity running the same
   `EXEC audit.usp_*`.
3. **Outbound access protection / private link** on the engineering workspace
   may block cross-workspace SQL connections to the audit database, from both
   pipelines and notebooks. Confirm with managed private endpoints or an
   allow-list.
4. **Schema-enabled Lakehouse** is required for the `schema.table` names
   (`staging.x`, `sqlserver.x`).
5. **`Lookup` `DataWarehouseSource` linked-service shape** is hand-authored.
   Export a real Warehouse Lookup and compare.
6. **`LakehouseTableSink` `tableActionOption: Overwrite`** should truncate and
   load atomically, and `additionalColumns` should stamp `_staging_run_id`.
   Fallback: `staging_manager.truncate()` before an Append copy.
7. **Fabric DW T-SQL features** used by `control.fn_active_entities`:
   `CREATE OR ALTER FUNCTION`, `STRING_AGG ... WITHIN GROUP`,
   `CROSS/OUTER APPLY`.
8. **`cursor.rowcount` after a Fabric DW `UPDATE`**, which the optimistic
   watermark commit relies on (`watermark_manager.WatermarkManager.commit`).
9. **Token audience for the audit SQL Database** (`pbi` vs
   `https://database.windows.net/.default`).
10. **Item-reference binding** (`notebookId`/`pipelineId` set to logical ids)
    after the first git sync (`fabric_items/README.md`).

11. **Parameterised source connection over an on-premises gateway.** The extract Copy's
    connection is `@pipeline().parameters.source_connection_id` (a Fabric connection GUID from
    `control.source_connection`). Fabric documents GUID-based connection parameterisation;
    support for gateway connections is reported by the community but not explicitly documented.
    The fallback is one statically bound extract pipeline per server.