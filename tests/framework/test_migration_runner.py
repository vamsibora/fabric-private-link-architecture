"""Unit tests for notebooks/framework/migration_runner.py.

Uses a small hand-written FakeCursor/FakeConnection (not MagicMock) so the
real ledger_table_exists/fetch_*/_insert_ledger_row SQL text gets
exercised, not just run_migrations' own orchestration logic. tmp_path
fixtures build small fake repo trees per test, for both targets.
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
WH_LEDGER = "CREATE TABLE [control].[schema_migration_history] (migration_id UNIQUEIDENTIFIER NOT NULL);"
AUDIT_LEDGER = "CREATE TABLE [audit].[schema_migration_history] (migration_id UNIQUEIDENTIFIER NOT NULL);"
TEMPLATE_CONTENT = "-- MIGRATION_RUNNER: SKIP\n-- template, nothing to run yet\n"
FUNCTION_CONTENT = "CREATE OR ALTER FUNCTION [control].[fn_x]() RETURNS TABLE AS RETURN SELECT 1 AS x;"
METADATA_CONTENT = "BEGIN TRANSACTION; DELETE FROM [control].[entity] WHERE entity_id = 1; COMMIT TRANSACTION;"


def _write(path: Path, content: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def _build_repo(tmp_path: Path) -> Path:
    _write(tmp_path / "warehouse/ddl/00_schemas/001_schema.sql", "CREATE SCHEMA [control];")
    _write(tmp_path / "warehouse/ddl/05_meta/050_ledger.sql", WH_LEDGER)
    _write(tmp_path / "warehouse/ddl/10_control/010_table.sql", SCHEMA_CONTENT)
    _write(tmp_path / "security/rls/001_predicate.sql", "CREATE FUNCTION dummy() RETURNS INT AS BEGIN RETURN 1 END;")
    _write(tmp_path / "security/rls/002_template.sql", TEMPLATE_CONTENT)
    _write(tmp_path / "warehouse/programmability/100_fn.sql", FUNCTION_CONTENT)
    _write(tmp_path / "warehouse/metadata/101_entity.sql", METADATA_CONTENT)
    _write(tmp_path / "sql_database/audit/ddl/00_schemas/001_schema.sql", "CREATE SCHEMA [audit];")
    _write(tmp_path / "sql_database/audit/ddl/05_meta/050_ledger.sql", AUDIT_LEDGER)
    _write(tmp_path / "sql_database/audit/procs/100_usp.sql", "CREATE OR ALTER PROCEDURE [audit].[usp_x] AS SELECT 1;")
    _write(tmp_path / "sql_database/audit/views/200_vw.sql", "CREATE OR ALTER VIEW [audit].[vw_x] AS SELECT 1 AS x;")
    return tmp_path


WAREHOUSE_ONCE = [
    "warehouse/ddl/00_schemas/001_schema.sql",
    "warehouse/ddl/05_meta/050_ledger.sql",
    "warehouse/ddl/10_control/010_table.sql",
    "security/rls/001_predicate.sql",
]
WAREHOUSE_REPEATABLE = ["warehouse/programmability/100_fn.sql", "warehouse/metadata/101_entity.sql"]


def test_discover_scripts_orders_once_roots_then_repeatable_roots(tmp_path):
    repo = _build_repo(tmp_path)
    scripts = mr.discover_scripts(repo, mr.WAREHOUSE_TARGET)

    assert [s.repo_relative for s in scripts] == [
        *WAREHOUSE_ONCE[:4],
        "security/rls/002_template.sql",
        *WAREHOUSE_REPEATABLE,
    ]
    assert [s.category for s in scripts] == ["SCHEMA", "SCHEMA", "SCHEMA", "RLS", "RLS", "PROGRAMMABILITY", "METADATA"]
    assert [s.repeatable for s in scripts] == [False] * 5 + [True] * 2


def test_discover_scripts_audit_target_only_reads_sql_database(tmp_path):
    repo = _build_repo(tmp_path)
    scripts = mr.discover_scripts(repo, mr.AUDIT_DB_TARGET)

    assert [s.repo_relative for s in scripts] == [
        "sql_database/audit/ddl/00_schemas/001_schema.sql",
        "sql_database/audit/ddl/05_meta/050_ledger.sql",
        "sql_database/audit/procs/100_usp.sql",
        "sql_database/audit/views/200_vw.sql",
    ]
    assert [s.category for s in scripts] == ["SCHEMA", "SCHEMA", "PROC", "VIEW"]


def test_is_template_detects_marker(tmp_path):
    template = _write(tmp_path / "t.sql", TEMPLATE_CONTENT)
    normal = _write(tmp_path / "n.sql", SCHEMA_CONTENT)

    assert mr.is_template(template) is True
    assert mr.is_template(normal) is False


class FakeCursor:
    """Minimal stand-in exercising the real ledger SQL text/param shapes for
    one target (its ledger is created by the script containing ledger_ddl)."""

    def __init__(self, target=mr.WAREHOUSE_TARGET):
        self.target = target
        self.ledger_created = False
        self.ledger_rows = []
        self.executed = []
        self._last_check = False
        self._fetchall_result = []

    def execute(self, sql, *params):
        self.executed.append(sql)
        if "SELECT 1 FROM sys.tables" in sql:
            assert params == (self.target.ledger_schema, self.target.ledger_table)
            self._last_check = self.ledger_created
        elif f"CREATE TABLE {self.target.ledger}" in sql:
            self.ledger_created = True
        elif sql.startswith("SELECT script_path, status, checksum"):
            # stored rows are full 10-column INSERT tuples:
            # (migration_id, script_path, script_category, checksum, status, ...)
            self._fetchall_result = [(row[1], row[4], row[3]) for row in self.ledger_rows]
        elif sql.startswith("SELECT script_path, checksum") and "SUCCEEDED" in sql:
            self._fetchall_result = [(row[1], row[3]) for row in self.ledger_rows if row[4] == "SUCCEEDED"]
        elif sql.startswith(f"INSERT INTO {self.target.ledger}"):
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


def test_fetch_helpers_use_latest_row_and_succeeded_checksums():
    cursor = FakeCursor()
    cursor.ledger_rows = [
        ("id-1", "a.sql", "SCHEMA", "chk1", "SUCCEEDED", None, 10, None, "tester", "2024-01-01"),
        ("id-2", "b.sql", "RLS", "chk2", "SKIPPED_TEMPLATE", None, None, None, "tester", "2024-01-01"),
        ("id-3", "c.sql", "METADATA", "chk3", "SUCCEEDED", None, 5, None, "tester", "2024-01-01"),
        ("id-4", "c.sql", "METADATA", "chk4", "FAILED", None, 5, "boom", "tester", "2024-01-02"),
    ]

    assert mr.fetch_succeeded_paths(cursor) == {"a.sql", "c.sql"}
    assert mr.fetch_succeeded_checksums(cursor) == {"a.sql": {"chk1"}, "c.sql": {"chk3"}}
    assert mr.fetch_failed_paths(cursor) == {"c.sql"}  # latest row for c.sql is FAILED
    assert mr.fetch_ledger_entries(cursor)["c.sql"].status == "FAILED"


def test_run_migrations_bootstraps_ledger_and_applies_all(tmp_path, patched_connection, fake_cursor):
    repo = _build_repo(tmp_path)

    result = mr.run_migrations("dummy-conn", repo, applied_by="tester")

    assert result.applied == WAREHOUSE_ONCE + WAREHOUSE_REPEATABLE
    assert result.skipped_templates == ["security/rls/002_template.sql"]
    # 6 applied + 1 template = 7 ledger rows, even though the first 2 scripts
    # ran before the ledger table existed (buffered, then flushed once it did).
    assert len(fake_cursor.ledger_rows) == 7
    assert patched_connection.closed is True


def test_run_migrations_is_a_no_op_on_second_call(tmp_path, patched_connection, fake_cursor):
    repo = _build_repo(tmp_path)
    mr.run_migrations("dummy-conn", repo, applied_by="tester")

    second = mr.run_migrations("dummy-conn", repo, applied_by="tester")

    assert second.applied == []
    assert len(second.already_applied) == 6
    assert second.skipped_templates == ["security/rls/002_template.sql"]
    assert len(fake_cursor.ledger_rows) == 7  # unchanged -- template not re-inserted


def test_repeatable_script_is_reapplied_only_when_checksum_changes(tmp_path, patched_connection, fake_cursor):
    repo = _build_repo(tmp_path)
    mr.run_migrations("dummy-conn", repo, applied_by="tester")

    (repo / "warehouse/metadata/101_entity.sql").write_text(METADATA_CONTENT + " -- v2", encoding="utf-8")
    result = mr.run_migrations("dummy-conn", repo, applied_by="tester")

    assert result.applied == ["warehouse/metadata/101_entity.sql"]
    assert result.checksum_drift == []  # repeatable scripts never count as drift
    rows = [r for r in fake_cursor.ledger_rows if r[1] == "warehouse/metadata/101_entity.sql"]
    assert [r[4] for r in rows] == ["SUCCEEDED", "SUCCEEDED"]
    assert rows[0][3] != rows[1][3]


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
    # nothing after the failure point (RLS, repeatables) ever ran
    assert not any("rls" in row[1] or "metadata" in row[1] for row in fake_cursor.ledger_rows)


def test_failed_repeatable_script_is_retried_next_run(tmp_path, patched_connection, fake_cursor):
    repo = _build_repo(tmp_path)
    real_execute = fake_cursor.execute
    calls = {"n": 0}

    def flaky_execute(sql, *params):
        if sql == METADATA_CONTENT:
            calls["n"] += 1
            if calls["n"] == 1:
                raise RuntimeError("transient")
        return real_execute(sql, *params)

    fake_cursor.execute = flaky_execute
    with pytest.raises(mr.MigrationRunError):
        mr.run_migrations("dummy-conn", repo, applied_by="tester")

    result = mr.run_migrations("dummy-conn", repo, applied_by="tester")
    assert result.applied == ["warehouse/metadata/101_entity.sql"]


def test_run_migrations_detects_checksum_drift_without_reexecuting(tmp_path, patched_connection, fake_cursor):
    repo = _build_repo(tmp_path)
    mr.run_migrations("dummy-conn", repo, applied_by="tester")

    (repo / "warehouse/ddl/10_control/010_table.sql").write_text(
        "CREATE TABLE dummy (Col INT, NewCol INT);", encoding="utf-8"
    )
    warnings = []
    before = len(fake_cursor.executed)
    result = mr.run_migrations("dummy-conn", repo, applied_by="tester", on_warning=warnings.append)

    assert result.checksum_drift == ["warehouse/ddl/10_control/010_table.sql"]
    assert result.applied == []
    assert len(warnings) == 1 and "010_table.sql" in warnings[0]
    assert not any("NewCol" in sql for sql in fake_cursor.executed[before:])


def test_audit_db_target_uses_audit_ledger(tmp_path):
    repo = _build_repo(tmp_path)
    cursor = FakeCursor(mr.AUDIT_DB_TARGET)
    conn = FakeConnection(cursor)

    result = mr.run_migrations("audit-conn", repo, applied_by="tester", target=mr.AUDIT_DB_TARGET,
                               connect=lambda cs: conn)

    assert result.applied == [
        "sql_database/audit/ddl/00_schemas/001_schema.sql",
        "sql_database/audit/ddl/05_meta/050_ledger.sql",
        "sql_database/audit/procs/100_usp.sql",
        "sql_database/audit/views/200_vw.sql",
    ]
    assert len(cursor.ledger_rows) == 4
    assert all(r[2] in {"SCHEMA", "PROC", "VIEW"} for r in cursor.ledger_rows)


def test_expected_state_pins_repeatable_checksums_only(tmp_path):
    repo = _build_repo(tmp_path)
    expected = mr.expected_state(repo, mr.WAREHOUSE_TARGET)

    assert "security/rls/002_template.sql" not in expected
    assert expected["warehouse/ddl/10_control/010_table.sql"] is None
    assert expected["warehouse/metadata/101_entity.sql"] == mr.compute_checksum(repo / "warehouse/metadata/101_entity.sql")


def test_real_repo_migration_roots_are_discoverable():
    """The repo's own DDL: every file is discovered, and each database's
    ledger DDL sorts before every table script so bootstrap buffering works."""
    repo_root = Path(__file__).resolve().parents[2]
    for target, ledger_file in (
        (mr.WAREHOUSE_TARGET, "warehouse/ddl/05_meta/050_control_schema_migration_history.sql"),
        (mr.AUDIT_DB_TARGET, "sql_database/audit/ddl/05_meta/050_audit_schema_migration_history.sql"),
    ):
        paths = [s.repo_relative for s in mr.discover_scripts(repo_root, target)]
        assert ledger_file in paths
        # only CREATE SCHEMA scripts may run before the ledger exists
        assert all("/00_schemas/" in p for p in paths[: paths.index(ledger_file)])
        assert f"CREATE TABLE {target.ledger}" in (repo_root / ledger_file).read_text(encoding="utf-8")
