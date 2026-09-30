"""config_loader.py: assembly of control-table rows into EntityConfig, and
metadata validation."""

import pytest

from notebooks.bronze import config_loader as cl
from notebooks.bronze.error_manager import MetadataError

ENTITY_ROWS = [
    {"entity_id": 103, "source_schema": "dbo", "source_table": "Order", "target_schema": "sqlserver",
     "target_table": "order", "staging_schema": "staging", "staging_table": "sqlserver_order",
     "entity_group": "sales", "load_type": "INCREMENTAL", "landing_enabled": 1, "history_required": 0,
     "merge_required": 1, "primary_key": "OrderId, OrderLineNumber", "watermark_column": "ModifiedDate",
     "watermark_type": "DATETIME", "change_detection_method": "HASH", "anonymisation_required": 0,
     "processing_priority": 30, "source_system_name": "SQLServer", "source_type": "SQLSERVER"},
    {"entity_id": 101, "source_schema": "dbo", "source_table": "Customer", "target_schema": "sqlserver",
     "target_table": "customer", "staging_schema": "staging", "staging_table": "sqlserver_customer",
     "entity_group": "sales", "load_type": "incremental", "landing_enabled": True, "history_required": True,
     "merge_required": False, "primary_key": "CustomerId", "watermark_column": "ModifiedDate",
     "watermark_type": "datetime", "change_detection_method": "hash", "anonymisation_required": True,
     "processing_priority": 10, "source_system_name": "SQLServer", "source_type": "SQLSERVER"},
]


def _col(entity_id, name, ordinal, dtype="STRING", pk=0, wm=0, hash_flag=1, anon=0, rule=None):
    return {"entity_id": entity_id, "source_column": name, "target_column": name, "ordinal_position": ordinal,
            "target_data_type": dtype, "nullable_flag": 1, "primary_key_flag": pk, "watermark_flag": wm,
            "hash_flag": hash_flag, "anonymisation_flag": anon, "anonymisation_rule_id": rule}


COLUMN_ROWS = [
    _col(103, "OrderLineNumber", 2, "INT", pk=1, hash_flag=0),
    _col(103, "OrderId", 1, "INT", pk=1, hash_flag=0),
    _col(103, "Quantity", 3, "INT"),
    _col(103, "ModifiedDate", 4, "timestamp", wm=1, hash_flag=0),
    _col(101, "CustomerId", 1, "INT", pk=1, hash_flag=0),
    _col(101, "Email", 2, anon=1, rule=1),
    _col(101, "Phone", 3, anon=0, rule=2),       # rule id present but flag off -> not anonymised
    _col(101, "ModifiedDate", 4, "TIMESTAMP", wm=1, hash_flag=0),
]
ANON_RULES = cl.assemble_anonymisation_rules([
    {"anonymisation_rule_id": 1, "rule_name": "HASH_EMAIL", "rule_type": "hash", "algorithm": "EMAIL",
     "parameters": '{"domain": "example.invalid"}', "salt_secret_name": "bronze-anonymisation-salt"},
])


def test_assemble_orders_by_priority_and_builds_composite_keys():
    entities = cl.assemble_entities(
        ENTITY_ROWS, COLUMN_ROWS,
        mapping_rows=[{"entity_id": 103, "target_column": "ModifiedDate",
                       "source_expression": "CAST(ModifiedDate AS TIMESTAMP)"}],
        load_rows=[{"entity_id": 103, "retry_enabled": 1, "max_retry_count": 3, "retry_delay_seconds": 60,
                    "delete_detection_enabled": 0, "row_count_anomaly_threshold_pct": None}],
        validation_rows=[{"validation_rule_id": 1031, "entity_id": 103, "rule_name": "qty", "rule_type": "custom",
                          "column_name": "Quantity", "expression": "Quantity > 0", "severity": "high",
                          "failure_action": "fail", "validation_stage": "pre"}],
        anonymisation_rules=ANON_RULES,
    )

    assert [e.entity_id for e in entities] == [101, 103]
    customer, order = entities
    assert order.primary_key == ("OrderId", "OrderLineNumber")
    assert [c.target_column for c in order.columns] == ["OrderId", "OrderLineNumber", "Quantity", "ModifiedDate"]
    assert order.column("ModifiedDate").source_expression == "CAST(ModifiedDate AS TIMESTAMP)"
    assert order.column("ModifiedDate").target_data_type == "TIMESTAMP"
    assert order.load_config.max_retry_count == 3
    assert order.validation_rules[0].failure_action == "FAIL"
    assert order.write_strategy == "MERGE"
    assert customer.write_strategy == "HISTORY" and customer.load_type == "INCREMENTAL"
    assert customer.column("Email").anonymisation_rule_id == 1
    assert customer.column("Phone").anonymisation_rule_id is None


def test_invalid_metadata_raises_with_every_problem():
    bad = dict(ENTITY_ROWS[1], entity_id=999, watermark_column=None, primary_key=None)
    with pytest.raises(MetadataError) as err:
        cl.assemble_entities([bad], [_col(999, "Email", 1, anon=1, rule=42)], anonymisation_rules=ANON_RULES)
    message = str(err.value)
    assert "INCREMENTAL load requires watermark_column" in message
    assert "HISTORY requires a primary_key" in message
    assert "unknown/inactive anonymisation_rule_id 42" in message
    assert err.value.retryable is False


def test_non_strict_mode_keeps_invalid_entities_for_reporting():
    bad = dict(ENTITY_ROWS[1], entity_id=999, watermark_column=None)
    entities = cl.assemble_entities([bad], [_col(999, "CustomerId", 1, pk=1)], strict=False)
    assert [e.entity_id for e in entities] == [999]


def test_validate_entity_accepts_seeded_shapes():
    [customer] = cl.assemble_entities([ENTITY_ROWS[1]], COLUMN_ROWS, anonymisation_rules=ANON_RULES)
    assert cl.validate_entity(customer, ANON_RULES) == []


class FakeCursor:
    def __init__(self, results):
        self.results = results
        self.description = None
        self._rows = []
        self.executed = []

    def execute(self, sql, *params):
        self.executed.append((sql, params))
        for marker, rows in self.results.items():
            if marker in sql:
                names = list(rows[0].keys()) if rows else ["x"]
                self.description = [(n,) for n in names]
                self._rows = [tuple(r[n] for n in names) for r in rows]
                return
        self.description, self._rows = [("x",)], []

    def fetchall(self):
        return self._rows


def _cursor():
    return FakeCursor({
        "[control].[framework_configuration]": [{"config_key": "max_parallel_entities", "config_value": "5"}],
        "[control].[anonymisation_rule]": [{"anonymisation_rule_id": 1, "rule_name": "HASH_EMAIL",
                                            "rule_type": "HASH", "algorithm": "EMAIL", "parameters": None,
                                            "salt_secret_name": None}],
        "[control].[entity] e": ENTITY_ROWS,
        "[control].[entity_column]": COLUMN_ROWS,
    })


def test_load_entities_uses_fixed_number_of_queries_and_filters():
    cursor = _cursor()
    entities = cl.load_entities(cursor, entity_ids=[101])
    assert [e.entity_id for e in entities] == [101]
    # anonymisation rules + one query per control table, independent of entity count
    assert len(cursor.executed) == 6


def test_load_entities_rejects_unknown_requested_ids():
    with pytest.raises(MetadataError):
        cl.load_entities(_cursor(), entity_ids=[101, 555])


def test_load_framework_config_is_environment_scoped():
    cursor = _cursor()
    config = cl.load_framework_config(cursor, "dev")
    assert config.environment == "DEV" and config.max_parallel_entities == 5
    assert cursor.executed[0][1] == ("DEV",)
