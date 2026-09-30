-- DEV-ONLY sample audit records (spec section 47: "Create sample audit
-- records"). NOT a migration root -- migration_runner never applies this
-- file. Run by hand against a DEV audit database to exercise the
-- monitoring views; never against UAT/PROD.
--
-- One PARTIAL_SUCCESS run: Customer (landing) succeeded, Product (staging)
-- failed validation.
EXEC [audit].[usp_start_run]
    @run_id = '20260930-081200-ABC123', @framework_name = 'BronzeFramework', @environment = 'DEV',
    @workspace_name = N'ws-engineering-dev', @pipeline_name = N'BronzeOrchestrator',
    @trigger_type = 'MANUAL', @run_timestamp = '20260930081200', @entity_group = 'sales', @total_entities = 2;

EXEC [audit].[usp_start_entity_run]
    @entity_run_id = '20260930-081200-ABC123-E101', @run_id = '20260930-081200-ABC123', @entity_id = 101,
    @source_system = 'SQLServer', @source_schema = 'dbo', @source_table = 'Customer',
    @target_schema = 'sqlserver', @target_table = 'customer', @load_type = 'INCREMENTAL',
    @landing_enabled = 1, @write_strategy = 'HISTORY', @watermark_before = N'2026-09-29 23:59:59.000000';

EXEC [audit].[usp_log_file]
    @run_id = '20260930-081200-ABC123', @entity_run_id = '20260930-081200-ABC123-E101', @entity_id = 101,
    @source_system = 'SQLServer', @source_table = 'Customer', @file_container = 'landing',
    @file_path = N'SQLServer/Customer/Customer_20260930081200.json', @file_name = N'Customer_20260930081200.json',
    @file_size_bytes = 18432, @row_count = 42;

EXEC [audit].[usp_update_entity_run]
    @entity_run_id = '20260930-081200-ABC123-E101', @status = 'EXTRACTED',
    @landing_path = N'SQLServer/Customer/Customer_20260930081200.json', @source_row_count = 42;

EXEC [audit].[usp_log_activity]
    @run_id = '20260930-081200-ABC123', @entity_run_id = '20260930-081200-ABC123-E101',
    @activity_type = 'COPY_COMPLETED', @activity_name = N'CopyToLanding', @status = 'SUCCEEDED',
    @rows_affected = 42, @activity_source = 'PIPELINE';

EXEC [audit].[usp_log_validation]
    @run_id = '20260930-081200-ABC123', @entity_run_id = '20260930-081200-ABC123-E101',
    @validation_rule = N'builtin_primary_key_null', @validation_type = 'PRIMARY_KEY_NULL', @validation_stage = 'PRE',
    @status = 'PASSED', @failure_action = 'FAIL', @expected_value = N'0', @actual_value = N'0', @failed_row_count = 0;

EXEC [audit].[usp_complete_entity_run]
    @entity_run_id = '20260930-081200-ABC123-E101', @status = 'SUCCEEDED', @staging_row_count = 42,
    @inserted_row_count = 40, @updated_row_count = 2, @deleted_row_count = 0, @rejected_row_count = 0,
    @bronze_row_count = 1040, @watermark_after = N'2026-09-30 08:05:13.000000', @write_strategy = 'HISTORY';

EXEC [audit].[usp_start_entity_run]
    @entity_run_id = '20260930-081200-ABC123-E102', @run_id = '20260930-081200-ABC123', @entity_id = 102,
    @source_system = 'SQLServer', @source_schema = 'dbo', @source_table = 'Product',
    @target_schema = 'sqlserver', @target_table = 'product', @load_type = 'INCREMENTAL',
    @landing_enabled = 0, @write_strategy = 'MERGE', @watermark_before = N'2026-09-29 23:00:00.000000';

EXEC [audit].[usp_log_validation]
    @run_id = '20260930-081200-ABC123', @entity_run_id = '20260930-081200-ABC123-E102', @validation_rule_id = 1021,
    @validation_rule = N'product_listprice_non_negative', @validation_type = 'CUSTOM', @validation_stage = 'PRE',
    @status = 'FAILED', @failure_action = 'FAIL', @severity = 'HIGH', @expected_value = N'0', @actual_value = N'3',
    @failed_row_count = 3, @error_message = N'3 row(s) violate: ListPrice IS NULL OR ListPrice >= 0';

EXEC [audit].[usp_log_error]
    @run_id = '20260930-081200-ABC123', @entity_run_id = '20260930-081200-ABC123-E102', @error_stage = 'VALIDATION',
    @error_code = 'VALIDATION_FAILED', @error_message = N'1 FAIL validation rule(s) failed: product_listprice_non_negative',
    @source_system = 'SQLServer', @source_table = 'Product', @target_table = 'sqlserver.product', @is_retryable = 0,
    @attempt_number = 1;

EXEC [audit].[usp_complete_entity_run]
    @entity_run_id = '20260930-081200-ABC123-E102', @status = 'FAILED', @staging_row_count = 17,
    @watermark_after = N'2026-09-29 23:00:00.000000', @write_strategy = 'MERGE',
    @error_message = N'1 FAIL validation rule(s) failed: product_listprice_non_negative';

EXEC [audit].[usp_complete_run] @run_id = '20260930-081200-ABC123';
