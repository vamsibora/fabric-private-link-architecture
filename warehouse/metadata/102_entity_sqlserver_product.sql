-- Seed: SQLServer dbo.Product (entity 102)
--   INCREMENTAL on ModifiedDate, landing DISABLED (the copy writes straight
--   to staging.sqlserver_product, which is truncated/overwritten each run),
--   CURRENT-STATE Bronze via MERGE, HASH change detection.
BEGIN TRANSACTION;

DELETE FROM [control].[column_mapping]     WHERE entity_id = 102;
DELETE FROM [control].[validation_rule]    WHERE entity_id = 102;
DELETE FROM [control].[load_configuration] WHERE entity_id = 102;
DELETE FROM [control].[entity_column]      WHERE entity_id = 102;
DELETE FROM [control].[entity]             WHERE entity_id = 102;

INSERT INTO [control].[entity]
    (entity_id, source_system_id, source_schema, source_table, target_schema, target_table,
     staging_schema, staging_table, entity_group, load_type, landing_enabled, history_required,
     merge_required, primary_key, watermark_column, watermark_type, change_detection_method,
     anonymisation_required, processing_priority, active_flag, created_datetime, created_by)
VALUES
    (102, 1, 'dbo', 'Product', 'sqlserver', 'product',
     'staging', 'sqlserver_product', 'sales', 'INCREMENTAL', 0, 0,
     1, 'ProductId', 'ModifiedDate', 'DATETIME', 'HASH',
     0, 20, 1, SYSUTCDATETIME(), 'metadata_deploy');

INSERT INTO [control].[entity_column]
    (entity_column_id, entity_id, source_column, target_column, ordinal_position, source_data_type,
     target_data_type, nullable_flag, primary_key_flag, watermark_flag, hash_flag, anonymisation_flag,
     anonymisation_rule_id, active_flag, created_datetime, created_by)
VALUES
    (10201, 102, 'ProductId',       'ProductId',       1, 'int',           'INT',           0, 1, 0, 0, 0, NULL, 1, SYSUTCDATETIME(), 'metadata_deploy'),
    (10202, 102, 'ProductName',     'ProductName',     2, 'nvarchar(200)', 'STRING',        0, 0, 0, 1, 0, NULL, 1, SYSUTCDATETIME(), 'metadata_deploy'),
    (10203, 102, 'ProductCategory', 'ProductCategory', 3, 'nvarchar(100)', 'STRING',        1, 0, 0, 1, 0, NULL, 1, SYSUTCDATETIME(), 'metadata_deploy'),
    (10204, 102, 'ListPrice',       'ListPrice',       4, 'decimal(18,2)', 'DECIMAL(18,2)', 1, 0, 0, 1, 0, NULL, 1, SYSUTCDATETIME(), 'metadata_deploy'),
    (10205, 102, 'IsActive',        'IsActive',        5, 'bit',           'BOOLEAN',       0, 0, 0, 1, 0, NULL, 1, SYSUTCDATETIME(), 'metadata_deploy'),
    (10206, 102, 'ModifiedDate',    'ModifiedDate',    6, 'datetime2',     'TIMESTAMP',     0, 0, 1, 0, 0, NULL, 1, SYSUTCDATETIME(), 'metadata_deploy');

INSERT INTO [control].[load_configuration]
    (load_configuration_id, entity_id, retry_enabled, max_retry_count, retry_delay_seconds,
     source_query_override, source_filter, delete_detection_enabled, row_count_anomaly_threshold_pct,
     active_flag, created_datetime, created_by)
VALUES
    (102, 102, 1, 3, 30, NULL, NULL, 0, NULL, 1, SYSUTCDATETIME(), 'metadata_deploy');

INSERT INTO [control].[validation_rule]
    (validation_rule_id, entity_id, rule_name, rule_type, column_name, expression, severity,
     failure_action, validation_stage, active_flag, created_datetime, created_by)
VALUES
    (1021, 102, 'product_listprice_non_negative', 'CUSTOM', 'ListPrice', 'ListPrice IS NULL OR ListPrice >= 0', 'HIGH', 'FAIL', 'PRE', 1, SYSUTCDATETIME(), 'metadata_deploy'),
    (1022, 102, 'product_name_mandatory',         'MANDATORY_COLUMN_NULL', 'ProductName', NULL, 'HIGH', 'FAIL', 'PRE', 1, SYSUTCDATETIME(), 'metadata_deploy');

INSERT INTO [control].[watermark] (entity_id, last_successful_watermark, last_run_id, last_entity_run_id, updated_datetime)
SELECT 102, NULL, NULL, NULL, SYSUTCDATETIME()
WHERE NOT EXISTS (SELECT 1 FROM [control].[watermark] WHERE entity_id = 102);

COMMIT TRANSACTION;
