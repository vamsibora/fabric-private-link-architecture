"""Orchestrator: runs the Bronze framework for a set of entities with
controlled parallelism (spec sections 13, 39, 56).

Per entity (process_entity), in this order:

    stage         landing JSON -> staging (landing on)  | verify copied staging (landing off)
    schema        ensure the Bronze table + technical columns exist
    read          this run's staged rows, projected/cast to target columns
    validate PRE  FAIL-action failures stop the entity here
    watermark     capture the batch max BEFORE anonymisation
    deduplicate
    anonymise     only where the environment + entity require it
    hash          bronze_record_hash
    write         MERGE | HISTORY | APPEND | REPLACE
    validate POST
    commit        watermark -- only now, only on success
    audit         entity_run SUCCEEDED with counts

Any failure: the error is classified and written to audit.error, the entity
is marked FAILED with watermark_after = the UNCHANGED previous watermark,
and -- because the watermark was never committed -- the entity is safe to
retry (every write strategy is idempotent). Retryable errors are retried in
place per control.load_configuration; others fail immediately.

Entities run in a bounded ThreadPoolExecutor (max_parallel_entities, never
uncontrolled fan-out). With continue_on_entity_failure off, the first
failure cancels entities that have not started yet.

Pipelines orchestrate extraction; this module processes. It never
extracts from a source itself.
"""

import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Callable, Dict, Iterable, List, Mapping, Optional, Sequence

from notebooks.bronze import error_manager as em
from notebooks.bronze.models import STAGE_POST, STAGE_PRE, STRATEGY_HISTORY, EntityConfig, FrameworkConfig
from notebooks.bronze.run_manager import RunContext

logger = logging.getLogger("fabric_medallion.bronze")

STATUS_SUCCEEDED = "SUCCEEDED"
STATUS_FAILED = "FAILED"
STATUS_PARTIAL = "PARTIAL_SUCCESS"
STATUS_CANCELLED = "CANCELLED"


@dataclass(frozen=True)
class WorkItem:
    entity: EntityConfig
    entity_run_id: str
    landing_path: Optional[str] = None       # relative landing path recorded by the extract pipeline
    source_row_count: Optional[int] = None   # rowsCopied reported by the extract pipeline


@dataclass
class EntityResult:
    entity_id: int
    entity_run_id: str
    status: str
    write_strategy: Optional[str] = None
    staging_rows: Optional[int] = None
    inserted: Optional[int] = None
    updated: Optional[int] = None
    deleted: Optional[int] = None
    rejected: Optional[int] = None
    bronze_rows: Optional[int] = None
    watermark_before: Optional[str] = None
    watermark_after: Optional[str] = None
    attempts: int = 0
    error_code: Optional[str] = None
    error_message: Optional[str] = None


@dataclass
class RunSummary:
    run_id: str
    status: str
    entities: List[EntityResult] = field(default_factory=list)

    @property
    def succeeded(self) -> int:
        return sum(1 for e in self.entities if e.status == STATUS_SUCCEEDED)

    @property
    def failed(self) -> int:
        return sum(1 for e in self.entities if e.status == STATUS_FAILED)

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "status": self.status,
            "succeeded": self.succeeded,
            "failed": self.failed,
            "cancelled": sum(1 for e in self.entities if e.status == STATUS_CANCELLED),
            "entities": [asdict(e) for e in self.entities],
        }


def rollup_status(statuses: Sequence[str]) -> str:
    """Run status from entity statuses (mirrors audit.usp_complete_run):
    nothing failed -> SUCCEEDED; nothing succeeded but something failed ->
    FAILED; both -> PARTIAL_SUCCESS. Cancelled entities make an otherwise
    clean run CANCELLED. An empty run SUCCEEDS (nothing to do)."""
    succeeded = sum(1 for s in statuses if s == STATUS_SUCCEEDED)
    failed = sum(1 for s in statuses if s == STATUS_FAILED)
    cancelled = sum(1 for s in statuses if s == STATUS_CANCELLED)
    if failed and succeeded:
        return STATUS_PARTIAL
    if failed:
        return STATUS_FAILED
    if cancelled:
        return STATUS_CANCELLED
    return STATUS_SUCCEEDED


def work_items_from_audit(entities: Iterable[EntityConfig], extracted_rows: Iterable[Mapping]) -> List[WorkItem]:
    """PIPELINE mode: process exactly the entities the extract pipelines
    reported EXTRACTED for this run (audit.usp_get_run_entities)."""
    by_id = {e.entity_id: e for e in entities}
    items = []
    for row in extracted_rows:
        entity = by_id.get(int(row["entity_id"]))
        if entity is None:
            logger.warning("extracted entity %s is not active in control.entity; skipped", row["entity_id"])
            continue
        count = row.get("source_row_count")
        items.append(WorkItem(entity, str(row["entity_run_id"]), row.get("landing_path"),
                              None if count is None else int(count)))
    return sorted(items, key=lambda i: (i.entity.processing_priority, i.entity.entity_id))


@dataclass
class FrameworkServices:
    """Everything process_entity needs, injected (so tests use fakes)."""

    spark: object
    config: FrameworkConfig
    audit: object
    landing: object
    staging: object
    schema: object
    validation: object
    dedup: object
    anonymisation: object
    hashing: object
    merge: object
    history: object
    watermarks: object
    batch_max_watermark: Callable = None
    sleep: Callable[[float], None] = time.sleep
    now: Callable[[], datetime] = lambda: datetime.now(timezone.utc).replace(tzinfo=None)


class _Stage:
    """Tags any exception escaping the block with the stage it came from."""

    def __init__(self, holder: dict, stage: str):
        self.holder, self.stage = holder, stage

    def __enter__(self):
        self.holder["stage"] = self.stage

    def __exit__(self, exc_type, exc, tb):
        if exc is not None and getattr(exc, "stage", None) is None:
            try:
                exc.stage = self.stage
            except Exception:
                pass
        return False


def _log_validations(services: FrameworkServices, entity_run_id: str, results) -> None:
    for result in results:
        services.audit.log_validation(entity_run_id, result)


def _process_once(item: WorkItem, ctx: RunContext, services: FrameworkServices,
                  watermark_before: Optional[str], attempt: int) -> EntityResult:
    from notebooks.bronze.merge_engine import technical_column_values
    from notebooks.bronze.validation_engine import blocking_failures

    entity, erid, audit = item.entity, item.entity_run_id, services.audit
    stage: dict = {}
    result = EntityResult(entity.entity_id, erid, STATUS_FAILED, entity.write_strategy,
                          watermark_before=watermark_before, attempts=attempt)

    with _Stage(stage, em.STAGE_STAGING):
        started = services.now()
        if entity.landing_enabled:
            path = services.landing.resolve(entity, ctx.run_timestamp, item.landing_path)
            result.staging_rows = services.staging.load_from_landing(entity, path, ctx.run_id)
            audit.log_activity(erid, "STAGING_LOADED_FROM_LANDING", "SUCCEEDED", activity_name=path,
                               rows_affected=result.staging_rows, start_datetime=started)
        else:
            result.staging_rows = services.staging.verify(entity, ctx.run_id, item.source_row_count)
            audit.log_activity(erid, "STAGING_VERIFIED", "SUCCEEDED", activity_name=entity.staging_fqn,
                               rows_affected=result.staging_rows, start_datetime=started)

    with _Stage(stage, em.STAGE_WRITE):
        services.schema.ensure_bronze_table(entity)

    previous_count = audit.previous_row_count(entity)
    raw = services.staging.read_raw(entity, ctx.run_id)
    df = services.staging.read(entity, ctx.run_id)

    with _Stage(stage, em.STAGE_VALIDATION):
        started = services.now()
        pre = services.validation.run(df, entity, STAGE_PRE, f"a{attempt}", previous_watermark=watermark_before,
                                      previous_row_count=previous_count, current_row_count=result.staging_rows,
                                      raw_df=raw)
        _log_validations(services, erid, pre)
        blocking = blocking_failures(pre, services.config.fail_on_validation_error)
        audit.log_activity(erid, "VALIDATION_COMPLETED", "FAILED" if blocking else "SUCCEEDED",
                           message=f"{len(pre)} rule(s), {len(blocking)} blocking", start_datetime=started)
        if blocking:
            raise em.ValidationFailedError(
                f"{len(blocking)} FAIL validation rule(s) failed: " + ", ".join(r.rule_name for r in blocking),
                stage=em.STAGE_VALIDATION)

    with _Stage(stage, em.STAGE_WATERMARK):
        batch_max = services.batch_max_watermark(df, entity) if entity.is_incremental else None

    with _Stage(stage, em.STAGE_VALIDATION):
        df, removed = services.dedup.deduplicate(df, entity)
        result.rejected = removed
        audit.log_activity(erid, "DEDUPLICATION_COMPLETED", "SUCCEEDED", rows_affected=removed)

    with _Stage(stage, em.STAGE_ANONYMISATION):
        df, anonymised = services.anonymisation.apply(df, entity, services.config.anonymisation_enabled)
        audit.log_activity(erid, "ANONYMISATION_COMPLETED", "SUCCEEDED" if anonymised else "SKIPPED",
                           message=("columns: " + ", ".join(anonymised)) if anonymised else "not required")

    with _Stage(stage, em.STAGE_HASH):
        df = services.hashing.add_hash(df, entity)
        ingestion = services.now()
        df = services.hashing.add_technical_columns(
            df, technical_column_values(entity, ctx.run_id, erid, ingestion))
        audit.log_activity(erid, "HASH_COMPLETED", "SUCCEEDED")

    with _Stage(stage, em.STAGE_WRITE):
        started = services.now()
        if entity.write_strategy == STRATEGY_HISTORY:
            metrics = services.history.write(df, entity, ingestion)
        else:
            metrics = services.merge.write(df, entity, ctx.run_id, erid)
        result.inserted, result.updated, result.deleted = metrics.inserted, metrics.updated, metrics.deleted
        audit.log_activity(erid, f"{entity.write_strategy}_COMPLETED", "SUCCEEDED",
                           activity_name=entity.target_name, rows_affected=metrics.inserted + metrics.updated,
                           message=f"inserted={metrics.inserted} updated={metrics.updated} deleted={metrics.deleted}",
                           start_datetime=started)

    with _Stage(stage, em.STAGE_VALIDATION):
        bronze = services.spark.table(entity.target_fqn)
        result.bronze_rows = bronze.count()
        post = services.validation.run(bronze, entity, STAGE_POST, f"a{attempt}", previous_watermark=watermark_before,
                                       previous_row_count=previous_count, current_row_count=result.staging_rows)
        _log_validations(services, erid, post)
        blocking = blocking_failures(post, services.config.fail_on_validation_error)
        if blocking:
            raise em.ValidationFailedError(
                f"{len(blocking)} POST validation rule(s) failed: " + ", ".join(r.rule_name for r in blocking),
                stage=em.STAGE_VALIDATION)

    with _Stage(stage, em.STAGE_WATERMARK):
        from notebooks.bronze.watermark_manager import resolve_watermark_after

        after = watermark_before
        if entity.is_incremental:
            after = resolve_watermark_after(watermark_before, batch_max, entity.watermark_type)
            if services.watermarks.commit(entity, watermark_before, after, ctx.run_id, erid):
                audit.log_activity(erid, "WATERMARK_UPDATED", "SUCCEEDED",
                                   message=f"{watermark_before} -> {after}")
        result.watermark_after = after

    result.status = STATUS_SUCCEEDED
    return result


def process_entity(item: WorkItem, ctx: RunContext, services: FrameworkServices) -> EntityResult:
    entity, erid, audit = item.entity, item.entity_run_id, services.audit
    audit.update_entity_run(erid, "PROCESSING", write_strategy=entity.write_strategy)
    watermark_before = services.watermarks.get(entity.entity_id) if entity.is_incremental else None
    attempts = {"n": 0}

    def attempt(n: int) -> EntityResult:
        attempts["n"] = n
        return _process_once(item, ctx, services, watermark_before, n)

    def on_retry(n: int, exc: BaseException) -> None:
        info = em.classify(exc)
        audit.log_error(info, entity, erid, attempt_number=n)
        audit.log_activity(erid, "RETRY_SCHEDULED", "WARNING", message=f"attempt {n} failed ({info.error_code})")

    lc = entity.load_config
    try:
        result = em.with_retry(attempt, lc.retry_enabled, lc.max_retry_count, lc.retry_delay_seconds,
                               on_retry=on_retry, sleep=services.sleep)
    except Exception as exc:
        info = em.classify(exc)
        audit.log_error(info, entity, erid, attempt_number=attempts["n"])
        audit.complete_entity_run(erid, STATUS_FAILED, watermark_after=watermark_before,
                                  write_strategy=entity.write_strategy, error_message=info.message)
        if entity.landing_enabled and item.landing_path:
            audit.log_file(entity, erid, item.landing_path, item.landing_path.rsplit("/", 1)[-1],
                           services.config.landing_container, "FAILED")
        return EntityResult(entity.entity_id, erid, STATUS_FAILED, entity.write_strategy,
                            watermark_before=watermark_before, watermark_after=watermark_before,
                            attempts=attempts["n"], error_code=info.error_code, error_message=info.message)

    audit.complete_entity_run(erid, STATUS_SUCCEEDED, staging_row_count=result.staging_rows,
                              inserted_row_count=result.inserted, updated_row_count=result.updated,
                              deleted_row_count=result.deleted, rejected_row_count=result.rejected,
                              bronze_row_count=result.bronze_rows, watermark_after=result.watermark_after,
                              write_strategy=entity.write_strategy)
    if entity.landing_enabled and item.landing_path:
        audit.log_file(entity, erid, item.landing_path, item.landing_path.rsplit("/", 1)[-1],
                       services.config.landing_container, "PROCESSED")
    return result


def run(ctx: RunContext, items: Sequence[WorkItem], services: FrameworkServices,
        complete_run: bool = True) -> RunSummary:
    """Process work items with bounded parallelism and close the audit run."""
    cancel = threading.Event()
    continue_on_failure = services.config.continue_on_entity_failure

    def guarded(item: WorkItem) -> EntityResult:
        if cancel.is_set():
            services.audit.complete_entity_run(item.entity_run_id, STATUS_CANCELLED,
                                               error_message="cancelled after an earlier entity failure")
            return EntityResult(item.entity.entity_id, item.entity_run_id, STATUS_CANCELLED,
                                item.entity.write_strategy)
        try:
            result = process_entity(item, ctx, services)
        except Exception as exc:  # audit fail-fast / critical errors escaping process_entity
            info = em.classify(exc, em.STAGE_ORCHESTRATION)
            logger.exception("entity %s aborted", item.entity.entity_id)
            result = EntityResult(item.entity.entity_id, item.entity_run_id, STATUS_FAILED,
                                  item.entity.write_strategy, error_code=info.error_code,
                                  error_message=info.message)
        if result.status == STATUS_FAILED and not continue_on_failure:
            cancel.set()
        return result

    workers = min(services.config.max_parallel_entities, max(1, len(items)))
    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="bronze-entity") as pool:
        results = list(pool.map(guarded, items))

    summary = RunSummary(ctx.run_id, rollup_status([r.status for r in results]), results)
    if complete_run:
        services.audit.complete_run(summary.status,
                                    message=f"{summary.succeeded} succeeded, {summary.failed} failed")
    return summary
