"""Builds the framework wheel (notebooks.framework + notebooks.bronze,
embedding every migration root -- warehouse/ddl, security/rls,
warehouse/programmability, warehouse/metadata and sql_database/audit -- as
package data) and publishes it as a custom library to a target Fabric
Environment item, so a Notebook using that Environment can
`from notebooks.framework import migration_runner` and
`from notebooks.bronze import orchestrator`.

Library publish operations can take several minutes -- this lengthens every
deploy. If that proves too slow/flaky in practice, the documented fallback
is staging the .sql files into a Lakehouse Files/ area instead of an
Environment custom library (see docs/cicd_pipeline.md).

Invoke as:
  python -m scripts.ci.fabric_publish_environment_library --workspace-id <id> --environment-id <id>
"""

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

from scripts.ci._fabric_api import FABRIC_API_BASE, FabricApiError, get_access_token, operation_id_from_response, poll_until, request

REPO_ROOT = Path(__file__).resolve().parents[2]
BUNDLE_DIR = REPO_ROOT / "notebooks" / "framework" / "_bundled_repo"

# Every folder migration_runner.discover_scripts() reads, for every target.
# Missing folders are skipped (e.g. a trimmed-down test repo).
BUNDLED_FOLDERS = (
    "warehouse/ddl",
    "warehouse/programmability",
    "warehouse/metadata",
    "security/rls",
    "sql_database/audit",
)


def stage_bundled_sql(repo_root: Path = REPO_ROOT) -> Path:
    """Copies every BUNDLED_FOLDERS entry into
    notebooks/framework/_bundled_repo/, mirroring its repo-relative layout --
    setuptools package_data can only include files that live inside the
    package tree, and migration_runner.discover_scripts() must find them at
    the same relative paths once unpacked from the wheel."""
    bundle_dir = repo_root / "notebooks" / "framework" / "_bundled_repo"
    if bundle_dir.exists():
        shutil.rmtree(bundle_dir)
    for folder in BUNDLED_FOLDERS:
        source = repo_root / folder
        if source.is_dir():
            shutil.copytree(source, bundle_dir / folder)
    return bundle_dir


def build_wheel(repo_root: Path = REPO_ROOT) -> Path:
    bundle_dir = stage_bundled_sql(repo_root)
    try:
        subprocess.run(
            [sys.executable, "-m", "build", "--wheel", "--outdir", "dist"],
            cwd=repo_root,
            check=True,
        )
    finally:
        shutil.rmtree(bundle_dir, ignore_errors=True)

    wheels = sorted((repo_root / "dist").glob("*.whl"), key=lambda p: p.stat().st_mtime)
    if not wheels:
        raise FabricApiError("python -m build did not produce a .whl file")
    return wheels[-1]


def publish_library(workspace_id: str, environment_id: str, wheel_path: Path, token: str) -> None:
    with open(wheel_path, "rb") as f:
        request(
            "POST",
            f"{FABRIC_API_BASE}/workspaces/{workspace_id}/environments/{environment_id}/staging/libraries",
            token,
            files={"file": (wheel_path.name, f, "application/octet-stream")},
        )

    response = request(
        "POST",
        f"{FABRIC_API_BASE}/workspaces/{workspace_id}/environments/{environment_id}/staging/publish",
        token,
    )

    operation_id = operation_id_from_response(response)
    if not operation_id:
        return

    poll_until(
        check_fn=lambda: request(
            "GET",
            f"{FABRIC_API_BASE}/workspaces/{workspace_id}/environments/{environment_id}/publish",
            token,
        ).json(),
        is_done_fn=lambda r: r.get("publishDetails", {}).get("state") in ("success", "failed"),
        is_success_fn=lambda r: r.get("publishDetails", {}).get("state") == "success",
        describe_fn=lambda r: f"environment publish: {r.get('publishDetails', {})}",
        interval_seconds=20.0,
        timeout_seconds=1800.0,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace-id", required=True)
    parser.add_argument("--environment-id", required=True, help="Fabric Environment item ID (CicdFramework.Environment)")
    args = parser.parse_args()

    token = get_access_token()
    try:
        wheel_path = build_wheel()
        publish_library(args.workspace_id, args.environment_id, wheel_path, token)
    except FabricApiError as ex:
        print(f"ERROR: {ex}", file=sys.stderr)
        return 1

    print(f"Published {wheel_path.name} to environment {args.environment_id}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
