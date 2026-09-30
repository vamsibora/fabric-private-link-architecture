# 13 — Audit Manager and Error Manager (spec §38, §55, change 2)

```text
Context: 00_master_context.md. Reference: notebooks/bronze/audit_manager.py, error_manager.py.

AuditManager(connection_string, RunContext, critical, enabled, connect, fallback_writer)
writes to the central audit SQL Database ONLY through audit.usp_* stored procedures, the same
ones the pipelines call, using named parameters (EXEC [audit].[p] @a = ?, ...).
- FAIL FAST (AuditConnectionError): start_run, start_entity_run, get_run_entities.
- FAIL SOFT (return bool): complete_run, update_entity_run, complete_entity_run,
  log_activity, log_error, log_validation, log_file, previous_row_count.
  On failure: write a JSON fallback under Files/_framework_fallback/audit/<kind>/ plus
  logger.critical. If audit_failure_is_critical, raise AuditCriticalError AFTER the fallback.
- A non-critical audit failure must never turn a successful Bronze load into a failed one.
- One pyodbc connection per thread (threading.local); reconnect once on failure.
- Capture workspace_id/name, environment, pipeline and notebook names from RunContext.
- enabled = False (audit_enabled off) -> every call is a no-op.

error_manager:
- FrameworkError subclasses: MetadataError, ValidationFailedError, StagingIntegrityError,
  LandingFileExistsError, WatermarkConflictError (all non-retryable); TransientError
  (retryable); AuditConnectionError; AuditCriticalError.
- is_retryable:
  - SQL transient error numbers and SQLSTATEs;
  - timeout, throttling, 429/503 and Delta Concurrent* text;
  - schema, syntax, permission and cast errors are non-retryable;
  - anything unknown is NON-retryable. Never blindly retry.
- extract_error_code keeps the ORIGINAL code (SQLSTATE:native, the Spark error class).
- sanitise_message redacts emails, long digit runs and quoted literals before anything reaches
  audit.
- with_retry(fn, retry_enabled, max_retry_count, retry_delay_seconds): linear back-off,
  retryable errors only.

Tests: tests/bronze/test_audit_manager.py and test_error_manager.py (MagicMock connection)
cover the EXEC text and named params, fail-fast raising, fail-soft fallback, critical
escalation, the disabled no-op, reconnect, sanitisation, classification per error family, and
retry counts and delays.
Report: what you could NOT verify live.
```
