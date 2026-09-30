-- audit.vw_recent_errors -- errors from the last 7 days, newest first
-- (ORDER BY belongs in the consuming query). "Which sources have
-- extraction problems?" -> filter error_stage = 'EXTRACT'.
CREATE OR ALTER VIEW [audit].[vw_recent_errors]
AS
SELECT
    e.error_id,
    e.error_datetime,
    r.environment,
    r.workspace_name,
    e.run_id,
    e.entity_run_id,
    e.source_system,
    e.source_table,
    e.target_table,
    e.error_stage,
    e.error_code,
    e.error_message,
    e.is_retryable,
    e.attempt_number
FROM [audit].[error] AS e
JOIN [audit].[run] AS r ON r.run_id = e.run_id
WHERE e.error_datetime >= DATEADD(DAY, -7, SYSUTCDATETIME());
