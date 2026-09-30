-- CONTROL.PipelineRun: top tier of the tracing hierarchy (ExecutionID ->
-- PipelineRunID -> TableRunID). One row per pipeline/notebook invocation.
--
-- PipelineRunID/ExecutionID are GUIDs generated in Python (uuid.uuid4()) before
-- insert, not IDENTITY -- this is a high-concurrency, append-heavy table (many
-- parallel pipeline runs), and the ID must be known up front so it can be
-- threaded into child CONTROL.TableRun rows without a round-trip lookup.
CREATE TABLE [CONTROL].[PipelineRun]
(
    PipelineRunID  UNIQUEIDENTIFIER NOT NULL,
    ExecutionID    UNIQUEIDENTIFIER NOT NULL,   -- correlates multiple pipeline runs under one logical execution
    PipelineName   VARCHAR(256)     NOT NULL,
    SourceSystem   VARCHAR(100)     NULL,
    StartTime      DATETIME2(6)     NOT NULL,
    EndTime        DATETIME2(6)     NULL,
    Status         VARCHAR(20)      NOT NULL,   -- 'RUNNING' | 'SUCCEEDED' | 'FAILED' | 'SUCCEEDED_WITH_ERRORS'
    TriggerType    VARCHAR(30)      NULL,       -- 'SCHEDULED' | 'MANUAL' | 'EVENT'
    ParametersJson VARCHAR(4000)    NULL,
    RowsProcessed  BIGINT           NULL,
    CreatedDate    DATETIME2(6)     NOT NULL,
    ModifiedDate   DATETIME2(6)     NULL
);
