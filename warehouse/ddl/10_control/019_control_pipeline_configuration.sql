-- control.pipeline_configuration: per-environment settings for the Fabric
-- orchestration pipelines (key/value), e.g. copy timeouts or which
-- entity_group a schedule runs. Pipelines orchestrate; they read settings
-- from here rather than embedding them.
CREATE TABLE [control].[pipeline_configuration]
(
    pipeline_configuration_id BIGINT        NOT NULL,
    pipeline_name             VARCHAR(128)  NOT NULL,
    environment               VARCHAR(10)   NOT NULL,   -- DEV | UAT | PROD
    config_key                VARCHAR(128)  NOT NULL,
    config_value              VARCHAR(4000) NULL,
    description               VARCHAR(4000) NULL,
    active_flag               BIT           NOT NULL,
    created_datetime          DATETIME2(6)  NOT NULL,
    created_by                VARCHAR(256)  NOT NULL,
    updated_datetime          DATETIME2(6)  NULL,
    updated_by                VARCHAR(256)  NULL
);
