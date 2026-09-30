-- Indexes for operational reporting and the framework's own lookups:
-- run_id, entity_run_id, source_system, source_table, status,
-- start_datetime and environment (spec section 47).
CREATE NONCLUSTERED INDEX ix_run_environment_start ON [audit].[run] (environment, start_datetime DESC) INCLUDE (status, framework_name);
CREATE NONCLUSTERED INDEX ix_run_status ON [audit].[run] (status, start_datetime DESC);

CREATE NONCLUSTERED INDEX ix_entity_run_run_status ON [audit].[entity_run] (run_id, status) INCLUDE (entity_id, landing_path, source_row_count);
CREATE NONCLUSTERED INDEX ix_entity_run_entity_start ON [audit].[entity_run] (entity_id, start_datetime DESC) INCLUDE (status, watermark_after);
CREATE NONCLUSTERED INDEX ix_entity_run_source ON [audit].[entity_run] (source_system, source_table, start_datetime DESC);
CREATE NONCLUSTERED INDEX ix_entity_run_status_start ON [audit].[entity_run] (status, start_datetime DESC);

CREATE NONCLUSTERED INDEX ix_activity_run ON [audit].[activity] (run_id, entity_run_id);
CREATE NONCLUSTERED INDEX ix_activity_type_created ON [audit].[activity] (activity_type, created_datetime DESC);

CREATE NONCLUSTERED INDEX ix_error_run ON [audit].[error] (run_id, entity_run_id);
CREATE NONCLUSTERED INDEX ix_error_datetime ON [audit].[error] (error_datetime DESC) INCLUDE (source_system, source_table, error_stage);
CREATE NONCLUSTERED INDEX ix_error_source ON [audit].[error] (source_system, source_table, error_datetime DESC);

CREATE NONCLUSTERED INDEX ix_validation_run ON [audit].[validation] (run_id, entity_run_id);
CREATE NONCLUSTERED INDEX ix_validation_status_created ON [audit].[validation] (status, created_datetime DESC);

CREATE NONCLUSTERED INDEX ix_file_entity_created ON [audit].[file] (entity_id, file_created_datetime DESC) INCLUDE (status, file_path);
CREATE NONCLUSTERED INDEX ix_file_status ON [audit].[file] (status, file_created_datetime DESC);
