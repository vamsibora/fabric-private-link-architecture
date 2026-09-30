-- Seed: source systems and their per-environment connection references.
--
-- source_system rows are repo-owned: deleted and re-inserted on every apply.
-- source_connection rows are ENVIRONMENT-owned: inserted only when missing,
-- never deleted or overwritten here. Operators set environment-specific values
-- (fabric_connection_id, gateway_name, database_name) with the UPDATE in
-- docs/runbooks/02_metadata_maintenance.md; a re-apply of this script must
-- not wipe them. No credentials, ever.
BEGIN TRANSACTION;

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
SELECT v.source_connection_id, v.source_system_id, v.environment, v.connection_reference, NULL,
       NULL, v.database_name, 'FABRIC_CONNECTION', NULL, 1, SYSUTCDATETIME(), 'metadata_deploy'
FROM (VALUES
        (CAST(11 AS BIGINT), CAST(1 AS BIGINT), 'DEV',  'sqlserver_sales', 'SalesDb'),
        (CAST(12 AS BIGINT), CAST(1 AS BIGINT), 'UAT',  'sqlserver_sales', 'SalesDb'),
        (CAST(13 AS BIGINT), CAST(1 AS BIGINT), 'PROD', 'sqlserver_sales', 'SalesDb')
     ) AS v (source_connection_id, source_system_id, environment, connection_reference, database_name)
WHERE NOT EXISTS (SELECT 1 FROM [control].[source_connection] AS c
                  WHERE c.source_connection_id = v.source_connection_id);

COMMIT TRANSACTION;
