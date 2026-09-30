-- control.entity_column: column-level metadata. Drives select lists, hash
-- expressions, merge conditions, validation, anonymisation and Bronze/staging
-- table definitions. target_data_type is a Spark SQL type (STRING, INT,
-- BIGINT, DECIMAL(18,2), TIMESTAMP, DATE, BOOLEAN, ...).
CREATE TABLE [control].[entity_column]
(
    entity_column_id      BIGINT        NOT NULL,
    entity_id             BIGINT        NOT NULL,
    source_column         VARCHAR(128)  NOT NULL,
    target_column         VARCHAR(128)  NOT NULL,
    ordinal_position      INT           NOT NULL,
    source_data_type      VARCHAR(128)  NULL,
    target_data_type      VARCHAR(128)  NOT NULL,
    nullable_flag         BIT           NOT NULL,
    primary_key_flag      BIT           NOT NULL,
    watermark_flag        BIT           NOT NULL,
    hash_flag             BIT           NOT NULL,   -- participates in bronze_record_hash
    anonymisation_flag    BIT           NOT NULL,
    anonymisation_rule_id BIGINT        NULL,
    active_flag           BIT           NOT NULL,
    created_datetime      DATETIME2(6)  NOT NULL,
    created_by            VARCHAR(256)  NOT NULL,
    updated_datetime      DATETIME2(6)  NULL,
    updated_by            VARCHAR(256)  NULL
);
