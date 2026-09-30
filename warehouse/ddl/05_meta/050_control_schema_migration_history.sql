-- control.schema_migration_history: ledger of applied Warehouse scripts,
-- consulted by notebooks/framework/migration_runner.py (target WAREHOUSE).
--
-- CREATE-once scripts (warehouse/ddl, security/rls) get exactly one
-- SUCCEEDED row. Repeatable scripts (warehouse/programmability,
-- warehouse/metadata) get one row per applied checksum; the latest row per
-- script_path (by created_datetime) is the one that counts.
--
-- Bootstrap: this table does not exist until this script runs, so the runner
-- buffers ledger rows in memory until immediately after this CREATE TABLE
-- succeeds (see migration_runner.run_migrations).
CREATE TABLE [control].[schema_migration_history]
(
    migration_id     UNIQUEIDENTIFIER NOT NULL,
    script_path      VARCHAR(400)     NOT NULL,   -- repo-relative POSIX path
    script_category  VARCHAR(20)      NOT NULL,   -- SCHEMA | RLS | PROGRAMMABILITY | METADATA
    checksum         VARCHAR(64)      NOT NULL,   -- SHA-256 hex of file content at apply time
    status           VARCHAR(20)      NOT NULL,   -- SUCCEEDED | FAILED | SKIPPED_TEMPLATE
    run_id           VARCHAR(64)      NULL,       -- audit.run.run_id of the migration batch
    duration_ms      INT              NULL,
    error_message    VARCHAR(4000)    NULL,
    applied_by       VARCHAR(256)     NOT NULL,
    created_datetime DATETIME2(6)     NOT NULL
);
