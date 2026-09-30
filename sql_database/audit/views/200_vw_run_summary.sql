-- audit.vw_run_summary -- "What runs are executing? How did recent runs go?"
CREATE OR ALTER VIEW [audit].[vw_run_summary]
AS
SELECT
    r.run_id,
    r.framework_name,
    r.environment,
    r.workspace_name,
    r.pipeline_name,
    r.trigger_type,
    r.entity_group,
    r.status,
    r.start_datetime,
    r.end_datetime,
    DATEDIFF(SECOND, r.start_datetime, COALESCE(r.end_datetime, SYSUTCDATETIME())) AS duration_seconds,
    CAST(CASE WHEN r.status IN ('STARTED', 'RUNNING') THEN 1 ELSE 0 END AS BIT)     AS is_executing,
    r.total_entities,
    r.successful_entities,
    r.failed_entities,
    r.skipped_entities,
    (SELECT COUNT(*) FROM [audit].[error] e WHERE e.run_id = r.run_id)              AS error_count,
    r.message
FROM [audit].[run] AS r;
