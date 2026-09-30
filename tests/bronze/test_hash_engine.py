"""hash_engine.py: deterministic canonicalisation and change detection
(spec section 52)."""

from datetime import date, datetime
from decimal import Decimal

from notebooks.bronze import hash_engine as he
from notebooks.bronze.models import ColumnConfig
from tests.bronze.factories import make_entity


def test_hash_expression_covers_only_hash_columns_in_ordinal_order(customer):
    expression = he.build_entity_hash_expression(customer)
    assert expression.startswith("sha2(concat_ws('\\u001F', ")
    positions = [expression.index(f"`{c}`") for c in ("FirstName", "Email", "Phone")]
    assert positions == sorted(positions)
    assert "`CustomerId`" not in expression      # primary key identifies, never "changes"
    assert "`ModifiedDate`" not in expression    # hash_flag = 0
    assert "bronze_" not in expression           # technical columns never hashed


def test_every_part_is_null_safe():
    expression = he.canonical_expression("Email", "STRING")
    assert expression == "CASE WHEN `Email` IS NULL THEN '\\N' ELSE CAST(`Email` AS STRING) END"


def test_type_specific_canonical_forms():
    assert "yyyy-MM-dd'T'HH:mm:ss.SSSSSS" in he.canonical_expression("ts", "TIMESTAMP")
    assert "'yyyy-MM-dd'" in he.canonical_expression("d", "DATE")
    assert "THEN 'true' ELSE 'false'" in he.canonical_expression("b", "BOOLEAN")
    assert "lower(hex(`bin`))" in he.canonical_expression("bin", "BINARY")
    assert "CAST(`p` AS STRING)" in he.canonical_expression("p", "DECIMAL(18,2)")


def test_no_hash_columns_hashes_to_constant():
    assert he.build_hash_expression(()) == "sha2('', 256)"


def test_reference_hash_is_deterministic_and_null_distinct_from_empty():
    types = ["STRING", "STRING"]
    assert he.compute_hash(["a", None], types) == he.compute_hash(["a", None], types)
    assert he.compute_hash(["a", None], types) != he.compute_hash(["a", ""], types)
    # position matters: ("ab", "") must differ from ("a", "b")
    assert he.compute_hash(["ab", ""], types) != he.compute_hash(["a", "b"], types)


def test_reference_canonical_values():
    assert he.canonical_value(None, "INT") == "\\N"
    assert he.canonical_value(datetime(2026, 9, 1, 10, 0, 0, 5), "TIMESTAMP") == "2026-09-01T10:00:00.000005"
    assert he.canonical_value(date(2026, 9, 1), "DATE") == "2026-09-01"
    assert he.canonical_value(True, "BOOLEAN") == "true"
    assert he.canonical_value(Decimal("12.5"), "DECIMAL(18,2)") == "12.50"
    assert he.canonical_value(Decimal("1E+2"), "DECIMAL(18,2)") == "100.00"   # never exponent notation
    assert he.canonical_value(b"\x01\xff", "BINARY") == "01ff"


def test_record_hash_detects_business_changes_only(customer):
    base = {"CustomerId": 100, "FirstName": "Ann", "Email": "a@x.invalid", "Phone": "1234",
            "ModifiedDate": datetime(2026, 9, 1)}
    same_business_newer_touch = dict(base, ModifiedDate=datetime(2026, 9, 10))
    changed = dict(base, FirstName="Anne")

    assert he.compute_record_hash(base, customer) == he.compute_record_hash(same_business_newer_touch, customer)
    assert he.compute_record_hash(base, customer) != he.compute_record_hash(changed, customer)


def test_composite_keys_are_excluded_from_hash():
    entity = make_entity(primary_key=("OrderId", "Line"), columns=(
        ColumnConfig("OrderId", "OrderId", 1, "INT", is_primary_key=True),
        ColumnConfig("Line", "Line", 2, "INT", is_primary_key=True),
        ColumnConfig("Qty", "Qty", 3, "INT"),
    ), watermark_column=None, watermark_type=None, load_type="FULL", history_required=False, merge_required=True)
    assert [c.target_column for c in entity.hash_columns] == ["Qty"]
