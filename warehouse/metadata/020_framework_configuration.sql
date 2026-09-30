-- Seed: environment-driven framework behaviour. Values are strings; typed
-- accessors live on notebooks/bronze/models.py FrameworkConfig.
-- Environment endpoints (Warehouse/audit connection strings, Key Vault URI,
-- workspace ids) are deliberately NOT here -- they are pipeline/notebook
-- parameters resolved per environment (Variable Library / deployment rules).
BEGIN TRANSACTION;

DELETE FROM [control].[framework_configuration]
WHERE framework_configuration_id BETWEEN 1000 AND 3999;

INSERT INTO [control].[framework_configuration]
    (framework_configuration_id, environment, config_key, config_value, description,
     active_flag, created_datetime, created_by)
VALUES
    -- DEV
    (1001, 'DEV', 'anonymisation_enabled',       'true',          'Apply anonymisation rules before the Bronze write', 1, SYSUTCDATETIME(), 'metadata_deploy'),
    (1002, 'DEV', 'audit_enabled',               'true',          'Write audit records to the central audit SQL Database', 1, SYSUTCDATETIME(), 'metadata_deploy'),
    (1003, 'DEV', 'fail_on_validation_error',    'true',          'Validation rules with failure_action FAIL fail the entity', 1, SYSUTCDATETIME(), 'metadata_deploy'),
    (1004, 'DEV', 'max_parallel_entities',       '5',             'Maximum entities processed concurrently by the framework', 1, SYSUTCDATETIME(), 'metadata_deploy'),
    (1005, 'DEV', 'continue_on_entity_failure',  'true',          'Keep processing independent entities after one fails', 1, SYSUTCDATETIME(), 'metadata_deploy'),
    (1006, 'DEV', 'audit_failure_is_critical',   'false',         'Fail the run when a non-critical audit write fails', 1, SYSUTCDATETIME(), 'metadata_deploy'),
    (1007, 'DEV', 'landing_globally_enabled',    'true',          'Environment switch ANDed with entity.landing_enabled', 1, SYSUTCDATETIME(), 'metadata_deploy'),
    (1008, 'DEV', 'landing_container',           'landing',       'ADLS Gen2 container (file system) holding landing files', 1, SYSUTCDATETIME(), 'metadata_deploy'),
    (1009, 'DEV', 'landing_lakehouse_path',      'Files/landing', 'Bronze Lakehouse OneLake shortcut to the landing container', 1, SYSUTCDATETIME(), 'metadata_deploy'),
    (1010, 'DEV', 'sql_token_audience',          'pbi',           'notebookutils.credentials.getToken audience for SQL endpoints', 1, SYSUTCDATETIME(), 'metadata_deploy'),
    (1011, 'DEV', 'spark_timezone',              'UTC',           'Spark session time zone (hash/watermark canonicalisation)', 1, SYSUTCDATETIME(), 'metadata_deploy'),
    (1012, 'DEV', 'audit_sql_token_audience',    'pbi',           'getToken audience for the audit SQL Database (verify live)', 1, SYSUTCDATETIME(), 'metadata_deploy'),
    -- UAT
    (2001, 'UAT', 'anonymisation_enabled',       'true',          'Apply anonymisation rules before the Bronze write', 1, SYSUTCDATETIME(), 'metadata_deploy'),
    (2002, 'UAT', 'audit_enabled',               'true',          'Write audit records to the central audit SQL Database', 1, SYSUTCDATETIME(), 'metadata_deploy'),
    (2003, 'UAT', 'fail_on_validation_error',    'true',          'Validation rules with failure_action FAIL fail the entity', 1, SYSUTCDATETIME(), 'metadata_deploy'),
    (2004, 'UAT', 'max_parallel_entities',       '10',            'Maximum entities processed concurrently by the framework', 1, SYSUTCDATETIME(), 'metadata_deploy'),
    (2005, 'UAT', 'continue_on_entity_failure',  'true',          'Keep processing independent entities after one fails', 1, SYSUTCDATETIME(), 'metadata_deploy'),
    (2006, 'UAT', 'audit_failure_is_critical',   'false',         'Fail the run when a non-critical audit write fails', 1, SYSUTCDATETIME(), 'metadata_deploy'),
    (2007, 'UAT', 'landing_globally_enabled',    'true',          'Environment switch ANDed with entity.landing_enabled', 1, SYSUTCDATETIME(), 'metadata_deploy'),
    (2008, 'UAT', 'landing_container',           'landing',       'ADLS Gen2 container (file system) holding landing files', 1, SYSUTCDATETIME(), 'metadata_deploy'),
    (2009, 'UAT', 'landing_lakehouse_path',      'Files/landing', 'Bronze Lakehouse OneLake shortcut to the landing container', 1, SYSUTCDATETIME(), 'metadata_deploy'),
    (2010, 'UAT', 'sql_token_audience',          'pbi',           'notebookutils.credentials.getToken audience for SQL endpoints', 1, SYSUTCDATETIME(), 'metadata_deploy'),
    (2011, 'UAT', 'spark_timezone',              'UTC',           'Spark session time zone (hash/watermark canonicalisation)', 1, SYSUTCDATETIME(), 'metadata_deploy'),
    (2012, 'UAT', 'audit_sql_token_audience',    'pbi',           'getToken audience for the audit SQL Database (verify live)', 1, SYSUTCDATETIME(), 'metadata_deploy'),
    -- PROD
    (3001, 'PROD', 'anonymisation_enabled',      'false',         'PROD preserves source values', 1, SYSUTCDATETIME(), 'metadata_deploy'),
    (3002, 'PROD', 'audit_enabled',              'true',          'Write audit records to the central audit SQL Database', 1, SYSUTCDATETIME(), 'metadata_deploy'),
    (3003, 'PROD', 'fail_on_validation_error',   'true',          'Validation rules with failure_action FAIL fail the entity', 1, SYSUTCDATETIME(), 'metadata_deploy'),
    (3004, 'PROD', 'max_parallel_entities',      '20',            'Maximum entities processed concurrently by the framework', 1, SYSUTCDATETIME(), 'metadata_deploy'),
    (3005, 'PROD', 'continue_on_entity_failure', 'true',          'Keep processing independent entities after one fails', 1, SYSUTCDATETIME(), 'metadata_deploy'),
    (3006, 'PROD', 'audit_failure_is_critical',  'false',         'Fail the run when a non-critical audit write fails', 1, SYSUTCDATETIME(), 'metadata_deploy'),
    (3007, 'PROD', 'landing_globally_enabled',   'true',          'Environment switch ANDed with entity.landing_enabled', 1, SYSUTCDATETIME(), 'metadata_deploy'),
    (3008, 'PROD', 'landing_container',          'landing',       'ADLS Gen2 container (file system) holding landing files', 1, SYSUTCDATETIME(), 'metadata_deploy'),
    (3009, 'PROD', 'landing_lakehouse_path',     'Files/landing', 'Bronze Lakehouse OneLake shortcut to the landing container', 1, SYSUTCDATETIME(), 'metadata_deploy'),
    (3010, 'PROD', 'sql_token_audience',         'pbi',           'notebookutils.credentials.getToken audience for SQL endpoints', 1, SYSUTCDATETIME(), 'metadata_deploy'),
    (3011, 'PROD', 'spark_timezone',             'UTC',           'Spark session time zone (hash/watermark canonicalisation)', 1, SYSUTCDATETIME(), 'metadata_deploy'),
    (3012, 'PROD', 'audit_sql_token_audience',   'pbi',           'getToken audience for the audit SQL Database (verify live)', 1, SYSUTCDATETIME(), 'metadata_deploy');

DELETE FROM [control].[pipeline_configuration]
WHERE pipeline_configuration_id BETWEEN 1000 AND 3999;

INSERT INTO [control].[pipeline_configuration]
    (pipeline_configuration_id, pipeline_name, environment, config_key, config_value, description,
     active_flag, created_datetime, created_by)
VALUES
    (1001, 'BronzeOrchestrator', 'DEV',  'copy_timeout', '0.02:00:00', 'Copy activity timeout (d.hh:mm:ss)', 1, SYSUTCDATETIME(), 'metadata_deploy'),
    (2001, 'BronzeOrchestrator', 'UAT',  'copy_timeout', '0.04:00:00', 'Copy activity timeout (d.hh:mm:ss)', 1, SYSUTCDATETIME(), 'metadata_deploy'),
    (3001, 'BronzeOrchestrator', 'PROD', 'copy_timeout', '0.08:00:00', 'Copy activity timeout (d.hh:mm:ss)', 1, SYSUTCDATETIME(), 'metadata_deploy');

COMMIT TRANSACTION;
