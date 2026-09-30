"""CONTROL-table logging framework for the ingestion pipeline framework.

Implements a 3-tier tracing hierarchy:

    ExecutionID (correlation GUID, no dedicated table -- carried on
    PipelineRun/ErrorLog; use the orchestrating Data Pipeline's own RunId,
    or let start_pipeline_run() mint one when running standalone)
        -> PipelineRun [PipelineRunID]   one row per pipeline/notebook invocation
              -> TableRun [TableRunID]   one row per table processed in that run
                    -> ErrorLog / Quarantine

Connection: pyodbc against the Fabric Warehouse SQL endpoint, authenticated
with an Entra token obtained from notebookutils.credentials.getToken().
Fabric Warehouse tables are not writable from Spark directly and the
endpoint is Entra-only, so this avoids any separate credential/secret
management -- it reuses the notebook's own run-as identity.

Exception-boundary design (deliberate, not uniform):
  - start_pipeline_run / start_table_run FAIL FAST (raise
    ControlConnectionError). If the opening row can't be written, the run
    is untracked, and silently continuing would create an unaudited run --
    worse than aborting loudly, especially in a framework that also governs
    anonymization/PII handling.
  - end_pipeline_run / end_table_run / log_error FAIL SOFT (never raise,
    return bool). These are typically called from except/finally blocks
    wrapping the caller's real business logic; if they raised, they could
    mask the original exception or leave a run stuck in RUNNING status with
    no visibility at all. On failure they fall back to writing a JSON line
    to the Lakehouse (Files/_framework_fallback/) and logging at CRITICAL,
    so the failure is never completely silent.
"""

import json
import logging
import traceback
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Optional

import notebookutils  # Fabric-injected runtime module
import pyodbc

from notebooks.framework.fabric_connection import (
    get_connection_notebookutils as _get_connection,
)

logger = logging.getLogger("fabric_medallion.control")


class ControlConnectionError(Exception):
    """Raised only by start_pipeline_run/start_table_run (fail-fast by design)."""


@contextmanager
def _cursor(connection_string: str):
    """Context manager yielding a cursor on a fresh connection, closed on exit."""
    conn = _get_connection(connection_string)
    try:
        yield conn.cursor()
    finally:
        conn.close()


def _fallback_log(payload: dict) -> None:
    """Last-resort sink when CONTROL is unreachable. Never raises.

    Writes the event as JSON under a Lakehouse Files/ path (independent of
    the Warehouse being reachable) and logs at CRITICAL so it still surfaces
    in Fabric monitoring even if the fallback file write also fails.
    """
    try:
        path = f"Files/_framework_fallback/{payload.get('kind', 'event')}/{uuid.uuid4()}.json"
        notebookutils.fs.put(path, json.dumps(payload, default=str), overwrite=True)
    except Exception:
        pass
    logger.critical("CONTROL fallback logged: %s", payload)


def start_pipeline_run(
    connection_string: str,
    pipeline_name: str,
    execution_id: Optional[str] = None,
    source_system: Optional[str] = None,
    trigger_type: str = "SCHEDULED",
    parameters: Optional[dict] = None,
) -> str:
    """Insert a CONTROL.PipelineRun row with Status='RUNNING'.

    Args:
        connection_string: Warehouse SQL endpoint connection string, resolved
            by the caller from config (never hardcode workspace/connection
            details here).
        pipeline_name: Name of the calling pipeline/notebook.
        execution_id: Correlation GUID for a logical execution spanning
            multiple pipeline runs. Pass the orchestrating Data Pipeline's
            RunId when available; a new GUID is minted if omitted.
        source_system: Optional source system this run is loading from.
        trigger_type: 'SCHEDULED' | 'MANUAL' | 'EVENT'.
        parameters: Optional dict of run parameters, stored as JSON text.

    Returns:
        The generated PipelineRunID (str GUID).

    Raises:
        ControlConnectionError: if the row could not be written. This
            function fails fast -- an unwritten PipelineRun means the run
            cannot be traced at all.
    """
    pipeline_run_id = str(uuid.uuid4())
    execution_id = execution_id or str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    try:
        with _cursor(connection_string) as cur:
            cur.execute(
                "INSERT INTO CONTROL.PipelineRun "
                "(PipelineRunID, ExecutionID, PipelineName, SourceSystem, StartTime, "
                " Status, TriggerType, ParametersJson, CreatedDate) "
                "VALUES (?, ?, ?, ?, ?, 'RUNNING', ?, ?, ?)",
                pipeline_run_id,
                execution_id,
                pipeline_name,
                source_system,
                now,
                trigger_type,
                json.dumps(parameters or {})[:4000],
                now,
            )
    except Exception as ex:
        logger.exception("start_pipeline_run failed")
        raise ControlConnectionError(str(ex)) from ex
    return pipeline_run_id


def end_pipeline_run(
    connection_string: str,
    pipeline_run_id: str,
    status: str,
    rows_processed: Optional[int] = None,
) -> bool:
    """Update a CONTROL.PipelineRun row with its final status.

    Args:
        connection_string: Warehouse SQL endpoint connection string.
        pipeline_run_id: PipelineRunID returned by start_pipeline_run().
        status: 'SUCCEEDED' | 'FAILED' | 'SUCCEEDED_WITH_ERRORS'.
        rows_processed: Optional total row count for the run.

    Returns:
        True if the update succeeded, False if it fell back to the
        fallback sink. Never raises -- safe to call from a finally block.
    """
    now = datetime.now(timezone.utc)
    try:
        with _cursor(connection_string) as cur:
            cur.execute(
                "UPDATE CONTROL.PipelineRun SET EndTime=?, Status=?, RowsProcessed=?, "
                "ModifiedDate=? WHERE PipelineRunID=?",
                now,
                status,
                rows_processed,
                now,
                pipeline_run_id,
            )
        return True
    except Exception:
        _fallback_log(
            {
                "kind": "end_pipeline_run",
                "pipeline_run_id": pipeline_run_id,
                "status": status,
                "rows_processed": rows_processed,
            }
        )
        return False


def start_table_run(
    connection_string: str,
    pipeline_run_id: str,
    source_system: str,
    target_table: str,
    ingestion_config_id: Optional[int] = None,
    watermark_value_start: Optional[str] = None,
) -> str:
    """Insert a CONTROL.TableRun row with Status='RUNNING'.

    Args:
        connection_string: Warehouse SQL endpoint connection string.
        pipeline_run_id: Parent PipelineRunID from start_pipeline_run().
        source_system: Source system this table is loaded from.
        target_table: Target table name being loaded.
        ingestion_config_id: Optional CONTROL.IngestionConfig.IngestionConfigID
            this run corresponds to.
        watermark_value_start: Optional watermark value the load started from.

    Returns:
        The generated TableRunID (str GUID).

    Raises:
        ControlConnectionError: if the row could not be written (fail-fast,
            same rationale as start_pipeline_run).
    """
    table_run_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    try:
        with _cursor(connection_string) as cur:
            cur.execute(
                "INSERT INTO CONTROL.TableRun "
                "(TableRunID, PipelineRunID, IngestionConfigID, SourceSystem, TargetTable, "
                " StartTime, Status, WatermarkValueStart, CreatedDate) "
                "VALUES (?, ?, ?, ?, ?, ?, 'RUNNING', ?, ?)",
                table_run_id,
                pipeline_run_id,
                ingestion_config_id,
                source_system,
                target_table,
                now,
                watermark_value_start,
                now,
            )
    except Exception as ex:
        logger.exception("start_table_run failed")
        raise ControlConnectionError(str(ex)) from ex
    return table_run_id


def end_table_run(
    connection_string: str,
    table_run_id: str,
    status: str,
    rows_read: Optional[int] = None,
    rows_inserted: Optional[int] = None,
    rows_updated: Optional[int] = None,
    rows_quarantined: Optional[int] = None,
    watermark_value_end: Optional[str] = None,
) -> bool:
    """Update a CONTROL.TableRun row with its final status and row counts.

    Returns:
        True if the update succeeded, False if it fell back to the
        fallback sink. Never raises -- safe to call from a finally block.
    """
    now = datetime.now(timezone.utc)
    try:
        with _cursor(connection_string) as cur:
            cur.execute(
                "UPDATE CONTROL.TableRun SET EndTime=?, Status=?, RowsRead=?, RowsInserted=?, "
                "RowsUpdated=?, RowsQuarantined=?, WatermarkValueEnd=?, ModifiedDate=? "
                "WHERE TableRunID=?",
                now,
                status,
                rows_read,
                rows_inserted,
                rows_updated,
                rows_quarantined,
                watermark_value_end,
                now,
                table_run_id,
            )
        return True
    except Exception:
        _fallback_log({"kind": "end_table_run", "table_run_id": table_run_id, "status": status})
        return False


def log_error(
    connection_string: str,
    error_message: str,
    severity: str = "ERROR",
    execution_id: Optional[str] = None,
    pipeline_run_id: Optional[str] = None,
    table_run_id: Optional[str] = None,
    source_system: Optional[str] = None,
    target_table: Optional[str] = None,
    source_stage: Optional[str] = None,
    exception: Optional[BaseException] = None,
) -> bool:
    """Insert a CONTROL.ErrorLog row.

    Args:
        connection_string: Warehouse SQL endpoint connection string.
        error_message: Short, human-readable error summary.
        severity: 'WARNING' | 'ERROR' | 'CRITICAL'.
        execution_id, pipeline_run_id, table_run_id: Optional tracing IDs to
            attach this error to whatever level of the hierarchy it occurred at.
        source_system, target_table, source_stage: Optional context columns.
        exception: Optional caught exception; its formatted traceback is
            stored in ErrorDetails.

    Returns:
        True if the insert succeeded, False if it fell back to the fallback
        sink. Never raises -- safe to call from any except/finally block,
        so it can't itself crash the pipeline it's meant to be logging for.
    """
    now = datetime.now(timezone.utc)
    details = (
        "".join(traceback.format_exception(type(exception), exception, exception.__traceback__))
        if exception
        else None
    )
    try:
        with _cursor(connection_string) as cur:
            cur.execute(
                "INSERT INTO CONTROL.ErrorLog "
                "(ErrorID, ExecutionID, PipelineRunID, TableRunID, SourceSystem, TargetTable, "
                " ErrorSeverity, ErrorMessage, ErrorDetails, SourceStage, CreatedDate) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                str(uuid.uuid4()),
                execution_id,
                pipeline_run_id,
                table_run_id,
                source_system,
                target_table,
                severity,
                error_message[:4000],
                details,
                source_stage,
                now,
            )
        return True
    except Exception:
        _fallback_log(
            {
                "kind": "log_error",
                "message": error_message,
                "severity": severity,
                "pipeline_run_id": pipeline_run_id,
                "table_run_id": table_run_id,
            }
        )
        return False
