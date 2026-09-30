-- Adds PK/FK/UNIQUE constraints to CONTROL and SECURITY tables.
--
-- Deploy this AFTER every table in both schemas has been created: Fabric
-- Warehouse doesn't allow inline PRIMARY KEY/FOREIGN KEY/UNIQUE in CREATE
-- TABLE, and a FOREIGN KEY's referenced table must already exist. All
-- constraints are NOT ENFORCED (Fabric DW's declarative-only model) --
-- they document intent and inform the query optimizer, but application code
-- is responsible for actually maintaining referential integrity.
--
-- Each ALTER TABLE statement below is one T-SQL batch; run them individually
-- in order if your execution path doesn't accept multi-statement scripts.

-- IngestionConfig
ALTER TABLE [CONTROL].[IngestionConfig]
    ADD CONSTRAINT PK_IngestionConfig PRIMARY KEY NONCLUSTERED (IngestionConfigID) NOT ENFORCED;

ALTER TABLE [CONTROL].[IngestionConfig]
    ADD CONSTRAINT UQ_IngestionConfig_Natural UNIQUE NONCLUSTERED (SourceSystem, TargetSchema, TargetTable) NOT ENFORCED;

-- AnonymizationRule
ALTER TABLE [CONTROL].[AnonymizationRule]
    ADD CONSTRAINT PK_AnonymizationRule PRIMARY KEY NONCLUSTERED (RuleID) NOT ENFORCED;

ALTER TABLE [CONTROL].[AnonymizationRule]
    ADD CONSTRAINT UQ_AnonymizationRule_Natural UNIQUE NONCLUSTERED (SourceSystem, SourceTable, ColumnName) NOT ENFORCED;

-- PipelineRun
ALTER TABLE [CONTROL].[PipelineRun]
    ADD CONSTRAINT PK_PipelineRun PRIMARY KEY NONCLUSTERED (PipelineRunID) NOT ENFORCED;

-- TableRun
ALTER TABLE [CONTROL].[TableRun]
    ADD CONSTRAINT PK_TableRun PRIMARY KEY NONCLUSTERED (TableRunID) NOT ENFORCED;

ALTER TABLE [CONTROL].[TableRun]
    ADD CONSTRAINT FK_TableRun_PipelineRun FOREIGN KEY (PipelineRunID)
    REFERENCES [CONTROL].[PipelineRun] (PipelineRunID) NOT ENFORCED;

ALTER TABLE [CONTROL].[TableRun]
    ADD CONSTRAINT FK_TableRun_IngestionConfig FOREIGN KEY (IngestionConfigID)
    REFERENCES [CONTROL].[IngestionConfig] (IngestionConfigID) NOT ENFORCED;

-- ErrorLog
ALTER TABLE [CONTROL].[ErrorLog]
    ADD CONSTRAINT PK_ErrorLog PRIMARY KEY NONCLUSTERED (ErrorID) NOT ENFORCED;

ALTER TABLE [CONTROL].[ErrorLog]
    ADD CONSTRAINT FK_ErrorLog_PipelineRun FOREIGN KEY (PipelineRunID)
    REFERENCES [CONTROL].[PipelineRun] (PipelineRunID) NOT ENFORCED;

ALTER TABLE [CONTROL].[ErrorLog]
    ADD CONSTRAINT FK_ErrorLog_TableRun FOREIGN KEY (TableRunID)
    REFERENCES [CONTROL].[TableRun] (TableRunID) NOT ENFORCED;

-- Quarantine
ALTER TABLE [CONTROL].[Quarantine]
    ADD CONSTRAINT PK_Quarantine PRIMARY KEY NONCLUSTERED (QuarantineID) NOT ENFORCED;

ALTER TABLE [CONTROL].[Quarantine]
    ADD CONSTRAINT FK_Quarantine_TableRun FOREIGN KEY (TableRunID)
    REFERENCES [CONTROL].[TableRun] (TableRunID) NOT ENFORCED;

ALTER TABLE [CONTROL].[Quarantine]
    ADD CONSTRAINT FK_Quarantine_ErrorLog FOREIGN KEY (ErrorID)
    REFERENCES [CONTROL].[ErrorLog] (ErrorID) NOT ENFORCED;

-- UserAccess
ALTER TABLE [SECURITY].[UserAccess]
    ADD CONSTRAINT PK_UserAccess PRIMARY KEY NONCLUSTERED (UserAccessID) NOT ENFORCED;

ALTER TABLE [SECURITY].[UserAccess]
    ADD CONSTRAINT UQ_UserAccess_Natural UNIQUE NONCLUSTERED (UserPrincipalName, RegionKey, CountryKey, BusinessUnitKey) NOT ENFORCED;

-- SchemaMigrationHistory
-- NOT ENFORCED, same as every other constraint here: this does not stop the
-- application layer from double-inserting a ScriptPath -- migration_runner.py's
-- own pending-set logic is the real uniqueness guarantee, not the database.
ALTER TABLE [CONTROL].[SchemaMigrationHistory]
    ADD CONSTRAINT PK_SchemaMigrationHistory PRIMARY KEY NONCLUSTERED (MigrationID) NOT ENFORCED;

ALTER TABLE [CONTROL].[SchemaMigrationHistory]
    ADD CONSTRAINT UQ_SchemaMigrationHistory_ScriptPath UNIQUE NONCLUSTERED (ScriptPath) NOT ENFORCED;
