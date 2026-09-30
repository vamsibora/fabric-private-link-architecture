"""Spark + Delta end-to-end scenarios (spec sections 58-59), run against a
local SparkSession with Delta Lake -- the real engines, staging, landing
reads and writes; only the audit database and the Warehouse watermark
table are faked.

    pytest -m spark tests/bronze/test_spark_end_to_end.py

Requires Java 11/17 and network access the first time
(configure_spark_with_delta_pip fetches the Delta jars). Skipped
automatically when pyspark, delta-spark or Java is unavailable -- these
tests were NOT executed in the session that wrote them.
"""

import json
import os
import shutil
from datetime import datetime
from decimal import Decimal

import pytest

pyspark = pytest.importorskip("pyspark")
pytest.importorskip("delta")
if not (shutil.which("java") or os.environ.get("JAVA_HOME")):
    pytest.skip("Java is required for Spark tests", allow_module_level=True)

pytestmark = pytest.mark.spark

from notebooks.bronze import hash_engine as he  # noqa: E402
from notebooks.bronze import orchestrator as orc  # noqa: E402
from notebooks.bronze.anonymisation_engine import AnonymisationEngine  # noqa: E402
from notebooks.bronze.dedup_engine import DedupEngine  # noqa: E402
from notebooks.bronze.error_manager import StagingIntegrityError  # noqa: E402
from notebooks.bronze.hash_engine import HashEngine  # noqa: E402
from notebooks.bronze.history_engine import HistoryEngine  # noqa: E402
from notebooks.bronze.landing_manager import LandingManager, landing_relative_path  # noqa: E402
from notebooks.bronze.merge_engine import MergeEngine  # noqa: E402
from notebooks.bronze.models import AnonymisationRule, FrameworkConfig, LoadConfig  # noqa: E402
from notebooks.bronze.run_manager import RunContext  # noqa: E402
from notebooks.bronze.schema_manager import SchemaManager  # noqa: E402
from notebooks.bronze.staging_manager import StagingManager  # noqa: E402
from notebooks.bronze.validation_engine import ValidationEngine  # noqa: E402
from notebooks.bronze.watermark_manager import batch_max_watermark  # noqa: E402
from tests.bronze.factories import make_entity  # noqa: E402
from tests.bronze.test_orchestrator import FakeWatermarks, RecordingAudit  # noqa: E402

RULES = {
    1: AnonymisationRule(1, "HASH_EMAIL", "HASH", "EMAIL", {"domain": "example.invalid", "length": 16}, "salt"),
    2: AnonymisationRule(2, "MASK_PHONE", "MASK", "PARTIAL", {"keep_last": 4, "mask_char": "*"}),
}


@pytest.fixture(scope="module")
def spark(tmp_path_factory):
    from delta import configure_spark_with_delta_pip
    from pyspark.sql import SparkSession

    warehouse = tmp_path_factory.mktemp("spark-warehouse")
    builder = (SparkSession.builder.master("local[2]").appName("bronze-framework-tests")
               .config("spark.sql.extensions", "io.delta.sql.DeltaSparkSessionExtension")
               .config("spark.sql.catalog.spark_catalog", "org.apache.spark.sql.delta.catalog.DeltaCatalog")
               .config("spark.sql.warehouse.dir", str(warehouse))
               .config("spark.sql.session.timeZone", "UTC")
               .config("spark.sql.shuffle.partitions", "2")
               .config("spark.ui.enabled", "false"))
    session = configure_spark_with_delta_pip(builder).getOrCreate()
    yield session
    session.stop()


@pytest.fixture
def landing_root(tmp_path):
    return tmp_path / "landing"


def _services(spark, landing_root, audit, watermarks, anonymisation_enabled=True):
    config = FrameworkConfig("DEV", {"max_parallel_entities": "2",
                                     "anonymisation_enabled": "true" if anonymisation_enabled else "false"})
    return orc.FrameworkServices(
        spark=spark, config=config, audit=audit,
        landing=LandingManager(str(landing_root), "landing", fs=None),
        staging=StagingManager(spark), schema=SchemaManager(spark), validation=ValidationEngine(spark),
        dedup=DedupEngine(), anonymisation=AnonymisationEngine(RULES, lambda name: "test-salt"),
        hashing=HashEngine(), merge=MergeEngine(spark), history=HistoryEngine(spark),
        watermarks=watermarks, batch_max_watermark=batch_max_watermark, sleep=lambda s: None,
    )


def _write_landing(landing_root, entity, run_ts, rows):
    path = landing_root / landing_relative_path(entity, run_ts)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")   # setOfObjects, as the copy writes
    return landing_relative_path(entity, run_ts)


def _customer(unique):
    return make_entity(target_schema=f"sqlserver_{unique}", staging_schema=f"staging_{unique}",
                       load_config=LoadConfig(True, 1, 0))


def _run(spark, landing_root, entity, run_id, landing_path=None, source_rows=None, watermarks=None,
         anonymisation_enabled=True):
    ctx = RunContext.create(environment="DEV", run_id=run_id)
    audit, watermarks = RecordingAudit(), watermarks or FakeWatermarks(None)
    services = _services(spark, landing_root, audit, watermarks, anonymisation_enabled)
    SchemaManager(spark).ensure_entity_tables(entity)
    item = orc.WorkItem(entity, ctx.entity_run_id(entity.entity_id), landing_path, source_rows)
    return orc.process_entity(item, ctx, services), audit, watermarks


def test_spark_hash_matches_python_reference(spark, customer):
    row = {"CustomerId": 1, "FirstName": None, "Email": "a@b.c", "Phone": "0123",
           "ModifiedDate": datetime(2026, 9, 1, 10, 0, 0, 123456)}
    df = spark.createDataFrame([row], "CustomerId INT, FirstName STRING, Email STRING, Phone STRING, ModifiedDate TIMESTAMP")
    spark_hash = HashEngine().add_hash(df, customer).collect()[0][he.HASH_COLUMN]
    assert spark_hash == he.compute_record_hash(row, customer)

    product = make_entity(columns=(
        *make_entity().columns[:1],
        type(make_entity().columns[0])("ListPrice", "ListPrice", 2, "DECIMAL(18,2)"),
    ))
    decimal_df = spark.createDataFrame([{"CustomerId": 1, "ListPrice": Decimal("12.50")}],
                                       "CustomerId INT, ListPrice DECIMAL(18,2)")
    assert HashEngine().add_hash(decimal_df, product).collect()[0][he.HASH_COLUMN] == he.compute_record_hash(
        {"ListPrice": Decimal("12.50")}, product)


def test_landing_enabled_history_initial_incremental_rerun(spark, landing_root):
    entity = _customer("hist")
    first = _write_landing(landing_root, entity, "20260901000000", [
        {"CustomerId": 100, "FirstName": "Ann", "Email": "ann@x.com", "Phone": "07700900001",
         "ModifiedDate": "2026-09-01T00:00:00"},
        {"CustomerId": 100, "FirstName": "Ann", "Email": "ann@x.com", "Phone": "07700900001",
         "ModifiedDate": "2026-09-01T00:00:00"},            # exact duplicate input
        {"CustomerId": 101, "FirstName": "Bob", "Email": None, "Phone": None, "ModifiedDate": "2026-09-01T00:00:00"},
    ])
    watermarks = FakeWatermarks(None)
    result, audit, _ = _run(spark, landing_root, entity, "20260901-000000-AAAAAA", first, watermarks=watermarks)
    assert result.status == "SUCCEEDED", result.error_message
    bronze = spark.table(entity.target_fqn)
    assert bronze.count() == 2 and bronze.filter("bronze_is_current").count() == 2
    assert result.watermark_after == "2026-09-01 00:00:00.000000"
    # anonymised in DEV, never the raw value
    assert bronze.filter("Email = 'ann@x.com'").count() == 0
    assert bronze.filter("Email LIKE '%@example.invalid'").count() == 1

    watermarks.value = result.watermark_after
    second = _write_landing(landing_root, entity, "20260910000000", [
        {"CustomerId": 100, "FirstName": "Anne", "Email": "ann@x.com", "Phone": "07700900001",
         "ModifiedDate": "2026-09-10T00:00:00"},             # changed record
        {"CustomerId": 101, "FirstName": "Bob", "Email": None, "Phone": None,
         "ModifiedDate": "2026-09-10T00:00:00"},             # touched, no business change
        {"CustomerId": 102, "FirstName": "Cy", "Email": "cy@x.com", "Phone": "07700900003",
         "ModifiedDate": "2026-09-10T00:00:00"},             # new record
    ])
    result, _, _ = _run(spark, landing_root, entity, "20260910-000000-BBBBBB", second, watermarks=watermarks)
    assert result.status == "SUCCEEDED", result.error_message
    bronze = spark.table(entity.target_fqn)
    assert bronze.filter("CustomerId = 100").count() == 2           # source history preserved
    assert bronze.filter("CustomerId = 100 AND bronze_is_current").collect()[0]["FirstName"] == "Anne"
    closed = bronze.filter("CustomerId = 100 AND NOT bronze_is_current").collect()[0]
    assert closed["bronze_valid_to"] == datetime(2026, 9, 10)
    assert bronze.filter("CustomerId = 101").count() == 1           # no-change touch is not a version
    assert bronze.filter("bronze_is_current").count() == 3

    before = bronze.count()
    result, _, _ = _run(spark, landing_root, entity, "20260910-000000-BBBBBB", second, watermarks=watermarks)
    assert result.status == "SUCCEEDED" and spark.table(entity.target_fqn).count() == before   # idempotent replay


def test_landing_disabled_merge_staging_truncation_validation_and_watermark(spark, landing_root, product):
    entity = make_entity(**{**product.__dict__, "target_schema": "sqlserver_merge", "staging_schema": "staging_merge",
                            "load_config": LoadConfig(False, 0, 0)})
    SchemaManager(spark).ensure_entity_tables(entity)

    def copy_to_staging(run_id, rows):   # what the pipeline Copy (table action Overwrite) does
        df = spark.createDataFrame(rows, "ProductId INT, ProductName STRING, ListPrice DECIMAL(18,2), "
                                         "ModifiedDate TIMESTAMP")
        from pyspark.sql import functions as F
        df.withColumn("_staging_run_id", F.lit(run_id)).write.format("delta").mode("overwrite") \
            .saveAsTable(entity.staging_fqn)

    watermarks = FakeWatermarks(None)
    copy_to_staging("20260901-000000-CCCCCC", [(1, "Pen", Decimal("1.00"), datetime(2026, 9, 1)),
                                               (2, "Ink", Decimal("2.00"), datetime(2026, 9, 1))])
    result, audit, _ = _run(spark, landing_root, entity, "20260901-000000-CCCCCC", source_rows=2,
                            watermarks=watermarks)
    assert result.status == "SUCCEEDED" and result.inserted == 2
    assert audit.named("log_file") == []                            # no landing file when landing is disabled
    watermarks.value = result.watermark_after

    # validation failure: nothing written, watermark preserved
    copy_to_staging("20260902-000000-DDDDDD", [(1, "Pen", Decimal("-5.00"), datetime(2026, 9, 2))])
    result, _, _ = _run(spark, landing_root, entity, "20260902-000000-DDDDDD", source_rows=1, watermarks=watermarks)
    assert result.status == "FAILED" and result.error_code == "VALIDATION_FAILED"
    assert watermarks.commits == [] or watermarks.commits[-1][2] != "2026-09-02 00:00:00.000000"
    assert spark.table(entity.target_fqn).filter("ListPrice < 0").count() == 0

    # staging not truncated / belongs to another run -> integrity failure, never processed
    with pytest.raises(StagingIntegrityError):
        StagingManager(spark).verify(entity, "20260903-000000-EEEEEE", 1)

    # change detection: one changed, one unchanged -> 1 update, 0 inserts
    copy_to_staging("20260904-000000-FFFFFF", [(1, "Pen v2", Decimal("1.00"), datetime(2026, 9, 4)),
                                               (2, "Ink", Decimal("2.00"), datetime(2026, 9, 4))])
    result, _, _ = _run(spark, landing_root, entity, "20260904-000000-FFFFFF", source_rows=2, watermarks=watermarks)
    assert result.status == "SUCCEEDED" and (result.inserted, result.updated) == (0, 1)
    created = spark.table(entity.target_fqn).filter("ProductId = 1").collect()[0]
    assert created["bronze_created_datetime"] < created["bronze_updated_datetime"]   # created never overwritten


def test_full_load_delete_detection_soft_deletes(spark, landing_root):
    entity = make_entity(entity_id=104, source_table="Territory", target_schema="sqlserver_full",
                         target_table="territory", staging_schema="staging_full", staging_table="t",
                         load_type="FULL", landing_enabled=False, history_required=False, merge_required=True,
                         primary_key=("TerritoryId",), watermark_column=None, watermark_type=None,
                         anonymisation_required=False, load_config=LoadConfig(delete_detection_enabled=True),
                         columns=(type(make_entity().columns[0])("TerritoryId", "TerritoryId", 1, "INT",
                                                                  is_primary_key=True, is_hash=False),
                                  type(make_entity().columns[0])("TerritoryName", "TerritoryName", 2, "STRING")))
    SchemaManager(spark).ensure_entity_tables(entity)
    from pyspark.sql import functions as F

    for run_id, rows in (("20260901-000000-GGGGGG", [(1, "North"), (2, "South")]),
                         ("20260902-000000-HHHHHH", [(1, "North")])):
        spark.createDataFrame(rows, "TerritoryId INT, TerritoryName STRING") \
            .withColumn("_staging_run_id", F.lit(run_id)).write.format("delta").mode("overwrite") \
            .saveAsTable(entity.staging_fqn)
        result, _, _ = _run(spark, landing_root, entity, run_id, source_rows=len(rows))
        assert result.status == "SUCCEEDED", result.error_message

    statuses = {r["TerritoryId"]: r["bronze_record_status"] for r in spark.table(entity.target_fqn).collect()}
    assert statuses == {1: "ACTIVE", 2: "DELETED"}                  # soft delete, row retained
