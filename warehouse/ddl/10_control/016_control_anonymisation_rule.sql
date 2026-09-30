-- control.anonymisation_rule: reusable anonymisation rules referenced by
-- control.entity_column.anonymisation_rule_id. Applied only in environments
-- where framework_configuration.anonymisation_enabled = 'true'.
CREATE TABLE [control].[anonymisation_rule]
(
    anonymisation_rule_id BIGINT        NOT NULL,
    rule_name             VARCHAR(100)  NOT NULL,   -- e.g. HASH_EMAIL, MASK_PHONE
    rule_type             VARCHAR(20)   NOT NULL,   -- HASH | MASK | REDACT | TOKENIZE | NULLIFY | CUSTOM
    algorithm             VARCHAR(50)   NULL,       -- SHA2_256 | EMAIL | ...
    parameters            VARCHAR(4000) NULL,       -- JSON text
    salt_secret_name      VARCHAR(256)  NULL,       -- Key Vault secret NAME only, never the salt itself
    active_flag           BIT           NOT NULL,
    created_datetime      DATETIME2(6)  NOT NULL,
    created_by            VARCHAR(256)  NOT NULL,
    updated_datetime      DATETIME2(6)  NULL,
    updated_by            VARCHAR(256)  NULL
);
