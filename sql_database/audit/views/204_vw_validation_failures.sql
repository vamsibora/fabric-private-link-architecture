-- audit.vw_validation_failures -- "Which validations are failing?"
-- Non-PASSED validation results with their entity context.
CREATE OR ALTER VIEW [audit].[vw_validation_failures]
AS
SELECT
    v.validation_id,
    v.created_datetime,
    r.environment,
    v.run_id,
    v.entity_run_id,
    er.entity_id,
    er.source_system,
    er.source_table,
    v.validation_rule_id,
    v.validation_rule,
    v.validation_type,
    v.validation_stage,
    v.status,
    v.failure_action,
    v.severity,
    v.expected_value,
    v.actual_value,
    v.failed_row_count,
    v.error_message
FROM [audit].[validation] AS v
JOIN [audit].[run] AS r ON r.run_id = v.run_id
JOIN [audit].[entity_run] AS er ON er.entity_run_id = v.entity_run_id
WHERE v.status IN ('FAILED', 'WARNING');
