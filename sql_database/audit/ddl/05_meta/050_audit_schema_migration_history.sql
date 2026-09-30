-- audit.schema_migration_history: migration ledger for this database
-- (migration_runner target AUDIT_DB). Same column contract as
-- control.schema_migration_history in the Warehouse so the runner code is
-- shared. Repeatable scripts (procs/, views/) get one row per applied checksum.
CREATE TABLE [audit].[schema_migration_history]
(
    migration_id     UNIQUEIDENTIFIER NOT NULL CONSTRAINT pk_audit_schema_migration_history PRIMARY KEY NONCLUSTERED,
    script_path      VARCHAR(400)     NOT NULL,
    script_category  VARCHAR(20)      NOT NULL,   -- SCHEMA | PROC | VIEW
    checksum         VARCHAR(64)      NOT NULL,
    status           VARCHAR(20)      NOT NULL,   -- SUCCEEDED | FAILED | SKIPPED_TEMPLATE
    run_id           VARCHAR(64)      NULL,
    duration_ms      INT              NULL,
    error_message    VARCHAR(4000)    NULL,
    applied_by       VARCHAR(256)     NOT NULL,
    created_datetime DATETIME2(6)     NOT NULL
);
