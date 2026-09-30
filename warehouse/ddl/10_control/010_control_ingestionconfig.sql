-- CONTROL.IngestionConfig: one row per source object -> target table mapping.
-- Drives what the ingestion framework loads and how (full/incremental/CDC).
--
-- Fabric Warehouse notes:
--   - No NVARCHAR/DATETIME/DEFAULT/CHECK support -> VARCHAR (UTF-8 collation),
--     DATETIME2(6), and audit columns populated by the calling code, not the table.
--   - PRIMARY KEY/UNIQUE cannot be declared inline; added later via
--     30_constraints/030_control_security_constraints.sql as NOT ENFORCED.
--   - IDENTITY(1,1) is fine here: this table is low-concurrency and admin/CI-managed.
CREATE TABLE [CONTROL].[IngestionConfig]
(
    IngestionConfigID     BIGINT       IDENTITY(1,1) NOT NULL,
    SourceSystem          VARCHAR(100) NOT NULL,
    SourceSchema          VARCHAR(128) NULL,
    SourceObject          VARCHAR(256) NULL,
    TargetSchema          VARCHAR(128) NOT NULL,
    TargetTable           VARCHAR(256) NOT NULL,
    LoadType              VARCHAR(20)  NOT NULL,   -- 'FULL' | 'INCREMENTAL' | 'CDC'
    WatermarkColumn       VARCHAR(128) NULL,       -- required when LoadType = 'INCREMENTAL'
    IsAnonymizationEnabled BIT         NOT NULL,
    IsActive              BIT          NOT NULL,
    CreatedDate           DATETIME2(6) NOT NULL,
    CreatedBy             VARCHAR(256) NOT NULL,
    ModifiedDate          DATETIME2(6) NULL,
    ModifiedBy            VARCHAR(256) NULL
);
