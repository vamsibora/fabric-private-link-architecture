"""Audit Manager: writes the central, cross-workspace audit trail to the
Fabric SQL Database (schema audit) through its stored procedures -- the
same procedures the pipelines call, so pipeline- and notebook-written audit
rows are identical in shape.

Exception boundaries are deliberately NOT uniform (carried over from the
original utils_logging design):

  start_run / start_entity_run        FAIL FAST -> AuditConnectionError.
      An untracked run or entity is worse than aborting loudly, especially
      in a framework that also governs anonymisation.

  everything else (log_*, update/complete_*)   FAIL SOFT -> returns bool.
      These run inside except/finally blocks around real work; raising
      could mask the real exception, or fail a Bronze load that actually
      succeeded. On failure the event goes to a JSON fallback file under
      Files/_framework_fallback/ plus logger.critical, so it is never
      silently lost. If audit_failure_is_critical is on, the failure is
      escalated as AuditCriticalError AFTER the fallback write.

Connections are one per thread (entities run in parallel threads and a
pyodbc connection must not be shared across threads), reopened on failure.
Nothing written here may contain source data values: callers pass
sanitised messages (error_manager.sanitise_message) and counts only.
"""

import json
import logging
import threading
import uuid
from datetime import datetime, timezone
from typing import Callable, Dict, Iterable, Optional

from notebooks.bronze.error_manager import (
    AuditConnectionError,
    AuditCriticalError,
    ErrorInfo,
    sanitise_message,
)
from notebooks.bronze.run_manager import RunContext

logger = logging.getLogger("fabric_medallion.audit")

ACTIVITY_SOURCE_NOTEBOOK = "NOTEBOOK"


def _exec_sql(proc: str, params: Dict[str, object]) -> tuple:
    """EXEC [audit].[<proc>] @a = ?, @b = ? ... with named parameters, so
    procedure signature changes that add optional parameters never break
    positional binding."""
    names = list(params)
    assignments = ", ".join(f"@{name} = ?" for name in names)
    sql = f"EXEC [audit].[{proc}] {assignments}" if names else f"EXEC [audit].[{proc}]"
    return sql, tuple(params[name] for name in names)


class AuditManager:
    def __init__(
        self,
        connection_string: str,
        context: RunContext,
        critical: bool = False,
        enabled: bool = True,
        connect: Optional[Callable[[str], object]] = None,
        fallback_writer: Optional[Callable[[str, str], None]] = None,
    ):
        """
        connection_string: audit SQL Database connection string, resolved by
            the caller from parameters/config -- never hard-coded.
        critical: framework_configuration.audit_failure_is_critical.
        enabled: framework_configuration.audit_enabled. When False every
            call is a no-op that reports success (fail-fast calls included).
        connect: connection factory (default: notebookutils token + pyodbc).
        fallback_writer: (path, content) sink for fail-soft fallbacks
            (default: notebookutils.fs.put).
        """
        self.connection_string = connection_string
        self.context = context
        self.critical = critical
        self.enabled = enabled
        self._connect = connect or self._default_connect
        self._fallback_writer = fallback_writer
        self._local = threading.local()

    # --- connection handling -------------------------------------------------

    @staticmethod
    def _default_connect(connection_string: str):
        from notebooks.framework.fabric_connection import get_connection_notebookutils

        return get_connection_notebookutils(connection_string)

    def _connection(self):
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = self._connect(self.connection_string)
            self._local.conn = conn
        return conn

    def _reset_connection(self) -> None:
        conn = getattr(self._local, "conn", None)
        self._local.conn = None
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass

    def _execute(self, proc: str, params: Dict[str, object], fetch: bool = False):
        """Run one audit procedure, reconnecting once on a dropped connection."""
        sql, values = _exec_sql(proc, params)
        for attempt in (1, 2):
            try:
                cursor = self._connection().cursor()
                cursor.execute(sql, *values)
                return cursor.fetchall() if fetch else None
            except Exception:
                self._reset_connection()
                if attempt == 2:
                    raise
        return None  # pragma: no cover

    def close(self) -> None:
        self._reset_connection()

    # --- boundary helpers ----------------------------------------------------

    def _fail_fast(self, kind: str, proc: str, params: Dict[str, object]):
        if not self.enabled:
            return None
        try:
            return self._execute(proc, params, fetch=True)
        except Exception as ex:
            logger.exception("audit %s failed", kind)
            raise AuditConnectionError(f"audit {kind} failed: {sanitise_message(str(ex))}") from ex

    def _fail_soft(self, kind: str, proc: str, params: Dict[str, object]) -> bool:
        if not self.enabled:
            return True
        try:
            self._execute(proc, params)
            return True
        except Exception as ex:
            self._fallback({"kind": kind, "proc": proc, "params": params,
                            "error": sanitise_message(str(ex))})
            if self.critical:
                raise AuditCriticalError(f"audit {kind} failed and audit_failure_is_critical is on") from ex
            return False

    def _fallback(self, payload: dict) -> None:
        """Last-resort sink when the audit database is unreachable. Never raises."""
        payload = dict(payload, run_id=self.context.run_id, logged_at=datetime.now(timezone.utc).isoformat())
        try:
            writer = self._fallback_writer
            if writer is None:
                import notebookutils  # Fabric-injected runtime module

                def writer(path, content):
                    notebookutils.fs.put(path, content, overwrite=True)

            writer(f"Files/_framework_fallback/audit/{payload.get('kind', 'event')}/{uuid.uuid4()}.json",
                   json.dumps(payload, default=str))
        except Exception:
            pass
        logger.critical("AUDIT fallback logged: %s", payload)

    # --- run level -------------------------------------------------------------

    def start_run(self, total_entities: Optional[int] = None, trigger_type: Optional[str] = None) -> str:
        ctx = self.context
        self._fail_fast("start_run", "usp_start_run", {
            "run_id": ctx.run_id,
            "framework_name": ctx.framework_name,
            "environment": ctx.environment,
            "workspace_id": ctx.workspace_id,
            "workspace_name": ctx.workspace_name,
            "pipeline_name": ctx.pipeline_name,
            "pipeline_run_id": ctx.pipeline_run_id,
            "notebook_name": ctx.notebook_name,
            "trigger_type": trigger_type or ctx.trigger_type,
            "trigger_name": ctx.trigger_name,
            "initiated_by": ctx.initiated_by,
            "run_timestamp": ctx.run_timestamp,
            "entity_group": ctx.entity_group,
            "total_entities": total_entities,
        })
        return ctx.run_id

    def complete_run(self, status: Optional[str] = None, message: Optional[str] = None) -> bool:
        return self._fail_soft("complete_run", "usp_complete_run", {
            "run_id": self.context.run_id,
            "status": status,
            "message": sanitise_message(message) if message else None,
        })

    # --- entity level ----------------------------------------------------------

    def start_entity_run(self, entity, watermark_before: Optional[str] = None, status: str = "PROCESSING") -> str:
        entity_run_id = self.context.entity_run_id(entity.entity_id)
        self._fail_fast("start_entity_run", "usp_start_entity_run", {
            "entity_run_id": entity_run_id,
            "run_id": self.context.run_id,
            "entity_id": entity.entity_id,
            "source_system": entity.source_system,
            "source_schema": entity.source_schema,
            "source_table": entity.source_table,
            "target_schema": entity.target_schema,
            "target_table": entity.target_table,
            "load_type": entity.load_type,
            "landing_enabled": 1 if entity.landing_enabled else 0,
            "write_strategy": entity.write_strategy,
            "watermark_before": watermark_before,
            "pipeline_run_id": self.context.pipeline_run_id,
            "status": status,
        })
        return entity_run_id

    def update_entity_run(self, entity_run_id: str, status: str, landing_path: Optional[str] = None,
                          source_row_count: Optional[int] = None, staging_row_count: Optional[int] = None,
                          write_strategy: Optional[str] = None, error_message: Optional[str] = None) -> bool:
        return self._fail_soft("update_entity_run", "usp_update_entity_run", {
            "entity_run_id": entity_run_id,
            "status": status,
            "landing_path": landing_path,
            "source_row_count": source_row_count,
            "staging_row_count": staging_row_count,
            "write_strategy": write_strategy,
            "error_message": sanitise_message(error_message) if error_message else None,
        })

    def complete_entity_run(self, entity_run_id: str, status: str, staging_row_count: Optional[int] = None,
                            inserted_row_count: Optional[int] = None, updated_row_count: Optional[int] = None,
                            deleted_row_count: Optional[int] = None, rejected_row_count: Optional[int] = None,
                            bronze_row_count: Optional[int] = None, watermark_after: Optional[str] = None,
                            write_strategy: Optional[str] = None, error_message: Optional[str] = None) -> bool:
        return self._fail_soft("complete_entity_run", "usp_complete_entity_run", {
            "entity_run_id": entity_run_id,
            "status": status,
            "staging_row_count": staging_row_count,
            "inserted_row_count": inserted_row_count,
            "updated_row_count": updated_row_count,
            "deleted_row_count": deleted_row_count,
            "rejected_row_count": rejected_row_count,
            "bronze_row_count": bronze_row_count,
            "watermark_after": watermark_after,
            "write_strategy": write_strategy,
            "error_message": sanitise_message(error_message) if error_message else None,
        })

    def get_run_entities(self, status: str = "EXTRACTED") -> Iterable[dict]:
        """Entities the extract pipelines finished for this run. Read path --
        raises AuditConnectionError, because without it the framework cannot
        know what to process."""
        rows = self._fail_fast("get_run_entities", "usp_get_run_entities",
                               {"run_id": self.context.run_id, "status": status}) or []
        keys = ("entity_run_id", "entity_id", "landing_enabled", "landing_path", "source_row_count",
                "attempt_number")
        return [dict(zip(keys, row)) for row in rows]

    def previous_row_count(self, entity) -> Optional[int]:
        """Staging row count of the entity's last successful run (the
        ROW_COUNT_ANOMALY baseline). Fail-soft: None when unavailable."""
        if not self.enabled:
            return None
        try:
            rows = self._execute("usp_get_entity_baseline", {
                "entity_id": entity.entity_id,
                "environment": self.context.environment,
                "exclude_run_id": self.context.run_id,
            }, fetch=True) or []
        except Exception as ex:
            self._fallback({"kind": "previous_row_count", "entity_id": entity.entity_id,
                            "error": sanitise_message(str(ex))})
            return None
        if not rows:
            return None
        value = rows[0][0] if rows[0][0] is not None else rows[0][1]
        return None if value is None else int(value)

    # --- detail ----------------------------------------------------------------

    def log_activity(self, entity_run_id: Optional[str], activity_type: str, status: str,
                     activity_name: Optional[str] = None, message: Optional[str] = None,
                     rows_affected: Optional[int] = None, start_datetime: Optional[datetime] = None,
                     end_datetime: Optional[datetime] = None) -> bool:
        return self._fail_soft("log_activity", "usp_log_activity", {
            "run_id": self.context.run_id,
            "entity_run_id": entity_run_id,
            "activity_type": activity_type,
            "activity_name": activity_name,
            "status": status,
            "message": sanitise_message(message) if message else None,
            "rows_affected": rows_affected,
            "start_datetime": start_datetime,
            "end_datetime": end_datetime,
            "activity_source": ACTIVITY_SOURCE_NOTEBOOK,
        })

    def log_error(self, error: ErrorInfo, entity=None, entity_run_id: Optional[str] = None,
                  attempt_number: Optional[int] = None) -> bool:
        return self._fail_soft("log_error", "usp_log_error", {
            "run_id": self.context.run_id,
            "entity_run_id": entity_run_id,
            "error_stage": error.stage,
            "error_code": (error.error_code or "")[:100] or None,
            "error_message": error.message,
            "source_system": getattr(entity, "source_system", None),
            "source_table": getattr(entity, "source_table", None),
            "target_table": getattr(entity, "target_name", None),
            "is_retryable": 1 if error.is_retryable else 0,
            "attempt_number": attempt_number,
            "stack_trace": error.stack_trace,
        })

    def log_validation(self, entity_run_id: str, result) -> bool:
        """result: validation_engine.ValidationResult (counts only, no values)."""
        return self._fail_soft("log_validation", "usp_log_validation", {
            "run_id": self.context.run_id,
            "entity_run_id": entity_run_id,
            "validation_rule_id": result.rule_id,
            "validation_rule": result.rule_name,
            "validation_type": result.rule_type,
            "validation_stage": result.stage,
            "status": result.status,
            "failure_action": result.failure_action,
            "severity": result.severity,
            "expected_value": None if result.expected_value is None else str(result.expected_value),
            "actual_value": None if result.actual_value is None else str(result.actual_value),
            "failed_row_count": result.failed_row_count,
            "error_message": sanitise_message(result.error_message) if result.error_message else None,
        })

    def log_file(self, entity, entity_run_id: Optional[str], file_path: str, file_name: str,
                 container: Optional[str], status: str, file_size_bytes: Optional[int] = None,
                 row_count: Optional[int] = None) -> bool:
        return self._fail_soft("log_file", "usp_log_file", {
            "run_id": self.context.run_id,
            "entity_run_id": entity_run_id,
            "entity_id": entity.entity_id,
            "source_system": entity.source_system,
            "source_table": entity.source_table,
            "file_container": container,
            "file_path": file_path,
            "file_name": file_name,
            "file_size_bytes": file_size_bytes,
            "row_count": row_count,
            "status": status,
            "processed_run_id": self.context.run_id if status in ("PROCESSED", "REPLAYED") else None,
        })
