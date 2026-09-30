-- control.column_mapping: optional source-expression overrides applied when
-- landing JSON / staging rows are read into the framework, e.g. casting a
-- JSON string to a timestamp or flattening a nested field. Most columns need
-- no row here -- entity_column.source_column -> target_column is the default.
CREATE TABLE [control].[column_mapping]
(
    column_mapping_id BIGINT        NOT NULL,
    entity_id         BIGINT        NOT NULL,
    target_column     VARCHAR(128)  NOT NULL,
    source_expression VARCHAR(4000) NOT NULL,   -- Spark SQL expression over the landing/staging row
    active_flag       BIT           NOT NULL,
    created_datetime  DATETIME2(6)  NOT NULL,
    created_by        VARCHAR(256)  NOT NULL,
    updated_datetime  DATETIME2(6)  NULL,
    updated_by        VARCHAR(256)  NULL
);
