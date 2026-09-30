"""Syncs a Fabric workspace's items from git (e.g. Dev workspace <- `main`).

Fabric's git integration is pull/API-triggered, not webhook-driven, in
current GA behavior -- a plain `git push` to `main` does NOT by itself make
Fabric update the workspace. This must be called explicitly at the start of
`deploy-dev`, before publishing the Environment library or running the
schema-migration job. Re-verify this assumption against current Fabric docs
before relying on it -- git integration has been iterating quickly.

Invoke as: python -m scripts.ci.fabric_git_sync --workspace-id <id>
"""

import argparse
import sys

from scripts.ci._fabric_api import FABRIC_API_BASE, FabricApiError, get_access_token, operation_id_from_response, poll_until, request


def sync_workspace_from_git(workspace_id: str, token: str) -> None:
    status = request("GET", f"{FABRIC_API_BASE}/workspaces/{workspace_id}/git/status", token).json()

    response = request(
        "POST",
        f"{FABRIC_API_BASE}/workspaces/{workspace_id}/git/updateFromGit",
        token,
        json={
            "workspaceHead": status.get("workspaceHead"),
            "remoteCommitHash": status.get("remoteCommitHash"),
        },
    )

    operation_id = operation_id_from_response(response)
    if not operation_id:
        return  # synchronous response, nothing to poll

    poll_until(
        check_fn=lambda: request("GET", f"{FABRIC_API_BASE}/operations/{operation_id}", token).json(),
        is_done_fn=lambda r: r.get("status") in ("Succeeded", "Failed"),
        is_success_fn=lambda r: r.get("status") == "Succeeded",
        describe_fn=lambda r: f"git updateFromGit operation {operation_id}: {r.get('status')}",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--workspace-id",
        required=True,
        help="Target Fabric workspace ID -- resolve from CI config/variables, never hardcode.",
    )
    args = parser.parse_args()

    token = get_access_token()
    try:
        sync_workspace_from_git(args.workspace_id, token)
    except FabricApiError as ex:
        print(f"ERROR: {ex}", file=sys.stderr)
        return 1

    print(f"Workspace {args.workspace_id} synced from git.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
