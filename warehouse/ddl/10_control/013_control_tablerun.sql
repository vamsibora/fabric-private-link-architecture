-- CONTROL.TableRun: middle tier of the tracing hierarchy. One row per table
-- processed within a PipelineRun. Multiple TableRun rows share one
-- PipelineRunID when a pipeline fans out over CONTROL.IngestionConfig.
CREATE TABLE [CONTROL].[TableRun]
(
    TableRunID          UNIQUEIDENTIFIER NOT NULL,
    PipelineRunID       UNIQUEIDENTIFIER NOT NULL,   -- parent; see 030 constraints for the FK
    IngestionConfigID   BIGINT           NULL,
    SourceSystem        VARCHAR(100)     NOT NULL,
    TargetTable         VARCHAR(256)     NOT NULL,
    StartTime           DATETIME2(6)     NOT NULL,
    EndTime             DATETIME2(6)     NULL,
    Status              VARCHAR(20)      NOT NULL,   -- 'RUNNING' | 'SUCCEEDED' | 'FAILED' | 'SUCCEEDED_WITH_ERRORS'
    WatermarkValueStart VARCHAR(256)     NULL,
    WatermarkValueEnd   VARCHAR(256)     NULL,
    RowsRead            BIGINT           NULL,
    RowsInserted        BIGINT           NULL,
    RowsUpdated         BIGINT           NULL,
    RowsQuarantined     BIGINT           NULL,
    CreatedDate         DATETIME2(6)     NOT NULL,
    ModifiedDate        DATETIME2(6)     NULL
);
