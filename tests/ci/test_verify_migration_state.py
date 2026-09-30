"""Unit tests for scripts/ci/verify_migration_state.py."""

from pathlib import Path
from unittest.mock import MagicMock, patch

from scripts.ci import verify_migration_state as vms


def _write(path: Path, content: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def _build_repo(tmp_path: Path) -> Path:
    _write(tmp_path / "warehouse/ddl/00_schemas/001_a.sql", "CREATE SCHEMA [CONTROL];")
    _write(tmp_path / "security/rls/001_pred.sql", "-- predicate")
    _write(tmp_path / "security/rls/002_template.sql", "-- MIGRATION_RUNNER: SKIP\n-- template")
    return tmp_path


def _fake_connection(fetchall_result):
    cursor = MagicMock()
    cursor.fetchall.return_value = fetchall_result
    conn = MagicMock()
    conn.cursor.return_value = cursor
    return conn


def test_verify_passes_when_all_succeeded_and_none_failed(tmp_path):
    repo = _build_repo(tmp_path)
    conn = _fake_connection([])  # no FAILED rows

    with patch.object(
        vms.migration_runner,
        "fetch_succeeded_paths",
        return_value={"warehouse/ddl/00_schemas/001_a.sql", "security/rls/001_pred.sql"},
    ), patch.object(vms.fabric_connection, "get_connection_with_token", return_value=conn):
        assert vms.verify("dummy-conn", "token", repo_root=repo) is True


def test_verify_fails_when_migration_missing(tmp_path):
    repo = _build_repo(tmp_path)
    conn = _fake_connection([])

    with patch.object(vms.migration_runner, "fetch_succeeded_paths", return_value=set()), patch.object(
        vms.fabric_connection, "get_connection_with_token", return_value=conn
    ):
        assert vms.verify("dummy-conn", "token", repo_root=repo) is False


def test_verify_fails_when_failed_rows_exist(tmp_path):
    repo = _build_repo(tmp_path)
    conn = _fake_connection([("warehouse/ddl/00_schemas/001_a.sql",)])

    with patch.object(
        vms.migration_runner,
        "fetch_succeeded_paths",
        return_value={"warehouse/ddl/00_schemas/001_a.sql", "security/rls/001_pred.sql"},
    ), patch.object(vms.fabric_connection, "get_connection_with_token", return_value=conn):
        assert vms.verify("dummy-conn", "token", repo_root=repo) is False


def test_verify_ignores_templates_when_computing_expected_set(tmp_path):
    repo = _build_repo(tmp_path)
    conn = _fake_connection([])

    with patch.object(
        vms.migration_runner,
        "fetch_succeeded_paths",
        return_value={"warehouse/ddl/00_schemas/001_a.sql", "security/rls/001_pred.sql"},
    ) as mock_fetch, patch.object(vms.fabric_connection, "get_connection_with_token", return_value=conn):
        # security/rls/002_template.sql is never expected to be SUCCEEDED
        assert vms.verify("dummy-conn", "token", repo_root=repo) is True
    mock_fetch.assert_called_once()
