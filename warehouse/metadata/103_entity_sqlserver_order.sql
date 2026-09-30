-- Seed: SQLServer dbo.Order (entity 103)
--   COMPOSITE primary key (OrderId, OrderLineNumber), INCREMENTAL on
--   ModifiedDate, landing ENABLED, CURRENT-STATE Bronze via MERGE.
--   "Order" is a reserved word -- the generated source query brackets it.
BEGIN TRANSACTION;

DELETE FROM [control].[column_mapping]     WHERE entity_id = 103;
DELETE FROM [control].[validation_rule]    WHERE entity_id = 103;
DELETE FROM [control].[load_configuration] WHERE entity_id = 103;
DELETE FROM [control].[entity_column]      WHERE entity_id = 103;
DELETE FROM [control].[entity]             WHERE entity_id = 103;

INSERT INTO [control].[entity]
    (entity_id, source_system_id, source_schema, source_table, target_schema, target_table,
     staging_schema, staging_table, entity_group, load_type, landing_enabled, history_required,
     merge_required, primary_key, watermark_column, watermark_type, change_detection_method,
     anonymisation_required, processing_priority, active_flag, created_datetime, created_by)
VALUES
    (103, 1, 'dbo', 'Order', 'sqlserver', 'order',
     'staging', 'sqlserver_order', 'sales', 'INCREMENTAL', 1, 0,
     1, 'OrderId,OrderLineNumber', 'ModifiedDate', 'DATETIME', 'HASH',
     0, 30, 1, SYSUTCDATETIME(), 'metadata_deploy');

INSERT INTO [control].[entity_column]
    (entity_column_id, entity_id, source_column, target_column, ordinal_position, source_data_type,
     target_data_type, nullable_flag, primary_key_flag, watermark_flag, hash_flag, anonymisation_flag,
     anonymisation_rule_id, active_flag, created_datetime, created_by)
VALUES
    (10301, 103, 'OrderId',         'OrderId',         1, 'int',           'INT',           0, 1, 0, 0, 0, NULL, 1, SYSUTCDATETIME(), 'metadata_deploy'),
    (10302, 103, 'OrderLineNumber', 'OrderLineNumber', 2, 'int',           'INT',           0, 1, 0, 0, 0, NULL, 1, SYSUTCDATETIME(), 'metadata_deploy'),
    (10303, 103, 'CustomerId',      'CustomerId',      3, 'int',           'INT',           0, 0, 0, 1, 0, NULL, 1, SYSUTCDATETIME(), 'metadata_deploy'),
    (10304, 103, 'ProductId',       'ProductId',       4, 'int',           'INT',           0, 0, 0, 1, 0, NULL, 1, SYSUTCDATETIME(), 'metadata_deploy'),
    (10305, 103, 'Quantity',        'Quantity',        5, 'int',           'INT',           0, 0, 0, 1, 0, NULL, 1, SYSUTCDATETIME(), 'metadata_deploy'),
    (10306, 103, 'UnitPrice',       'UnitPrice',       6, 'decimal(18,2)', 'DECIMAL(18,2)', 0, 0, 0, 1, 0, NULL, 1, SYSUTCDATETIME(), 'metadata_deploy'),
    (10307, 103, 'OrderDate',       'OrderDate',       7, 'datetime2',     'TIMESTAMP',     0, 0, 0, 1, 0, NULL, 1, SYSUTCDATETIME(), 'metadata_deploy'),
    (10308, 103, 'ModifiedDate',    'ModifiedDate',    8, 'datetime2',     'TIMESTAMP',     0, 0, 1, 0, 0, NULL, 1, SYSUTCDATETIME(), 'metadata_deploy');

INSERT INTO [control].[load_configuration]
    (load_configuration_id, entity_id, retry_enabled, max_retry_count, retry_delay_seconds,
     source_query_override, source_filter, delete_detection_enabled, row_count_anomaly_threshold_pct,
     active_flag, created_datetime, created_by)
VALUES
    (103, 103, 1, 3, 60, NULL, NULL, 0, NULL, 1, SYSUTCDATETIME(), 'metadata_deploy');

INSERT INTO [control].[validation_rule]
    (validation_rule_id, entity_id, rule_name, rule_type, column_name, expression, severity,
     failure_action, validation_stage, active_flag, created_datetime, created_by)
VALUES
    (1031, 103, 'order_quantity_positive', 'CUSTOM', 'Quantity', 'Quantity > 0', 'HIGH', 'FAIL', 'PRE', 1, SYSUTCDATETIME(), 'metadata_deploy'),
    (1032, 103, 'order_unitprice_type',    'DATA_TYPE_MISMATCH', 'UnitPrice', NULL, 'HIGH', 'FAIL', 'PRE', 1, SYSUTCDATETIME(), 'metadata_deploy');

INSERT INTO [control].[column_mapping]
    (column_mapping_id, entity_id, target_column, source_expression, active_flag, created_datetime, created_by)
VALUES
    (10301, 103, 'OrderDate',    'CAST(OrderDate AS TIMESTAMP)',    1, SYSUTCDATETIME(), 'metadata_deploy'),
    (10302, 103, 'ModifiedDate', 'CAST(ModifiedDate AS TIMESTAMP)', 1, SYSUTCDATETIME(), 'metadata_deploy');

INSERT INTO [control].[watermark] (entity_id, last_successful_watermark, last_run_id, last_entity_run_id, updated_datetime)
SELECT 103, NULL, NULL, NULL, SYSUTCDATETIME()
WHERE NOT EXISTS (SELECT 1 FROM [control].[watermark] WHERE entity_id = 103);

COMMIT TRANSACTION;
