"""models.py (write strategy derivation, FrameworkConfig) and run_manager.py."""

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from notebooks.bronze import run_manager as rm
from notebooks.bronze.models import FrameworkConfig
from tests.bronze.factories import make_entity


@pytest.mark.parametrize(
    "history,merge,load_type,expected",
    [
        (True, False, "INCREMENTAL", "HISTORY"),
        (True, True, "INCREMENTAL", "HISTORY"),   # history wins
        (False, True, "INCREMENTAL", "MERGE"),
        (False, True, "FULL", "MERGE"),
        (False, False, "FULL", "REPLACE"),
        (False, False, "INCREMENTAL", "APPEND"),
    ],
)
def test_write_strategy_is_derived_from_metadata(history, merge, load_type, expected):
    entity = make_entity(history_required=history, merge_required=merge, load_type=load_type)
    assert entity.write_strategy == expected


def test_hash_columns_exclude_primary_key_and_non_hash_columns(customer):
    assert [c.target_column for c in customer.hash_columns] == ["FirstName", "Email", "Phone"]


def test_composite_key_and_names(customer):
    entity = make_entity(primary_key=("OrderId", "OrderLineNumber"))
    assert entity.primary_key == ("OrderId", "OrderLineNumber")
    assert customer.target_fqn == "`sqlserver`.`customer`"
    assert customer.staging_fqn == "`staging`.`sqlserver_customer`"
    assert customer.watermark_target_column == "ModifiedDate"


def test_framework_config_typed_accessors_and_defaults():
    dev = FrameworkConfig("DEV", {"anonymisation_enabled": "true", "max_parallel_entities": "5",
                                  "landing_globally_enabled": "false", "audit_failure_is_critical": ""})
    prod = FrameworkConfig("PROD", {"anonymisation_enabled": "false"})
    empty = FrameworkConfig("UAT", {})

    assert dev.anonymisation_enabled is True and prod.anonymisation_enabled is False
    assert empty.anonymisation_enabled is True           # safe default: anonymise
    assert dev.max_parallel_entities == 5
    assert FrameworkConfig("DEV", {"max_parallel_entities": "0"}).max_parallel_entities == 1
    assert dev.landing_globally_enabled is False and empty.landing_globally_enabled is True
    assert dev.audit_failure_is_critical is False         # empty string -> default
    assert empty.landing_lakehouse_path == "Files/landing"
    assert empty.audit_sql_token_audience is None
    assert FrameworkConfig("DEV", {"sql_token_audience": "pbi"}).audit_sql_token_audience == "pbi"


NOW = datetime(2026, 9, 30, 8, 12, 5, tzinfo=timezone.utc)


def test_run_id_format_matches_spec():
    run_id = rm.new_run_id(NOW, suffix="abc123")
    assert run_id == "20260930-081205-ABC123"
    assert rm.RUN_ID_PATTERN.match(rm.new_run_id())


def test_run_timestamp_keeps_minutes_and_seconds():
    # The spec's literal 'yyyymmddhhss' would drop the minutes (collisions
    # within an hour); the framework uses yyyyMMddHHmmss.
    assert rm.run_timestamp(NOW) == "20260930081205"
    assert rm.run_timestamp_from_run_id("20260930-081205-ABC123") == "20260930081205"


def test_entity_run_id_is_deterministic():
    assert rm.entity_run_id("20260930-081205-ABC123", 101) == "20260930-081205-ABC123-E101"


def test_run_context_derives_timestamp_from_run_id_and_validates():
    ctx = rm.RunContext.create(environment="dev", run_id="20260930-081205-ABC123")
    assert ctx.run_timestamp == "20260930081205"
    assert ctx.environment == "DEV"
    assert ctx.entity_run_id(102) == "20260930-081205-ABC123-E102"
    with pytest.raises(ValueError):
        rm.RunContext(run_id="x", run_timestamp="2026-09-30", environment="DEV")


def test_run_context_reads_notebook_identity_when_available():
    fake_nbu = SimpleNamespace(runtime=SimpleNamespace(context={
        "currentWorkspaceId": "ws-1", "currentWorkspaceName": "eng-dev", "currentNotebookName": "BronzeFramework"}))
    ctx = rm.RunContext.create(environment="DEV", now=NOW).with_notebook_context(fake_nbu)
    assert (ctx.workspace_id, ctx.workspace_name, ctx.notebook_name) == ("ws-1", "eng-dev", "BronzeFramework")
    # outside Fabric (no runtime.context) it is a no-op
    assert rm.RunContext.create(environment="DEV", now=NOW).with_notebook_context(object()).workspace_id is None
