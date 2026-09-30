"""validation_engine.py: metadata-driven rules, built-ins, actions (spec section 50)."""

import pytest

from notebooks.bronze import validation_engine as ve
from notebooks.bronze.models import ValidationRule
from tests.bronze.factories import make_entity


def _rule(rule_type, column=None, expression=None, action="FAIL", stage="PRE", rule_id=1):
    return ValidationRule(rule_id, f"r_{rule_type.lower()}", rule_type, column, expression, "HIGH", action, stage)


def test_builtins_apply_unless_overridden(customer):
    types = [r.rule_type for r in ve.effective_rules(customer, "PRE")]
    assert types == ["COLUMN_MISSING", "DATA_TYPE_MISMATCH", "PRIMARY_KEY_NULL", "DUPLICATE_PRIMARY_KEY"]
    duplicate = next(r for r in ve.effective_rules(customer, "PRE") if r.rule_type == "DUPLICATE_PRIMARY_KEY")
    assert duplicate.failure_action == "WARN"      # dedup resolves duplicates; keep them visible

    override = make_entity(validation_rules=(_rule("DUPLICATE_PRIMARY_KEY", action="FAIL", rule_id=7),))
    rules = ve.effective_rules(override, "PRE")
    assert [r.rule_id for r in rules if r.rule_type == "DUPLICATE_PRIMARY_KEY"] == [7]


def test_stage_filtering(customer):
    entity = make_entity(validation_rules=(_rule("ROW_COUNT_ANOMALY", stage="POST"),))
    assert [r.rule_type for r in ve.effective_rules(entity, "POST")] == ["ROW_COUNT_ANOMALY"]
    assert ve.effective_rules(make_entity(primary_key=()), "POST") == []


def test_primary_key_sql_supports_composite_keys():
    entity = make_entity(primary_key=("OrderId", "OrderLineNumber"))
    null_sql = ve.build_rule_sql(_rule("PRIMARY_KEY_NULL"), entity, "v")
    dup_sql = ve.build_rule_sql(_rule("DUPLICATE_PRIMARY_KEY"), entity, "v")
    assert "WHERE `OrderId` IS NULL OR `OrderLineNumber` IS NULL" in null_sql
    assert "GROUP BY `OrderId`, `OrderLineNumber` HAVING COUNT(*) > 1" in dup_sql
    assert "SUM(n - 1)" in dup_sql     # counts surplus rows, not keys


def test_column_rule_sql(product):
    assert ve.build_rule_sql(_rule("MANDATORY_COLUMN_NULL", "ProductName"), product, "v").endswith(
        "WHERE `ProductName` IS NULL")
    type_sql = ve.build_rule_sql(_rule("DATA_TYPE_MISMATCH", "ListPrice"), product, "v", raw_view="raw")
    assert type_sql == ("SELECT COUNT(*) AS failed_row_count FROM raw WHERE "
                        "(`ListPrice` IS NOT NULL AND try_cast(CAST(`ListPrice` AS STRING) AS DECIMAL(18,2)) IS NULL)")
    assert ve.build_rule_sql(_rule("CUSTOM", expression="ListPrice >= 0"), product, "v").endswith(
        "WHERE NOT (ListPrice >= 0)")


def test_builtin_type_check_covers_every_typed_column_against_raw_staging(customer):
    # Spark's non-ANSI CAST silently NULLs bad values, so types are checked on the
    # RAW (source-shaped) staging rows: raw value present but conversion NULL.
    sql = ve.build_rule_sql(ValidationRule(None, "b", "DATA_TYPE_MISMATCH"), customer, "v", raw_view="raw")
    assert "FROM raw WHERE" in sql
    assert "(`CustomerId` IS NOT NULL AND try_cast(CAST(`CustomerId` AS STRING) AS INT) IS NULL)" in sql
    # a column_mapping expression is evaluated as configured
    assert ("(`ModifiedDate` IS NOT NULL AND CAST((CAST(ModifiedDate AS TIMESTAMP)) AS TIMESTAMP) IS NULL)"
            in sql)
    assert "`FirstName`" not in sql          # STRING columns cannot mismatch
    only_strings = make_entity(columns=(make_entity().columns[1],), primary_key=(), history_required=False,
                               watermark_column=None, watermark_type=None, load_type="FULL")
    assert not any(r.rule_type == "DATA_TYPE_MISMATCH" for r in ve.effective_rules(only_strings, "PRE"))


def test_column_specific_type_rule_keeps_the_builtin(product):
    entity = make_entity(**{**product.__dict__, "validation_rules": (
        _rule("DATA_TYPE_MISMATCH", "ListPrice", action="WARN", rule_id=9),)})
    type_rules = [r for r in ve.effective_rules(entity, "PRE") if r.rule_type == "DATA_TYPE_MISMATCH"]
    assert [(r.rule_id, r.failure_action) for r in type_rules] == [(None, "FAIL"), (9, "WARN")]


def test_watermark_invalid_checks_null_and_regression(customer):
    sql = ve.build_rule_sql(_rule("WATERMARK_INVALID", "ModifiedDate"), customer, "v",
                            previous_watermark="2026-09-01 00:00:00.000000")
    assert "`ModifiedDate` IS NULL OR `ModifiedDate` < CAST('2026-09-01 00:00:00.000000' AS TIMESTAMP)" in sql
    first_load = ve.build_rule_sql(_rule("WATERMARK_INVALID"), customer, "v", previous_watermark=None)
    assert first_load.endswith("WHERE `ModifiedDate` IS NULL")


def test_non_sql_rules_return_none_and_unknown_raises(customer):
    assert ve.build_rule_sql(_rule("COLUMN_MISSING"), customer, "v") is None
    assert ve.build_rule_sql(_rule("ROW_COUNT_ANOMALY"), customer, "v") is None
    with pytest.raises(ValueError):
        ve.build_rule_sql(_rule("NOT_A_RULE"), customer, "v")
    with pytest.raises(ValueError):
        ve.build_rule_sql(_rule("CUSTOM"), customer, "v")


@pytest.mark.parametrize(
    "action,failed,status",
    [("FAIL", True, "FAILED"), ("WARN", True, "WARNING"), ("IGNORE", True, "IGNORED"),
     ("FAIL", False, "PASSED"), ("IGNORE", False, "PASSED")],
)
def test_failure_actions(action, failed, status):
    result = ve.to_result(_rule("CUSTOM", expression="x", action=action), failed, 3 if failed else 0, "0", "3", "m")
    assert result.status == status
    assert (result.error_message is not None) is failed


def test_blocking_failures_respect_fail_on_validation_error():
    results = [ve.to_result(_rule("CUSTOM", expression="x", action="FAIL"), True),
               ve.to_result(_rule("CUSTOM", expression="x", action="WARN"), True)]
    assert len(ve.blocking_failures(results, True)) == 1
    assert ve.blocking_failures(results, False) == []


def test_row_count_anomaly_and_missing_columns(customer):
    assert ve.row_count_anomaly(150, 100, 50.0) == 50.0
    assert ve.row_count_anomaly(10, None, 50.0) is None      # no baseline yet
    assert ve.row_count_anomaly(10, 100, None) is None       # not configured
    assert ve.row_count_anomaly(5, 0, 10.0) == 100.0
    assert ve.missing_columns(customer, ["customerid", "FirstName", "Email", "Phone"]) == ["ModifiedDate"]


class FakeDF:
    def __init__(self, columns, count=10):
        self.columns = columns
        self._count = count

    def createOrReplaceTempView(self, name):
        self.view = name

    def count(self):
        return self._count


class FakeSpark:
    def __init__(self, failed_rows):
        self.failed_rows = failed_rows
        self.queries = []
        self.catalog = self

    def sql(self, query):
        self.queries.append(query)
        rows = self.failed_rows

        class Result:
            def collect(self_inner):
                return [{"failed_row_count": rows}]

        return Result()

    def dropTempView(self, name):
        self.dropped = name


def test_engine_evaluates_all_rules_and_drops_view(product):
    spark = FakeSpark(failed_rows=2)
    df = FakeDF(["ProductId", "ProductName", "ListPrice", "ModifiedDate"])
    raw = FakeDF(["ProductId", "ProductName", "ListPrice", "_staging_run_id"])
    results = ve.ValidationEngine(spark).run(df, product, "PRE", "a1", raw_df=raw)
    by_type = {r.rule_type: r for r in results}
    assert by_type["COLUMN_MISSING"].status == "FAILED" and "ModifiedDate" in by_type["COLUMN_MISSING"].error_message
    assert by_type["PRIMARY_KEY_NULL"].failed_row_count == 2
    assert by_type["DUPLICATE_PRIMARY_KEY"].status == "WARNING"
    assert by_type["CUSTOM"].status == "FAILED"
    assert by_type["DATA_TYPE_MISMATCH"].status == "PASSED"   # skipped: a column is missing
    assert raw.view == df.view + "_raw" and spark.dropped == raw.view
    # results carry counts only, never row values
    assert all(r.actual_value in (None, "0", "1", "2") for r in results)
