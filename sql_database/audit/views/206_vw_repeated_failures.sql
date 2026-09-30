-- audit.vw_repeated_failures -- "Which entities repeatedly fail?"
-- Entities with 3+ FAILED entity runs in the last 7 days.
CREATE OR ALTER VIEW [audit].[vw_repeated_failures]
AS
SELECT
    r.environment,
    er.entity_id,
    er.source_system,
    er.source_table,
    COUNT(*)               AS failures_last_7_days,
    MAX(er.start_datetime) AS last_failure_datetime
FROM [audit].[entity_run] AS er
JOIN [audit].[run] AS r ON r.run_id = er.run_id
WHERE er.status = 'FAILED'
  AND er.start_datetime >= DATEADD(DAY, -7, SYSUTCDATETIME())
GROUP BY r.environment, er.entity_id, er.source_system, er.source_table
HAVING COUNT(*) >= 3;
