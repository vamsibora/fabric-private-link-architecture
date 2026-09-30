"""Unit tests for notebooks/framework/migration_runner.py.

Uses a small hand-written FakeCursor/FakeConnection (not MagicMock) so the
real ledger_table_exists/fetch_ledger_entries/_insert_ledger_row SQL text
gets exercised, not just run_migrations' own orchestration logic. tmp_path
fixtures build small fake warehouse/ddl + security/rls trees per test.
"""

import sys
import types
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.modules.setdefault("notebookutils", types.ModuleType("notebookutils"))
sys.modules["notebookutils"].credentials = MagicMock(getToken=MagicMock(return_value="fake-token"))
sys.modules["notebookutils"].fs = MagicMock()

from notebooks.framework import migration_runner as mr  # noqa: E402

SCHEMA_CONTENT = "CREATE TABLE dummy (Col INT);"
LEDGER_CONTENT = "CREATE TABLE [CONTROL].[SchemaMigrationHistory] (MigrationID UNIQUEIDENTIFIER NOT NULL);"
TEMPLATE_CONTENT = "-- MIGRATION_RUNNER: SKIP\n-- template, nothing to run yet\n"


def _write(path: Path, content: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def _build_repo(tmp_path: Path) -> Path:
    _write(tmp_path / "warehouse/ddl/00_schemas/001_schema.sql", "CREATE SCHEMA [CONTROL];")
    _write(tmp_path / "warehouse/ddl/05_meta/050_ledger.sql", LEDGER_CONTENT)
    _write(tmp_path / "warehouse/ddl/10_control/010_table.sql", SCHEMA_CONTENT)
    _write(tmp_path / "security/rls/001_predicate.sql", "CREATE FUNCTION dummy() RETURNS INT AS BEGIN RETURN 1 END;")
    _write(tmp_path / "security/rls/002_template.sql", TEMPLATE_CONTENT)
    return tmp_path


def test_discover_scripts_orders_schema_before_rls_and_by_path(tmp_path):
    repo = _build_repo(tmp_path)
    scripts = mr.discover_scripts(repo)

    assert [s.repo_relative for s in scripts] == [
        "warehouse/ddl/00_schemas/001_schema.sql",
        "warehouse/ddl/05_meta/050_ledger.sql",
        "warehouse/ddl/10_control/010_table.sql",
        "security/rls/001_predicate.sql",
        "security/rls/002_template.sql",
    ]
    assert [s.category for s in scripts] == ["SCHEMA", "SCHEMA", "SCHEMA", "RLS", "RLS"]


def test_is_template_detects_marker(tmp_path):
    template = _write(tmp_path / "t.sql", TEMPLATE_CONTENT)
    normal = _write(tmp_path / "n.sql", SCHEMA_CONTENT)

    assert mr.is_template(template) is True
    assert mr.is_template(normal) is False


class FakeCursor:
    """Minimal stand-in exercising the real ledger SQL text/param shapes."""

    def __init__(self):
        self.ledger_created = False
        self.ledger_rows = []
        self._last_check = False
        self._fetchall_result = []

    def execute(self, sql, *params):
        if "SELECT 1 FROM sys.tables" in sql:
            self._last_check = self.ledger_created
        elif "CREATE TABLE [CONTROL].[SchemaMigrationHistory]" in sql:
            self.ledger_created = True
        elif sql.startswith("SELECT ScriptPath, Status, Checksum"):
            # Project to the 3 selected columns -- stored rows are full
            # 10-column INSERT tuples (MigrationID, ScriptPath, ScriptCategory,
            # Checksum, Status, ...).
            self._fetchall_result = [(row[1], row[4], row[3]) for row in self.ledger_rows]
        elif sql.startswith("INSERT INTO [CONTROL].[SchemaMigrationHistory]"):
            self.ledger_rows.append(params)

    def fetchone(self):
        return (1,) if self._last_check else None

    def fetchall(self):
        return self._fetchall_result


class FakeConnection:
    def __init__(self, cursor):
        self._cursor = cursor
        self.closed = False

    def cursor(self):
        return self._cursor

    def close(self):
        self.closed = True


@pytest.fixture
def fake_cursor():
    return FakeCursor()


@pytest.fixture
def patched_connection(fake_cursor):
    conn = FakeConnection(fake_cursor)
    with patch.object(mr, "_get_connection", return_value=conn):
        yield conn


def test_fetch_succeeded_and_template_paths():
    cursor = FakeCursor()
    cursor.ledger_rows = [
        ("id-1", "a.sql", "SCHEMA", "chk1", "SUCCEEDED", None, 10, None, "tester", "2024-01-01"),
        ("id-2", "b.sql", "RLS", "chk2", "SKIPPED_TEMPLATE", None, None, None, "tester", "2024-01-01"),
    ]

    assert mr.fetch_succeeded_paths(cursor) == {"a.sql"}
    assert mr.fetch_template_paths(cursor) == {"b.sql"}


def test_run_migrations_bootstraps_ledger_and_applies_all(tmp_path, patched_connection, fake_cursor):
    repo = _build_repo(tmp_path)

    result = mr.run_migrations("dummy-conn", repo, applied_by="tester")

    assert result.applied == [
        "warehouse/ddl/00_schemas/001_schema.sql",
        "warehouse/ddl/05_meta/050_ledger.sql",
        "warehouse/ddl/10_control/010_table.sql",
        "security/rls/001_predicate.sql",
    ]
    assert result.skipped_templates == ["security/rls/002_template.sql"]
    # 4 applied + 1 template = 5 ledger rows, even though the first 2 scripts
    # ran before the ledger table existed (buffered, then flushed once it did).
    assert len(fake_cursor.ledger_rows) == 5
    assert patched_connection.closed is True


def test_run_migrations_is_a_no_op_on_second_call(tmp_path, patched_connection, fake_cursor):
    repo = _build_repo(tmp_path)
    mr.run_migrations("dummy-conn", repo, applied_by="tester")

    second = mr.run_migrations("dummy-conn", repo, applied_by="tester")

    assert second.applied == []
    assert len(second.already_applied) == 4
    assert second.skipped_templates == ["security/rls/002_template.sql"]
    assert len(fake_cursor.ledger_rows) == 5  # unchanged -- template not re-inserted


def test_run_migrations_halts_on_failure(tmp_path, patched_connection, fake_cursor):
    repo = _build_repo(tmp_path)
    real_execute = fake_cursor.execute

    def failing_execute(sql, *params):
        if sql == SCHEMA_CONTENT:
            raise RuntimeError("syntax error")
        return real_execute(sql, *params)

    fake_cursor.execute = failing_execute

    with pytest.raises(mr.MigrationRunError):
        mr.run_migrations("dummy-conn", repo, applied_by="tester")

    failed_rows = [row for row in fake_cursor.ledger_rows if row[1] == "warehouse/ddl/10_control/010_table.sql"]
    assert len(failed_rows) == 1
    assert failed_rows[0][4] == "FAILED"
    # nothing after the failure point (the RLS scripts) ever ran
    assert not any("rls" in row[1] for row in fake_cursor.ledger_rows)


def test_run_migrations_detects_checksum_drift_without_reexecuting(tmp_path, patched_connection, fake_cursor):
    repo = _build_repo(tmp_path)
    mr.run_migrations("dummy-conn", repo, applied_by="tester")

    (repo / "warehouse/ddl/10_control/010_table.sql").write_text(
        "CREATE TABLE dummy (Col INT, NewCol INT);", encoding="utf-8"
    )

    with patch("notebooks.framework.utils_logging.log_error") as mock_log_error:
        result = mr.run_migrations("dummy-conn", repo, applied_by="tester")

    assert result.checksum_drift == ["warehouse/ddl/10_control/010_table.sql"]
    assert result.applied == []
    mock_log_error.assert_called_once()
