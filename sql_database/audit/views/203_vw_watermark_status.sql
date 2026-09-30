-- audit.vw_watermark_status -- "What is the latest watermark? Which entities
-- have not loaded recently / have stale watermarks?"
-- Based on the last SUCCEEDED entity_run per environment/entity (the audit
-- copy of what was committed to control.watermark). An entity is flagged
-- stale when its last success is older than 24 hours or its watermark has
-- not moved across its last 5 successful runs.
CREATE OR ALTER VIEW [audit].[vw_watermark_status]
AS
WITH successes AS
(
    SELECT
        r.environment,
        er.entity_id,
        er.source_system,
        er.source_table,
        er.run_id,
        er.end_datetime,
        er.watermark_after,
        ROW_NUMBER() OVER (PARTITION BY r.environment, er.entity_id ORDER BY er.end_datetime DESC) AS rn
    FROM [audit].[entity_run] AS er
    JOIN [audit].[run] AS r ON r.run_id = er.run_id
    WHERE er.status = 'SUCCEEDED'
),
movement AS
(
    SELECT environment, entity_id, COUNT(DISTINCT watermark_after) AS distinct_recent_watermarks
    FROM successes
    WHERE rn <= 5
    GROUP BY environment, entity_id
)
SELECT
    s.environment,
    s.entity_id,
    s.source_system,
    s.source_table,
    s.watermark_after                                        AS latest_watermark,
    s.run_id                                                 AS last_successful_run_id,
    s.end_datetime                                           AS last_success_datetime,
    DATEDIFF(HOUR, s.end_datetime, SYSUTCDATETIME())         AS hours_since_last_success,
    CAST(CASE WHEN DATEDIFF(HOUR, s.end_datetime, SYSUTCDATETIME()) > 24 THEN 1 ELSE 0 END AS BIT) AS is_not_loaded_recently,
    CAST(CASE WHEN m.distinct_recent_watermarks = 1
               AND (SELECT COUNT(*) FROM successes s2
                    WHERE s2.environment = s.environment AND s2.entity_id = s.entity_id AND s2.rn <= 5) = 5
              THEN 1 ELSE 0 END AS BIT)                      AS is_watermark_stale
FROM successes AS s
JOIN movement AS m ON m.environment = s.environment AND m.entity_id = s.entity_id
WHERE s.rn = 1;
