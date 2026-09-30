"""Error Manager: framework exception types, retryable/non-retryable
classification, message sanitisation and the retry loop.

The framework must not blindly retry every error (spec section 38):
transient infrastructure failures are retryable, while metadata, schema,
data-type and validation failures are not -- retrying them only repeats the
failure. Anything unrecognised is treated as NON-retryable.
"""

import re
import time
import traceback
from dataclasses import dataclass
from typing import Callable, Optional, TypeVar

T = TypeVar("T")

# Pipeline/processing stages used in audit.error.error_stage.
STAGE_EXTRACT = "EXTRACT"
STAGE_LANDING = "LANDING"
STAGE_STAGING = "STAGING"
STAGE_VALIDATION = "VALIDATION"
STAGE_ANONYMISATION = "ANONYMISATION"
STAGE_HASH = "HASH"
STAGE_WRITE = "WRITE"
STAGE_WATERMARK = "WATERMARK"
STAGE_AUDIT = "AUDIT"
STAGE_METADATA = "METADATA"
STAGE_ORCHESTRATION = "ORCHESTRATION"


class FrameworkError(Exception):
    """Base class for errors the framework raises deliberately."""

    retryable = False
    error_code = "FRAMEWORK_ERROR"

    def __init__(self, message: str, stage: Optional[str] = None, error_code: Optional[str] = None):
        super().__init__(message)
        self.stage = stage
        if error_code:
            self.error_code = error_code


class MetadataError(FrameworkError):
    """Invalid or inconsistent control metadata. Never retryable."""

    error_code = "INVALID_METADATA"


class ValidationFailedError(FrameworkError):
    """One or more FAIL-action validation rules failed."""

    error_code = "VALIDATION_FAILED"


class StagingIntegrityError(FrameworkError):
    """Staging does not contain exactly this run's rows."""

    error_code = "STAGING_INTEGRITY"


class LandingFileExistsError(FrameworkError):
    """A landing file already exists -- the framework never overwrites one."""

    error_code = "LANDING_FILE_EXISTS"


class WatermarkConflictError(FrameworkError):
    """control.watermark changed underneath this entity run (a concurrent
    run for the same entity). Not retried: the other run owns the entity."""

    error_code = "WATERMARK_CONFLICT"


class TransientError(FrameworkError):
    """Explicitly retryable framework error."""

    retryable = True
    error_code = "TRANSIENT"


class AuditConnectionError(FrameworkError):
    """The audit database could not record a fail-fast event (run/entity start)."""

    error_code = "AUDIT_UNAVAILABLE"


class AuditCriticalError(FrameworkError):
    """A fail-soft audit write failed AND audit_failure_is_critical is on."""

    error_code = "AUDIT_WRITE_FAILED"


# SQL Server / Azure SQL transient error numbers (connection drops,
# throttling, failover, database unavailable).
_TRANSIENT_SQL_ERRORS = {"40613", "40197", "40501", "49918", "49919", "49920", "10928", "10929", "10053", "10054",
                         "10060", "233", "64", "4060", "4221", "1205"}
_TRANSIENT_SQLSTATES = {"08S01", "08001", "HYT00", "HYT01", "40001"}

_TRANSIENT_PATTERNS = re.compile(
    r"timed? ?out|timeout|connection (reset|refused|closed|was forcibly)|temporar(y|ily)|transient|"
    r"too many requests|\b429\b|\b503\b|service unavailable|throttl|capacity|"
    r"ConcurrentAppendException|ConcurrentModificationException|ConcurrentDeleteReadException|"
    r"gateway (timeout|is unreachable)|socket",
    re.IGNORECASE,
)
_NON_RETRYABLE_PATTERNS = re.compile(
    r"UNRESOLVED_COLUMN|cannot resolve|DATATYPE_MISMATCH|CAST_INVALID_INPUT|PARSE_SYNTAX_ERROR|"
    r"schema mismatch|A schema mismatch detected|TABLE_OR_VIEW_NOT_FOUND|Invalid column name|"
    r"Invalid object name|Incorrect syntax|permission|not authorized|Login failed",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ErrorInfo:
    error_code: str
    message: str
    is_retryable: bool
    stage: Optional[str]
    stack_trace: Optional[str]


def extract_error_code(exc: BaseException) -> Optional[str]:
    """Best-effort original error code: pyodbc args[0] is the SQLSTATE and
    the message carries '(<native error number>)'; Spark exceptions expose
    getErrorClass(); FrameworkErrors carry their own code."""
    if isinstance(exc, FrameworkError):
        return exc.error_code
    get_error_class = getattr(exc, "getErrorClass", None)
    if callable(get_error_class):
        try:
            error_class = get_error_class()
            if error_class:
                return str(error_class)
        except Exception:
            pass
    args = getattr(exc, "args", ())
    if args and isinstance(args[0], str) and re.fullmatch(r"[0-9A-Z]{5}", args[0]):
        native = re.search(r"\((\d{2,6})\)", " ".join(str(a) for a in args[1:]))
        return f"{args[0]}:{native.group(1)}" if native else args[0]
    return type(exc).__name__


def is_retryable(exc: BaseException) -> bool:
    if isinstance(exc, FrameworkError):
        return exc.retryable
    code = extract_error_code(exc) or ""
    sqlstate, _, native = code.partition(":")
    if native in _TRANSIENT_SQL_ERRORS or sqlstate in _TRANSIENT_SQLSTATES:
        return True
    text = f"{type(exc).__name__}: {exc}"
    if _NON_RETRYABLE_PATTERNS.search(text):
        return False
    return bool(_TRANSIENT_PATTERNS.search(text))


# Values that must never reach audit tables or logs: e-mail addresses, long
# digit runs (phone/card/account numbers) and quoted literals Spark/SQL echo
# back from the offending row.
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_LONG_DIGITS = re.compile(r"\b\d{7,}\b")
_QUOTED_LITERAL = re.compile(r"'[^']{3,}'")


def sanitise_message(message: str, max_length: int = 4000) -> str:
    # Quoted literals first (a quoted value may itself be an e-mail/number),
    # then bare e-mails and digit runs in what remains.
    text = _QUOTED_LITERAL.sub("'<redacted>'", str(message))
    text = _EMAIL.sub("<redacted-email>", text)
    text = _LONG_DIGITS.sub("<redacted-number>", text)
    return text[:max_length]


def classify(exc: BaseException, stage: Optional[str] = None) -> ErrorInfo:
    stage = stage or getattr(exc, "stage", None)
    trace = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    return ErrorInfo(
        error_code=extract_error_code(exc) or "UNKNOWN",
        message=sanitise_message(f"{type(exc).__name__}: {exc}"),
        is_retryable=is_retryable(exc),
        stage=stage,
        stack_trace=sanitise_message(trace, max_length=32000),
    )


def with_retry(
    fn: Callable[[int], T],
    retry_enabled: bool,
    max_retry_count: int,
    retry_delay_seconds: int,
    on_retry: Optional[Callable[[int, BaseException], None]] = None,
    sleep: Callable[[float], None] = time.sleep,
) -> T:
    """Run fn(attempt_number), retrying only retryable errors, up to
    max_retry_count extra attempts, with linear back-off
    (retry_delay_seconds * attempt). Non-retryable errors and the final
    failure propagate unchanged."""
    attempts = 1 + (max(0, max_retry_count) if retry_enabled else 0)
    for attempt in range(1, attempts + 1):
        try:
            return fn(attempt)
        except Exception as exc:
            if attempt >= attempts or not is_retryable(exc):
                raise
            if on_retry:
                on_retry(attempt, exc)
            sleep(max(0, retry_delay_seconds) * attempt)
    raise AssertionError("unreachable")  # pragma: no cover
