-- Seed: source systems and their per-environment connection references.
-- fabric_connection_id is left NULL here: it is an environment-specific
-- identifier that an operator sets per environment (see
-- docs/bronze_framework/11_Deployment.md). No credentials, ever.
BEGIN TRANSACTION;

DELETE FROM [control].[source_connection] WHERE source_connection_id IN (11, 12, 13);
DELETE FROM [control].[source_system] WHERE source_system_id IN (1);

INSERT INTO [control].[source_system]
    (source_system_id, source_system_name, source_type, description, bronze_schema,
     connection_reference, active_flag, created_datetime, created_by)
VALUES
    (1, 'SQLServer', 'SQLSERVER', 'On-premises SQL Server via on-premises data gateway', 'sqlserver',
     'sqlserver_sales', 1, SYSUTCDATETIME(), 'metadata_deploy');

INSERT INTO [control].[source_connection]
    (source_connection_id, source_system_id, environment, connection_reference, fabric_connection_id,
     gateway_name, database_name, auth_type, key_vault_secret_name, active_flag, created_datetime, created_by)
VALUES
    (11, 1, 'DEV',  'sqlserver_sales', NULL, NULL, 'SalesDb', 'FABRIC_CONNECTION', NULL, 1, SYSUTCDATETIME(), 'metadata_deploy'),
    (12, 1, 'UAT',  'sqlserver_sales', NULL, NULL, 'SalesDb', 'FABRIC_CONNECTION', NULL, 1, SYSUTCDATETIME(), 'metadata_deploy'),
    (13, 1, 'PROD', 'sqlserver_sales', NULL, NULL, 'SalesDb', 'FABRIC_CONNECTION', NULL, 1, SYSUTCDATETIME(), 'metadata_deploy');

COMMIT TRANSACTION;
