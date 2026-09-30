-- audit.usp_start_entity_run: create the entity_run row, or -- when the same
-- entity is retried within the same run -- reopen it and increment
-- attempt_number. Called by the extract child pipeline before the copy, and
-- by the framework notebook in standalone/replay mode.
CREATE OR ALTER PROCEDURE [audit].[usp_start_entity_run]
    @entity_run_id    VARCHAR(80),
    @run_id           VARCHAR(64),
    @entity_id        BIGINT,
    @source_system    VARCHAR(100),
    @source_schema    VARCHAR(128)  = NULL,
    @source_table     VARCHAR(256),
    @target_schema    VARCHAR(128)  = NULL,
    @target_table     VARCHAR(256),
    @load_type        VARCHAR(20)   = NULL,
    @landing_enabled  BIT,
    @write_strategy   VARCHAR(20)   = NULL,
    @watermark_before NVARCHAR(100) = NULL,
    @pipeline_run_id  VARCHAR(64)   = NULL,
    @status           VARCHAR(20)   = 'EXTRACTING'
AS
BEGIN
    SET NOCOUNT ON;

    IF EXISTS (SELECT 1 FROM [audit].[entity_run] WHERE entity_run_id = @entity_run_id)
    BEGIN
        UPDATE [audit].[entity_run]
        SET status           = @status,
            attempt_number   = attempt_number + 1,
            end_datetime     = NULL,
            error_message    = NULL,
            landing_enabled  = @landing_enabled,
            watermark_before = COALESCE(@watermark_before, watermark_before),
            write_strategy   = COALESCE(@write_strategy, write_strategy),
            pipeline_run_id  = COALESCE(@pipeline_run_id, pipeline_run_id),
            updated_datetime = SYSUTCDATETIME()
        WHERE entity_run_id = @entity_run_id;
    END
    ELSE
    BEGIN
        INSERT INTO [audit].[entity_run]
            (entity_run_id, run_id, entity_id, source_system, source_schema, source_table, target_schema,
             target_table, load_type, write_strategy, landing_enabled, status, watermark_before, pipeline_run_id)
        VALUES
            (@entity_run_id, @run_id, @entity_id, @source_system, @source_schema, @source_table, @target_schema,
             @target_table, @load_type, @write_strategy, @landing_enabled, @status, @watermark_before, @pipeline_run_id);
    END

    SELECT entity_run_id, attempt_number FROM [audit].[entity_run] WHERE entity_run_id = @entity_run_id;
END;
