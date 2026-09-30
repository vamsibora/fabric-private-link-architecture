-- audit.validation: one row per validation rule evaluated per entity run.
-- expected_value / actual_value hold counts and thresholds only -- never
-- source data values.
CREATE TABLE [audit].[validation]
(
    validation_id      BIGINT         IDENTITY(1, 1) NOT NULL CONSTRAINT pk_validation PRIMARY KEY CLUSTERED,
    run_id             VARCHAR(64)    NOT NULL CONSTRAINT fk_validation_run REFERENCES [audit].[run] (run_id),
    entity_run_id      VARCHAR(80)    NOT NULL CONSTRAINT fk_validation_entity_run REFERENCES [audit].[entity_run] (entity_run_id),
    validation_rule_id BIGINT         NULL,   -- control.validation_rule id; NULL for built-in rules
    validation_rule    NVARCHAR(100)  NOT NULL,
    validation_type    VARCHAR(40)    NOT NULL,
    validation_stage   VARCHAR(10)    NULL,   -- PRE | POST
    status             VARCHAR(10)    NOT NULL,
    failure_action     VARCHAR(10)    NULL,
    severity           VARCHAR(10)    NULL,
    expected_value     NVARCHAR(400)  NULL,
    actual_value       NVARCHAR(400)  NULL,
    failed_row_count   BIGINT         NULL,
    error_message      NVARCHAR(4000) NULL,
    created_datetime   DATETIME2(3)   NOT NULL CONSTRAINT df_validation_created DEFAULT SYSUTCDATETIME(),
    CONSTRAINT ck_validation_status CHECK (status IN ('PASSED', 'FAILED', 'WARNING', 'IGNORED'))
);
