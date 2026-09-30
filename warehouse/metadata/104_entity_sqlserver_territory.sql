-- Seed: SQLServer dbo.Territory (entity 104)
--   FULL load, landing DISABLED, CURRENT-STATE MERGE with delete detection:
--   keys missing from the full extract are soft-deleted
--   (bronze_record_status = 'DELETED'), never physically removed.
BEGIN TRANSACTION;

DELETE FROM [control].[column_mapping]     WHERE entity_id = 104;
DELETE FROM [control].[validation_rule]    WHERE entity_id = 104;
DELETE FROM [control].[load_configuration] WHERE entity_id = 104;
DELETE FROM [control].[entity_column]      WHERE entity_id = 104;
DELETE FROM [control].[entity]             WHERE entity_id = 104;

INSERT INTO [control].[entity]
    (entity_id, source_system_id, source_schema, source_table, target_schema, target_table,
     staging_schema, staging_table, entity_group, load_type, landing_enabled, history_required,
     merge_required, primary_key, watermark_column, watermark_type, change_detection_method,
     anonymisation_required, processing_priority, active_flag, created_datetime, created_by)
VALUES
    (104, 1, 'dbo', 'Territory', 'sqlserver', 'territory',
     'staging', 'sqlserver_territory', 'reference', 'FULL', 0, 0,
     1, 'TerritoryId', NULL, NULL, 'HASH',
     0, 5, 1, SYSUTCDATETIME(), 'metadata_deploy');

INSERT INTO [control].[entity_column]
    (entity_column_id, entity_id, source_column, target_column, ordinal_position, source_data_type,
     target_data_type, nullable_flag, primary_key_flag, watermark_flag, hash_flag, anonymisation_flag,
     anonymisation_rule_id, active_flag, created_datetime, created_by)
VALUES
    (10401, 104, 'TerritoryId',   'TerritoryId',   1, 'int',           'INT',    0, 1, 0, 0, 0, NULL, 1, SYSUTCDATETIME(), 'metadata_deploy'),
    (10402, 104, 'TerritoryName', 'TerritoryName', 2, 'nvarchar(100)', 'STRING', 0, 0, 0, 1, 0, NULL, 1, SYSUTCDATETIME(), 'metadata_deploy'),
    (10403, 104, 'RegionCode',    'RegionCode',    3, 'nvarchar(10)',  'STRING', 1, 0, 0, 1, 0, NULL, 1, SYSUTCDATETIME(), 'metadata_deploy');

INSERT INTO [control].[load_configuration]
    (load_configuration_id, entity_id, retry_enabled, max_retry_count, retry_delay_seconds,
     source_query_override, source_filter, delete_detection_enabled, row_count_anomaly_threshold_pct,
     active_flag, created_datetime, created_by)
VALUES
    (104, 104, 1, 2, 30, NULL, NULL, 1, 80.00, 1, SYSUTCDATETIME(), 'metadata_deploy');

INSERT INTO [control].[validation_rule]
    (validation_rule_id, entity_id, rule_name, rule_type, column_name, expression, severity,
     failure_action, validation_stage, active_flag, created_datetime, created_by)
VALUES
    (1041, 104, 'territory_row_count_anomaly', 'ROW_COUNT_ANOMALY', NULL, NULL, 'HIGH', 'FAIL', 'PRE', 1, SYSUTCDATETIME(), 'metadata_deploy');

INSERT INTO [control].[watermark] (entity_id, last_successful_watermark, last_run_id, last_entity_run_id, updated_datetime)
SELECT 104, NULL, NULL, NULL, SYSUTCDATETIME()
WHERE NOT EXISTS (SELECT 1 FROM [control].[watermark] WHERE entity_id = 104);

COMMIT TRANSACTION;
