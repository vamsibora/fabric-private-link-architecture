-- CONTROL.Quarantine: holds rows rejected during a TableRun (e.g. failed data
-- quality checks) so they can be inspected and replayed after a fix, rather
-- than silently dropped or failing the whole load.
CREATE TABLE [CONTROL].[Quarantine]
(
    QuarantineID     UNIQUEIDENTIFIER NOT NULL,
    TableRunID       UNIQUEIDENTIFIER NULL,
    SourceSystem     VARCHAR(100)     NOT NULL,
    TargetTable      VARCHAR(256)     NOT NULL,
    RecordKey        VARCHAR(1000)    NULL,       -- business/natural key, for traceability back to source
    RawRecordJson    VARCHAR(MAX)     NULL,       -- offending payload, for replay after the underlying issue is fixed
    QuarantineReason VARCHAR(1000)    NOT NULL,
    ErrorID          UNIQUEIDENTIFIER NULL,
    IsReprocessed    BIT              NOT NULL,
    CreatedDate      DATETIME2(6)     NOT NULL,
    ReprocessedDate  DATETIME2(6)     NULL
);
