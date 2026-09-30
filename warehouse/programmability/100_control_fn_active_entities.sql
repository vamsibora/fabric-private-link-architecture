-- control.fn_active_entities(@environment, @entity_group)
--
-- Single source for the orchestration pipeline's Lookup: one row per active
-- entity with everything the extract child pipeline needs, including the
-- fully resolved source query (watermark already applied) and the landing
-- location. Pipelines orchestrate -- all the metadata logic lives here, not
-- in pipeline expressions.
--
-- REPEATABLE script (CREATE OR ALTER): migration_runner re-applies it
-- whenever its checksum changes.
--
-- Watermark literal rules (must match watermark_manager.format_watermark):
--   DATETIME -> CAST('yyyy-MM-dd HH:mm:ss.ffffff' AS DATETIME2(7))  (safe against
--               datetime columns, which reject >3 fractional digits in an implicit cast)
--   NUMERIC  -> the value, unquoted
--   STRING   -> quoted, with embedded quotes doubled
-- landing_enabled is the entity flag ANDed with the environment's
-- landing_globally_enabled switch.
-- source_connection_id is the environment's Fabric connection for the entity's
-- source system; the extract pipeline binds its Copy source to it dynamically.
CREATE OR ALTER FUNCTION [control].[fn_active_entities]
(
    @environment  VARCHAR(10),
    @entity_group VARCHAR(100)
)
RETURNS TABLE
AS
RETURN
SELECT
    e.entity_id,
    ss.source_system_id,
    ss.source_system_name,
    ss.source_type,
    e.source_schema,
    e.source_table,
    e.target_schema,
    e.target_table,
    e.staging_schema,
    e.staging_table,
    e.entity_group,
    e.load_type,
    CAST(CASE WHEN e.landing_enabled = 1 AND COALESCE(fc_land.config_value, 'true') = 'true'
              THEN 1 ELSE 0 END AS BIT)                                  AS landing_enabled,
    COALESCE(fc_container.config_value, 'landing')                        AS landing_container,
    CONCAT(ss.source_system_name, '/', e.source_table)                    AS landing_folder,
    e.history_required,
    e.merge_required,
    e.primary_key,
    e.watermark_column,
    e.watermark_type,
    w.last_successful_watermark,
    sc.connection_reference,
    sc.database_name                                                      AS source_database,
    sc.fabric_connection_id                                               AS source_connection_id,  -- Fabric connection GUID used by the extract Copy (parameterised connection)
    e.processing_priority,
    COALESCE(lc.retry_enabled, CAST(0 AS BIT))                            AS retry_enabled,
    COALESCE(lc.max_retry_count, 0)                                       AS max_retry_count,
    COALESCE(lc.retry_delay_seconds, 30)                                  AS retry_delay_seconds,
    CASE
        WHEN lc.source_query_override IS NOT NULL
            THEN REPLACE(lc.source_query_override, '{watermark}', COALESCE(wm.watermark_literal, wm.watermark_floor))
        ELSE CONCAT(
            'SELECT ', COALESCE(cols.select_list, '*'),
            ' FROM ', CASE WHEN e.source_schema IS NULL THEN '' ELSE CONCAT('[', e.source_schema, '].') END,
            '[', e.source_table, ']',
            CASE
                WHEN pred.incremental_predicate IS NULL AND lc.source_filter IS NULL THEN ''
                WHEN pred.incremental_predicate IS NULL THEN CONCAT(' WHERE (', lc.source_filter, ')')
                WHEN lc.source_filter IS NULL THEN CONCAT(' WHERE ', pred.incremental_predicate)
                ELSE CONCAT(' WHERE ', pred.incremental_predicate, ' AND (', lc.source_filter, ')')
            END)
    END                                                                   AS source_query
FROM [control].[entity] AS e
JOIN [control].[source_system] AS ss
    ON ss.source_system_id = e.source_system_id
   AND ss.active_flag = 1
LEFT JOIN [control].[source_connection] AS sc
    ON sc.source_system_id = ss.source_system_id
   AND sc.environment = @environment
   AND sc.active_flag = 1
LEFT JOIN [control].[load_configuration] AS lc
    ON lc.entity_id = e.entity_id
   AND lc.active_flag = 1
LEFT JOIN [control].[watermark] AS w
    ON w.entity_id = e.entity_id
LEFT JOIN [control].[framework_configuration] AS fc_land
    ON fc_land.environment = @environment
   AND fc_land.config_key = 'landing_globally_enabled'
   AND fc_land.active_flag = 1
LEFT JOIN [control].[framework_configuration] AS fc_container
    ON fc_container.environment = @environment
   AND fc_container.config_key = 'landing_container'
   AND fc_container.active_flag = 1
CROSS APPLY (
    SELECT
        CASE
            WHEN w.last_successful_watermark IS NULL THEN NULL
            WHEN e.watermark_type = 'NUMERIC' THEN w.last_successful_watermark
            WHEN e.watermark_type = 'DATETIME' THEN CONCAT('CAST(''', w.last_successful_watermark, ''' AS DATETIME2(7))')
            ELSE CONCAT('''', REPLACE(w.last_successful_watermark, '''', ''''''), '''')
        END AS watermark_literal,
        CASE
            WHEN e.watermark_type = 'NUMERIC' THEN '-999999999999999999'
            WHEN e.watermark_type = 'DATETIME' THEN 'CAST(''1900-01-01 00:00:00.000000'' AS DATETIME2(7))'
            ELSE ''''''
        END AS watermark_floor
) AS wm
CROSS APPLY (
    SELECT CASE
               WHEN e.load_type = 'INCREMENTAL' AND wm.watermark_literal IS NOT NULL
                   THEN CONCAT('[', e.watermark_column, '] > ', wm.watermark_literal)
           END AS incremental_predicate
) AS pred
OUTER APPLY (
    SELECT STRING_AGG(CONCAT('[', c.source_column, ']'), ', ') WITHIN GROUP (ORDER BY c.ordinal_position) AS select_list
    FROM [control].[entity_column] AS c
    WHERE c.entity_id = e.entity_id
      AND c.active_flag = 1
) AS cols
WHERE e.active_flag = 1
  AND (@entity_group IS NULL OR e.entity_group = @entity_group);
