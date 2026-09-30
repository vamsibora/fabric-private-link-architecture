-- audit.vw_load_performance -- "Which pipelines/entities are slow?"
-- Duration and throughput per completed entity run, plus the copy and
-- write activity durations recorded in audit.activity.
CREATE OR ALTER VIEW [audit].[vw_load_performance]
AS
SELECT
    r.environment,
    r.pipeline_name,
    er.run_id,
    er.entity_run_id,
    er.entity_id,
    er.source_system,
    er.source_table,
    er.write_strategy,
    er.landing_enabled,
    er.status,
    er.start_datetime,
    er.end_datetime,
    DATEDIFF_BIG(MILLISECOND, er.start_datetime, er.end_datetime) / 1000.0 AS duration_seconds,
    er.source_row_count,
    CASE WHEN DATEDIFF_BIG(MILLISECOND, er.start_datetime, er.end_datetime) > 0
         THEN er.source_row_count * 1000.0 / DATEDIFF_BIG(MILLISECOND, er.start_datetime, er.end_datetime)
    END                                                                  AS rows_per_second,
    (SELECT SUM(a.duration_ms) FROM [audit].[activity] a
     WHERE a.entity_run_id = er.entity_run_id AND a.activity_type LIKE 'COPY%')   AS copy_duration_ms,
    (SELECT SUM(a.duration_ms) FROM [audit].[activity] a
     WHERE a.entity_run_id = er.entity_run_id AND a.activity_type IN ('MERGE_COMPLETED', 'HISTORY_COMPLETED', 'APPEND_COMPLETED', 'REPLACE_COMPLETED')) AS write_duration_ms
FROM [audit].[entity_run] AS er
JOIN [audit].[run] AS r ON r.run_id = er.run_id
WHERE er.end_datetime IS NOT NULL;
