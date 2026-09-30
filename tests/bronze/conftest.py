"""Shared fixtures for notebooks.bronze tests.

notebookutils only exists inside a Fabric runtime -- stub it before any
module under test imports it (same pattern as tests/framework, see
docs/runbook.md section 6.1).
"""

import sys
import types
from unittest.mock import MagicMock

import pytest

sys.modules.setdefault("notebookutils", types.ModuleType("notebookutils"))
sys.modules["notebookutils"].credentials = MagicMock(getToken=MagicMock(return_value="fake-token"),
                                                     getSecret=MagicMock(return_value="fake-salt"))
sys.modules["notebookutils"].fs = MagicMock()

from tests.bronze.factories import make_entity  # noqa: E402
from notebooks.bronze.models import ColumnConfig, ValidationRule  # noqa: E402


@pytest.fixture
def customer():
    return make_entity()


@pytest.fixture
def product():
    return make_entity(
        entity_id=102, source_table="Product", target_table="product", staging_table="sqlserver_product",
        landing_enabled=False, history_required=False, merge_required=True, primary_key=("ProductId",),
        anonymisation_required=False,
        columns=(
            ColumnConfig("ProductId", "ProductId", 1, "INT", nullable=False, is_primary_key=True, is_hash=False),
            ColumnConfig("ProductName", "ProductName", 2, "STRING"),
            ColumnConfig("ListPrice", "ListPrice", 3, "DECIMAL(18,2)"),
            ColumnConfig("ModifiedDate", "ModifiedDate", 4, "TIMESTAMP", is_watermark=True, is_hash=False),
        ),
        validation_rules=(ValidationRule(1021, "product_listprice_non_negative", "CUSTOM", "ListPrice",
                                         "ListPrice IS NULL OR ListPrice >= 0", "HIGH", "FAIL", "PRE"),),
    )
