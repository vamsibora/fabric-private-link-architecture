-- PK/UNIQUE/FK constraints for the control and SECURITY schemas.
--
-- Deploy AFTER every table in both schemas exists: Fabric Warehouse doesn't
-- allow inline PRIMARY KEY/FOREIGN KEY/UNIQUE in CREATE TABLE, and a FOREIGN
-- KEY's referenced table must already exist. All constraints are NOT
-- ENFORCED (Fabric DW's declarative-only model) -- they document intent and
-- inform the optimizer; the metadata scripts and framework code are
-- responsible for actually maintaining integrity.

-- source_system
ALTER TABLE [control].[source_system]
    ADD CONSTRAINT pk_source_system PRIMARY KEY NONCLUSTERED (source_system_id) NOT ENFORCED;
ALTER TABLE [control].[source_system]
    ADD CONSTRAINT uq_source_system_name UNIQUE NONCLUSTERED (source_system_name) NOT ENFORCED;

-- source_connection
ALTER TABLE [control].[source_connection]
    ADD CONSTRAINT pk_source_connection PRIMARY KEY NONCLUSTERED (source_connection_id) NOT ENFORCED;
ALTER TABLE [control].[source_connection]
    ADD CONSTRAINT uq_source_connection_env UNIQUE NONCLUSTERED (source_system_id, environment, connection_reference) NOT ENFORCED;
ALTER TABLE [control].[source_connection]
    ADD CONSTRAINT fk_source_connection_source_system FOREIGN KEY (source_system_id)
    REFERENCES [control].[source_system] (source_system_id) NOT ENFORCED;

-- entity
ALTER TABLE [control].[entity]
    ADD CONSTRAINT pk_entity PRIMARY KEY NONCLUSTERED (entity_id) NOT ENFORCED;
ALTER TABLE [control].[entity]
    ADD CONSTRAINT uq_entity_source UNIQUE NONCLUSTERED (source_system_id, source_schema, source_table) NOT ENFORCED;
ALTER TABLE [control].[entity]
    ADD CONSTRAINT uq_entity_target UNIQUE NONCLUSTERED (target_schema, target_table) NOT ENFORCED;
ALTER TABLE [control].[entity]
    ADD CONSTRAINT fk_entity_source_system FOREIGN KEY (source_system_id)
    REFERENCES [control].[source_system] (source_system_id) NOT ENFORCED;

-- entity_column
ALTER TABLE [control].[entity_column]
    ADD CONSTRAINT pk_entity_column PRIMARY KEY NONCLUSTERED (entity_column_id) NOT ENFORCED;
ALTER TABLE [control].[entity_column]
    ADD CONSTRAINT uq_entity_column_target UNIQUE NONCLUSTERED (entity_id, target_column) NOT ENFORCED;
ALTER TABLE [control].[entity_column]
    ADD CONSTRAINT fk_entity_column_entity FOREIGN KEY (entity_id)
    REFERENCES [control].[entity] (entity_id) NOT ENFORCED;

-- load_configuration
ALTER TABLE [control].[load_configuration]
    ADD CONSTRAINT pk_load_configuration PRIMARY KEY NONCLUSTERED (load_configuration_id) NOT ENFORCED;
ALTER TABLE [control].[load_configuration]
    ADD CONSTRAINT fk_load_configuration_entity FOREIGN KEY (entity_id)
    REFERENCES [control].[entity] (entity_id) NOT ENFORCED;

-- watermark (one row per entity)
ALTER TABLE [control].[watermark]
    ADD CONSTRAINT pk_watermark PRIMARY KEY NONCLUSTERED (entity_id) NOT ENFORCED;
ALTER TABLE [control].[watermark]
    ADD CONSTRAINT fk_watermark_entity FOREIGN KEY (entity_id)
    REFERENCES [control].[entity] (entity_id) NOT ENFORCED;

-- anonymisation_rule
ALTER TABLE [control].[anonymisation_rule]
    ADD CONSTRAINT pk_anonymisation_rule PRIMARY KEY NONCLUSTERED (anonymisation_rule_id) NOT ENFORCED;
ALTER TABLE [control].[anonymisation_rule]
    ADD CONSTRAINT uq_anonymisation_rule_name UNIQUE NONCLUSTERED (rule_name) NOT ENFORCED;
ALTER TABLE [control].[entity_column]
    ADD CONSTRAINT fk_entity_column_anonymisation_rule FOREIGN KEY (anonymisation_rule_id)
    REFERENCES [control].[anonymisation_rule] (anonymisation_rule_id) NOT ENFORCED;

-- validation_rule
ALTER TABLE [control].[validation_rule]
    ADD CONSTRAINT pk_validation_rule PRIMARY KEY NONCLUSTERED (validation_rule_id) NOT ENFORCED;
ALTER TABLE [control].[validation_rule]
    ADD CONSTRAINT fk_validation_rule_entity FOREIGN KEY (entity_id)
    REFERENCES [control].[entity] (entity_id) NOT ENFORCED;

-- column_mapping
ALTER TABLE [control].[column_mapping]
    ADD CONSTRAINT pk_column_mapping PRIMARY KEY NONCLUSTERED (column_mapping_id) NOT ENFORCED;
ALTER TABLE [control].[column_mapping]
    ADD CONSTRAINT uq_column_mapping_target UNIQUE NONCLUSTERED (entity_id, target_column) NOT ENFORCED;
ALTER TABLE [control].[column_mapping]
    ADD CONSTRAINT fk_column_mapping_entity FOREIGN KEY (entity_id)
    REFERENCES [control].[entity] (entity_id) NOT ENFORCED;

-- pipeline_configuration / framework_configuration
ALTER TABLE [control].[pipeline_configuration]
    ADD CONSTRAINT pk_pipeline_configuration PRIMARY KEY NONCLUSTERED (pipeline_configuration_id) NOT ENFORCED;
ALTER TABLE [control].[pipeline_configuration]
    ADD CONSTRAINT uq_pipeline_configuration_key UNIQUE NONCLUSTERED (pipeline_name, environment, config_key) NOT ENFORCED;
ALTER TABLE [control].[framework_configuration]
    ADD CONSTRAINT pk_framework_configuration PRIMARY KEY NONCLUSTERED (framework_configuration_id) NOT ENFORCED;
ALTER TABLE [control].[framework_configuration]
    ADD CONSTRAINT uq_framework_configuration_key UNIQUE NONCLUSTERED (environment, config_key) NOT ENFORCED;

-- schema_migration_history
-- Repeatable scripts produce one row per applied checksum, so uniqueness is
-- (script_path, checksum), not script_path alone. NOT ENFORCED: the
-- runner's pending-set logic is the real guarantee.
ALTER TABLE [control].[schema_migration_history]
    ADD CONSTRAINT pk_schema_migration_history PRIMARY KEY NONCLUSTERED (migration_id) NOT ENFORCED;

-- SECURITY.UserAccess (unchanged model)
ALTER TABLE [SECURITY].[UserAccess]
    ADD CONSTRAINT PK_UserAccess PRIMARY KEY NONCLUSTERED (UserAccessID) NOT ENFORCED;
ALTER TABLE [SECURITY].[UserAccess]
    ADD CONSTRAINT UQ_UserAccess_Natural UNIQUE NONCLUSTERED (UserPrincipalName, RegionKey, CountryKey, BusinessUnitKey) NOT ENFORCED;
