"""Metadata-driven Bronze ingestion framework.

Component map (spec section 42):

    config_loader         Configuration Loader   (control.* -> models)
    run_manager           Run Manager            (run_id / entity_run_id / run timestamp)
    landing_manager       Landing Manager        (Storage Account JSON landing files)
    staging_manager       Staging Manager        (Bronze Lakehouse staging tables)
    schema_manager        Schema Manager         (Delta table DDL + technical columns)
    validation_engine     Validation Engine
    dedup_engine          Deduplication Engine
    anonymisation_engine  Anonymisation Engine
    hash_engine           Hash Engine
    merge_engine          Merge Engine           (current-state MERGE / APPEND / REPLACE)
    history_engine        Historical Load Engine (source-history append, no SCD2)
    watermark_manager     Watermark Manager
    audit_manager         Audit Manager          (central audit SQL Database)
    error_manager         Error Manager          (classification + retry)
    orchestrator          Orchestrator

Modules keep their pure logic (SQL/expression builders, classification,
roll-ups) separate from the thin Spark/pyodbc adapters, so the logic is unit
tested without a Fabric runtime. pyspark is imported lazily inside the
adapters only.
"""
