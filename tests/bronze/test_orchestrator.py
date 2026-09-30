"""orchestrator.py with fake services: processing order, failure handling,
retry, watermark preservation, landing on/off, controlled parallelism and
run status roll-up (spec sections 13, 37-39, 56-59).

These are the Fabric-independent halves of the spec section 59 scenarios;
the Spark-backed halves live in test_spark_end_to_end.py."""

import threading
import time
from datetime import datetime

import pytest

from notebooks.bronze import orchestrator as orc
from notebooks.bronze.error_manager import TransientError
from notebooks.bronze.merge_engine import WriteMetrics
from notebooks.bronze.models import FrameworkConfig, LoadConfig
from notebooks.bronze.run_manager import RunContext
from notebooks.bronze.validation_engine import ValidationResult
from tests.bronze.factories import make_entity

CTX = RunContext.create(environment="DEV", run_id="20260930-081205-ABC123")


class FakeDF:
    columns = ["CustomerId"]

    def count(self):
        return 3


class RecordingAudit:
    def __init__(self):
        self.calls, self.lock = [], threading.Lock()

    def __getattr__(self, name):
        def record(*args, **kwargs):
            with self.lock:
                self.calls.append((name, args, kwargs))
            return None if name == "previous_row_count" else True
        return record

    def named(self, name):
        return [c for c in self.calls if c[0] == name]


class FakeWatermarks:
    def __init__(self, value="2026-09-01 00:00:00.000000"):
        self.value, self.commits = value, []

    def get(self, entity_id):
        return self.value

    def commit(self, entity, before, after, run_id, erid):
        self.commits.append((entity.entity_id, before, after))
        return after != before


class Stub:
    def __init__(self, **methods):
        for name, fn in methods.items():
            setattr(self, name, fn)


def _services(audit=None, watermarks=None, write=None, validate=None, config=None, staging=None, sleep=None):
    events = []
    passed = [ValidationResult(None, "builtin_primary_key_null", "PRIMARY_KEY_NULL", "PRE", "PASSED", "FAIL", "HIGH", 0)]
    return orc.FrameworkServices(
        spark=Stub(table=lambda name: FakeDF()),
        config=config or FrameworkConfig("DEV", {"max_parallel_entities": "2", "anonymisation_enabled": "true"}),
        audit=audit or RecordingAudit(),
        landing=Stub(resolve=lambda e, ts, recorded: f"Files/landing/{recorded}"),
        staging=staging or Stub(
            load_from_landing=lambda e, path, run_id: events.append(("landing", path)) or 3,
            verify=lambda e, run_id, expected: events.append(("verify", expected)) or 3,
            read_raw=lambda e, run_id: FakeDF(),
            read=lambda e, run_id: FakeDF(),
        ),
        schema=Stub(ensure_bronze_table=lambda e: []),
        validation=Stub(run=validate or (lambda *a, **k: passed)),
        dedup=Stub(deduplicate=lambda df, e: (df, 1)),
        anonymisation=Stub(apply=lambda df, e, enabled: (df, ["Email"] if enabled and e.anonymisation_required else [])),
        hashing=Stub(add_hash=lambda df, e: df, add_technical_columns=lambda df, values: df),
        merge=Stub(write=write or (lambda df, e, run_id, erid: WriteMetrics(inserted=2, updated=1))),
        history=Stub(write=lambda df, e, ingestion: (write or (lambda *a: WriteMetrics(inserted=3)))(df, e, None, None)),
        watermarks=watermarks or FakeWatermarks(),
        batch_max_watermark=lambda df, e: datetime(2026, 9, 30, 8, 5, 13),
        sleep=sleep or (lambda s: None),
    ), events


def _item(entity, landing_path=None, rows=3):
    return orc.WorkItem(entity, CTX.entity_run_id(entity.entity_id), landing_path, rows)


def test_successful_entity_commits_watermark_after_write_and_audits(customer):
    services, events = _services()
    result = orc.process_entity(_item(customer, "SQLServer/Customer/Customer_20260930081205.json"), CTX, services)

    assert result.status == "SUCCEEDED"
    assert events == [("landing", "Files/landing/SQLServer/Customer/Customer_20260930081205.json")]
    assert services.watermarks.commits == [(101, "2026-09-01 00:00:00.000000", "2026-09-30 08:05:13.000000")]
    assert result.watermark_after == "2026-09-30 08:05:13.000000"
    assert (result.inserted, result.rejected, result.bronze_rows) == (3, 1, 3)

    audit = services.audit
    activities = [c[1][1] for c in audit.named("log_activity")]
    assert activities == ["STAGING_LOADED_FROM_LANDING", "VALIDATION_COMPLETED", "DEDUPLICATION_COMPLETED",
                          "ANONYMISATION_COMPLETED", "HASH_COMPLETED", "HISTORY_COMPLETED", "WATERMARK_UPDATED"]
    [complete] = audit.named("complete_entity_run")
    assert complete[1][1] == "SUCCEEDED" and complete[2]["watermark_after"] == "2026-09-30 08:05:13.000000"
    [landing_file] = audit.named("log_file")
    assert landing_file[1][5] == "PROCESSED"


def test_landing_disabled_verifies_staging_instead_of_reading_files(product):
    services, events = _services()
    result = orc.process_entity(_item(product, rows=3), CTX, services)
    assert result.status == "SUCCEEDED"
    assert events == [("verify", 3)]      # copy's rowsCopied checked against staging
    assert services.audit.named("log_file") == []
    assert [c[1][1] for c in services.audit.named("log_activity")][0] == "STAGING_VERIFIED"


def test_validation_failure_fails_entity_without_touching_watermark_or_bronze(product):
    failed = [ValidationResult(1021, "product_listprice_non_negative", "CUSTOM", "PRE", "FAILED", "FAIL", "HIGH", 3)]
    writes = []
    services, _ = _services(validate=lambda *a, **k: failed,
                            write=lambda *a: writes.append(a) or WriteMetrics())
    result = orc.process_entity(_item(product), CTX, services)

    assert result.status == "FAILED" and result.error_code == "VALIDATION_FAILED"
    assert writes == [] and services.watermarks.commits == []
    assert result.watermark_after == result.watermark_before       # watermark preserved
    [error] = services.audit.named("log_error")
    assert error[1][0].stage == "VALIDATION" and error[1][0].is_retryable is False
    assert len(services.audit.named("log_validation")) == 1


def test_warn_validation_does_not_block(product):
    warned = [ValidationResult(None, "builtin_duplicate_primary_key", "DUPLICATE_PRIMARY_KEY", "PRE", "WARNING",
                               "WARN", "MEDIUM", 2)]
    services, _ = _services(validate=lambda *a, **k: warned)
    assert orc.process_entity(_item(product), CTX, services).status == "SUCCEEDED"


def test_processing_failure_preserves_watermark_and_marks_landing_file_failed(customer):
    def broken_write(*args):
        raise RuntimeError("[DELTA_MERGE_UNRESOLVED_EXPRESSION] cannot resolve s.Emial")

    services, _ = _services(write=broken_write)
    result = orc.process_entity(_item(customer, "SQLServer/Customer/Customer_20260930081205.json"), CTX, services)

    assert result.status == "FAILED" and result.attempts == 1        # schema error: not retried
    assert services.watermarks.commits == []
    [complete] = services.audit.named("complete_entity_run")
    assert complete[1][1] == "FAILED"
    assert complete[2]["watermark_after"] == "2026-09-01 00:00:00.000000"
    assert services.audit.named("log_file")[0][1][5] == "FAILED"      # landing file stays replayable


def test_transient_failure_is_retried_then_succeeds(product):
    attempts, sleeps = [], []

    def flaky(*args):
        attempts.append(1)
        if len(attempts) < 3:
            raise TransientError("capacity throttled")
        return WriteMetrics(inserted=1)

    services, _ = _services(write=flaky, sleep=sleeps.append)
    product = make_entity(**{**product.__dict__, "load_config": LoadConfig(True, 3, 30)})
    result = orc.process_entity(_item(product), CTX, services)

    assert result.status == "SUCCEEDED" and result.attempts == 3 and sleeps == [30, 60]
    assert len(services.audit.named("log_error")) == 2                # each failed attempt audited
    assert [c for c in services.audit.named("log_activity") if c[1][1] == "RETRY_SCHEDULED"]


def test_empty_incremental_batch_keeps_watermark(product):
    services, _ = _services()
    services.batch_max_watermark = lambda df, e: None
    result = orc.process_entity(_item(product), CTX, services)
    assert result.status == "SUCCEEDED" and result.watermark_after == "2026-09-01 00:00:00.000000"
    assert services.watermarks.commits == [(102, "2026-09-01 00:00:00.000000", "2026-09-01 00:00:00.000000")]


def test_full_load_never_uses_watermark():
    territory = make_entity(entity_id=104, load_type="FULL", history_required=False, merge_required=True,
                            watermark_column=None, watermark_type=None, landing_enabled=False,
                            anonymisation_required=False)
    services, _ = _services()
    result = orc.process_entity(_item(territory), CTX, services)
    assert result.status == "SUCCEEDED" and services.watermarks.commits == []


@pytest.mark.parametrize(
    "statuses,expected",
    [([], "SUCCEEDED"), (["SUCCEEDED", "SUCCEEDED"], "SUCCEEDED"), (["FAILED"], "FAILED"),
     (["SUCCEEDED", "FAILED"], "PARTIAL_SUCCESS"), (["FAILED", "CANCELLED"], "FAILED"),
     (["SUCCEEDED", "CANCELLED"], "CANCELLED")],
)
def test_rollup_status(statuses, expected):
    assert orc.rollup_status(statuses) == expected


def test_partial_run_continues_after_entity_failure_and_completes_run(customer, product):
    def write(df, entity, run_id, erid):
        if entity.entity_id == 102:
            raise ValueError("bad data")
        return WriteMetrics(inserted=1)

    services, _ = _services(write=write)
    summary = orc.run(CTX, [_item(customer, "SQLServer/Customer/Customer_20260930081205.json"), _item(product)],
                      services)
    assert summary.status == "PARTIAL_SUCCESS" and summary.succeeded == 1 and summary.failed == 1
    [complete] = services.audit.named("complete_run")
    assert complete[1][0] == "PARTIAL_SUCCESS"
    assert summary.to_dict()["entities"][1]["error_code"] == "ValueError"


def test_stop_on_first_failure_cancels_remaining_entities(product):
    config = FrameworkConfig("DEV", {"max_parallel_entities": "1", "continue_on_entity_failure": "false"})
    services, _ = _services(config=config, write=lambda *a: (_ for _ in ()).throw(ValueError("boom")))
    items = [_item(make_entity(**{**product.__dict__, "entity_id": i})) for i in (201, 202, 203)]
    summary = orc.run(CTX, items, services)
    assert [e.status for e in summary.entities] == ["FAILED", "CANCELLED", "CANCELLED"]
    assert summary.status == "FAILED"


def test_complete_framework_failure(product):
    services, _ = _services(write=lambda *a: (_ for _ in ()).throw(ValueError("boom")))
    summary = orc.run(CTX, [_item(product)], services)
    assert summary.status == "FAILED"


def test_parallelism_is_bounded_by_max_parallel_entities(product):
    active, peak, lock = [0], [0], threading.Lock()

    def slow_write(*args):
        with lock:
            active[0] += 1
            peak[0] = max(peak[0], active[0])
        time.sleep(0.02)
        with lock:
            active[0] -= 1
        return WriteMetrics(inserted=1)

    config = FrameworkConfig("DEV", {"max_parallel_entities": "3"})
    services, _ = _services(config=config, write=slow_write)
    items = [_item(make_entity(**{**product.__dict__, "entity_id": 300 + i})) for i in range(10)]
    summary = orc.run(CTX, items, services)
    assert summary.succeeded == 10 and 1 < peak[0] <= 3


def test_audit_failure_to_start_is_contained_per_entity(product):
    class ExplodingAudit(RecordingAudit):
        def update_entity_run(self, *args, **kwargs):
            raise RuntimeError("audit db unreachable")

    services, _ = _services(audit=ExplodingAudit())
    summary = orc.run(CTX, [_item(product)], services)
    assert summary.status == "FAILED" and summary.entities[0].error_code == "RuntimeError"


def test_work_items_from_audit_keeps_only_extracted_active_entities(customer, product):
    rows = [{"entity_id": 102, "entity_run_id": "r-E102", "landing_path": None, "source_row_count": 17},
            {"entity_id": 101, "entity_run_id": "r-E101", "landing_path": "SQLServer/Customer/Customer_1.json",
             "source_row_count": None},
            {"entity_id": 999, "entity_run_id": "r-E999", "landing_path": None, "source_row_count": 1}]
    items = orc.work_items_from_audit([customer, product], rows)
    assert [(i.entity.entity_id, i.source_row_count) for i in items] == [(101, None), (102, 17)]
