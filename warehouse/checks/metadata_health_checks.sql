-- Metadata health checks for the control schema -- READ ONLY.
-- NOT a migration root: migration_runner never applies this file. Run it by
-- hand in the Warehouse SQL editor after every metadata deployment
-- (docs/runbooks/02_metadata_maintenance.md -> "Validate").
--
-- Every query returns the PROBLEM rows; an empty result means the check
-- passed. The framework's config_loader.validate_entity applies the same
-- rules at run time and fails the run (MetadataError) on any of them.

-- 1. Active entity whose source system is missing or inactive
SELECT 'entity without active source_system' AS problem, e.entity_id, e.source_table
FROM [control].[entity] e
LEFT JOIN [control].[source_system] s ON s.source_system_id = e.source_system_id AND s.active_flag = 1
WHERE e.active_flag = 1 AND s.source_system_id IS NULL;

-- 2. Active entity with no active columns
SELECT 'entity without columns' AS problem, e.entity_id, e.source_table
FROM [control].[entity] e
WHERE e.active_flag = 1
  AND NOT EXISTS (SELECT 1 FROM [control].[entity_column] c WHERE c.entity_id = e.entity_id AND c.active_flag = 1);

-- 3. MERGE/HISTORY entity without a primary key
SELECT 'MERGE/HISTORY without primary_key' AS problem, e.entity_id, e.source_table
FROM [control].[entity] e
WHERE e.active_flag = 1 AND (e.merge_required = 1 OR e.history_required = 1)
  AND (e.primary_key IS NULL OR LTRIM(RTRIM(e.primary_key)) = '');

-- 4. primary_key lists a column that is not an active target_column
SELECT 'primary_key column not in entity_column' AS problem, e.entity_id, LTRIM(RTRIM(k.value)) AS key_column
FROM [control].[entity] e
CROSS APPLY STRING_SPLIT(e.primary_key, ',') k
WHERE e.active_flag = 1
  AND NOT EXISTS (SELECT 1 FROM [control].[entity_column] c
                  WHERE c.entity_id = e.entity_id AND c.active_flag = 1 AND c.target_column = LTRIM(RTRIM(k.value)));

-- 5. primary_key_flag disagrees with entity.primary_key
SELECT 'primary_key_flag set but column not in entity.primary_key' AS problem, c.entity_id, c.target_column
FROM [control].[entity_column] c
JOIN [control].[entity] e ON e.entity_id = c.entity_id AND e.active_flag = 1
WHERE c.active_flag = 1 AND c.primary_key_flag = 1
  AND NOT EXISTS (SELECT 1 FROM STRING_SPLIT(e.primary_key, ',') k WHERE LTRIM(RTRIM(k.value)) = c.target_column);

-- 6. INCREMENTAL without a valid watermark definition
SELECT 'INCREMENTAL watermark definition invalid' AS problem, e.entity_id, e.watermark_column, e.watermark_type
FROM [control].[entity] e
WHERE e.active_flag = 1 AND e.load_type = 'INCREMENTAL'
  AND (e.watermark_column IS NULL
       OR e.watermark_type NOT IN ('DATETIME', 'NUMERIC', 'STRING')
       OR NOT EXISTS (SELECT 1 FROM [control].[entity_column] c
                      WHERE c.entity_id = e.entity_id AND c.active_flag = 1
                        AND (c.source_column = e.watermark_column OR c.watermark_flag = 1)));

-- 7. Active entity without a watermark row (runtime state)
SELECT 'missing control.watermark row' AS problem, e.entity_id, e.source_table
FROM [control].[entity] e
WHERE e.active_flag = 1
  AND NOT EXISTS (SELECT 1 FROM [control].[watermark] w WHERE w.entity_id = e.entity_id);

-- 8. HISTORY entity without HASH change detection
SELECT 'history_required without HASH change detection' AS problem, e.entity_id, e.change_detection_method
FROM [control].[entity] e
WHERE e.active_flag = 1 AND e.history_required = 1 AND e.change_detection_method <> 'HASH';

-- 9. Column references a missing/inactive anonymisation rule
SELECT 'anonymisation_rule_id not found/inactive' AS problem, c.entity_id, c.target_column, c.anonymisation_rule_id
FROM [control].[entity_column] c
LEFT JOIN [control].[anonymisation_rule] r ON r.anonymisation_rule_id = c.anonymisation_rule_id AND r.active_flag = 1
WHERE c.active_flag = 1 AND c.anonymisation_flag = 1 AND r.anonymisation_rule_id IS NULL;

-- 10. Entity marked anonymisation_required but no column is anonymised (or vice versa)
SELECT 'anonymisation_required inconsistent with columns' AS problem, e.entity_id, e.anonymisation_required
FROM [control].[entity] e
WHERE e.active_flag = 1
  AND e.anonymisation_required <> CASE WHEN EXISTS (SELECT 1 FROM [control].[entity_column] c
                                                    WHERE c.entity_id = e.entity_id AND c.active_flag = 1
                                                      AND c.anonymisation_flag = 1) THEN 1 ELSE 0 END;

-- 11. Invalid validation rule settings
SELECT 'validation_rule invalid' AS problem, v.validation_rule_id, v.rule_type, v.failure_action, v.validation_stage
FROM [control].[validation_rule] v
WHERE v.active_flag = 1
  AND (v.failure_action NOT IN ('FAIL', 'WARN', 'IGNORE')
       OR v.validation_stage NOT IN ('PRE', 'POST')
       OR v.rule_type NOT IN ('PRIMARY_KEY_NULL', 'DUPLICATE_PRIMARY_KEY', 'MANDATORY_COLUMN_NULL', 'COLUMN_MISSING',
                              'DATA_TYPE_MISMATCH', 'WATERMARK_INVALID', 'ROW_COUNT_ANOMALY', 'CUSTOM')
       OR (v.rule_type = 'CUSTOM' AND (v.expression IS NULL OR v.expression = ''))
       OR (v.rule_type IN ('MANDATORY_COLUMN_NULL', 'DATA_TYPE_MISMATCH') AND v.column_name IS NULL));

-- 12. Duplicate natural keys (constraints are NOT ENFORCED in Fabric DW)
SELECT 'duplicate entity target' AS problem, target_schema, target_table, COUNT(*) AS n
FROM [control].[entity] GROUP BY target_schema, target_table HAVING COUNT(*) > 1;
SELECT 'duplicate entity_column target' AS problem, entity_id, target_column, COUNT(*) AS n
FROM [control].[entity_column] GROUP BY entity_id, target_column HAVING COUNT(*) > 1;
SELECT 'duplicate framework_configuration key' AS problem, environment, config_key, COUNT(*) AS n
FROM [control].[framework_configuration] GROUP BY environment, config_key HAVING COUNT(*) > 1;

-- 13. Every environment has the same framework_configuration keys
SELECT 'framework_configuration key missing for environment' AS problem, e.environment, k.config_key
FROM (SELECT DISTINCT environment FROM [control].[framework_configuration]) e
CROSS JOIN (SELECT DISTINCT config_key FROM [control].[framework_configuration]) k
WHERE NOT EXISTS (SELECT 1 FROM [control].[framework_configuration] f
                  WHERE f.environment = e.environment AND f.config_key = k.config_key AND f.active_flag = 1);

-- 14. Active source system with no connection row for an environment in use
SELECT 'source_connection missing' AS problem, s.source_system_id, env.environment
FROM [control].[source_system] s
CROSS JOIN (SELECT DISTINCT environment FROM [control].[framework_configuration]) env
WHERE s.active_flag = 1
  AND NOT EXISTS (SELECT 1 FROM [control].[source_connection] c
                  WHERE c.source_system_id = s.source_system_id AND c.environment = env.environment AND c.active_flag = 1);

-- 15. Source connection not configured for an environment (the extract pipeline binds its
--     Copy source to fabric_connection_id dynamically and fails fast when it is NULL)
SELECT 'fabric_connection_id not set' AS problem, c.source_connection_id, c.source_system_id, c.environment
FROM [control].[source_connection] c
JOIN [control].[source_system] s ON s.source_system_id = c.source_system_id AND s.active_flag = 1
WHERE c.active_flag = 1 AND s.source_type = 'SQLSERVER'
  AND (c.fabric_connection_id IS NULL OR LTRIM(RTRIM(c.fabric_connection_id)) = '');

-- 16. Final smoke check: the pipeline Lookup resolves (inspect source_query per entity)
SELECT entity_id, source_system_name, source_table, landing_enabled, landing_folder, source_query
FROM [control].[fn_active_entities]('DEV', NULL)
ORDER BY processing_priority, entity_id;
