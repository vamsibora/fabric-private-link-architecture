# 10 — Error Handling and Retry

## Failure flow

```text
Run started ─► Entity started ─► Extract ─► Stage ─► Validate ─► Transform ─► Bronze commit
            ─► POST validation ─► Watermark commit ─► Entity SUCCEEDED

any failure:
  classify (error_manager.classify) ─► audit.error (sanitised message, original error_code,
  is_retryable, attempt_number, stack trace)
  ─► retryable and attempts left? ─► RETRY_SCHEDULED activity, sleep delay*attempt, retry in place
  ─► else entity FAILED, watermark_after = watermark_before (UNCHANGED)
         landing file → FAILED (still replayable)
  ─► other entities continue (continue_on_entity_failure) ─► run PARTIAL_SUCCESS / FAILED
```

Every write strategy is idempotent and the watermark only moves on success,
so an entity can always be retried or re-run.

## Exceptions (`error_manager.py`)

| Exception | Retryable | Raised when |
|---|---|---|
| `MetadataError` | no | Invalid/inconsistent control metadata (`config_loader.validate_entity`), unknown rule types, missing salt resolver |
| `ValidationFailedError` | no | FAIL-action validation failed |
| `StagingIntegrityError` | no | Staging holds another run's rows, or the count ≠ rowsCopied |
| `LandingFileExistsError` | no | A landing file would be overwritten |
| `WatermarkConflictError` | no | control.watermark changed concurrently |
| `TransientError` | yes | Explicit transient failure |
| `AuditConnectionError` | — | A fail-fast audit call failed (run/entity start, entity list) |
| `AuditCriticalError` | — | A fail-soft audit write failed with `audit_failure_is_critical = true` |

## Classification of other exceptions

The framework does not blindly retry every error (spec §38). An error is
**retryable** when any of these match:
- SQL transient error numbers: 40613, 40197, 40501, 49918–49920,
  10928/10929, 10053/10054/10060, 233, 64, 4060, 4221, 1205
- SQLSTATEs: 08S01, 08001, HYT00, HYT01, 40001
- message patterns: timeout, connection reset/refused/closed, temporary,
  transient, 429, 503, service unavailable, throttling, capacity, Delta
  `Concurrent*Exception`, gateway timeout, socket.

It is **non-retryable** for:
- schema/resolution errors (`UNRESOLVED_COLUMN`, `DATATYPE_MISMATCH`,
  `CAST_INVALID_INPUT`, `PARSE_SYNTAX_ERROR`, `TABLE_OR_VIEW_NOT_FOUND`,
  invalid column/object name, incorrect syntax)
- permission and login failures
- **anything unrecognised**.

`error_code` preserves the original code: pyodbc `SQLSTATE:native`, the Spark
`getErrorClass()`, or the framework code.

## Retry configuration

`control.load_configuration`: `retry_enabled`, `max_retry_count` and
`retry_delay_seconds` (linear back-off, delay × attempt). This governs
**framework processing**. Copy activities have their own static activity
policy (`retry: 2`, 60 s), because pipeline activity policies cannot be
expression-driven.

Within a run, audit keeps a single `entity_run` row per entity.
`attempt_number` records the number of attempts, and each failed attempt is
its own `audit.error` row.

## Pipeline-side failures

- **Copy failure:** `usp_log_error` (stage EXTRACT, with the Fabric
  `errorCode`), then `usp_update_entity_run FAILED`, then a Fail activity. The
  entity is not processed. The ForEach continues with other entities, and the
  notebook still runs after the ForEach completes.
- **Landing file exists:** a Fail activity (`LANDING_FILE_EXISTS`), then
  `usp_log_error` + FAILED.
- **Unsupported `source_type`:** `usp_log_error UNSUPPORTED_SOURCE_TYPE`.
- **Notebook or Lookup failure:** `usp_complete_run @status = 'FAILED'`. This
  is a no-op if the notebook already completed the run.

## Sensitive data

`sanitise_message` redacts e-mail addresses, 7+ digit numbers and quoted
literals of 3+ characters from messages and stack traces before they reach
audit or fallback files.
