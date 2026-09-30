-- audit.usp_log_activity: append one framework event. duration_ms is
-- derived when both timestamps are supplied.
CREATE OR ALTER PROCEDURE [audit].[usp_log_activity]
    @run_id          VARCHAR(64),
    @entity_run_id   VARCHAR(80)    = NULL,
    @activity_type   VARCHAR(50),
    @activity_name   NVARCHAR(256)  = NULL,
    @status          VARCHAR(20),
    @message         NVARCHAR(4000) = NULL,
    @rows_affected   BIGINT         = NULL,
    @start_datetime  DATETIME2(3)   = NULL,
    @end_datetime    DATETIME2(3)   = NULL,
    @activity_source VARCHAR(20)    = 'NOTEBOOK'
AS
BEGIN
    SET NOCOUNT ON;

    INSERT INTO [audit].[activity]
        (run_id, entity_run_id, activity_type, activity_name, activity_source, start_datetime,
         end_datetime, status, message, rows_affected, duration_ms)
    VALUES
        (@run_id, @entity_run_id, @activity_type, @activity_name, @activity_source, @start_datetime,
         COALESCE(@end_datetime, SYSUTCDATETIME()), @status, @message, @rows_affected,
         CASE WHEN @start_datetime IS NULL THEN NULL
              ELSE DATEDIFF_BIG(MILLISECOND, @start_datetime, COALESCE(@end_datetime, SYSUTCDATETIME())) END);
END;
