"""Post-deploy smoke test: verifies a target database's migration ledger
reflects every non-template script as SUCCEEDED -- CREATE-once scripts at
any checksum, repeatable scripts (procs/views/functions/metadata) at their
CURRENT on-disk checksum -- with zero scripts whose latest row is FAILED.

Targets (see notebooks/framework/migration_runner.TARGETS):
  warehouse  control.schema_migration_history  env var WAREHOUSE_CONNECTION_STRING
  audit_db   audit.schema_migration_history    env var AUDIT_DB_CONNECTION_STRING

Runs directly in the GitHub Actions runner (not inside Fabric) via a
service-principal SQL connection, reusing the `az login` OIDC session
azure/login@v2 already established -- read-only, cheap.

Invoke as:
  python -m scripts.ci.verify_migration_state --env dev --target warehouse
"""

import argparse
import os
import sys
from pathlib import Path

from notebooks.framework import fabric_connection, migration_runner
from scripts.ci._fabric_api import SQL_RESOURCE, get_access_token

REPO_ROOT = Path(__file__).resolve().parents[2]

_CONNECTION_ENV_VARS = {
    "warehouse": "WAREHOUSE_CONNECTION_STRING",
    "audit_db": "AUDIT_DB_CONNECTION_STRING",
}


def verify(
    connection_string: str,
    token: str,
    repo_root: Path = REPO_ROOT,
    target: migration_runner.MigrationTarget = migration_runner.WAREHOUSE_TARGET,
) -> bool:
    expected = migration_runner.expected_state(repo_root, target)

    conn = fabric_connection.get_connection_with_token(connection_string, token)
    try:
        cursor = conn.cursor()
        succeeded = migration_runner.fetch_succeeded_checksums(cursor, target)
        failed = migration_runner.fetch_failed_paths(cursor, target)
    finally:
        conn.close()

    missing = sorted(path for path, checksum in expected.items() if checksum is None and path not in succeeded)
    stale = sorted(
        path
        for path, checksum in expected.items()
        if checksum is not None and checksum not in succeeded.get(path, set())
    )
    if missing:
        print(f"FAIL: {len(missing)} expected migration(s) not SUCCEEDED: {missing}", file=sys.stderr)
        return False
    if stale:
        print(f"FAIL: {len(stale)} repeatable script(s) not applied at current checksum: {stale}", file=sys.stderr)
        return False
    if failed:
        print(f"FAIL: {len(failed)} migration(s) in FAILED state: {sorted(failed)}", file=sys.stderr)
        return False

    print(f"OK [{target.name}]: {len(expected)} migrations SUCCEEDED, 0 FAILED.")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env", required=True, help="Environment label for log output only (dev/uat/prod)")
    parser.add_argument("--target", choices=sorted(_CONNECTION_ENV_VARS), default="warehouse")
    args = parser.parse_args()

    target = migration_runner.TARGETS[args.target.upper()]
    connection_string = os.environ[_CONNECTION_ENV_VARS[args.target]]
    token = get_access_token(SQL_RESOURCE)

    print(f"Verifying {target.name} migration state for environment: {args.env}")
    return 0 if verify(connection_string, token, target=target) else 1


if __name__ == "__main__":
    sys.exit(main())
