# 08 — Anonymisation

Anonymisation happens as data enters Bronze, **before** the hash and the
Bronze write (`anonymisation_engine.py`). It applies only when both of these
are true:
- `framework_configuration.anonymisation_enabled` for the environment (DEV and
  UAT `true`, PROD `false`)
- `entity.anonymisation_required = 1`.

Which columns are anonymised comes only from `control.entity_column`
(`anonymisation_flag = 1`, `anonymisation_rule_id`). No column is named in
code.

## Rules (`control.anonymisation_rule`)

| rule_type | Behaviour | parameters |
|---|---|---|
| HASH | `sha2(salt ‖ value, 256)`. With `algorithm = EMAIL`: `<first N hex>@<domain>` | `{"domain": "example.invalid", "length": 16}` |
| MASK | Keep the last N characters, mask the rest | `{"keep_last": 4, "mask_char": "*"}` |
| REDACT | Constant | `{"replacement": "REDACTED"}` |
| TOKENIZE | `<prefix><first N hex of sha2(salt ‖ value)>` | `{"prefix": "TKN_", "length": 12}` |
| NULLIFY | Typed NULL | — |
| CUSTOM | Spark SQL with `{col}` placeholder | `{"expression": "upper(substr({col},1,1))"}` |

For every rule, NULL input stays NULL, and the result is cast back to the
column's `target_data_type`.

Seeded: `HASH_EMAIL` (Customer.Email) and `MASK_PHONE` (Customer.Phone), plus
`HASH_SHA256`, `REDACT_TEXT` and `TOKEN_NAME` available for reuse.

## Determinism and salts

- All rules are deterministic within an environment, so hash-based change
  detection and MERGE keep working on anonymised data.
- Salts come from Key Vault by **secret name** (`salt_secret_name`) through
  `key_vault_secret_resolver(key_vault_uri)`, which calls
  `notebookutils.credentials.getSecret`. The vault URI is a notebook/pipeline
  parameter. Each distinct secret is resolved once per run.
- If a rule needs a salt and no resolver is configured, the framework raises
  `MetadataError`. `build_framework` refuses to start when anonymisation is
  enabled without `key_vault_uri`.
- Different environments should use different salt values (same secret name,
  different vault), so lower-environment tokens cannot be joined to another
  environment's.

## What is recorded

`audit.activity ANONYMISATION_COMPLETED` lists **column names** only (or
`SKIPPED` / "not required"). Salts, source values and anonymised values are
never logged or audited.

Caveat: the salt is embedded in the Spark SQL expression, so it can appear in
Spark query plans and the Spark UI for that session. Restrict notebook and
Spark UI access in lower environments (see
[security_review.md](security_review.md)).
