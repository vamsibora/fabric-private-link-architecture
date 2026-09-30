-- audit.usp_get_entity_baseline: the entity's most recent SUCCEEDED run in
-- this environment (excluding the current run) -- the baseline for
-- ROW_COUNT_ANOMALY validation.
CREATE OR ALTER PROCEDURE [audit].[usp_get_entity_baseline]
    @entity_id      BIGINT,
    @environment    VARCHAR(10),
    @exclude_run_id VARCHAR(64) = NULL
AS
BEGIN
    SET NOCOUNT ON;

    SELECT TOP (1)
        er.staging_row_count,
        er.source_row_count,
        er.bronze_row_count,
        er.watermark_after,
        er.end_datetime
    FROM [audit].[entity_run] AS er
    JOIN [audit].[run] AS r ON r.run_id = er.run_id
    WHERE er.entity_id = @entity_id
      AND r.environment = @environment
      AND er.status = 'SUCCEEDED'
      AND (@exclude_run_id IS NULL OR er.run_id <> @exclude_run_id)
    ORDER BY er.end_datetime DESC;
END;
