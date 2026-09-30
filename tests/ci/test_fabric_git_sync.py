"""Unit tests for scripts/ci/fabric_git_sync.py."""

from unittest.mock import MagicMock, patch

from scripts.ci import fabric_git_sync as fgs


def test_sync_workspace_from_git_polls_to_completion():
    status_response = MagicMock()
    status_response.json.return_value = {"workspaceHead": "abc", "remoteCommitHash": "def"}

    update_response = MagicMock()
    update_response.headers = {"Location": "https://api.fabric.microsoft.com/v1/operations/op-1"}

    op_response = MagicMock()
    op_response.json.return_value = {"status": "Succeeded"}

    with patch.object(fgs, "request", side_effect=[status_response, update_response, op_response]) as mock_request:
        fgs.sync_workspace_from_git("ws-1", "token")

    assert mock_request.call_count == 3
    get_status_call, update_call, poll_call = mock_request.call_args_list
    assert get_status_call.args[:2] == ("GET", "https://api.fabric.microsoft.com/v1/workspaces/ws-1/git/status")
    assert update_call.args[:2] == ("POST", "https://api.fabric.microsoft.com/v1/workspaces/ws-1/git/updateFromGit")
    assert poll_call.args[:2] == ("GET", "https://api.fabric.microsoft.com/v1/operations/op-1")


def test_sync_workspace_from_git_no_op_when_synchronous():
    status_response = MagicMock()
    status_response.json.return_value = {"workspaceHead": "abc", "remoteCommitHash": "def"}

    update_response = MagicMock()
    update_response.headers = {}

    with patch.object(fgs, "request", side_effect=[status_response, update_response]) as mock_request:
        fgs.sync_workspace_from_git("ws-1", "token")

    assert mock_request.call_count == 2


def test_sync_workspace_from_git_raises_when_operation_fails():
    status_response = MagicMock()
    status_response.json.return_value = {"workspaceHead": "abc", "remoteCommitHash": "def"}

    update_response = MagicMock()
    update_response.headers = {"Location": "https://api.fabric.microsoft.com/v1/operations/op-1"}

    op_response = MagicMock()
    op_response.json.return_value = {"status": "Failed"}

    with patch.object(fgs, "request", side_effect=[status_response, update_response, op_response]):
        try:
            fgs.sync_workspace_from_git("ws-1", "token")
            assert False, "expected FabricApiError"
        except fgs.FabricApiError:
            pass
