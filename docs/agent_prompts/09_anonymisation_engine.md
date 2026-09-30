# 09 — Anonymisation Engine (spec §19, §25, §51)

```text
Context: 00_master_context.md. Reference: notebooks/bronze/anonymisation_engine.py.

- Columns come from control.entity_column (anonymisation_flag + anonymisation_rule_id). Rules
  come from control.anonymisation_rule. Never name a specific column in code.
- Applies only when framework_configuration.anonymisation_enabled (DEV/UAT true, PROD false)
  AND entity.anonymisation_required.
- Rule types; all DETERMINISTIC so hash change detection keeps working; NULL stays NULL:
  HASH      sha2(salt || value, 256); algorithm EMAIL -> '<first N hex>@<domain>'
  MASK      keep the last N characters, mask the rest (keep_last, mask_char)
  REDACT    constant replacement
  TOKENIZE  prefix + first N hex of the salted sha2
  NULLIFY   typed NULL
  CUSTOM    a Spark SQL expression with a {col} placeholder
  An unknown type or a bad CUSTOM raises MetadataError.
- Salt comes from Key Vault by secret NAME (salt_secret_name), through an injected resolver
  (notebookutils.credentials.getSecret(key_vault_uri, name)). Each secret is resolved once
  per run. The key_vault_uri is a notebook parameter.
- Apply BEFORE the hash and the Bronze write, and AFTER capturing the batch max watermark.
- Audit ANONYMISATION_COMPLETED with column NAMES only. Never log salts or values.

Tests: tests/bronze/test_anonymisation_engine.py covers the expression per rule type, NULL
preservation, quote escaping in literals, the enable switch, a missing resolver, salt caching,
and an unknown rule.
Spark test: determinism (same input -> same output).
Report: what you could NOT verify live (Key Vault access from the notebook identity).
```
