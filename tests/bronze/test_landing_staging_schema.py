"""landing_manager.py, staging_manager.py, schema_manager.py
(change 1: optional landing layer; spec sections 5-11, 41, 48-49)."""

from types import SimpleNamespace

import pytest

from notebooks.bronze import landing_manager as lm
from notebooks.bronze import schema_manager as sm
from notebooks.bronze import staging_manager as st
from notebooks.bronze.error_manager import LandingFileExistsError, StagingIntegrityError
from notebooks.bronze.models import ColumnConfig
from tests.bronze.factories import make_entity

TS = "20260930081205"


# --- landing ------------------------------------------------------------------

def test_landing_path_follows_source_system_table_timestamp_format(customer):
    assert lm.landing_folder(customer) == "SQLServer/Customer"
    assert lm.landing_file_name(customer, TS) == "Customer_20260930081205.json"
    assert lm.landing_relative_path(customer, TS) == "SQLServer/Customer/Customer_20260930081205.json"
    assert lm.lakehouse_path("Files/landing/", "SQLServer/Customer/Customer_20260930081205.json") == (
        "Files/landing/SQLServer/Customer/Customer_20260930081205.json")


@pytest.mark.parametrize("bad_ts", ["202609300812", "2026-09-30 08:12:05", "", None])
def test_landing_timestamp_must_be_14_digits(customer, bad_ts):
    with pytest.raises(ValueError):
        lm.landing_file_name(customer, bad_ts)


def test_unsafe_path_segments_are_rejected():
    with pytest.raises(ValueError):
        lm.landing_folder(make_entity(source_table="../etc"))
    with pytest.raises(ValueError):
        lm.landing_folder(make_entity(source_system="SQL Server"))


def test_replayable_files_are_ordered_and_filtered(customer):
    names = ["Customer_20260930090000.json", "Customer_20260929090000.json", "Product_20260930090000.json",
             "Customer_latest.json", "Customer_20260930090000.json.tmp"]
    files = lm.replayable_files(customer, names)
    assert [f.run_timestamp for f in files] == ["20260929090000", "20260930090000"]
    assert files[0].relative_path == "SQLServer/Customer/Customer_20260929090000.json"
    assert [f.run_timestamp for f in lm.replayable_files(customer, names, since_run_ts="20260930000000")] == [
        "20260930090000"]


class FakeFS:
    def __init__(self, existing=()):
        self.existing = set(existing)

    def exists(self, path):
        return path in self.existing

    def ls(self, folder):
        return [SimpleNamespace(name=p.rsplit("/", 1)[1], size=100)
                for p in sorted(self.existing) if p.rsplit("/", 1)[0] == folder]


def test_landing_file_is_never_overwritten(customer):
    path = "Files/landing/SQLServer/Customer/Customer_20260930081205.json"
    manager = lm.LandingManager("Files/landing", "landing", fs=FakeFS({path}))
    with pytest.raises(LandingFileExistsError):
        manager.assert_not_exists(customer, TS)
    assert lm.LandingManager("Files/landing", "landing", fs=FakeFS()).assert_not_exists(customer, TS) == path


def test_landing_manager_resolve_prefers_audit_recorded_path_and_lists_replay(customer):
    fs = FakeFS({"Files/landing/SQLServer/Customer/Customer_20260929000000.json"})
    manager = lm.LandingManager("Files/landing", "landing", fs=fs)
    assert manager.resolve(customer, TS, "SQLServer/Customer/Customer_20260929000000.json") == (
        "Files/landing/SQLServer/Customer/Customer_20260929000000.json")
    assert manager.resolve(customer, TS) == "Files/landing/SQLServer/Customer/Customer_20260930081205.json"
    [replay] = manager.list_replayable(customer)
    assert replay.size_bytes == 100 and replay.run_timestamp == "20260929000000"


# --- staging ------------------------------------------------------------------

def test_staging_verification_accepts_only_this_runs_rows():
    assert st.check_staging_counts(10, 10, 10) == []
    assert st.check_staging_counts(10, 10, None) == []
    assert "another run" in st.check_staging_counts(12, 10, 10)[0]           # stale rows not truncated
    assert "copy reported 11" in st.check_staging_counts(10, 10, 11)[0]      # partial copy


def test_staging_sql_targets_staging_never_bronze(product):
    counts = st.build_staging_counts_sql(product, "run-1")
    assert "FROM `staging`.`sqlserver_product`" in counts and "`_staging_run_id` = 'run-1'" in counts
    assert st.build_truncate_sql(product) == "DELETE FROM `staging`.`sqlserver_product`"
    assert "sqlserver`.`product" not in st.build_truncate_sql(product)


def test_projection_applies_mapping_then_casts_once(customer):
    projection = dict(st.projection(customer, ["customerid", "FirstName", "Email", "Phone", "ModifiedDate"]))
    assert projection["CustomerId"] == "CAST(`customerid` AS INT)"      # case-insensitive source match
    assert projection["ModifiedDate"] == "CAST(CAST(ModifiedDate AS TIMESTAMP) AS TIMESTAMP)"


def test_landing_json_is_read_with_explicit_string_schema(customer):
    assert st.landing_read_schema_ddl(customer) == (
        "`CustomerId` STRING, `FirstName` STRING, `Email` STRING, `Phone` STRING, `ModifiedDate` STRING")
    assert st.missing_source_columns(customer, ["CustomerId", "Email"]) == ["FirstName", "Phone", "ModifiedDate"]


class FakeSpark:
    def __init__(self, total, run_rows):
        self.row = {"total_rows": total, "run_rows": run_rows}

    def sql(self, query):
        row = self.row
        return SimpleNamespace(collect=lambda: [row])


def test_staging_manager_verify_raises_on_integrity_problem(product):
    assert st.StagingManager(FakeSpark(5, 5)).verify(product, "run-1", 5) == 5
    with pytest.raises(StagingIntegrityError):
        st.StagingManager(FakeSpark(7, 5)).verify(product, "run-1", 5)


# --- schema -------------------------------------------------------------------

def test_bronze_definitions_add_technical_columns_and_history_only_when_needed(customer, product):
    history_cols = [n for n, _ in sm.bronze_column_definitions(customer)]
    current_cols = [n for n, _ in sm.bronze_column_definitions(product)]
    for required in ("bronze_run_id", "bronze_created_datetime", "bronze_updated_datetime",
                     "bronze_source_system", "bronze_source_table", "bronze_record_hash"):
        assert required in history_cols and required in current_cols
    assert {"bronze_valid_from", "bronze_valid_to", "bronze_is_current"} <= set(history_cols)
    assert "bronze_is_current" not in current_cols
    assert history_cols[:5] == ["CustomerId", "FirstName", "Email", "Phone", "ModifiedDate"]   # names unchanged


def test_staging_definitions_are_source_shaped():
    entity = make_entity(columns=(ColumnConfig("cust_id", "CustomerId", 1, "INT", is_primary_key=True),),
                         primary_key=("CustomerId",), watermark_column=None, watermark_type=None, load_type="FULL")
    assert sm.staging_column_definitions(entity) == [("cust_id", "INT"), ("_staging_run_id", "STRING")]


def test_ddl_builders(customer):
    create = sm.build_create_table_sql(customer.target_fqn, [("a", "INT"), ("we`ird", "STRING")])
    assert create.startswith("CREATE TABLE IF NOT EXISTS `sqlserver`.`customer` (")
    assert "`we``ird` STRING" in create and create.endswith("USING DELTA")
    assert sm.build_create_schema_sql("sqlserver") == "CREATE SCHEMA IF NOT EXISTS `sqlserver`"
    assert sm.missing_columns(["A", "b"], [("a", "INT"), ("c", "STRING")]) == [("c", "STRING")]
    assert sm.build_add_columns_sql("`s`.`t`", [("c", "STRING")]) == "ALTER TABLE `s`.`t` ADD COLUMNS (`c` STRING)"
