"""Unit tests for scripts/ci/_fabric_api.py shared helpers."""

from unittest.mock import MagicMock, patch

import pytest

from scripts.ci import _fabric_api as api


def test_get_access_token_calls_az_cli():
    mock_result = MagicMock(stdout="fake-token\n")
    with patch("subprocess.run", return_value=mock_result) as mock_run:
        token = api.get_access_token("https://example.com")

    assert token == "fake-token"
    args = mock_run.call_args[0][0]
    assert args[:3] == ["az", "account", "get-access-token"]
    assert "https://example.com" in args


def test_request_raises_fabric_api_error_on_http_error():
    mock_response = MagicMock(status_code=404, text="not found")
    with patch("requests.request", return_value=mock_response):
        with pytest.raises(api.FabricApiError):
            api.request("GET", "https://example.com", "token")


def test_request_returns_response_on_success_with_auth_header():
    mock_response = MagicMock(status_code=200)
    with patch("requests.request", return_value=mock_response) as mock_req:
        response = api.request("GET", "https://example.com", "tok", params={"a": 1})

    assert response is mock_response
    _, kwargs = mock_req.call_args
    assert kwargs["headers"]["Authorization"] == "Bearer tok"
    assert kwargs["params"] == {"a": 1}


def test_operation_id_from_response_prefers_custom_header():
    response = MagicMock(headers={"x-ms-operation-id": "op-1", "Location": "https://x/operations/op-2"})
    assert api.operation_id_from_response(response) == "op-1"


def test_operation_id_from_response_falls_back_to_location():
    response = MagicMock(headers={"Location": "https://x/operations/op-2"})
    assert api.operation_id_from_response(response) == "op-2"


def test_operation_id_from_response_none_when_no_headers():
    response = MagicMock(headers={})
    assert api.operation_id_from_response(response) is None


def test_poll_until_returns_result_on_success():
    calls = iter([{"status": "Running"}, {"status": "Succeeded"}])
    result = api.poll_until(
        check_fn=lambda: next(calls),
        is_done_fn=lambda r: r["status"] != "Running",
        is_success_fn=lambda r: r["status"] == "Succeeded",
        describe_fn=lambda r: str(r),
        sleep_fn=lambda s: None,
    )
    assert result == {"status": "Succeeded"}


def test_poll_until_raises_on_failure_terminal_state():
    with pytest.raises(api.FabricApiError):
        api.poll_until(
            check_fn=lambda: {"status": "Failed"},
            is_done_fn=lambda r: True,
            is_success_fn=lambda r: r["status"] == "Succeeded",
            describe_fn=lambda r: str(r),
            sleep_fn=lambda s: None,
        )


def test_poll_until_raises_on_timeout():
    now_values = iter([0, 0, 100])
    with pytest.raises(api.FabricApiError):
        api.poll_until(
            check_fn=lambda: {"status": "Running"},
            is_done_fn=lambda r: False,
            is_success_fn=lambda r: True,
            describe_fn=lambda r: str(r),
            timeout_seconds=10,
            sleep_fn=lambda s: None,
            now_fn=lambda: next(now_values),
        )
