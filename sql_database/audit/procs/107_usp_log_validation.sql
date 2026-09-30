-- audit.usp_log_validation: append one validation result.
CREATE OR ALTER PROCEDURE [audit].[usp_log_validation]
    @run_id             VARCHAR(64),
    @entity_run_id      VARCHAR(80),
    @validation_rule_id BIGINT         = NULL,
    @validation_rule    NVARCHAR(100),
    @validation_type    VARCHAR(40),
    @validation_stage   VARCHAR(10)    = NULL,
    @status             VARCHAR(10),
    @failure_action     VARCHAR(10)    = NULL,
    @severity           VARCHAR(10)    = NULL,
    @expected_value     NVARCHAR(400)  = NULL,
    @actual_value       NVARCHAR(400)  = NULL,
    @failed_row_count   BIGINT         = NULL,
    @error_message      NVARCHAR(4000) = NULL
AS
BEGIN
    SET NOCOUNT ON;

    INSERT INTO [audit].[validation]
        (run_id, entity_run_id, validation_rule_id, validation_rule, validation_type, validation_stage,
         status, failure_action, severity, expected_value, actual_value, failed_row_count, error_message)
    VALUES
        (@run_id, @entity_run_id, @validation_rule_id, @validation_rule, @validation_type, @validation_stage,
         @status, @failure_action, @severity, @expected_value, @actual_value, @failed_row_count, @error_message);
END;
