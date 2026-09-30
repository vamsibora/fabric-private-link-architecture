"""Shared Fabric REST API helpers for scripts/ci/*.py.

Auth: expects `az login` (via azure/login@v2 with OIDC federated
credentials -- see docs/service_principal_requirements.md) to have already
run in the GitHub Actions workflow step. These helpers shell out to
`az account get-access-token` rather than re-implementing MSAL, so they
inherit whatever identity the workflow step already established -- no
separate stored secret needed for the Fabric REST calls.

Exact Fabric REST API paths (git status/updateFromGit, job-instance
polling, environment library staging/publish, deployment-pipeline
stage-deploy) should be double-checked against current Microsoft Learn docs
before relying on this in production -- the Fabric REST surface is still
evolving.
"""

import subprocess
import time
from typing import Any, Callable, Optional

import requests

FABRIC_API_BASE = "https://api.fabric.microsoft.com/v1"
FABRIC_RESOURCE = "https://api.fabric.microsoft.com"
SQL_RESOURCE = "https://database.windows.net"


class FabricApiError(Exception):
    """Raised when a Fabric REST call fails, or a job/operation ends in a
    non-success terminal state."""


def get_access_token(resource: str = FABRIC_RESOURCE) -> str:
    """Fetches an access token for `resource` from the `az` CLI session
    established by the azure/login@v2 step earlier in the workflow."""
    result = subprocess.run(
        ["az", "account", "get-access-token", "--resource", resource, "--query", "accessToken", "-o", "tsv"],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def request(method: str, url: str, token: str, **kwargs) -> requests.Response:
    headers = {**_headers(token), **kwargs.pop("headers", {})}
    response = requests.request(method, url, headers=headers, timeout=30, **kwargs)
    if response.status_code >= 400:
        raise FabricApiError(f"{method} {url} failed ({response.status_code}): {response.text}")
    return response


def operation_id_from_response(response: requests.Response) -> Optional[str]:
    """Fabric long-running operations are returned via a Location header
    (or x-ms-operation-id) pointing at /operations/{id}; a plain 200 with no
    such header means the call was synchronous."""
    operation_id = response.headers.get("x-ms-operation-id")
    if operation_id:
        return operation_id
    location = response.headers.get("Location", "")
    return location.rstrip("/").split("/")[-1] or None


def poll_until(
    check_fn: Callable[[], Any],
    is_done_fn: Callable[[Any], bool],
    is_success_fn: Callable[[Any], bool],
    describe_fn: Callable[[Any], str],
    interval_seconds: float = 10.0,
    timeout_seconds: float = 1800.0,
    sleep_fn: Callable[[float], None] = time.sleep,
    now_fn: Callable[[], float] = time.monotonic,
) -> Any:
    """Polls check_fn() until is_done_fn(result) is True, then asserts
    is_success_fn(result); raises FabricApiError on failure or timeout.
    Generic over git-sync status, job instances, and long-running
    operations, which all follow this poll-to-terminal-state shape.
    """
    start = now_fn()
    while True:
        result = check_fn()
        if is_done_fn(result):
            if not is_success_fn(result):
                raise FabricApiError(f"Operation did not succeed: {describe_fn(result)}")
            return result
        if now_fn() - start > timeout_seconds:
            raise FabricApiError(f"Timed out waiting for operation: {describe_fn(result)}")
        sleep_fn(interval_seconds)
