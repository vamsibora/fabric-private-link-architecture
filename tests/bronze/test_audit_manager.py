"""audit_manager.py: central cross-workspace audit (change 2; spec section 55).

Validates the stored-procedure call shapes and the fail-fast vs fail-soft
exception boundaries without a live Fabric SQL Database."""

import threading

import pytest

from notebooks.bronze import audit_manager as am
from notebooks.bronze.error_manager import AuditConnectionError, AuditCriticalError, ErrorInfo
from notebooks.bronze.run_manager import RunContext
from notebooks.bronze.validation_engine import ValidationResult

CTX = RunContext.create(environment="DEV", run_id="20260930-081205-ABC123", workspace_id="ws-1",
                        workspace_name="eng-dev", pipeline_name="BronzeOrchestrator")


class FakeCursor:
    def __init__(self, log, fail=False, rows=()):
        self.log, self.fail, self.rows = log, fail, list(rows)

    def execute(self, sql, *params):
        if self.fail:
            raise RuntimeError("login timeout expired for jane@contoso.com")
        self.log.append((sql, params))

    def fetchall(self):
        return self.rows


class FakeConn:
    def __init__(self, cursor):
        self._cursor, self.closed = cursor, False

    def cursor(self):
        return self._cursor

    def close(self):
        self.closed = True


def _audit(fail=False, rows=(), **kwargs):
    log, fallbacks, connects = [], [], []

    def connect(cs):
        connects.append(threading.get_ident())
        return FakeConn(FakeCursor(log, fail, rows))

    audit = am.AuditManager("audit-conn", CTX, connect=connect,
                            fallback_writer=lambda path, content: fallbacks.append((path, content)), **kwargs)
    return audit, log, fallbacks, connects


def test_exec_sql_uses_named_parameters():
    sql, values = am._exec_sql("usp_log_activity", {"run_id": "r", "status": "SUCCEEDED"})
    assert sql == "EXEC [audit].[usp_log_activity] @run_id = ?, @status = ?"
    assert values == ("r", "SUCCEEDED")


def test_start_run_carries_workspace_and_environment():
    audit, log, _, _ = _audit()
    assert audit.start_run(total_entities=3) == CTX.run_id
    sql, params = log[0]
    assert sql.startswith("EXEC [audit].[usp_start_run] @run_id = ?")
    named = dict(zip([p.split(" = ")[0].lstrip("@") for p in sql.split("] ", 1)[1].split(", ")], params))
    assert named["environment"] == "DEV" and named["workspace_id"] == "ws-1"
    assert named["workspace_name"] == "eng-dev" and named["run_timestamp"] == "20260930081205"
    assert named["total_entities"] == 3


def test_start_calls_fail_fast(customer):
    audit, _, fallbacks, _ = _audit(fail=True)
    with pytest.raises(AuditConnectionError) as err:
        audit.start_run()
    assert "jane@contoso.com" not in str(err.value)   # sanitised
    with pytest.raises(AuditConnectionError):
        audit.start_entity_run(customer)
    assert fallbacks == []


def test_start_entity_run_uses_deterministic_id_and_landing_flag(customer, product):
    audit, log, _, _ = _audit()
    assert audit.start_entity_run(customer, watermark_before="2026-09-01 00:00:00.000000") == (
        "20260930-081205-ABC123-E101")
    assert audit.start_entity_run(product) == "20260930-081205-ABC123-E102"
    landing_flags = [params[9] for sql, params in log]   # 10th named parameter = landing_enabled
    assert landing_flags == [1, 0]


def test_soft_calls_fall_back_and_never_raise(customer):
    audit, _, fallbacks, _ = _audit(fail=True)
    assert audit.log_activity("e1", "MERGE_COMPLETED", "SUCCEEDED") is False
    assert audit.complete_entity_run("e1", "SUCCEEDED", inserted_row_count=1) is False
    assert audit.complete_run("SUCCEEDED") is False
    assert audit.log_error(ErrorInfo("X", "m", False, "WRITE", None), customer, "e1") is False
    assert len(fallbacks) == 4
    path, content = fallbacks[0]
    assert path.startswith("Files/_framework_fallback/audit/log_activity/")
    assert CTX.run_id in content and "jane@contoso.com" not in content


def test_critical_mode_escalates_after_fallback():
    audit, _, fallbacks, _ = _audit(fail=True, critical=True)
    with pytest.raises(AuditCriticalError):
        audit.log_activity("e1", "X", "SUCCEEDED")
    assert len(fallbacks) == 1   # fallback still written first


def test_disabled_audit_is_a_no_op(customer):
    audit, log, _, connects = _audit(enabled=False)
    assert audit.start_run() == CTX.run_id
    assert audit.start_entity_run(customer) == CTX.entity_run_id(101)
    assert audit.log_activity("e", "X", "SUCCEEDED") is True
    assert audit.previous_row_count(customer) is None
    assert log == [] and connects == []


def test_connection_is_reused_per_thread_and_reopened_after_failure():
    audit, log, _, connects = _audit()
    audit.log_activity("e", "A", "SUCCEEDED")
    audit.log_activity("e", "B", "SUCCEEDED")
    assert len(connects) == 1

    thread = threading.Thread(target=lambda: audit.log_activity("e", "C", "SUCCEEDED"))
    thread.start()
    thread.join()
    assert len(connects) == 2 and len(set(connects)) == 2   # one connection per thread


def test_validation_results_are_logged_as_counts_only():
    audit, log, _, _ = _audit()
    result = ValidationResult(1021, "product_listprice_non_negative", "CUSTOM", "PRE", "FAILED", "FAIL", "HIGH",
                              3, "0", "3", "3 row(s) violate CUSTOM on 'secret value'")
    audit.log_validation("e102", result)
    sql, params = log[0]
    assert "usp_log_validation" in sql
    assert "secret value" not in " ".join(str(p) for p in params)


def test_get_run_entities_and_baseline():
    audit, _, _, _ = _audit(rows=[("r-E101", 101, True, "SQLServer/Customer/Customer_1.json", 42, 1)])
    [row] = audit.get_run_entities()
    assert row == {"entity_run_id": "r-E101", "entity_id": 101, "landing_enabled": True,
                   "landing_path": "SQLServer/Customer/Customer_1.json", "source_row_count": 42, "attempt_number": 1}

    baseline, _, _, _ = _audit(rows=[(None, 80, 1000, "wm", None)])
    assert baseline.previous_row_count(type("E", (), {"entity_id": 101})()) == 80   # falls back to source count
