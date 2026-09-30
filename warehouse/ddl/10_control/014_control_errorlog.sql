-- CONTROL.ErrorLog: written by utils_logging.log_error(). May reference a
-- PipelineRunID and/or TableRunID (both nullable -- an error can occur before
-- a TableRun exists, e.g. during pipeline-level setup).
CREATE TABLE [CONTROL].[ErrorLog]
(
    ErrorID       UNIQUEIDENTIFIER NOT NULL,
    ExecutionID   UNIQUEIDENTIFIER NULL,
    PipelineRunID UNIQUEIDENTIFIER NULL,
    TableRunID    UNIQUEIDENTIFIER NULL,
    SourceSystem  VARCHAR(100)     NULL,
    TargetTable   VARCHAR(256)     NULL,
    ErrorSeverity VARCHAR(20)      NOT NULL,   -- 'WARNING' | 'ERROR' | 'CRITICAL'
    ErrorMessage  VARCHAR(4000)    NOT NULL,
    ErrorDetails  VARCHAR(MAX)     NULL,       -- full exception/stack trace text
    SourceStage   VARCHAR(50)      NULL,       -- 'BRONZE' | 'SILVER' | 'GOLD' | 'ANONYMIZATION' | 'RLS' | 'CONTROL'
    CreatedDate   DATETIME2(6)     NOT NULL
);
