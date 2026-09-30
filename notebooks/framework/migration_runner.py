"""Ledger-driven schema migration runner for the Fabric Warehouse AND the
central audit Fabric SQL Database.

A MigrationTarget describes one database: which repo folders it owns, in
what order, and where its ledger table lives.

  WAREHOUSE_TARGET  warehouse/ddl/** -> security/rls/*        CREATE-once
                    warehouse/programmability/** -> warehouse/metadata/**  repeatable
                    ledger: control.schema_migration_history
  AUDIT_DB_TARGET   sql_database/audit/ddl/**                 CREATE-once
                    sql_database/audit/procs/** -> views/**   repeatable
                    ledger: audit.schema_migration_history

CREATE-once scripts (tables, constraints, RLS) are applied exactly once: a
SUCCEEDED script is NEVER re-executed, even if its content changed -- that
is flagged as checksum drift, never silently re-run (Fabric DW DDL is
CREATE-only and non-idempotent). Add a new numbered file instead.

Repeatable scripts (CREATE OR ALTER procs/views/functions, idempotent
metadata upserts) are re-applied whenever their checksum differs from the
latest SUCCEEDED ledger row for that path.

Bootstrap: the ledger table does not exist until its own DDL script runs
(05_meta/050_...). Until then every ledger row is buffered in memory and
flushed immediately after that CREATE TABLE succeeds. A failure before the
ledger exists can't be logged to it, so it falls back to the same
notebookutils.fs.put() JSON + logger.critical pattern as the audit manager.
"""

import hashlib
import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Dict, List, Optional, Set, Tuple

from notebooks.framework.fabric_connection import (
    get_connection_notebookutils as _get_connection,
)

logger = logging.getLogger("fabric_medallion.migration")

_TEMPLATE_MARKER = "MIGRATION_RUNNER: SKIP"


class MigrationRunError(Exception):
    """Raised when a migration script fails. Halts the run -- later scripts
    may assume earlier ones already succeeded."""


@dataclass(frozen=True)
class MigrationTarget:
    name: str
    ledger_schema: str
    ledger_table: str
    once_roots: Tuple[Tuple[str, str], ...]  # (repo-relative folder, category), applied in this order
    repeatable_roots: Tuple[Tuple[str, str], ...] = ()  # applied after every once_root

    @property
    def ledger(self) -> str:
        return f"[{self.ledger_schema}].[{self.ledger_table}]"


WAREHOUSE_TARGET = MigrationTarget(
    name="WAREHOUSE",
    ledger_schema="control",
    ledger_table="schema_migration_history",
    once_roots=(("warehouse/ddl", "SCHEMA"), ("security/rls", "RLS")),
    repeatable_roots=(("warehouse/programmability", "PROGRAMMABILITY"), ("warehouse/metadata", "METADATA")),
)

AUDIT_DB_TARGET = MigrationTarget(
    name="AUDIT_DB",
    ledger_schema="audit",
    ledger_table="schema_migration_history",
    once_roots=(("sql_database/audit/ddl", "SCHEMA"),),
    repeatable_roots=(("sql_database/audit/procs", "PROC"), ("sql_database/audit/views", "VIEW")),
)

TARGETS: Dict[str, MigrationTarget] = {t.name: t for t in (WAREHOUSE_TARGET, AUDIT_DB_TARGET)}


@dataclass(frozen=True)
class MigrationScript:
    path: Path
    repo_relative: str  # POSIX path, used as the ledger's script_path key
    category: str
    repeatable: bool = False


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


def discover_scripts(repo_root: Path, target: MigrationTarget = WAREHOUSE_TARGET) -> List[MigrationScript]:
    """Every once_root in declared order (each sorted by path), then every
    repeatable_root in declared order -- an explicit concatenation, not a
    single sort (a naive sort would run 'security/' before 'warehouse/'
    alphabetically, which is wrong: RLS must always run after schema DDL)."""

    def _sorted(root: Path) -> List[Path]:
        if not root.is_dir():
            return []
        return sorted(root.rglob("*.sql"), key=lambda p: p.relative_to(repo_root).as_posix())

    scripts: List[MigrationScript] = []
    for roots, repeatable in ((target.once_roots, False), (target.repeatable_roots, True)):
        for folder, category in roots:
            for path in _sorted(repo_root / folder):
                scripts.append(
                    MigrationScript(
                        path=path,
                        repo_relative=path.relative_to(repo_root).as_posix(),
                        category=category,
                        repeatable=repeatable,
                    )
                )
    return scripts


def compute_checksum(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def is_template(path: Path) -> bool:
    """A script marked with a '-- MIGRATION_RUNNER: SKIP' comment is a
    template with nothing real to apply yet. Re-checked on every run -- once
    the marker is removed it's picked up as a normal pending script."""
    return _TEMPLATE_MARKER in path.read_text(encoding="utf-8")


def ledger_table_exists(cursor, target: MigrationTarget = WAREHOUSE_TARGET) -> bool:
    cursor.execute(
        "SELECT 1 FROM sys.tables t JOIN sys.schemas s ON t.schema_id = s.schema_id "
        "WHERE s.name = ? AND t.name = ?",
        target.ledger_schema,
        target.ledger_table,
    )
    return cursor.fetchone() is not None


def fetch_ledger_entries(cursor, target: MigrationTarget = WAREHOUSE_TARGET) -> Dict[str, LedgerEntry]:
    """Latest ledger row per script_path (rows are read oldest-first, so the
    last one written for a path wins)."""
    cursor.execute(
        f"SELECT script_path, status, checksum FROM {target.ledger} ORDER BY created_datetime"
    )
    return {row[0]: LedgerEntry(status=row[1], checksum=row[2]) for row in cursor.fetchall()}


def fetch_succeeded_checksums(cursor, target: MigrationTarget = WAREHOUSE_TARGET) -> Dict[str, Set[str]]:
    """Every checksum ever SUCCEEDED per script_path."""
    cursor.execute(
        f"SELECT script_path, checksum FROM {target.ledger} WHERE status = 'SUCCEEDED'"
    )
    result: Dict[str, Set[str]] = {}
    for path, checksum in cursor.fetchall():
        result.setdefault(path, set()).add(checksum)
    return result


def fetch_succeeded_paths(cursor, target: MigrationTarget = WAREHOUSE_TARGET) -> Set[str]:
    return set(fetch_succeeded_checksums(cursor, target))


def fetch_failed_paths(cursor, target: MigrationTarget = WAREHOUSE_TARGET) -> Set[str]:
    """Paths whose LATEST ledger row is FAILED (a later success clears it)."""
    return {path for path, entry in fetch_ledger_entries(cursor, target).items() if entry.status == "FAILED"}


def _insert_ledger_row(cursor, target: MigrationTarget, row: Tuple) -> None:
    cursor.execute(
        f"INSERT INTO {target.ledger} "
        "(migration_id, script_path, script_category, checksum, status, run_id, "
        " duration_ms, error_message, applied_by, created_datetime) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        *row,
    )


def _build_row(
    script: MigrationScript,
    checksum: str,
    status: str,
    run_id: Optional[str],
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
        run_id,
        duration_ms,
        error_message,
        applied_by,
        datetime.now(timezone.utc),
    )


def _fallback_log(payload: dict) -> None:
    """Last-resort sink for a ledger write that can't happen yet (the ledger
    table itself doesn't exist and the write is a FAILED row). Never raises."""
    try:
        import notebookutils  # Fabric-injected runtime module

        path = f"Files/_framework_fallback/schema_migration/{uuid.uuid4()}.json"
        notebookutils.fs.put(path, json.dumps(payload, default=str), overwrite=True)
    except Exception:
        pass
    logger.critical("Schema migration fallback logged: %s", payload)


def _default_warning(message: str) -> None:
    logger.warning(message)


def run_migrations(
    connection_string: str,
    repo_root: Path,
    applied_by: str,
    run_id: Optional[str] = None,
    target: MigrationTarget = WAREHOUSE_TARGET,
    on_warning: Optional[Callable[[str], None]] = None,
    connect: Optional[Callable[[str], object]] = None,
) -> MigrationRunResult:
    """Applies every pending script of `target` in discover_scripts() order.

    Never re-runs a SUCCEEDED CREATE-once script; re-applies a repeatable
    script only when its checksum changed. Re-checks templates every run.
    Halts on first failure and raises MigrationRunError.

    on_warning receives checksum-drift messages (e.g. the audit manager's
    log_error); connect overrides how the connection is opened (e.g. to pass
    a specific token audience).
    """
    warn = on_warning or _default_warning
    scripts = discover_scripts(repo_root, target)
    result = MigrationRunResult()

    conn = (connect or _get_connection)(connection_string)
    try:
        cursor = conn.cursor()

        ledger_ready = ledger_table_exists(cursor, target)
        latest = fetch_ledger_entries(cursor, target) if ledger_ready else {}
        succeeded = fetch_succeeded_checksums(cursor, target) if ledger_ready else {}
        pending_buffer: List[Tuple] = []

        def _write_row(row: Tuple) -> None:
            nonlocal ledger_ready
            if not ledger_ready:
                ledger_ready = ledger_table_exists(cursor, target)
            if ledger_ready:
                for buffered in pending_buffer:
                    _insert_ledger_row(cursor, target, buffered)
                pending_buffer.clear()
                _insert_ledger_row(cursor, target, row)
            else:
                pending_buffer.append(row)

        for script in scripts:
            entry = latest.get(script.repo_relative)
            checksum = compute_checksum(script.path)
            done_checksums = succeeded.get(script.repo_relative, set())

            if script.repeatable:
                if entry and entry.status == "SUCCEEDED" and entry.checksum == checksum:
                    result.already_applied.append(script.repo_relative)
                    continue
            elif done_checksums:
                result.already_applied.append(script.repo_relative)
                if checksum not in done_checksums:
                    result.checksum_drift.append(script.repo_relative)
                    warn(f"Checksum drift detected for already-applied migration: {script.repo_relative}")
                continue

            if is_template(script.path):
                result.skipped_templates.append(script.repo_relative)
                if not (entry and entry.status == "SKIPPED_TEMPLATE"):
                    _write_row(_build_row(script, checksum, "SKIPPED_TEMPLATE", run_id, None, None, applied_by))
                continue

            start = time.monotonic()
            try:
                cursor.execute(script.path.read_text(encoding="utf-8"))
            except Exception as ex:
                duration_ms = int((time.monotonic() - start) * 1000)
                error_message = str(ex)[:4000]
                row = _build_row(script, checksum, "FAILED", run_id, duration_ms, error_message, applied_by)
                if ledger_ready or ledger_table_exists(cursor, target):
                    _write_row(row)
                else:
                    _fallback_log(
                        {
                            "kind": "schema_migration_failed",
                            "target": target.name,
                            "script_path": script.repo_relative,
                            "error": error_message,
                        }
                    )
                raise MigrationRunError(
                    f"[{target.name}] Migration failed at {script.repo_relative}: {error_message}"
                ) from ex

            duration_ms = int((time.monotonic() - start) * 1000)
            _write_row(_build_row(script, checksum, "SUCCEEDED", run_id, duration_ms, None, applied_by))
            result.applied.append(script.repo_relative)
    finally:
        conn.close()

    return result


def expected_state(repo_root: Path, target: MigrationTarget = WAREHOUSE_TARGET) -> Dict[str, Optional[str]]:
    """What a fully migrated database must contain: script_path -> required
    checksum (None = any SUCCEEDED row is enough, i.e. CREATE-once).
    Templates are excluded. Used by scripts/ci/verify_migration_state.py."""
    expected: Dict[str, Optional[str]] = {}
    for script in discover_scripts(repo_root, target):
        if is_template(script.path):
            continue
        expected[script.repo_relative] = compute_checksum(script.path) if script.repeatable else None
    return expected
