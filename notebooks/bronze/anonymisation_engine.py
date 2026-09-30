"""Anonymisation Engine: metadata-driven, environment-dependent
anonymisation applied BEFORE the hash and the Bronze write (spec section 51).

Which columns: control.entity_column rows with anonymisation_flag = 1 and
an anonymisation_rule_id. Whether at all: framework_configuration
anonymisation_enabled for the environment (DEV/UAT true, PROD false) AND
entity.anonymisation_required. Nothing here names a specific column.

Every rule is DETERMINISTIC (same input -> same output within an
environment), so hash-based change detection keeps working on anonymised
data. Salts come from Key Vault by secret NAME
(anonymisation_rule.salt_secret_name) through a resolver injected by the
caller (notebookutils.credentials.getSecret in Fabric); they are never
logged or audited. Only column names and counts are ever reported.

Rule types (anonymisation_rule.rule_type):
  HASH      sha2(salt || value, 256); algorithm EMAIL renders
            '<first N hex>@<domain>' so the value still looks like an e-mail
            parameters: {"domain": "example.invalid", "length": 16}
  MASK      keep the last N characters, mask the rest
            parameters: {"keep_last": 4, "mask_char": "*"}
  REDACT    constant replacement   parameters: {"replacement": "REDACTED"}
  TOKENIZE  '<prefix><first N hex of sha2(salt || value)>'
            parameters: {"prefix": "TKN_", "length": 12}
  NULLIFY   NULL (typed to the column)
  CUSTOM    Spark SQL expression with {col} placeholder
            parameters: {"expression": "upper(substr({col}, 1, 1))"}
NULL input stays NULL for every rule type.
"""

from typing import Callable, Dict, List, Mapping, Optional, Tuple

from notebooks.bronze.error_manager import STAGE_ANONYMISATION, MetadataError
from notebooks.bronze.models import AnonymisationRule, ColumnConfig, EntityConfig
from notebooks.bronze.schema_manager import quote

RULE_TYPES = ("HASH", "MASK", "REDACT", "TOKENIZE", "NULLIFY", "CUSTOM")


def _sql_literal(value: str) -> str:
    return "'" + str(value).replace("\\", "\\\\").replace("'", "\\'") + "'"


def _salted_sha(col: str, salt: Optional[str]) -> str:
    salt_part = _sql_literal(salt or "")
    return f"sha2(concat({salt_part}, CAST({col} AS STRING)), 256)"


def build_rule_expression(column: ColumnConfig, rule: AnonymisationRule, salt: Optional[str] = None) -> str:
    """Spark SQL expression implementing `rule` for `column`. Pure; salt is
    passed in already resolved."""
    col = quote(column.target_column)
    params = dict(rule.parameters or {})
    rule_type = rule.rule_type.upper()

    if rule_type == "HASH":
        digest = _salted_sha(col, salt)
        if (rule.algorithm or "").upper() == "EMAIL":
            length = int(params.get("length", 16))
            domain = _sql_literal(params.get("domain", "example.invalid"))
            body = f"concat(substr({digest}, 1, {length}), '@', {domain})"
        else:
            body = digest
    elif rule_type == "MASK":
        keep_last = int(params.get("keep_last", 4))
        mask_char = _sql_literal(str(params.get("mask_char", "*"))[:1] or "*")
        text = f"CAST({col} AS STRING)"
        body = (f"concat(repeat({mask_char}, greatest(length({text}) - {keep_last}, 0)), "
                f"CASE WHEN length({text}) > {keep_last} THEN right({text}, {keep_last}) ELSE '' END)")
        if keep_last == 0:
            body = f"repeat({mask_char}, length({text}))"
    elif rule_type == "REDACT":
        body = _sql_literal(params.get("replacement", "REDACTED"))
    elif rule_type == "TOKENIZE":
        length = int(params.get("length", 12))
        prefix = _sql_literal(params.get("prefix", "TKN_"))
        body = f"concat({prefix}, substr({_salted_sha(col, salt)}, 1, {length}))"
    elif rule_type == "NULLIFY":
        return f"CAST(NULL AS {column.target_data_type})"
    elif rule_type == "CUSTOM":
        expression = params.get("expression")
        if not expression or "{col}" not in str(expression):
            raise MetadataError(
                f"CUSTOM anonymisation rule {rule.rule_name!r} needs parameters.expression containing {{col}}",
                stage=STAGE_ANONYMISATION,
            )
        body = str(expression).replace("{col}", col)
    else:
        raise MetadataError(f"Unknown anonymisation rule_type {rule.rule_type!r} ({rule.rule_name})",
                            stage=STAGE_ANONYMISATION)

    return f"CASE WHEN {col} IS NULL THEN NULL ELSE CAST({body} AS {column.target_data_type}) END"


def columns_to_anonymise(
    entity: EntityConfig, rules: Mapping[int, AnonymisationRule]
) -> List[Tuple[ColumnConfig, AnonymisationRule]]:
    pairs = []
    for column in entity.ordered_columns:
        if column.anonymisation_rule_id is None:
            continue
        rule = rules.get(column.anonymisation_rule_id)
        if rule is None:
            raise MetadataError(
                f"{entity.target_name}.{column.target_column}: anonymisation_rule_id "
                f"{column.anonymisation_rule_id} not found",
                stage=STAGE_ANONYMISATION,
            )
        pairs.append((column, rule))
    return pairs


def should_anonymise(entity: EntityConfig, anonymisation_enabled: bool) -> bool:
    return bool(anonymisation_enabled and entity.anonymisation_required)


def plan_expressions(
    entity: EntityConfig,
    rules: Mapping[int, AnonymisationRule],
    secret_resolver: Optional[Callable[[str], str]] = None,
) -> Dict[str, str]:
    """target_column -> anonymising Spark SQL expression. Each distinct
    salt secret is resolved once."""
    salts: Dict[str, str] = {}
    plan: Dict[str, str] = {}
    for column, rule in columns_to_anonymise(entity, rules):
        salt = None
        if rule.salt_secret_name:
            if secret_resolver is None:
                raise MetadataError(
                    f"rule {rule.rule_name!r} needs salt secret {rule.salt_secret_name!r} but no secret resolver "
                    "is configured",
                    stage=STAGE_ANONYMISATION,
                )
            if rule.salt_secret_name not in salts:
                salts[rule.salt_secret_name] = secret_resolver(rule.salt_secret_name)
            salt = salts[rule.salt_secret_name]
        plan[column.target_column] = build_rule_expression(column, rule, salt)
    return plan


class AnonymisationEngine:
    """Spark adapter. Returns (df, anonymised_column_names)."""

    def __init__(self, rules: Mapping[int, AnonymisationRule],
                 secret_resolver: Optional[Callable[[str], str]] = None):
        self.rules = rules
        self.secret_resolver = secret_resolver

    def apply(self, df, entity: EntityConfig, anonymisation_enabled: bool):
        if not should_anonymise(entity, anonymisation_enabled):
            return df, []
        from pyspark.sql import functions as F

        plan = plan_expressions(entity, self.rules, self.secret_resolver)
        for column, expression in plan.items():
            df = df.withColumn(column, F.expr(expression))
        return df, list(plan)


def key_vault_secret_resolver(key_vault_uri: str, notebookutils_module=None) -> Callable[[str], str]:
    """Resolver backed by notebookutils.credentials.getSecret. The vault URI
    is an environment parameter, never hard-coded."""

    def resolve(secret_name: str) -> str:
        module = notebookutils_module
        if module is None:
            import notebookutils as module  # Fabric-injected runtime module
        return module.credentials.getSecret(key_vault_uri, secret_name)

    return resolve
