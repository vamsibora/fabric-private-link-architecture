# 01 — Architecture builder (spec §45, phase 1)

```text
Context: 00_master_context.md.

Goal: establish the architecture and implementation plan BEFORE writing framework code.

1. Inspect the target (DEV only, read-only):
   - Fabric workspaces: the private engineering workspace, the Audit/Operations workspace and
     the reporting workspace.
   - Items: the Bronze Lakehouse (is it schema-enabled?), the Warehouse, and the Fabric SQL
     Database BronzeFrameworkAudit.
   - Connections and gateway: SQL Server via the on-premises gateway; the ADLS Gen2 landing
     account and its private endpoint.
   - Notebook runtime: Spark / Delta versions and whether notebookutils is available.
   - Pipeline and Copy capabilities: SqlServerSource, JsonSink, LakehouseTableSink Overwrite +
     additionalColumns, Lookup on a Warehouse, the Stored procedure activity on a Fabric SQL DB,
     and InvokePipeline.
   If no Fabric access is available, say so and work from the reference items in
   C:\Work\Data_Platform\src\ito_dp_fabric_dev\rio.
2. List every Fabric limitation you found or could not confirm (start from the risk list in 00).
3. Write docs/bronze_framework/01_Architecture.md covering:
   - Diagram: source -> Copy -> (landing JSON | staging) -> Bronze framework -> Bronze Delta ->
     Silver/Gold -> reporting. Show the control plane (Warehouse control) and the audit plane
     (cross-workspace SQL DB audit) separately.
   - Orchestration decision: the pipeline extracts each entity; ONE BronzeFramework notebook
     processes the whole run with a ThreadPoolExecutor(max_parallel_entities), instead of one
     Spark session per entity.
   - Decisions: yyyyMMddHHmmss timestamp; lowercase control schema; explicit BIGINT ids; Copy
     activity rather than Copy Job, because a Copy Job writes a fixed file name and cannot be
     parameterised per entity or run.
   - Component map (spec §42) -> notebooks/bronze/<module>.py.
   - The live-verification risk register.
4. Produce the phase plan 02..21 with each phase's files and tests.

Allowed paths: docs/bronze_framework/01_Architecture.md, docs/index.md.
Acceptance: the document exists; every risk has a verification step or fallback; no framework
code is written in this phase.
Report: the findings, the plan, and what you could NOT verify live.
```
