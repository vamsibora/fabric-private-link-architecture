-- control.source_connection: per-environment connection REFERENCES for a
-- source system. Never holds a credential: authentication is done by the
-- Fabric connection / gateway itself, and anything secret is referenced by
-- Key Vault secret NAME only.
CREATE TABLE [control].[source_connection]
(
    source_connection_id  BIGINT        NOT NULL,
    source_system_id      BIGINT        NOT NULL,
    environment           VARCHAR(10)   NOT NULL,   -- DEV | UAT | PROD
    connection_reference  VARCHAR(128)  NOT NULL,   -- matches control.source_system.connection_reference
    fabric_connection_id  VARCHAR(64)   NULL,       -- Fabric connection GUID (an identifier, not a secret)
    gateway_name          VARCHAR(128)  NULL,       -- on-premises data gateway / VNet gateway name
    database_name         VARCHAR(128)  NULL,       -- source database (relational sources)
    auth_type             VARCHAR(30)   NOT NULL,   -- FABRIC_CONNECTION | MANAGED_IDENTITY | KEY_VAULT_SECRET
    key_vault_secret_name VARCHAR(256)  NULL,       -- secret NAME only, never a value
    active_flag           BIT           NOT NULL,
    created_datetime      DATETIME2(6)  NOT NULL,
    created_by            VARCHAR(256)  NOT NULL,
    updated_datetime      DATETIME2(6)  NULL,
    updated_by            VARCHAR(256)  NULL
);
