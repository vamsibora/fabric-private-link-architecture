"""Unit tests for scripts/ci/fabric_run_item_job.py."""

from unittest.mock import MagicMock, patch

import pytest

from scripts.ci import fabric_run_item_job as frj


def test_run_item_job_polls_until_completed():
    submit_response = MagicMock()
    submit_response.headers = {"Location": "https://api.fabric.microsoft.com/v1/.../jobs/instances/job-1"}

    status_response = MagicMock()
    status_response.json.return_value = {"status": "Completed"}

    with patch.object(frj, "request", side_effect=[submit_response, status_response]) as mock_request:
        result = frj.run_item_job("ws-1", "item-1", "token", parameters={"TargetEnvironment": "dev"})

    assert result == {"status": "Completed"}
    submit_call, poll_call = mock_request.call_args_list
    assert submit_call.args[:2] == ("POST", "https://api.fabric.microsoft.com/v1/workspaces/ws-1/items/item-1/jobs/instances")
    assert submit_call.kwargs["params"] == {"jobType": "Pipeline"}
    assert submit_call.kwargs["json"] == {"executionData": {"parameters": {"TargetEnvironment": "dev"}}}
    assert poll_call.args[0] == "GET"
    assert poll_call.args[1].endswith("/jobs/instances/job-1")


def test_run_item_job_raises_when_no_job_instance_id():
    submit_response = MagicMock()
    submit_response.headers = {}

    with patch.object(frj, "request", return_value=submit_response):
        with pytest.raises(frj.FabricApiError):
            frj.run_item_job("ws-1", "item-1", "token")


def test_run_item_job_raises_on_failed_terminal_status():
    submit_response = MagicMock()
    submit_response.headers = {"Location": "https://api.fabric.microsoft.com/v1/.../jobs/instances/job-1"}
    status_response = MagicMock()
    status_response.json.return_value = {"status": "Failed", "failureReason": "boom"}

    with patch.object(frj, "request", side_effect=[submit_response, status_response]):
        with pytest.raises(frj.FabricApiError):
            frj.run_item_job("ws-1", "item-1", "token")
