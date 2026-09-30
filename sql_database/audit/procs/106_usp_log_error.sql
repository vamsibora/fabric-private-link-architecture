-- audit.usp_log_error: append one error. Callers must already have
-- sanitised messages (no source data values) -- see
-- notebooks/bronze/error_manager.sanitise_message.
CREATE OR ALTER PROCEDURE [audit].[usp_log_error]
    @run_id         VARCHAR(64),
    @entity_run_id  VARCHAR(80)    = NULL,
    @error_stage    VARCHAR(50)    = NULL,
    @error_code     VARCHAR(100)   = NULL,
    @error_message  NVARCHAR(4000),
    @source_system  VARCHAR(100)   = NULL,
    @source_table   VARCHAR(256)   = NULL,
    @target_table   VARCHAR(256)   = NULL,
    @is_retryable   BIT            = 0,
    @attempt_number INT            = NULL,
    @stack_trace    NVARCHAR(MAX)  = NULL
AS
BEGIN
    SET NOCOUNT ON;

    INSERT INTO [audit].[error]
        (run_id, entity_run_id, error_stage, error_code, error_message, source_system, source_table,
         target_table, is_retryable, attempt_number, stack_trace)
    VALUES
        (@run_id, @entity_run_id, @error_stage, @error_code, LEFT(@error_message, 4000), @source_system,
         @source_table, @target_table, COALESCE(@is_retryable, 0), @attempt_number, @stack_trace);
END;
