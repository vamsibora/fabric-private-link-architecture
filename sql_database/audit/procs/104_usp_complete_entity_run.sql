-- audit.usp_complete_entity_run: final status and row counts for one entity
-- in one run. watermark_after is only ever the COMMITTED watermark (the
-- framework passes the previous value when the entity failed).
CREATE OR ALTER PROCEDURE [audit].[usp_complete_entity_run]
    @entity_run_id      VARCHAR(80),
    @status             VARCHAR(20),
    @staging_row_count  BIGINT         = NULL,
    @inserted_row_count BIGINT         = NULL,
    @updated_row_count  BIGINT         = NULL,
    @deleted_row_count  BIGINT         = NULL,
    @rejected_row_count BIGINT         = NULL,
    @bronze_row_count   BIGINT         = NULL,
    @watermark_after    NVARCHAR(100)  = NULL,
    @write_strategy     VARCHAR(20)    = NULL,
    @error_message      NVARCHAR(4000) = NULL
AS
BEGIN
    SET NOCOUNT ON;

    UPDATE [audit].[entity_run]
    SET status             = @status,
        end_datetime       = SYSUTCDATETIME(),
        staging_row_count  = COALESCE(@staging_row_count, staging_row_count),
        inserted_row_count = @inserted_row_count,
        updated_row_count  = @updated_row_count,
        deleted_row_count  = @deleted_row_count,
        rejected_row_count = @rejected_row_count,
        bronze_row_count   = @bronze_row_count,
        watermark_after    = @watermark_after,
        write_strategy     = COALESCE(@write_strategy, write_strategy),
        error_message      = @error_message,
        updated_datetime   = SYSUTCDATETIME()
    WHERE entity_run_id = @entity_run_id;
END;
