-- CONTROL.AnonymizationRule: defines WHAT should be anonymized (column, rule
-- type, parameters) for a source table. Does NOT execute anonymization itself
-- -- see docs/control_framework.md for the execution-engine scope note.
CREATE TABLE [CONTROL].[AnonymizationRule]
(
    RuleID             BIGINT        IDENTITY(1,1) NOT NULL,
    SourceSystem       VARCHAR(100)  NOT NULL,
    SourceTable        VARCHAR(256)  NOT NULL,
    ColumnName         VARCHAR(128)  NOT NULL,
    RuleType           VARCHAR(30)   NOT NULL,   -- 'HASH' | 'MASK' | 'TOKENIZE' | 'NULLIFY' | 'ENCRYPT'
    RuleParameters     VARCHAR(4000) NULL,       -- JSON text (no XML type available in Fabric DW)
    SaltKeyVaultSecret VARCHAR(256)  NULL,       -- Key Vault secret NAME/URI only, never a raw salt value
    IsActive           BIT           NOT NULL,
    CreatedDate        DATETIME2(6)  NOT NULL,
    CreatedBy          VARCHAR(256)  NOT NULL,
    ModifiedDate       DATETIME2(6)  NULL,
    ModifiedBy         VARCHAR(256)  NULL
);
