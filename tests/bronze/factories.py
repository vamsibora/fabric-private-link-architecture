"""Test factories for notebooks.bronze (importable from any test module)."""

from notebooks.bronze.models import (
    ColumnConfig,
    EntityConfig,
    LoadConfig,
    ValidationRule,
)


def make_entity(**overrides) -> EntityConfig:
    """SQLServer dbo.Customer as seeded in warehouse/metadata/101 (HISTORY,
    landing on), overridable per test."""
    columns = overrides.pop("columns", None) or (
        ColumnConfig("CustomerId", "CustomerId", 1, "INT", nullable=False, is_primary_key=True, is_hash=False),
        ColumnConfig("FirstName", "FirstName", 2, "STRING"),
        ColumnConfig("Email", "Email", 3, "STRING", anonymisation_rule_id=1),
        ColumnConfig("Phone", "Phone", 4, "STRING", anonymisation_rule_id=2),
        ColumnConfig("ModifiedDate", "ModifiedDate", 5, "TIMESTAMP", nullable=False, is_watermark=True,
                     is_hash=False, source_expression="CAST(ModifiedDate AS TIMESTAMP)"),
    )
    values = dict(
        entity_id=101,
        source_system="SQLServer",
        source_type="SQLSERVER",
        source_schema="dbo",
        source_table="Customer",
        target_schema="sqlserver",
        target_table="customer",
        staging_schema="staging",
        staging_table="sqlserver_customer",
        load_type="INCREMENTAL",
        landing_enabled=True,
        history_required=True,
        merge_required=False,
        primary_key=("CustomerId",),
        watermark_column="ModifiedDate",
        watermark_type="DATETIME",
        change_detection_method="HASH",
        anonymisation_required=True,
        columns=columns,
        validation_rules=(),
        load_config=LoadConfig(retry_enabled=True, max_retry_count=2, retry_delay_seconds=1),
    )
    values.update(overrides)
    return EntityConfig(**values)
