-- audit.usp_update_entity_run: intermediate status transitions
-- (EXTRACTED / PROCESSING / extract FAILED), recording extraction facts as
-- they become known. NULL parameters leave the existing value unchanged.
-- Terminal statuses (SUCCEEDED/FAILED/SKIPPED/CANCELLED) also set end_datetime.
CREATE OR ALTER PROCEDURE [audit].[usp_update_entity_run]
    @entity_run_id     VARCHAR(80),
    @status            VARCHAR(20),
    @landing_path      NVARCHAR(1000) = NULL,
    @source_row_count  BIGINT         = NULL,
    @staging_row_count BIGINT         = NULL,
    @write_strategy    VARCHAR(20)    = NULL,
    @error_message     NVARCHAR(4000) = NULL
AS
BEGIN
    SET NOCOUNT ON;

    UPDATE [audit].[entity_run]
    SET status            = @status,
        landing_path      = COALESCE(@landing_path, landing_path),
        source_row_count  = COALESCE(@source_row_count, source_row_count),
        staging_row_count = COALESCE(@staging_row_count, staging_row_count),
        write_strategy    = COALESCE(@write_strategy, write_strategy),
        error_message     = COALESCE(@error_message, error_message),
        end_datetime      = CASE WHEN @status IN ('SUCCEEDED', 'FAILED', 'SKIPPED', 'CANCELLED')
                                 THEN SYSUTCDATETIME() ELSE end_datetime END,
        updated_datetime  = SYSUTCDATETIME()
    WHERE entity_run_id = @entity_run_id;
END;
