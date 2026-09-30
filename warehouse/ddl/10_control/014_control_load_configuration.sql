-- control.load_configuration: per-entity load behaviour -- retry policy,
-- source query override and delete detection. At most one active row per entity.
CREATE TABLE [control].[load_configuration]
(
    load_configuration_id           BIGINT        NOT NULL,
    entity_id                       BIGINT        NOT NULL,
    retry_enabled                   BIT           NOT NULL,
    max_retry_count                 INT           NOT NULL,
    retry_delay_seconds             INT           NOT NULL,
    source_query_override           VARCHAR(8000) NULL,   -- may contain {watermark}; resolved by control.fn_active_entities
    source_filter                   VARCHAR(4000) NULL,   -- extra predicate ANDed onto the generated query
    delete_detection_enabled        BIT           NOT NULL,   -- FULL loads only: soft-delete keys missing from source
    row_count_anomaly_threshold_pct DECIMAL(9,2)  NULL,       -- NULL = no row-count anomaly check
    active_flag                     BIT           NOT NULL,
    created_datetime                DATETIME2(6)  NOT NULL,
    created_by                      VARCHAR(256)  NOT NULL,
    updated_datetime                DATETIME2(6)  NULL,
    updated_by                      VARCHAR(256)  NULL
);
