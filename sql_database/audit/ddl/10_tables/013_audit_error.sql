-- audit.error: centralised errors. error_code keeps the ORIGINAL source
-- error code (SQLSTATE / SQL error number / Fabric failure code) wherever
-- the framework could extract it; is_retryable is the framework's
-- classification (notebooks/bronze/error_manager.py).
CREATE TABLE [audit].[error]
(
    error_id         BIGINT         IDENTITY(1, 1) NOT NULL CONSTRAINT pk_error PRIMARY KEY CLUSTERED,
    run_id           VARCHAR(64)    NOT NULL CONSTRAINT fk_error_run REFERENCES [audit].[run] (run_id),
    entity_run_id    VARCHAR(80)    NULL CONSTRAINT fk_error_entity_run REFERENCES [audit].[entity_run] (entity_run_id),
    error_datetime   DATETIME2(3)   NOT NULL CONSTRAINT df_error_datetime DEFAULT SYSUTCDATETIME(),
    error_stage      VARCHAR(50)    NULL,   -- EXTRACT | LANDING | STAGING | VALIDATION | ANONYMISATION | HASH | WRITE | WATERMARK | AUDIT | ORCHESTRATION
    error_code       VARCHAR(100)   NULL,
    error_message    NVARCHAR(4000) NOT NULL,
    source_system    VARCHAR(100)   NULL,
    source_table     VARCHAR(256)   NULL,
    target_table     VARCHAR(256)   NULL,
    is_retryable     BIT            NOT NULL CONSTRAINT df_error_retryable DEFAULT 0,
    attempt_number   INT            NULL,
    stack_trace      NVARCHAR(MAX)  NULL,
    created_datetime DATETIME2(3)   NOT NULL CONSTRAINT df_error_created DEFAULT SYSUTCDATETIME()
);
