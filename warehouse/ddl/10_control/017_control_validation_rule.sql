-- control.validation_rule: metadata-driven data-quality rules. The framework
-- also applies built-in PRIMARY_KEY_NULL / DUPLICATE_PRIMARY_KEY /
-- COLUMN_MISSING rules to every entity unless a row here overrides them
-- (see notebooks/bronze/validation_engine.py).
CREATE TABLE [control].[validation_rule]
(
    validation_rule_id BIGINT        NOT NULL,
    entity_id          BIGINT        NOT NULL,
    rule_name          VARCHAR(100)  NOT NULL,
    rule_type          VARCHAR(40)   NOT NULL,   -- PRIMARY_KEY_NULL | DUPLICATE_PRIMARY_KEY | MANDATORY_COLUMN_NULL
                                                 -- COLUMN_MISSING | DATA_TYPE_MISMATCH | WATERMARK_INVALID
                                                 -- ROW_COUNT_ANOMALY | CUSTOM
    column_name        VARCHAR(128)  NULL,
    expression         VARCHAR(4000) NULL,       -- CUSTOM: Spark SQL predicate every row must satisfy
    severity           VARCHAR(10)   NOT NULL,   -- LOW | MEDIUM | HIGH | CRITICAL
    failure_action     VARCHAR(10)   NOT NULL,   -- FAIL | WARN | IGNORE
    validation_stage   VARCHAR(10)   NOT NULL,   -- PRE (staging) | POST (after the Bronze write)
    active_flag        BIT           NOT NULL,
    created_datetime   DATETIME2(6)  NOT NULL,
    created_by         VARCHAR(256)  NOT NULL,
    updated_datetime   DATETIME2(6)  NULL,
    updated_by         VARCHAR(256)  NULL
);
