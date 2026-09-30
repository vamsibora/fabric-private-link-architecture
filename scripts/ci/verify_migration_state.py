"""Post-deploy smoke test: verifies CONTROL.SchemaMigrationHistory reflects
every non-template DDL/RLS script as SUCCEEDED, with zero FAILED rows, for
a given environment's Warehouse.

Runs directly in the GitHub Actions runner (not inside Fabric) via a
service-principal SQL connection, reusing the `az login` OIDC session
azure/login@v2 already established -- read-only, cheap, no Fabric job
round-trip needed just to check row counts.

Invoke as:
  python -m scripts.ci.verify_migration_state --env dev
Requires WAREHOUSE_CONNECTION_STRING in the environment.
"""

import argparse
import os
import sys
from pathlib import Path

from notebooks.framework import fabric_connection, migration_runner
from scripts.ci._fabric_api import SQL_RESOURCE, get_access_token

REPO_ROOT = Path(__file__).resolve().parents[2]


def verify(connection_string: str, token: str, repo_root: Path = REPO_ROOT) -> bool:
    scripts = migration_runner.discover_scripts(repo_root)
    expected = {s.repo_relative for s in scripts if not migration_runner.is_template(s.path)}

    conn = fabric_connection.get_connection_with_token(connection_string, token)
    try:
        cursor = conn.cursor()
        succeeded = migration_runner.fetch_succeeded_paths(cursor)
        cursor.execute("SELECT ScriptPath FROM CONTROL.SchemaMigrationHistory WHERE Status = 'FAILED'")
        failed = {row[0] for row in cursor.fetchall()}
    finally:
        conn.close()

    missing = sorted(expected - succeeded)
    if missing:
        print(f"FAIL: {len(missing)} expected migration(s) not SUCCEEDED: {missing}", file=sys.stderr)
        return False
    if failed:
        print(f"FAIL: {len(failed)} migration(s) in FAILED state: {sorted(failed)}", file=sys.stderr)
        return False

    print(f"OK: {len(expected)} migrations SUCCEEDED, 0 FAILED.")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env", required=True, help="Environment label for log output only (dev/uat/prod)")
    args = parser.parse_args()

    connection_string = os.environ["WAREHOUSE_CONNECTION_STRING"]
    token = get_access_token(SQL_RESOURCE)

    print(f"Verifying migration state for environment: {args.env}")
    return 0 if verify(connection_string, token) else 1


if __name__ == "__main__":
    sys.exit(main())
