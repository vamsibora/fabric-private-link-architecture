"""anonymisation_engine.py: metadata-driven, environment-dependent,
deterministic anonymisation (spec sections 19, 51)."""

import pytest

from notebooks.bronze import anonymisation_engine as ae
from notebooks.bronze.error_manager import MetadataError
from notebooks.bronze.models import AnonymisationRule, ColumnConfig
from tests.bronze.factories import make_entity

RULES = {
    1: AnonymisationRule(1, "HASH_EMAIL", "HASH", "EMAIL", {"domain": "example.invalid", "length": 16},
                         "bronze-anonymisation-salt"),
    2: AnonymisationRule(2, "MASK_PHONE", "MASK", "PARTIAL", {"keep_last": 4, "mask_char": "*"}),
}
EMAIL = ColumnConfig("Email", "Email", 3, "STRING")
PHONE = ColumnConfig("Phone", "Phone", 4, "STRING")


@pytest.mark.parametrize(
    "environment_enabled,entity_required,expected",
    [(True, True, True), (False, True, False), (True, False, False)],
)
def test_environment_and_entity_both_gate_anonymisation(environment_enabled, entity_required, expected):
    entity = make_entity(anonymisation_required=entity_required)
    assert ae.should_anonymise(entity, environment_enabled) is expected


def test_plan_targets_only_metadata_columns_and_resolves_each_salt_once(customer):
    resolved = []

    def resolver(name):
        resolved.append(name)
        return "s3cr3t"

    plan = ae.plan_expressions(customer, RULES, resolver)
    assert set(plan) == {"Email", "Phone"}            # never hard-coded column names
    assert resolved == ["bronze-anonymisation-salt"]  # only the HASH rule needs a salt


def test_hash_email_rule_is_salted_and_format_preserving():
    expression = ae.build_rule_expression(EMAIL, RULES[1], salt="s3cr3t")
    assert expression.startswith("CASE WHEN `Email` IS NULL THEN NULL ELSE")   # NULL stays NULL
    assert "sha2(concat('s3cr3t', CAST(`Email` AS STRING)), 256)" in expression
    assert "'@', 'example.invalid'" in expression and "substr(" in expression


def test_mask_keeps_last_characters():
    expression = ae.build_rule_expression(PHONE, RULES[2])
    assert "repeat('*', greatest(length(CAST(`Phone` AS STRING)) - 4, 0))" in expression
    assert "right(CAST(`Phone` AS STRING), 4)" in expression


@pytest.mark.parametrize(
    "rule,fragment",
    [
        (AnonymisationRule(3, "R", "REDACT", None, {"replacement": "GONE"}), "'GONE'"),
        (AnonymisationRule(4, "T", "TOKENIZE", "SHA2_256", {"prefix": "TKN_", "length": 12}), "concat('TKN_', substr("),
        (AnonymisationRule(5, "C", "CUSTOM", None, {"expression": "upper(substr({col}, 1, 1))"}),
         "upper(substr(`Email`, 1, 1))"),
    ],
)
def test_other_rule_types(rule, fragment):
    assert fragment in ae.build_rule_expression(EMAIL, rule, salt="s")


def test_nullify_is_typed():
    rule = AnonymisationRule(6, "N", "NULLIFY")
    assert ae.build_rule_expression(ColumnConfig("Dob", "Dob", 1, "DATE"), rule) == "CAST(NULL AS DATE)"


def test_salt_literal_is_escaped():
    expression = ae.build_rule_expression(EMAIL, AnonymisationRule(1, "H", "HASH", "SHA2_256"), salt="a'b")
    assert "'a\\'b'" in expression


def test_invalid_rules_are_metadata_errors(customer):
    with pytest.raises(MetadataError):
        ae.build_rule_expression(EMAIL, AnonymisationRule(9, "C", "CUSTOM", None, {"expression": "upper(x)"}))
    with pytest.raises(MetadataError):
        ae.build_rule_expression(EMAIL, AnonymisationRule(9, "X", "SCRAMBLE"))
    with pytest.raises(MetadataError):   # salt needed but no Key Vault resolver configured
        ae.plan_expressions(customer, RULES, secret_resolver=None)
    with pytest.raises(MetadataError):   # dangling rule id
        ae.columns_to_anonymise(customer, {1: RULES[1]})


def test_engine_is_a_no_op_when_not_required(customer):
    engine = ae.AnonymisationEngine(RULES, lambda name: "salt")
    df = object()
    assert engine.apply(df, customer, anonymisation_enabled=False) == (df, [])


def test_key_vault_resolver_uses_notebookutils():
    class Credentials:
        def getSecret(self, vault, name):
            return f"{vault}|{name}"

    class NBU:
        credentials = Credentials()

    resolve = ae.key_vault_secret_resolver("https://kv.vault.azure.net/", NBU)
    assert resolve("bronze-anonymisation-salt") == "https://kv.vault.azure.net/|bronze-anonymisation-salt"
