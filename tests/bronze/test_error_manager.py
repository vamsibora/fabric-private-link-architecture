"""error_manager.py: retryable classification, sanitisation, retry loop
(spec section 38: do not blindly retry every error)."""

import pytest

from notebooks.bronze import error_manager as em


class FakePyodbcError(Exception):
    """pyodbc errors carry (SQLSTATE, message-with-native-code)."""


@pytest.mark.parametrize(
    "exc",
    [
        FakePyodbcError("08S01", "[Microsoft][ODBC Driver 18] TCP Provider: connection reset (10054)"),
        FakePyodbcError("42000", "Database 'x' is not currently available. (40613)"),
        TimeoutError("Gateway timeout while reading from source"),
        RuntimeError("io.delta.exceptions.ConcurrentAppendException: Files were added"),
        RuntimeError("HTTP 429 Too Many Requests"),
        em.TransientError("capacity throttled"),
    ],
)
def test_transient_errors_are_retryable(exc):
    assert em.is_retryable(exc) is True


@pytest.mark.parametrize(
    "exc",
    [
        RuntimeError("[UNRESOLVED_COLUMN.WITH_SUGGESTION] A column cannot be resolved: Emial"),
        RuntimeError("[CAST_INVALID_INPUT] The value 'abc' cannot be cast to INT"),
        FakePyodbcError("42S02", "Invalid object name 'dbo.Custmer'. (208)"),
        em.MetadataError("missing primary key"),
        em.ValidationFailedError("1 FAIL rule"),
        em.LandingFileExistsError("exists"),
        ValueError("something unexpected"),   # unknown -> NOT retried
    ],
)
def test_non_transient_errors_are_not_retried(exc):
    assert em.is_retryable(exc) is False


def test_error_code_keeps_original_source_code():
    assert em.extract_error_code(FakePyodbcError("08S01", "reset (10054)")) == "08S01:10054"
    assert em.extract_error_code(em.ValidationFailedError("x")) == "VALIDATION_FAILED"
    assert em.extract_error_code(KeyError("k")) == "KeyError"


def test_sanitise_message_strips_source_values():
    raw = ("Cast failed for 'john.smith@contoso.com' in row with Phone 07700900123, owner jane@contoso.com "
           "and value 'Birmingham Road'")
    clean = em.sanitise_message(raw)
    for secret in ("john.smith", "07700900123", "jane@", "Birmingham"):
        assert secret not in clean
    assert clean == ("Cast failed for '<redacted>' in row with Phone <redacted-number>, owner <redacted-email> "
                     "and value '<redacted>'")
    assert len(em.sanitise_message("x" * 5000)) == 4000


def test_classify_carries_stage_and_sanitised_trace():
    try:
        raise em.StagingIntegrityError("staging holds 3 row(s) from another run", stage=em.STAGE_STAGING)
    except em.StagingIntegrityError as ex:
        info = em.classify(ex)
    assert info.stage == "STAGING" and info.error_code == "STAGING_INTEGRITY" and info.is_retryable is False
    assert "StagingIntegrityError" in info.stack_trace


def test_with_retry_retries_only_retryable_errors_with_backoff():
    calls, sleeps, retried = [], [], []

    def flaky(attempt):
        calls.append(attempt)
        if attempt < 3:
            raise TimeoutError("timed out")
        return "ok"

    result = em.with_retry(flaky, True, 3, 10, on_retry=lambda n, e: retried.append(n), sleep=sleeps.append)
    assert result == "ok" and calls == [1, 2, 3] and retried == [1, 2] and sleeps == [10, 20]


def test_with_retry_does_not_retry_non_retryable():
    calls = []

    def broken(attempt):
        calls.append(attempt)
        raise em.MetadataError("bad")

    with pytest.raises(em.MetadataError):
        em.with_retry(broken, True, 5, 0, sleep=lambda s: None)
    assert calls == [1]


def test_with_retry_gives_up_after_max_and_respects_disabled():
    calls = []

    def always_transient(attempt):
        calls.append(attempt)
        raise TimeoutError("timeout")

    with pytest.raises(TimeoutError):
        em.with_retry(always_transient, True, 2, 0, sleep=lambda s: None)
    assert calls == [1, 2, 3]

    calls.clear()
    with pytest.raises(TimeoutError):
        em.with_retry(always_transient, False, 5, 0, sleep=lambda s: None)
    assert calls == [1]
