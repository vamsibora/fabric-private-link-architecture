"""Unit tests for scripts/ci/fabric_publish_environment_library.py."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from scripts.ci import fabric_publish_environment_library as lib


def _write(path: Path, content: str = "") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def test_stage_bundled_sql_copies_ddl_and_rls(tmp_path):
    _write(tmp_path / "warehouse/ddl/00_schemas/001_a.sql", "CREATE SCHEMA [CONTROL];")
    _write(tmp_path / "security/rls/001_pred.sql", "-- predicate")

    bundle_dir = lib.stage_bundled_sql(tmp_path)

    assert (bundle_dir / "warehouse/ddl/00_schemas/001_a.sql").read_text() == "CREATE SCHEMA [CONTROL];"
    assert (bundle_dir / "security/rls/001_pred.sql").read_text() == "-- predicate"


def test_stage_bundled_sql_copies_every_migration_root(tmp_path):
    for folder in lib.BUNDLED_FOLDERS:
        _write(tmp_path / folder / "x" / "001.sql", folder)

    bundle_dir = lib.stage_bundled_sql(tmp_path)

    for folder in lib.BUNDLED_FOLDERS:
        assert (bundle_dir / folder / "x" / "001.sql").read_text() == folder


def test_stage_bundled_sql_skips_missing_roots(tmp_path):
    _write(tmp_path / "warehouse/ddl/00_schemas/001_a.sql", "x")

    bundle_dir = lib.stage_bundled_sql(tmp_path)

    assert (bundle_dir / "warehouse/ddl/00_schemas/001_a.sql").exists()
    assert not (bundle_dir / "sql_database").exists()


def test_stage_bundled_sql_overwrites_stale_bundle(tmp_path):
    _write(tmp_path / "warehouse/ddl/00_schemas/001_a.sql", "v1")
    _write(tmp_path / "security/rls/001_pred.sql", "v1")
    lib.stage_bundled_sql(tmp_path)

    _write(tmp_path / "warehouse/ddl/00_schemas/001_a.sql", "v2")
    bundle_dir = lib.stage_bundled_sql(tmp_path)

    assert (bundle_dir / "warehouse/ddl/00_schemas/001_a.sql").read_text() == "v2"


def test_build_wheel_invokes_build_and_returns_newest_wheel(tmp_path):
    _write(tmp_path / "warehouse/ddl/00_schemas/001_a.sql", "CREATE SCHEMA [CONTROL];")
    _write(tmp_path / "security/rls/001_pred.sql", "-- predicate")
    dist_dir = tmp_path / "dist"
    dist_dir.mkdir()

    def fake_build(*args, **kwargs):
        _write(dist_dir / "fabric_medallion_framework-0.1.0-py3-none-any.whl", "fake wheel")
        return MagicMock()

    with patch("subprocess.run", side_effect=fake_build) as mock_run:
        wheel_path = lib.build_wheel(tmp_path)

    assert wheel_path.name == "fabric_medallion_framework-0.1.0-py3-none-any.whl"
    mock_run.assert_called_once()
    assert not (tmp_path / "notebooks/framework/_bundled_repo").exists()


def test_build_wheel_raises_when_no_wheel_produced(tmp_path):
    _write(tmp_path / "warehouse/ddl/00_schemas/001_a.sql", "x")
    _write(tmp_path / "security/rls/001_pred.sql", "x")
    (tmp_path / "dist").mkdir()

    with patch("subprocess.run", return_value=MagicMock()):
        with pytest.raises(lib.FabricApiError):
            lib.build_wheel(tmp_path)


def test_publish_library_uploads_and_polls(tmp_path):
    wheel_path = _write(tmp_path / "dist" / "pkg.whl", "fake wheel bytes")

    upload_response = MagicMock()
    upload_response.headers = {}
    publish_response = MagicMock()
    publish_response.headers = {"Location": "https://api.fabric.microsoft.com/v1/operations/op-1"}
    status_response = MagicMock()
    status_response.json.return_value = {"publishDetails": {"state": "success"}}

    with patch.object(lib, "request", side_effect=[upload_response, publish_response, status_response]) as mock_request:
        lib.publish_library("ws-1", "env-1", wheel_path, "token")

    assert mock_request.call_count == 3
