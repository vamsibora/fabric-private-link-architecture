-- audit.activity: detailed framework events (COPY_COMPLETED,
-- VALIDATION_COMPLETED, MERGE_COMPLETED, WATERMARK_UPDATED, ...), written by
-- both pipelines (activity_source = 'PIPELINE') and the framework notebook
-- ('NOTEBOOK'). Never contains source data values.
CREATE TABLE [audit].[activity]
(
    activity_id      BIGINT         IDENTITY(1, 1) NOT NULL CONSTRAINT pk_activity PRIMARY KEY CLUSTERED,
    run_id           VARCHAR(64)    NOT NULL CONSTRAINT fk_activity_run REFERENCES [audit].[run] (run_id),
    entity_run_id    VARCHAR(80)    NULL CONSTRAINT fk_activity_entity_run REFERENCES [audit].[entity_run] (entity_run_id),
    activity_type    VARCHAR(50)    NOT NULL,
    activity_name    NVARCHAR(256)  NULL,
    activity_source  VARCHAR(20)    NOT NULL CONSTRAINT df_activity_source DEFAULT 'NOTEBOOK',
    start_datetime   DATETIME2(3)   NULL,
    end_datetime     DATETIME2(3)   NULL,
    status           VARCHAR(20)    NOT NULL,   -- STARTED | SUCCEEDED | FAILED | WARNING | SKIPPED
    message          NVARCHAR(4000) NULL,
    rows_affected    BIGINT         NULL,
    duration_ms      BIGINT         NULL,
    created_datetime DATETIME2(3)   NOT NULL CONSTRAINT df_activity_created DEFAULT SYSUTCDATETIME()
);
