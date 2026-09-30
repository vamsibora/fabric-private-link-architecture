-- audit.usp_log_file: record a landing file (status CREATED by the extract
-- pipeline after the copy), or update its status later (PROCESSED /
-- FAILED / REPLAYED by the framework). Keyed on (file_container, file_path),
-- which is unique -- landing files are never overwritten.
CREATE OR ALTER PROCEDURE [audit].[usp_log_file]
    @run_id           VARCHAR(64),
    @entity_run_id    VARCHAR(80)    = NULL,
    @entity_id        BIGINT,
    @source_system    VARCHAR(100),
    @source_table     VARCHAR(256),
    @file_container   VARCHAR(100)   = NULL,
    @file_path        NVARCHAR(1000),
    @file_name        NVARCHAR(400),
    @file_size_bytes  BIGINT         = NULL,
    @row_count        BIGINT         = NULL,
    @status           VARCHAR(20)    = 'CREATED',
    @processed_run_id VARCHAR(64)    = NULL
AS
BEGIN
    SET NOCOUNT ON;

    IF EXISTS (SELECT 1 FROM [audit].[file]
               WHERE file_path = @file_path
                 AND (file_container = @file_container OR (file_container IS NULL AND @file_container IS NULL)))
    BEGIN
        UPDATE [audit].[file]
        SET status             = @status,
            file_size_bytes    = COALESCE(@file_size_bytes, file_size_bytes),
            row_count          = COALESCE(@row_count, row_count),
            processed_run_id   = CASE WHEN @status IN ('PROCESSED', 'REPLAYED') THEN COALESCE(@processed_run_id, @run_id)
                                      ELSE processed_run_id END,
            processed_datetime = CASE WHEN @status IN ('PROCESSED', 'REPLAYED') THEN SYSUTCDATETIME()
                                      ELSE processed_datetime END
        WHERE file_path = @file_path
          AND (file_container = @file_container OR (file_container IS NULL AND @file_container IS NULL));
    END
    ELSE
    BEGIN
        INSERT INTO [audit].[file]
            (run_id, entity_run_id, entity_id, source_system, source_table, file_container, file_path,
             file_name, file_size_bytes, row_count, status)
        VALUES
            (@run_id, @entity_run_id, @entity_id, @source_system, @source_table, @file_container, @file_path,
             @file_name, @file_size_bytes, @row_count, @status);
    END
END;
