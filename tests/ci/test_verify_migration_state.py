"""Unit tests for scripts/ci/verify_migration_state.py."""

from pathlib import Path
from unittest.mock import MagicMock, patch

from notebooks.framework import migration_runner as mr
from scripts.ci import verify_migration_state as vms


def _write(path: Path, content: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def _build_repo(tmp_path: Path) -> Path:
    _write(tmp_path / "warehouse/ddl/00_schemas/001_a.sql", "CREATE SCHEMA [control];")
    _write(tmp_path / "security/rls/001_pred.sql", "-- predicate")
    _write(tmp_path / "security/rls/002_template.sql", "-- MIGRATION_RUNNER: SKIP\n-- template")
    _write(tmp_path / "warehouse/metadata/101_entity.sql", "-- metadata v1")
    _write(tmp_path / "sql_database/audit/ddl/00_schemas/001_a.sql", "CREATE SCHEMA [audit];")
    _write(tmp_path / "sql_database/audit/views/200_vw.sql", "-- view v1")
    return tmp_path


def _all_succeeded(repo: Path, target=mr.WAREHOUSE_TARGET):
    return {s.repo_relative: {mr.compute_checksum(s.path)}
            for s in mr.discover_scripts(repo, target) if not mr.is_template(s.path)}


def _verify(repo, succeeded, failed=frozenset(), target=mr.WAREHOUSE_TARGET):
    with patch.object(vms.migration_runner, "fetch_succeeded_checksums", return_value=succeeded), patch.object(
        vms.migration_runner, "fetch_failed_paths", return_value=set(failed)
    ), patch.object(vms.fabric_connection, "get_connection_with_token", return_value=MagicMock()):
        return vms.verify("dummy-conn", "token", repo_root=repo, target=target)


def test_verify_passes_when_all_succeeded_and_none_failed(tmp_path):
    repo = _build_repo(tmp_path)
    assert _verify(repo, _all_succeeded(repo)) is True


def test_verify_fails_when_migration_missing(tmp_path):
    repo = _build_repo(tmp_path)
    assert _verify(repo, {}) is False


def test_verify_fails_when_failed_rows_exist(tmp_path):
    repo = _build_repo(tmp_path)
    assert _verify(repo, _all_succeeded(repo), failed={"warehouse/ddl/00_schemas/001_a.sql"}) is False


def test_verify_ignores_templates_when_computing_expected_set(tmp_path):
    repo = _build_repo(tmp_path)
    succeeded = _all_succeeded(repo)
    assert "security/rls/002_template.sql" not in succeeded
    assert _verify(repo, succeeded) is True


def test_verify_fails_when_repeatable_script_not_at_current_checksum(tmp_path):
    repo = _build_repo(tmp_path)
    succeeded = _all_succeeded(repo)
    succeeded["warehouse/metadata/101_entity.sql"] = {"old-checksum"}
    assert _verify(repo, succeeded) is False


def test_verify_audit_db_target(tmp_path):
    repo = _build_repo(tmp_path)
    succeeded = _all_succeeded(repo, mr.AUDIT_DB_TARGET)
    assert set(succeeded) == {"sql_database/audit/ddl/00_schemas/001_a.sql", "sql_database/audit/views/200_vw.sql"}
    assert _verify(repo, succeeded, target=mr.AUDIT_DB_TARGET) is True
