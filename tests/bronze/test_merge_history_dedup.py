"""merge_engine.py, history_engine.py, dedup_engine.py clause builders
(spec sections 16-18, 53)."""

from datetime import datetime

import pytest

from notebooks.bronze import dedup_engine as de
from notebooks.bronze import history_engine as hi
from notebooks.bronze import merge_engine as me
from notebooks.bronze.models import LoadConfig
from tests.bronze.factories import make_entity


def test_merge_condition_supports_composite_keys():
    assert me.build_merge_condition(("OrderId", "OrderLineNumber")) == (
        "t.`OrderId` = s.`OrderId` AND t.`OrderLineNumber` = s.`OrderLineNumber`")
    with pytest.raises(ValueError):
        me.build_merge_condition(())


def test_matched_update_only_on_real_change(product):
    condition = me.build_matched_condition(product)
    assert "t.`bronze_record_hash` <> s.`bronze_record_hash`" in condition
    assert "t.`bronze_record_status` <> 'ACTIVE'" in condition        # soft-deleted row reappears
    assert me.build_matched_condition(make_entity(change_detection_method="NONE")) is None


def test_update_set_never_touches_keys_or_created_datetime(product):
    update = me.build_update_set(product)
    assert "ProductId" not in update
    assert "bronze_created_datetime" not in update
    assert update["ProductName"] == "s.`ProductName`"
    assert update["bronze_record_hash"] == "s.`bronze_record_hash`"
    assert update["bronze_run_id"] == "s.`bronze_run_id`"


def test_delete_detection_only_for_full_merge_with_flag():
    full = dict(load_type="FULL", history_required=False, merge_required=True, watermark_column=None,
                watermark_type=None)
    assert me.delete_detection_applies(make_entity(**full, load_config=LoadConfig(delete_detection_enabled=True)))
    assert not me.delete_detection_applies(make_entity(**full, load_config=LoadConfig(delete_detection_enabled=False)))
    assert not me.delete_detection_applies(make_entity(history_required=False, merge_required=True,
                                                       load_config=LoadConfig(delete_detection_enabled=True)))
    soft_delete = me.build_soft_delete_set("run-1", "run-1-E104")
    assert soft_delete["bronze_record_status"] == "'DELETED'"   # soft delete, never physical


def test_parse_merge_metrics_counts_soft_deletes_separately():
    metrics = me.parse_merge_metrics({"numTargetRowsInserted": "5", "numTargetRowsUpdated": "7",
                                      "numTargetRowsMatchedUpdated": "4",
                                      "numTargetRowsNotMatchedBySourceUpdated": "3"})
    assert metrics == me.WriteMetrics(inserted=5, updated=4, deleted=3)
    assert me.parse_merge_metrics({}) == me.WriteMetrics()


def test_append_is_idempotent_per_entity_run():
    assert me.build_append_replace_where("r-1-E5") == "bronze_entity_run_id = 'r-1-E5'"
    assert me.build_append_replace_where("x'y") == "bronze_entity_run_id = 'x''y'"


def test_technical_column_values(customer):
    now = datetime(2026, 9, 30, 8, 12)
    values = me.technical_column_values(customer, "run-1", "run-1-E101", now)
    assert values["bronze_source_system"] == "SQLServer" and values["bronze_source_table"] == "Customer"
    assert values["bronze_created_datetime"] == values["bronze_updated_datetime"] == now
    assert values["bronze_record_status"] == "ACTIVE"


def test_history_merge_closes_only_the_current_version():
    condition = hi.build_history_merge_condition(("CustomerId",))
    assert condition == "t.`CustomerId` = s.`_mk_CustomerId` AND t.`bronze_is_current` = true"
    assert hi.build_insert_condition(("OrderId", "Line")) == "s.`_mk_OrderId` IS NULL AND s.`_mk_Line` IS NULL"
    assert hi.build_close_set() == {"bronze_is_current": "false", "bronze_valid_to": "s.`bronze_valid_from`",
                                    "bronze_updated_datetime": "s.`bronze_updated_datetime`"}


def test_history_temporal_filter_makes_reruns_a_no_op():
    predicate = hi.build_temporal_keep_predicate()
    assert "_cur_valid_from IS NULL" in predicate                    # new key
    assert "bronze_valid_from > _cur_valid_from" in predicate        # newer version
    assert "bronze_record_hash <> _cur_hash" in predicate            # same instant, corrected value


def test_history_valid_from_source(customer):
    assert hi.valid_from_source(customer) == "watermark"
    assert hi.valid_from_source(make_entity(watermark_column=None, watermark_type=None, load_type="FULL")) == "ingestion"
    assert hi.valid_from_source(make_entity(watermark_type="NUMERIC")) == "ingestion"


def test_dedup_mode_keeps_history_rows(customer, product):
    assert de.dedup_mode(customer) == "EXACT"            # history: several versions per key are legitimate
    assert de.dedup_mode(product) == "LATEST_PER_KEY"
    assert de.dedup_mode(make_entity(primary_key=(), history_required=False)) == "EXACT"
    assert de.latest_per_key_order(product) == [("ModifiedDate", "desc_nulls_last"), ("_bronze_ingest_seq", "desc")]
