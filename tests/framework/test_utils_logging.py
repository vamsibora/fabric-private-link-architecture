"""Unit tests for notebooks/framework/utils_logging.py.

All Fabric-specific dependencies (pyodbc, notebookutils) are mocked -- these
tests validate SQL text/parameter binding and the fail-fast vs fail-soft
exception boundaries without needing a live Fabric connection. Live
pyodbc/notebookutils integration can only be exercised inside an actual
Fabric notebook against a dev Warehouse.
"""

import sys
import types
from unittest.mock import MagicMock, patch

import pytest

# notebookutils only exists inside a Fabric runtime -- stub it out so the
# module under test can be imported here.
sys.modules.setdefault("notebookutils", types.ModuleType("notebookutils"))
sys.modules["notebookutils"].credentials = MagicMock(getToken=MagicMock(return_value="fake-token"))
sys.modules["notebookutils"].fs = MagicMock()

from notebooks.framework import utils_logging as ul  # noqa: E402


@pytest.fixture
def mock_cursor():
    """Patch _get_connection so _cursor() yields a MagicMock cursor, and
    return that cursor for assertions on the executed SQL/params."""
    cursor = MagicMock()
    connection = MagicMock()
    connection.cursor.return_value = cursor
    with patch.object(ul, "_get_connection", return_value=connection):
        yield cursor


def test_start_pipeline_run_inserts_and_returns_id(mock_cursor):
    pipeline_run_id = ul.start_pipeline_run("dummy-conn-string", "bronze_ingest")

    assert isinstance(pipeline_run_id, str)
    sql, params = mock_cursor.execute.call_args[0][0], mock_cursor.execute.call_args[0][1:]
    assert "INSERT INTO CONTROL.PipelineRun" in sql
    assert params[0] == pipeline_run_id  # PipelineRunID is the first bound param


def test_start_pipeline_run_raises_control_connection_error_on_failure():
    with patch.object(ul, "_get_connection", side_effect=RuntimeError("connection refused")):
        with pytest.raises(ul.ControlConnectionError):
            ul.start_pipeline_run("dummy-conn-string", "bronze_ingest")


def test_start_table_run_inserts_and_returns_id(mock_cursor):
    table_run_id = ul.start_table_run(
        "dummy-conn-string", pipeline_run_id="pr-1", source_system="CRM", target_table="dbo.Customer"
    )

    assert isinstance(table_run_id, str)
    sql = mock_cursor.execute.call_args[0][0]
    assert "INSERT INTO CONTROL.TableRun" in sql


def test_start_table_run_raises_control_connection_error_on_failure():
    with patch.object(ul, "_get_connection", side_effect=RuntimeError("connection refused")):
        with pytest.raises(ul.ControlConnectionError):
            ul.start_table_run("dummy-conn-string", "pr-1", "CRM", "dbo.Customer")


def test_end_pipeline_run_returns_true_on_success(mock_cursor):
    assert ul.end_pipeline_run("dummy-conn-string", "pr-1", "SUCCEEDED", rows_processed=100) is True
    sql = mock_cursor.execute.call_args[0][0]
    assert "UPDATE CONTROL.PipelineRun" in sql


def test_end_pipeline_run_fails_soft_and_falls_back():
    with patch.object(ul, "_get_connection", side_effect=RuntimeError("connection refused")):
        with patch.object(ul, "_fallback_log") as fallback:
            result = ul.end_pipeline_run("dummy-conn-string", "pr-1", "FAILED")
    assert result is False
    fallback.assert_called_once()


def test_end_table_run_fails_soft_and_falls_back():
    with patch.object(ul, "_get_connection", side_effect=RuntimeError("connection refused")):
        with patch.object(ul, "_fallback_log") as fallback:
            result = ul.end_table_run("dummy-conn-string", "tr-1", "SUCCEEDED")
    assert result is False
    fallback.assert_called_once()


def test_log_error_inserts_and_captures_exception_details(mock_cursor):
    try:
        raise ValueError("boom")
    except ValueError as exc:
        result = ul.log_error("dummy-conn-string", "something broke", exception=exc)

    assert result is True
    sql, params = mock_cursor.execute.call_args[0][0], mock_cursor.execute.call_args[0][1:]
    assert "INSERT INTO CONTROL.ErrorLog" in sql
    error_details = params[-3]  # ErrorDetails column, per column order in the INSERT
    assert "ValueError: boom" in error_details


def test_log_error_never_raises_and_falls_back_on_connection_failure():
    with patch.object(ul, "_get_connection", side_effect=RuntimeError("connection refused")):
        with patch.object(ul, "_fallback_log") as fallback:
            result = ul.log_error("dummy-conn-string", "something broke")
    assert result is False
    fallback.assert_called_once()
