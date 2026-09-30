-- audit.vw_entity_status -- latest attempt per entity: "Which entities
-- failed / succeeded? What were the source and Bronze row counts?"
CREATE OR ALTER VIEW [audit].[vw_entity_status]
AS
WITH ranked AS
(
    SELECT
        er.*,
        r.environment,
        ROW_NUMBER() OVER (PARTITION BY r.environment, er.entity_id ORDER BY er.start_datetime DESC) AS rn
    FROM [audit].[entity_run] AS er
    JOIN [audit].[run] AS r ON r.run_id = er.run_id
)
SELECT
    environment,
    entity_id,
    source_system,
    source_schema,
    source_table,
    target_schema,
    target_table,
    load_type,
    write_strategy,
    landing_enabled,
    run_id,
    entity_run_id,
    status,
    attempt_number,
    start_datetime,
    end_datetime,
    source_row_count,
    staging_row_count,
    inserted_row_count,
    updated_row_count,
    deleted_row_count,
    rejected_row_count,
    bronze_row_count,
    watermark_before,
    watermark_after,
    error_message
FROM ranked
WHERE rn = 1;
