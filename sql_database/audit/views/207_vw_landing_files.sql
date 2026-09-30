-- audit.vw_landing_files -- "Which landing files were created?" and which
-- are still replayable (CREATED/FAILED, i.e. not yet processed).
CREATE OR ALTER VIEW [audit].[vw_landing_files]
AS
SELECT
    f.file_id,
    r.environment,
    f.run_id,
    f.entity_run_id,
    f.entity_id,
    f.source_system,
    f.source_table,
    f.file_container,
    f.file_path,
    f.file_name,
    f.file_size_bytes,
    f.row_count,
    f.file_created_datetime,
    f.status,
    f.processed_run_id,
    f.processed_datetime,
    CAST(CASE WHEN f.status IN ('CREATED', 'FAILED') THEN 1 ELSE 0 END AS BIT) AS is_replayable
FROM [audit].[file] AS f
JOIN [audit].[run] AS r ON r.run_id = f.run_id;
