-- control.framework_configuration: environment-driven framework behaviour
-- (key/value per environment). Framework code reads these and never
-- hard-codes DEV/UAT/PROD differences. Known keys are documented on
-- notebooks/bronze/models.py FrameworkConfig and seeded by
-- warehouse/metadata/020_framework_configuration.sql.
CREATE TABLE [control].[framework_configuration]
(
    framework_configuration_id BIGINT        NOT NULL,
    environment                VARCHAR(10)   NOT NULL,   -- DEV | UAT | PROD
    config_key                 VARCHAR(128)  NOT NULL,
    config_value               VARCHAR(4000) NULL,
    description                VARCHAR(4000) NULL,
    active_flag                BIT           NOT NULL,
    created_datetime           DATETIME2(6)  NOT NULL,
    created_by                 VARCHAR(256)  NOT NULL,
    updated_datetime           DATETIME2(6)  NULL,
    updated_by                 VARCHAR(256)  NULL
);
