"""Runs a Fabric item job (the SchemaMigration Data Pipeline, targeting a
given environment) and polls it to a terminal state.

Invoke as:
  python -m scripts.ci.fabric_run_item_job --workspace-id <id> --item-id <id> --target-environment dev
"""

import argparse
import sys
from typing import Optional

from scripts.ci._fabric_api import FABRIC_API_BASE, FabricApiError, get_access_token, operation_id_from_response, poll_until, request


def run_item_job(
    workspace_id: str,
    item_id: str,
    token: str,
    job_type: str = "Pipeline",
    parameters: Optional[dict] = None,
) -> dict:
    response = request(
        "POST",
        f"{FABRIC_API_BASE}/workspaces/{workspace_id}/items/{item_id}/jobs/instances",
        token,
        params={"jobType": job_type},
        json={"executionData": {"parameters": parameters or {}}},
    )

    job_instance_id = operation_id_from_response(response)
    if not job_instance_id:
        raise FabricApiError("Fabric did not return a job instance id (Location header missing)")

    status_url = f"{FABRIC_API_BASE}/workspaces/{workspace_id}/items/{item_id}/jobs/instances/{job_instance_id}"
    return poll_until(
        check_fn=lambda: request("GET", status_url, token).json(),
        is_done_fn=lambda r: r.get("status") in ("Completed", "Failed", "Cancelled", "Deduped"),
        is_success_fn=lambda r: r.get("status") == "Completed",
        describe_fn=lambda r: f"job instance {job_instance_id}: {r.get('status')} {r.get('failureReason', '')}".strip(),
        interval_seconds=15.0,
        timeout_seconds=3600.0,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace-id", required=True)
    parser.add_argument("--item-id", required=True, help="Fabric Data Pipeline item ID (SchemaMigration.DataPipeline)")
    parser.add_argument("--target-environment", required=True, help="Passed as the pipeline's TargetEnvironment parameter")
    args = parser.parse_args()

    token = get_access_token()
    try:
        result = run_item_job(
            args.workspace_id,
            args.item_id,
            token,
            parameters={"TargetEnvironment": args.target_environment},
        )
    except FabricApiError as ex:
        print(f"ERROR: {ex}", file=sys.stderr)
        return 1

    print(f"Job succeeded: {result.get('status')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
