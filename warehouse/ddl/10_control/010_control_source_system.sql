-- control.source_system: one row per source system (SQLSERVER, SERVICENOW, ...).
--
-- Fabric Warehouse notes (apply to every control table):
--   - No NVARCHAR/DATETIME/DEFAULT/CHECK -> VARCHAR (UTF-8 collation) and
--     DATETIME2(6); audit columns are populated by the deploying script.
--   - No inline PK/FK/UNIQUE -> added in 30_constraints as NOT ENFORCED.
--   - Ids are explicit BIGINTs set by warehouse/metadata scripts, NOT
--     IDENTITY: metadata is promoted DEV -> UAT -> PROD and ids must be
--     identical everywhere, which IDENTITY (preview, no IDENTITY_INSERT)
--     cannot guarantee.
CREATE TABLE [control].[source_system]
(
    source_system_id     BIGINT        NOT NULL,
    source_system_name   VARCHAR(100)  NOT NULL,   -- used in landing paths: <landing_root>/<source_system_name>/...
    source_type          VARCHAR(50)   NOT NULL,   -- SQLSERVER | ORACLE | POSTGRES | SERVICENOW | LOGICMONITOR | REST
    description          VARCHAR(4000) NULL,
    bronze_schema        VARCHAR(128)  NOT NULL,   -- default Bronze Lakehouse schema for this source's entities
    connection_reference VARCHAR(128)  NULL,       -- logical name; resolved to control.source_connection per environment
    active_flag          BIT           NOT NULL,
    created_datetime     DATETIME2(6)  NOT NULL,
    created_by           VARCHAR(256)  NOT NULL,
    updated_datetime     DATETIME2(6)  NULL,
    updated_by           VARCHAR(256)  NULL
);
