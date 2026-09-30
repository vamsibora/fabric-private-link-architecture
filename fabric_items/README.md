# fabric_items/

Git-sync root for the **Dev** Fabric workspace (branch `main`, folder
`/fabric_items`). UAT and Prod are not git-connected: they get content only
through the Fabric Deployment Pipeline's "deploy" action (see
`docs/cicd_pipeline.md`).

## Items

| Item | Type | Purpose |
|---|---|---|
| `BronzeOrchestrator.DataPipeline` | DataPipeline | One framework run: start audit run, Lookup `control.fn_active_entities`, ForEach entity → source-type child pipeline, then the `BronzeFramework` notebook |
| `BronzeExtractSqlServerEntity.DataPipeline` | DataPipeline | Extracts one SQL Server entity, either to Storage Account JSON landing or to a Bronze Lakehouse staging table |
| `SchemaMigration.DataPipeline` | DataPipeline | Runs `SchemaMigrationRunner` (audit DB first, then the Warehouse) |
| `BronzeFramework.Notebook` | Notebook | Thin wrapper over `notebooks.bronze` (PIPELINE / REPLAY modes) |
| `MetadataInitialisation.Notebook` | Notebook | Creates staging and Bronze Delta tables for every active entity |
| `SchemaMigrationRunner.Notebook` | Notebook | Thin wrapper over `notebooks.framework.migration_runner` |
| `CicdFramework.Environment` | Environment | Hosts the framework wheel as a custom library |

The Warehouse and the audit SQL Database are **not** synced items here. Their
schema is managed entirely by `migration_runner` (`warehouse/`,
`sql_database/`).

## Syntax reference

Item JSON and notebook source follow the **working Dev reference items** in
`ito_dp_fabric_dev/rio`:

- `pl_data_delta_load` for the Copy activity shape: `SqlServerSource` with an
  expression `sqlReaderQuery`, and `JsonSink` + `AzureBlobFSLocation` with
  `@concat(...)` `fileSystem`, `folderPath` and `fileName`.
- `pl_rio_load` / `pl_invoke_audit` for `InvokePipeline`
  (`InvokeFabricPipeline`) and `TridentNotebook`.
- `nb_landing_bronze` for the `# Fabric notebook source` / `# META` /
  `# CELL` format.
- `.platform` files for schema `platformProperties/2.0.0`.

`.platform` files are included, with freshly generated `logicalId`s, so the
first git sync can import the items directly. Cross-item references
(`notebookId`, `pipelineId`) use the target item's `logicalId`. After the first
sync into Dev, check in the portal that each activity is bound to the right
item, then use "Commit to Git" so Fabric rewrites any ids it resolved itself.

## Placeholders to bind per environment

These values are environment-specific. They are deliberately placeholders,
never real ids. Bind them via Deployment Pipeline rules / a Variable Library,
or once in the Dev portal before the first "Commit to Git".
`tests/fabric_items/test_fabric_items.py` fails if any other GUID appears in
these files.

| Placeholder | Meaning |
|---|---|
| `00000000-0000-0000-0000-000000000000` | current workspace (same pattern as `pl_rio_load`) |
| `00000000-0000-0000-0000-00000000a001` | *Reserved / unused.* The source SQL Server connection is **parameterised**: the extract Copy binds to `@pipeline().parameters.source_connection_id`, which comes from `control.source_connection.fabric_connection_id` per source system and environment |
| `00000000-0000-0000-0000-00000000a002` | Fabric connection to the ADLS Gen2 landing Storage Account |
| `00000000-0000-0000-0000-00000000a003` | Fabric connection to the central audit SQL Database (cross-workspace) |
| `00000000-0000-0000-0000-00000000a004` | Fabric connection used by `InvokePipeline` (as in `pl_invoke_audit`) |
| `00000000-0000-0000-0000-00000000b001` | control Warehouse item id; `<control-warehouse-sql-endpoint>` is its SQL endpoint |
| `00000000-0000-0000-0000-00000000b002` | Bronze Lakehouse item id (schema-enabled) |

The pipeline parameters `warehouse_connection_string`,
`audit_connection_string` and `key_vault_uri` default to empty. Bind them per
stage, and never commit real values.

Notebooks carry **no** default Lakehouse/Environment ids in their `# META`
blocks. The reference notebook hard-codes them, which would pin Dev ids into
UAT/Prod. Attach the Bronze Lakehouse (as default) and `CicdFramework`
Environment in each workspace instead.

## Parameterised source connection

`BronzeExtractSqlServerEntity` has no hard-bound source connection. Both
Copy activities use:

```json
"externalReferences": { "connection": { "value": "@pipeline().parameters.source_connection_id", "type": "Expression" } }
```

`BronzeOrchestrator` passes `item().source_connection_id` from
`control.fn_active_entities`, which reads `control.source_connection`. One
pipeline therefore serves every SQL Server instance and environment. An
empty id fails the entity fast, with an `audit.error` row
(`SOURCE_CONNECTION_NOT_CONFIGURED`), before any copy runs.

## Design notes to verify on first live run

These are listed as risks in `docs/bronze_framework/01_Architecture.md`:

- `SqlServerStoredProcedure` against a **Fabric SQL Database** over a
  cross-workspace connection. The fallback is a Script activity running the
  same `EXEC audit.usp_*`.
- `Lookup` `DataWarehouseSource` linked-service shape. Export one real
  Warehouse Lookup from the portal and compare.
- `LakehouseTableSink` `tableActionOption: Overwrite` truncates and loads
  staging atomically. The fallback is `staging_manager.truncate()` before the
  copy.
- **Parameterised connection over an on-premises gateway.** Fabric documents
  connection-GUID parameterisation, and community reports say it works for
  gateway SQL Server by **id** (not by name). Export the Copy activity after
  setting "dynamic content" on its connection in the portal, compare the JSON
  shape with the one above, and run one entity per gateway. Fallback: bind the
  connection statically and add one extract pipeline per server (RB-04).
- ForEach `batchCount` is static (20). Actual processing concurrency is
  `framework_configuration.max_parallel_entities` inside the notebook.
