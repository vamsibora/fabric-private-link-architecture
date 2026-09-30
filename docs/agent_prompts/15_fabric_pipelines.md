# 15 — Fabric pipelines (spec §4, §57)

```text
Context: 00_master_context.md. Reference: fabric_items/pipelines/*, fabric_items/README.md.
Syntax: copy the working items in C:\Work\Data_Platform\src\ito_dp_fabric_dev\rio.

Use metadata, not one pipeline per table. Pipelines orchestrate; there is no business logic in
pipeline expressions.

BronzeOrchestrator.DataPipeline:
1. SetVariable run_id = yyyyMMdd-HHmmss-<6 chars of RunId>, and
   run_timestamp = yyyyMMddHHmmss, both from TriggerTime.
2. usp_start_run.
3. Lookup (DataWarehouseSource):
   SELECT * FROM control.fn_active_entities('<env>', <group|NULL>).
4. ForEach (isSequential false, static batchCount) -> Switch on source_type -> SQLSERVER:
   InvokePipeline BronzeExtractSqlServerEntity with parameters from item(). The default case
   runs usp_log_error UNSUPPORTED_SOURCE_TYPE.
5. TridentNotebook BronzeFramework (depends on ForEach Completed), with parameters environment,
   connection strings, key_vault_uri, run_id, run_timestamp, pipeline name/run id and
   mode = PIPELINE.
6. On notebook or Lookup failure: usp_complete_run 'FAILED'. This is guarded in the proc and
   never overwrites a terminal status.

BronzeExtractSqlServerEntity.DataPipeline:
- The Copy SOURCE connection is PARAMETERISED:
  externalReferences.connection = @pipeline().parameters.source_connection_id, a Fabric
  connection GUID from control.source_connection.fabric_connection_id, passed through
  fn_active_entities and the orchestrator. Use the connection ID, not the name. One pipeline
  serves every SQL Server instance.
- usp_start_entity_run (EXTRACTING) ->
  IfCondition empty(source_connection_id): usp_log_error SOURCE_CONNECTION_NOT_CONFIGURED ->
  usp_update_entity_run FAILED -> Fail ->
  (on Succeeded)
  IfCondition landing_enabled:
  TRUE:
    - GetMetadata exists -> Fail LANDING_FILE_EXISTS
      (+ usp_log_error / usp_update_entity_run FAILED);
    - Copy SqlServerSource(sqlReaderQuery = item source_query) -> JsonSink AzureBlobFSLocation
      (fileSystem = container, folderPath = <source_system>/<table>,
       fileName = <table>_<run_timestamp>.json, setOfObjects);
    - usp_log_file CREATED (rowsCopied, dataWritten), usp_log_activity COPY_COMPLETED,
      usp_update_entity_run EXTRACTED (landing_path, source_row_count).
  FALSE:
    - Copy -> LakehouseTableSink staging.<table>, tableActionOption Overwrite, additionalColumns
      _staging_run_id;
    - usp_log_activity, usp_update_entity_run EXTRACTED.
  Copy failure (both branches): usp_log_error (EXTRACT, the original error code/message) ->
  usp_update_entity_run FAILED -> Fail.
- Copy retry: static activity policy.
- Framework retries: load_configuration, in the notebook.

SchemaMigration.DataPipeline: TridentNotebook SchemaMigrationRunner (audit DB first, then the
Warehouse).

Rules:
- Include .platform files (schema 2.0.0, new logicalIds). Cross-item references use the
  target's logicalId.
- Use ONLY the placeholder GUIDs from 00. Connection-string parameters default to "".
- Notebooks: no default Lakehouse/Environment ids in META.

Tests: tests/fabric_items/test_fabric_items.py covers:
- every JSON parses;
- activity types are in the reference set;
- dependsOn names resolve within the same scope;
- every GUID is a placeholder or a declared logicalId;
- notebooks have "# Fabric notebook source" and balanced CELL/METADATA blocks;
- the landing fileName and folderPath expressions match the contract.
Report: what you could NOT verify live (the SP activity against a Fabric SQL DB, the Lookup
linked-service shape, Overwrite, logicalId binding).
```
