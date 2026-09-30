# 18 — Security review (spec §60)

```text
Context: 00_master_context.md.

Review the whole framework as built (code, SQL, fabric_items, docs) and the target design:
- Workspace roles: private engineering, Audit/Operations, reporting.
- Lakehouse, Warehouse and SQL DB permissions: which identity writes the control watermark,
  which writes audit, and least-privilege roles (e.g. EXECUTE on the audit procs only, no
  direct table DML).
- ADLS landing: RBAC, private endpoint, trusted workspace access for the OneLake shortcut, and
  retention.
- Gateway connectivity; cross-workspace SQL DB access under private link / outbound access
  protection.
- Secrets: grep the repo for connection strings, keys, tokens and real GUIDs in notebooks,
  metadata, pipeline parameters, source and audit. Key Vault secret NAMES only.
- Environment separation (DEV/UAT anonymisation on, PROD off; no PROD data in lower
  environments).
- Sensitive data: sanitise_message coverage; validation and audit rows hold counts only;
  fallback files.
- RLS (security/rls) and reporting workspace separation.

Output docs/bronze_framework/security_review.md with a table:
Finding | Risk (H/M/L) | Evidence (file:line) | Remediation | Required configuration.
Do not change code in this phase; list the changes as remediation items.
Report: what you could NOT verify live.
```
