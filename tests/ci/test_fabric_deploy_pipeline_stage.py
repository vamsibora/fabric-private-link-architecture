"""Unit tests for scripts/ci/fabric_deploy_pipeline_stage.py."""

from unittest.mock import MagicMock, patch

import pytest

from scripts.ci import fabric_deploy_pipeline_stage as fdp


def test_deploy_stage_polls_to_completion():
    deploy_response = MagicMock()
    deploy_response.headers = {"Location": "https://api.fabric.microsoft.com/v1/operations/op-1"}
    op_response = MagicMock()
    op_response.json.return_value = {"status": "Succeeded"}

    with patch.object(fdp, "request", side_effect=[deploy_response, op_response]) as mock_request:
        fdp.deploy_stage("pipe-1", "stage-dev", "stage-uat", "token")

    deploy_call, poll_call = mock_request.call_args_list
    assert deploy_call.args[:2] == ("POST", "https://api.fabric.microsoft.com/v1/deploymentPipelines/pipe-1/deploy")
    assert deploy_call.kwargs["json"]["sourceStageId"] == "stage-dev"
    assert deploy_call.kwargs["json"]["targetStageId"] == "stage-uat"
    assert poll_call.args[:2] == ("GET", "https://api.fabric.microsoft.com/v1/operations/op-1")


def test_deploy_stage_no_op_when_synchronous():
    deploy_response = MagicMock()
    deploy_response.headers = {}

    with patch.object(fdp, "request", return_value=deploy_response) as mock_request:
        fdp.deploy_stage("pipe-1", "stage-dev", "stage-uat", "token")

    assert mock_request.call_count == 1


def test_deploy_stage_raises_on_failure():
    deploy_response = MagicMock()
    deploy_response.headers = {"Location": "https://api.fabric.microsoft.com/v1/operations/op-1"}
    op_response = MagicMock()
    op_response.json.return_value = {"status": "Failed"}

    with patch.object(fdp, "request", side_effect=[deploy_response, op_response]):
        with pytest.raises(fdp.FabricApiError):
            fdp.deploy_stage("pipe-1", "stage-dev", "stage-uat", "token")
