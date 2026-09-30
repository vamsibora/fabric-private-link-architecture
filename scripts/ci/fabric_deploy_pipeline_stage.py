"""Promotes content from one Fabric Deployment Pipeline stage to the next
(Dev -> UAT, or UAT -> Prod). Only non-Warehouse-schema items (notebooks,
data pipelines, environments, and later semantic models/reports) are
promoted this way -- Warehouse schema is handled entirely by
migration_runner.py via fabric_run_item_job.py, run separately afterward
against the newly-promoted target stage.

Invoke as:
  python -m scripts.ci.fabric_deploy_pipeline_stage --pipeline-id <id> --source-stage-id <id> --target-stage-id <id>
"""

import argparse
import sys

from scripts.ci._fabric_api import FABRIC_API_BASE, FabricApiError, get_access_token, operation_id_from_response, poll_until, request


def deploy_stage(pipeline_id: str, source_stage_id: str, target_stage_id: str, token: str) -> None:
    response = request(
        "POST",
        f"{FABRIC_API_BASE}/deploymentPipelines/{pipeline_id}/deploy",
        token,
        json={
            "sourceStageId": source_stage_id,
            "targetStageId": target_stage_id,
            "note": "Automated CI/CD promotion",
        },
    )

    operation_id = operation_id_from_response(response)
    if not operation_id:
        return

    poll_until(
        check_fn=lambda: request("GET", f"{FABRIC_API_BASE}/operations/{operation_id}", token).json(),
        is_done_fn=lambda r: r.get("status") in ("Succeeded", "Failed"),
        is_success_fn=lambda r: r.get("status") == "Succeeded",
        describe_fn=lambda r: f"deployment pipeline operation {operation_id}: {r.get('status')}",
        interval_seconds=15.0,
        timeout_seconds=1800.0,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pipeline-id", required=True, help="Fabric Deployment Pipeline object ID")
    parser.add_argument("--source-stage-id", required=True)
    parser.add_argument("--target-stage-id", required=True)
    args = parser.parse_args()

    token = get_access_token()
    try:
        deploy_stage(args.pipeline_id, args.source_stage_id, args.target_stage_id, token)
    except FabricApiError as ex:
        print(f"ERROR: {ex}", file=sys.stderr)
        return 1

    print(f"Deployed stage {args.source_stage_id} -> {args.target_stage_id}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
