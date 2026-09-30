"""Ledger-driven schema/RLS migration runner for the Fabric Warehouse.

Applies every `warehouse/ddl/**/*.sql` script (in path order), then every
`security/rls/*.sql` script (in filename order), skipping anything already
recorded as SUCCEEDED in CONTROL.SchemaMigrationHistory. Designed to be
invoked from inside a Fabric notebook (see fabric_items/notebooks/
SchemaMigrationRunner.Notebook), which wraps a single run_migrations() call
with utils_logging.start_pipeline_run/end_pipeline_run for the batch.

Bootstrap: CONTROL.SchemaMigrationHistory does not exist until its own DDL
script (warehouse/ddl/05_meta/050_...) runs. Until then, every ledger row is
buffered in memory and flushed immediately after that CREATE TABLE succeeds
-- see run_migrations(). A failure before the ledger exists can't be logged
to it, so it falls back to the same notebookutils.fs.put() JSON +
logger.critical pattern utils_logging._fallback_log() uses.

Fabric DW DDL is CREATE-only and non-idempotent -- a SUCCEEDED script is
NEVER re-executed, even if its on-disk content has changed (that's flagged
as checksum drift, not silently re-run). Add a new numbered file for any new
schema change instead of editing an already-applied one.
"""

import hashlib
import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from notebooks.framework.fabric_connection import (
    get_connection_notebookutils as _get_connection,
)

logger = logging.getLogger("fabric_medallion.migration")

_LEDGER_SCHEMA = "CONTROL"
_LEDGER_TABLE = "SchemaMigrationHistory"
_TEMPLATE_MARKER = "MIGRATION_RUNNER: SKIP"


class MigrationRunError(Exception):
    """Raised when a migration script fails. Halts the run -- later scripts
    may assume earlier ones already succeeded."""


@dataclass(frozen=True)
class MigrationScript:
    path: Path
    repo_relative: str  # POSIX path, used as the ledger's ScriptPath key
    category: str  # 'SCHEMA' | 'RLS'


@dataclass(frozen=True)
class LedgerEntry:
    status: str
    checksum: str


@dataclass
class MigrationRunResult:
    applied: List[str] = field(default_factory=list)
    already_applied: List[str] = field(default_factory=list)
    skipped_templates: List[str] = field(default_factory=list)
    checksum_drift: List[str] = field(default_factory=list)


def discover_scripts(repo_root: Path) -> List[MigrationScript]:
    """warehouse/ddl/**/*.sql in path order, THEN security/rls/*.sql in
    filename order -- an explicit two-list concatenation, not a single sort
    (a naive sort would run 'security/' before 'warehouse/' alphabetically,
    which is wrong: RLS must always run after schema DDL)."""

    def _sorted(root: Path) -> List[Path]:
        if not root.is_dir():
            return []
        return sorted(root.rglob("*.sql"), key=lambda p: p.relative_to(repo_root).as_posix())

    scripts: List[MigrationScript] = []
    for path in _sorted(repo_root / "warehouse" / "ddl"):
        scripts.append(
            MigrationScript(path=path, repo_relative=path.relative_to(repo_root).as_posix(), category="SCHEMA")
        )
    for path in _sorted(repo_root / "security" / "rls"):
        scripts.append(
            MigrationScript(path=path, repo_relative=path.relative_to(repo_root).as_posix(), category="RLS")
        )
    return scripts


def compute_checksum(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def is_template(path: Path) -> bool:
    """A script marked with a leading '-- MIGRATION_RUNNER: SKIP' comment is
    a template with nothing real to apply yet. Re-checked on every run --
    once the marker is removed (the file is bound to a real table), it's
    picked up as a normal pending script on the next run."""
    return _TEMPLATE_MARKER in path.read_text(encoding="utf-8")


def ledger_table_exists(cursor) -> bool:
    cursor.execute(
        "SELECT 1 FROM sys.tables t JOIN sys.schemas s ON t.schema_id = s.schema_id "
        "WHERE s.name = ? AND t.name = ?",
        _LEDGER_SCHEMA,
        _LEDGER_TABLE,
    )
    return cursor.fetchone() is not None


def fetch_ledger_entries(cursor) -> Dict[str, LedgerEntry]:
    cursor.execute(f"SELECT ScriptPath, Status, Checksum FROM [{_LEDGER_SCHEMA}].[{_LEDGER_TABLE}]")
    return {row[0]: LedgerEntry(status=row[1], checksum=row[2]) for row in cursor.fetchall()}


def fetch_succeeded_paths(cursor) -> Set[str]:
    return {path for path, entry in fetch_ledger_entries(cursor).items() if entry.status == "SUCCEEDED"}


def fetch_template_paths(cursor) -> Set[str]:
    return {path for path, entry in fetch_ledger_entries(cursor).items() if entry.status == "SKIPPED_TEMPLATE"}


def _insert_ledger_row(cursor, row: Tuple) -> None:
    cursor.execute(
        f"INSERT INTO [{_LEDGER_SCHEMA}].[{_LEDGER_TABLE}] "
        "(MigrationID, ScriptPath, ScriptCategory, Checksum, Status, PipelineRunID, "
        " DurationMs, ErrorMessage, AppliedBy, CreatedDate) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        *row,
    )


def _build_row(
    script: MigrationScript,
    checksum: str,
    status: str,
    pipeline_run_id: Optional[str],
    duration_ms: Optional[int],
    error_message: Optional[str],
    applied_by: str,
) -> Tuple:
    return (
        str(uuid.uuid4()),
        script.repo_relative,
        script.category,
        checksum,
        status,
        pipeline_run_id,
        duration_ms,
        error_message,
        applied_by,
        datetime.now(timezone.utc),
    )


def _fallback_log(payload: dict) -> None:
    """Last-resort sink for a ledger write that can't happen yet (the ledger
    table itself doesn't exist and the write is a FAILED row). Mirrors
    utils_logging._fallback_log -- never raises."""
    try:
        import notebookutils  # Fabric-injected runtime module

        path = f"Files/_framework_fallback/schema_migration/{uuid.uuid4()}.json"
        notebookutils.fs.put(path, json.dumps(payload, default=str), overwrite=True)
    except Exception:
        pass
    logger.critical("Schema migration fallback logged: %s", payload)


def run_migrations(
    connection_string: str,
    repo_root: Path,
    applied_by: str,
    pipeline_run_id: Optional[str] = None,
) -> MigrationRunResult:
    """Applies every not-yet-SUCCEEDED script in discover_scripts() order.
    Never re-runs a SUCCEEDED script. Re-checks templates every run. Halts
    on first failure and raises MigrationRunError -- later scripts may
    depend on it.
    """
    scripts = discover_scripts(repo_root)
    result = MigrationRunResult()

    conn = _get_connection(connection_string)
    try:
        cursor = conn.cursor()

        ledger_ready = ledger_table_exists(cursor)
        ledger_entries = fetch_ledger_entries(cursor) if ledger_ready else {}
        pending_buffer: List[Tuple] = []

        def _write_row(row: Tuple) -> None:
            nonlocal ledger_ready
            if not ledger_ready:
                ledger_ready = ledger_table_exists(cursor)
            if ledger_ready:
                for buffered in pending_buffer:
                    _insert_ledger_row(cursor, buffered)
                pending_buffer.clear()
                _insert_ledger_row(cursor, row)
            else:
                pending_buffer.append(row)

        for script in scripts:
            entry = ledger_entries.get(script.repo_relative)
            checksum = compute_checksum(script.path)

            if entry and entry.status == "SUCCEEDED":
                result.already_applied.append(script.repo_relative)
                if entry.checksum != checksum:
                    result.checksum_drift.append(script.repo_relative)
                    _warn_checksum_drift(connection_string, script.repo_relative, pipeline_run_id)
                continue

            if is_template(script.path):
                result.skipped_templates.append(script.repo_relative)
                if not (entry and entry.status == "SKIPPED_TEMPLATE"):
                    _write_row(_build_row(script, checksum, "SKIPPED_TEMPLATE", pipeline_run_id, None, None, applied_by))
                continue

            start = time.monotonic()
            try:
                cursor.execute(script.path.read_text(encoding="utf-8"))
            except Exception as ex:
                duration_ms = int((time.monotonic() - start) * 1000)
                error_message = str(ex)[:4000]
                row = _build_row(script, checksum, "FAILED", pipeline_run_id, duration_ms, error_message, applied_by)
                if ledger_ready or ledger_table_exists(cursor):
                    _write_row(row)
                else:
                    _fallback_log(
                        {
                            "kind": "schema_migration_failed",
                            "script_path": script.repo_relative,
                            "error": error_message,
                        }
                    )
                raise MigrationRunError(f"Migration failed at {script.repo_relative}: {error_message}") from ex

            duration_ms = int((time.monotonic() - start) * 1000)
            _write_row(_build_row(script, checksum, "SUCCEEDED", pipeline_run_id, duration_ms, None, applied_by))
            result.applied.append(script.repo_relative)
    finally:
        conn.close()

    return result


def _warn_checksum_drift(connection_string: str, script_path: str, pipeline_run_id: Optional[str]) -> None:
    """A SUCCEEDED script's on-disk content no longer matches what was
    applied. Never re-executed (CREATE-only DDL) -- just surfaced loudly."""
    try:
        from notebooks.framework import utils_logging as ul

        ul.log_error(
            connection_string,
            f"Checksum drift detected for already-applied migration: {script_path}",
            severity="WARNING",
            pipeline_run_id=pipeline_run_id,
            source_stage="schema_migration",
        )
    except Exception:
        logger.warning("Checksum drift detected for %s (and warning log failed)", script_path)
