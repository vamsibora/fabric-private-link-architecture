-- Seed: SQLServer dbo.Customer (entity 101)
--   INCREMENTAL on ModifiedDate, landing ENABLED (JSON in the Storage Account),
--   HISTORICAL Bronze (history_required = 1), HASH change detection,
--   Email/Phone anonymised in environments with anonymisation_enabled = true.
-- This is the spec's end-to-end demonstration entity (spec section 58).
BEGIN TRANSACTION;

DELETE FROM [control].[column_mapping]     WHERE entity_id = 101;
DELETE FROM [control].[validation_rule]    WHERE entity_id = 101;
DELETE FROM [control].[load_configuration] WHERE entity_id = 101;
DELETE FROM [control].[entity_column]      WHERE entity_id = 101;
DELETE FROM [control].[entity]             WHERE entity_id = 101;

INSERT INTO [control].[entity]
    (entity_id, source_system_id, source_schema, source_table, target_schema, target_table,
     staging_schema, staging_table, entity_group, load_type, landing_enabled, history_required,
     merge_required, primary_key, watermark_column, watermark_type, change_detection_method,
     anonymisation_required, processing_priority, active_flag, created_datetime, created_by)
VALUES
    (101, 1, 'dbo', 'Customer', 'sqlserver', 'customer',
     'staging', 'sqlserver_customer', 'sales', 'INCREMENTAL', 1, 1,
     0, 'CustomerId', 'ModifiedDate', 'DATETIME', 'HASH',
     1, 10, 1, SYSUTCDATETIME(), 'metadata_deploy');

INSERT INTO [control].[entity_column]
    (entity_column_id, entity_id, source_column, target_column, ordinal_position, source_data_type,
     target_data_type, nullable_flag, primary_key_flag, watermark_flag, hash_flag, anonymisation_flag,
     anonymisation_rule_id, active_flag, created_datetime, created_by)
VALUES
    (10101, 101, 'CustomerId',   'CustomerId',   1, 'int',           'INT',       0, 1, 0, 0, 0, NULL, 1, SYSUTCDATETIME(), 'metadata_deploy'),
    (10102, 101, 'FirstName',    'FirstName',    2, 'nvarchar(100)', 'STRING',    1, 0, 0, 1, 0, NULL, 1, SYSUTCDATETIME(), 'metadata_deploy'),
    (10103, 101, 'LastName',     'LastName',     3, 'nvarchar(100)', 'STRING',    1, 0, 0, 1, 0, NULL, 1, SYSUTCDATETIME(), 'metadata_deploy'),
    (10104, 101, 'Email',        'Email',        4, 'nvarchar(256)', 'STRING',    1, 0, 0, 1, 1, 1,    1, SYSUTCDATETIME(), 'metadata_deploy'),
    (10105, 101, 'Phone',        'Phone',        5, 'nvarchar(50)',  'STRING',    1, 0, 0, 1, 1, 2,    1, SYSUTCDATETIME(), 'metadata_deploy'),
    (10106, 101, 'Address',      'Address',      6, 'nvarchar(400)', 'STRING',    1, 0, 0, 1, 0, NULL, 1, SYSUTCDATETIME(), 'metadata_deploy'),
    (10107, 101, 'City',         'City',         7, 'nvarchar(100)', 'STRING',    1, 0, 0, 1, 0, NULL, 1, SYSUTCDATETIME(), 'metadata_deploy'),
    (10108, 101, 'ModifiedDate', 'ModifiedDate', 8, 'datetime2',     'TIMESTAMP', 0, 0, 1, 0, 0, NULL, 1, SYSUTCDATETIME(), 'metadata_deploy');

INSERT INTO [control].[load_configuration]
    (load_configuration_id, entity_id, retry_enabled, max_retry_count, retry_delay_seconds,
     source_query_override, source_filter, delete_detection_enabled, row_count_anomaly_threshold_pct,
     active_flag, created_datetime, created_by)
VALUES
    (101, 101, 1, 3, 30, NULL, NULL, 0, 50.00, 1, SYSUTCDATETIME(), 'metadata_deploy');

INSERT INTO [control].[validation_rule]
    (validation_rule_id, entity_id, rule_name, rule_type, column_name, expression, severity,
     failure_action, validation_stage, active_flag, created_datetime, created_by)
VALUES
    (1011, 101, 'customer_lastname_mandatory', 'MANDATORY_COLUMN_NULL', 'LastName', NULL, 'MEDIUM', 'WARN', 'PRE', 1, SYSUTCDATETIME(), 'metadata_deploy'),
    (1012, 101, 'customer_email_format',       'CUSTOM', 'Email', 'Email IS NULL OR Email LIKE ''%@%''', 'LOW', 'WARN', 'PRE', 1, SYSUTCDATETIME(), 'metadata_deploy'),
    (1013, 101, 'customer_watermark_valid',    'WATERMARK_INVALID', 'ModifiedDate', NULL, 'HIGH', 'FAIL', 'PRE', 1, SYSUTCDATETIME(), 'metadata_deploy'),
    (1014, 101, 'customer_row_count_anomaly',  'ROW_COUNT_ANOMALY', NULL, NULL, 'MEDIUM', 'WARN', 'POST', 1, SYSUTCDATETIME(), 'metadata_deploy');

-- JSON landing preserves strings; make the watermark a real timestamp.
INSERT INTO [control].[column_mapping]
    (column_mapping_id, entity_id, target_column, source_expression, active_flag, created_datetime, created_by)
VALUES
    (10101, 101, 'ModifiedDate', 'CAST(ModifiedDate AS TIMESTAMP)', 1, SYSUTCDATETIME(), 'metadata_deploy');

-- Runtime state: create the watermark row once, never reset it.
INSERT INTO [control].[watermark] (entity_id, last_successful_watermark, last_run_id, last_entity_run_id, updated_datetime)
SELECT 101, NULL, NULL, NULL, SYSUTCDATETIME()
WHERE NOT EXISTS (SELECT 1 FROM [control].[watermark] WHERE entity_id = 101);

COMMIT TRANSACTION;
