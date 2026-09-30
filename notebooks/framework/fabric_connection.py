"""Shared pyodbc/Entra connection helpers for the Fabric Warehouse SQL endpoint.

Two token-acquisition paths, one packing helper:
  - get_connection_notebookutils(): notebookutils.credentials.getToken() --
    used by code running inside a real Fabric notebook (bronze/audit_manager.py,
    migration_runner.py, the Bronze framework), reusing the notebook's own
    run-as identity.
  - get_connection_service_principal(): MSAL/Entra client-credentials (secret
    or federated OIDC assertion) -- used by scripts/ci/verify_migration_state.py,
    which runs in a GitHub Actions runner with no notebookutils available.

Both return a plain pyodbc.Connection with autocommit enabled; callers are
responsible for closing it (see bronze/audit_manager.py for the pattern).
"""

import struct
from typing import Optional

import pyodbc

# SQL_COPT_SS_ACCESS_TOKEN: the pyodbc/ODBC Driver connection attribute used
# to pass an Entra access token in place of a username/password.
_SQL_COPT_SS_ACCESS_TOKEN = 1256
_TOKEN_AUDIENCE = "https://database.windows.net/.default"
# Default notebookutils audience for Fabric SQL endpoints. The working Dev
# reference notebook (ito_dp_fabric_dev/rio/nb_landing_bronze) connects to a
# Warehouse with getToken("pbi"); the database.windows.net audience hit
# internal 500s there. Callers can override per connection -- the value
# comes from control.framework_configuration (sql_token_audience /
# audit_sql_token_audience), never hard-coded at call sites.
DEFAULT_NOTEBOOK_TOKEN_AUDIENCE = "pbi"


def _pack_token(token: str) -> bytes:
    """Pack an Entra access token into the length-prefixed UTF-16LE struct
    the ODBC Driver expects for SQL_COPT_SS_ACCESS_TOKEN -- not a plain string."""
    token_bytes = token.encode("utf-16-le")
    return struct.pack(f"<I{len(token_bytes)}s", len(token_bytes), token_bytes)


def get_connection_with_token(connection_string: str, token: str) -> pyodbc.Connection:
    """Open a pyodbc connection given an already-acquired Entra access token.

    Public building block for both connection paths below, and for
    scripts/ci/verify_migration_state.py, which acquires its token via the
    `az` CLI session azure/login@v2 (OIDC) already established in the
    GitHub Actions workflow step -- no separate stored secret needed just
    for the smoke test.
    """
    conn = pyodbc.connect(
        connection_string,
        attrs_before={_SQL_COPT_SS_ACCESS_TOKEN: _pack_token(token)},
        timeout=30,
    )
    conn.autocommit = True
    return conn


def get_connection_notebookutils(connection_string: str, audience: Optional[str] = None) -> pyodbc.Connection:
    """Open a pyodbc connection using the notebook's own Entra identity.

    Only callable from inside a real Fabric notebook runtime (imports
    notebookutils lazily so this module can still be imported -- e.g. by
    scripts/ci/* -- in environments where notebookutils doesn't exist).

    audience: token audience passed to notebookutils.credentials.getToken;
    defaults to DEFAULT_NOTEBOOK_TOKEN_AUDIENCE.
    """
    import notebookutils  # Fabric-injected runtime module

    token = notebookutils.credentials.getToken(audience or DEFAULT_NOTEBOOK_TOKEN_AUDIENCE)
    return get_connection_with_token(connection_string, token)


def get_connection_service_principal(
    connection_string: str,
    tenant_id: str,
    client_id: str,
    client_secret: Optional[str] = None,
    federated_token: Optional[str] = None,
) -> pyodbc.Connection:
    """Open a pyodbc connection authenticated as a service principal.

    Used by CI (GitHub Actions), which has no notebookutils runtime. Exactly
    one of client_secret or federated_token must be provided:
      - client_secret: confidential-client secret flow (fallback).
      - federated_token: a federated (e.g. GitHub OIDC) assertion, exchanged
        for an Entra token via the federated-credential flow (preferred --
        no long-lived secret to leak or rotate).
    """
    import msal

    if bool(client_secret) == bool(federated_token):
        raise ValueError("Provide exactly one of client_secret or federated_token")

    authority = f"https://login.microsoftonline.com/{tenant_id}"
    if federated_token:
        app = msal.ConfidentialClientApplication(
            client_id,
            authority=authority,
            client_credential={"client_assertion": federated_token},
        )
    else:
        app = msal.ConfidentialClientApplication(
            client_id,
            authority=authority,
            client_credential=client_secret,
        )

    result = app.acquire_token_for_client(scopes=[_TOKEN_AUDIENCE])
    if "access_token" not in result:
        raise RuntimeError(
            f"Failed to acquire SPN token: {result.get('error')}: {result.get('error_description')}"
        )
    return get_connection_with_token(connection_string, result["access_token"])
