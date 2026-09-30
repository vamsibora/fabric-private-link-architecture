-- CONTROL.SchemaMigrationHistory: ledger of applied DDL/RLS scripts,
-- consulted by notebooks/framework/migration_runner.py to decide what
-- still needs to run against a given environment's Warehouse.
--
-- Append-heavy, chronological -> GUID PK generated in Python, per the same
-- convention as PipelineRun/TableRun/ErrorLog (see docs/context_prompt.md
-- "Key decisions to preserve"), not the BIGINT IDENTITY used for config
-- tables like IngestionConfig/UserAccess.
--
-- Bootstrap note: this table does not exist until this very script runs, so
-- migration_runner.py treats every script (including 00_schemas/001, 002,
-- and this file itself) as pending on a fresh Warehouse and buffers their
-- ledger rows in memory until immediately after this CREATE TABLE succeeds,
-- rather than querying this table to decide whether to run it.
--
-- Sort position deliberately sits between 00_schemas and 10_control (its own
-- 05_meta tier) so it is created immediately after the schemas it lives in,
-- before any control-plane operational table, without renumbering anything.
CREATE TABLE [CONTROL].[SchemaMigrationHistory]
(
    MigrationID    UNIQUEIDENTIFIER NOT NULL,
    ScriptPath     VARCHAR(400)     NOT NULL,   -- repo-relative POSIX path, e.g. warehouse/ddl/10_control/010_control_ingestionconfig.sql
    ScriptCategory VARCHAR(20)      NOT NULL,   -- 'SCHEMA' | 'RLS'
    Checksum       VARCHAR(64)      NOT NULL,   -- SHA-256 hex of file content at apply time (drift detection)
    Status         VARCHAR(20)      NOT NULL,   -- 'SUCCEEDED' | 'FAILED' | 'SKIPPED_TEMPLATE'
    PipelineRunID  UNIQUEIDENTIFIER NULL,       -- CONTROL.PipelineRun for the migration batch that applied it
    DurationMs     INT              NULL,
    ErrorMessage   VARCHAR(4000)    NULL,
    AppliedBy      VARCHAR(256)     NOT NULL,   -- caller identity (SPN UPN / notebook run-as identity)
    CreatedDate    DATETIME2(6)     NOT NULL
);
