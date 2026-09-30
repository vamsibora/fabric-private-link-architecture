-- audit.file: landing files written to the Storage Account when
-- landing_enabled = 1. Supports replay: a CREATED/FAILED file can be
-- reprocessed without reconnecting to the source. file_path is unique --
-- the framework never overwrites a landing file.
CREATE TABLE [audit].[file]
(
    file_id               BIGINT         IDENTITY(1, 1) NOT NULL CONSTRAINT pk_file PRIMARY KEY CLUSTERED,
    run_id                VARCHAR(64)    NOT NULL CONSTRAINT fk_file_run REFERENCES [audit].[run] (run_id),
    entity_run_id         VARCHAR(80)    NULL CONSTRAINT fk_file_entity_run REFERENCES [audit].[entity_run] (entity_run_id),
    entity_id             BIGINT         NOT NULL,
    source_system         VARCHAR(100)   NOT NULL,
    source_table          VARCHAR(256)   NOT NULL,
    file_container        VARCHAR(100)   NULL,
    file_path             NVARCHAR(1000) NOT NULL,   -- <source_system>/<table>/<table>_<yyyyMMddHHmmss>.json
    file_name             NVARCHAR(400)  NOT NULL,
    file_size_bytes       BIGINT         NULL,
    row_count             BIGINT         NULL,
    file_created_datetime DATETIME2(3)   NOT NULL CONSTRAINT df_file_file_created DEFAULT SYSUTCDATETIME(),
    status                VARCHAR(20)    NOT NULL,
    processed_run_id      VARCHAR(64)    NULL,
    processed_datetime    DATETIME2(3)   NULL,
    created_datetime      DATETIME2(3)   NOT NULL CONSTRAINT df_file_created DEFAULT SYSUTCDATETIME(),
    CONSTRAINT uq_file_path UNIQUE NONCLUSTERED (file_container, file_path),
    CONSTRAINT ck_file_status CHECK (status IN ('CREATED', 'PROCESSED', 'FAILED', 'REPLAYED'))
);
