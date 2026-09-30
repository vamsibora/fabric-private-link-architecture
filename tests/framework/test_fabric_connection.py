"""Unit tests for notebooks/framework/fabric_connection.py.

pyodbc, notebookutils, and msal are all mocked -- these tests validate token
packing and the two connection-acquisition paths without a live Fabric or
Entra connection.
"""

import sys
import types
from unittest.mock import MagicMock, patch

import pytest

sys.modules.setdefault("notebookutils", types.ModuleType("notebookutils"))
sys.modules["notebookutils"].credentials = MagicMock(getToken=MagicMock(return_value="fake-token"))

from notebooks.framework import fabric_connection as fc  # noqa: E402


def test_pack_token_produces_length_prefixed_utf16le_struct():
    packed = fc._pack_token("abc")
    token_bytes = "abc".encode("utf-16-le")
    assert packed[:4] == len(token_bytes).to_bytes(4, "little")
    assert packed[4:] == token_bytes


def test_get_connection_notebookutils_uses_notebook_token():
    mock_conn = MagicMock()
    with patch("pyodbc.connect", return_value=mock_conn) as mock_connect:
        conn = fc.get_connection_notebookutils("dummy-conn-string")

    assert conn is mock_conn
    assert mock_conn.autocommit is True
    args, kwargs = mock_connect.call_args
    assert args[0] == "dummy-conn-string"
    assert fc._SQL_COPT_SS_ACCESS_TOKEN in kwargs["attrs_before"]


def test_get_connection_service_principal_requires_exactly_one_credential():
    with pytest.raises(ValueError):
        fc.get_connection_service_principal("dummy-conn-string", "tenant", "client")

    with pytest.raises(ValueError):
        fc.get_connection_service_principal(
            "dummy-conn-string", "tenant", "client", client_secret="s", federated_token="t"
        )


def _stub_msal(monkeypatch, token_result):
    mock_app = MagicMock()
    mock_app.acquire_token_for_client.return_value = token_result
    mock_msal_module = types.ModuleType("msal")
    mock_msal_module.ConfidentialClientApplication = MagicMock(return_value=mock_app)
    monkeypatch.setitem(sys.modules, "msal", mock_msal_module)
    return mock_msal_module


def test_get_connection_service_principal_with_secret(monkeypatch):
    mock_msal_module = _stub_msal(monkeypatch, {"access_token": "spn-token"})
    mock_conn = MagicMock()

    with patch("pyodbc.connect", return_value=mock_conn):
        conn = fc.get_connection_service_principal(
            "dummy-conn-string", "tenant-id", "client-id", client_secret="super-secret"
        )

    assert conn is mock_conn
    mock_msal_module.ConfidentialClientApplication.assert_called_once()


def test_get_connection_service_principal_with_federated_token(monkeypatch):
    mock_msal_module = _stub_msal(monkeypatch, {"access_token": "spn-token"})
    mock_conn = MagicMock()

    with patch("pyodbc.connect", return_value=mock_conn):
        conn = fc.get_connection_service_principal(
            "dummy-conn-string", "tenant-id", "client-id", federated_token="oidc-assertion"
        )

    assert conn is mock_conn
    _, kwargs = mock_msal_module.ConfidentialClientApplication.call_args
    assert kwargs["client_credential"] == {"client_assertion": "oidc-assertion"}


def test_get_connection_service_principal_raises_on_token_failure(monkeypatch):
    _stub_msal(monkeypatch, {"error": "invalid_client", "error_description": "bad credentials"})

    with pytest.raises(RuntimeError):
        fc.get_connection_service_principal("dummy-conn-string", "tenant-id", "client-id", client_secret="s")
