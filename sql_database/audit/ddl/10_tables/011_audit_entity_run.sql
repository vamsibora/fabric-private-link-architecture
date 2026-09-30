-- audit.entity_run: one row per entity per run -- the primary operational
-- audit table ("what happened to Customer during run 12345?").
-- entity_run_id = <run_id>-E<entity_id> (deterministic, so the extract
-- pipeline and the framework notebook address the same row without a
-- lookup). A retry within the same run increments attempt_number on the
-- same row rather than creating a new one.
CREATE TABLE [audit].[entity_run]
(
    entity_run_id      VARCHAR(80)    NOT NULL CONSTRAINT pk_entity_run PRIMARY KEY CLUSTERED,
    run_id             VARCHAR(64)    NOT NULL CONSTRAINT fk_entity_run_run REFERENCES [audit].[run] (run_id),
    entity_id          BIGINT         NOT NULL,
    source_system      VARCHAR(100)   NOT NULL,
    source_schema      VARCHAR(128)   NULL,
    source_table       VARCHAR(256)   NOT NULL,
    target_schema      VARCHAR(128)   NULL,
    target_table       VARCHAR(256)   NOT NULL,
    load_type          VARCHAR(20)    NULL,
    write_strategy     VARCHAR(20)    NULL,   -- MERGE | HISTORY | APPEND | REPLACE
    landing_enabled    BIT            NOT NULL,
    landing_path       NVARCHAR(1000) NULL,
    start_datetime     DATETIME2(3)   NOT NULL CONSTRAINT df_entity_run_start DEFAULT SYSUTCDATETIME(),
    end_datetime       DATETIME2(3)   NULL,
    status             VARCHAR(20)    NOT NULL,
    attempt_number     INT            NOT NULL CONSTRAINT df_entity_run_attempt DEFAULT 1,
    source_row_count   BIGINT         NULL,
    staging_row_count  BIGINT         NULL,
    inserted_row_count BIGINT         NULL,
    updated_row_count  BIGINT         NULL,
    deleted_row_count  BIGINT         NULL,
    rejected_row_count BIGINT         NULL,
    bronze_row_count   BIGINT         NULL,
    watermark_before   NVARCHAR(100)  NULL,
    watermark_after    NVARCHAR(100)  NULL,
    pipeline_run_id    VARCHAR(64)    NULL,
    error_message      NVARCHAR(4000) NULL,
    created_datetime   DATETIME2(3)   NOT NULL CONSTRAINT df_entity_run_created DEFAULT SYSUTCDATETIME(),
    updated_datetime   DATETIME2(3)   NULL,
    CONSTRAINT ck_entity_run_status CHECK (status IN
        ('STARTED', 'EXTRACTING', 'EXTRACTED', 'PROCESSING', 'SUCCEEDED', 'FAILED', 'SKIPPED', 'CANCELLED'))
);
