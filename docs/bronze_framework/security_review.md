# Security Review — Bronze Framework (spec §60)

Scope: the repo design and code as written. This is a desk review. **No live
tenant configuration has been inspected**, so every "required configuration"
item is to be implemented and verified per environment.

## Findings

| # | Area | Finding | Risk | Remediation |
|---|---|---|---|---|
| S1 | Secrets | No credentials are in code, metadata, pipeline JSON or audit. Source auth sits in Fabric connections/gateway; salts are referenced by Key Vault secret **name**; connection strings are empty-default parameters. `tests/fabric_items` fails on non-placeholder GUIDs. | Low | Keep it enforced in PR review. Connection strings are endpoints, not secrets, but should still be bound by deployment rules / Variable Library, never committed. |
| S2 | Anonymisation salt exposure | The salt is embedded in Spark SQL expressions, so it can appear in query plans / the Spark UI for the session. | Medium (lower envs) | Restrict notebook/Spark UI access in DEV/UAT to the engineering group. Use distinct salts per environment. Rotate the salt only with a planned Bronze rebuild (rotation changes every token and hash). |
| S3 | Audit sanitisation | Messages/traces pass through `sanitise_message` (e-mail, 7+ digit numbers, quoted literals). Validation rows hold counts only. It is pattern-based, not a guarantee. | Medium | Review `audit.error` samples after the first live runs. Extend the patterns if source-specific identifiers leak. Restrict read access to `audit.error.stack_trace`. |
| S4 | Cross-workspace audit access | Notebooks and pipelines in every engineering workspace connect to one SQL Database in another workspace. With **outbound access protection** / private-link-restricted workspaces, cross-workspace SQL connections can be blocked. | High (availability) | Verify in Dev. Configure managed private endpoints / an allowed-destinations list for the audit database. Otherwise audit is fail-fast at run start (`AuditConnectionError`), so runs stop rather than run unaudited. |
| S5 | Audit DB permissions | Writers need only EXECUTE on `audit.usp_*`. The code never issues ad-hoc DML against audit tables. | Low if granted narrowly | Grant `EXECUTE ON SCHEMA::audit` to the workspace identity / notebook run-as identity. Do not grant `db_owner` to runtime identities. Readers (operations) get `SELECT` on `audit.vw_*`. |
| S6 | Warehouse permissions | The runtime needs `SELECT` on `control.*` and `UPDATE`/`INSERT` on `control.watermark` only. The migration identity needs DDL. | Medium | Split identities: CI/migration (DDL on `control`/`SECURITY`) vs runtime (read control, write watermark). |
| S7 | Storage account | Landing holds raw, **un-anonymised** source data in every environment (anonymisation happens at Bronze). | High | ADLS Gen2 with the public network disabled and a private endpoint. Access via workspace identity / trusted workspace access, not account keys or SAS. RBAC: `Storage Blob Data Contributor` for the Copy connection identity on the `landing` container only; `Reader` for the shortcut identity. Lifecycle policy for retention. For lower environments, only enable landing where needed (`landing_enabled`). |
| S8 | Lakehouse | Staging and landing shortcuts contain raw data; Bronze in DEV/UAT is anonymised. | Medium | Limit Lakehouse access to the engineering workspace roles. Do not share the Bronze Lakehouse with the reporting workspace. Downstream layers read through Silver/Gold. |
| S9 | Workspace roles | The CI SPN is Member on engineering workspaces (`service_principal_requirements.md`). | Medium | Separate SPNs per environment before PROD go-live (hardening path). Human access to PROD is Viewer, except break-glass. |
| S10 | Gateway | The on-premises gateway carries source credentials. | Medium | Gateway cluster on hardened hosts. Connection credentials held in the gateway, with least-privilege read-only SQL logins / gMSA on source databases. Restrict who can use the connection. |
| S11 | Environment separation | Anonymisation is environment-driven (`anonymisation_enabled`). A mis-set PROD→DEV copy would move real data. | High | Keep `framework_configuration` rows per environment in git. Never point DEV connections at PROD sources. Review `source_connection` changes like code. |
| S12 | Metadata as code | `CUSTOM` validation expressions and `column_mapping` / `CUSTOM` anonymisation expressions execute as Spark SQL. `source_query_override` executes on the source. | Medium | Treat `warehouse/metadata/` as code: PR review required. Restrict Warehouse write access on `control` to the migration identity. |
| S13 | Reporting separation | The reporting workspace consumes Gold only. | Low | No direct access from reporting identities to the engineering workspace, landing storage or the audit database. RLS (`SECURITY.fn_SecurityPredicate`) applies to Gold fact tables once bound. |
| S14 | Audit tampering | Audit is writable through procedures by every runtime identity. | Low | Operations read via views only. Consider periodic export of audit to immutable storage for regulatory needs. |

## Required configuration (per environment)

1. **Engineering workspace:** private; roles per S9. If outbound access
   protection is enabled, configure managed private endpoints to the
   audit SQL Database, ADLS and Key Vault.
2. **Warehouse:** `CREATE USER [<runtime identity>] FROM EXTERNAL PROVIDER;`
   grant `SELECT ON SCHEMA::control`, `UPDATE, INSERT ON control.watermark`.
   The migration identity: DDL on `control`/`SECURITY` (see
   `service_principal_requirements.md`).
3. **Audit SQL Database:** `CREATE USER` for the runtime identity of each
   engineering workspace plus the migration identity. Runtime:
   `GRANT EXECUTE ON SCHEMA::audit`. Migration: DDL on `audit`. Operators:
   `SELECT` on the views.
4. **ADLS:** public access off, private endpoint, RBAC per S7, no shared keys
   (`allowSharedKeyAccess = false` where supported by the Fabric connection
   type), lifecycle policy.
5. **Key Vault:** secret `bronze-anonymisation-salt`, a distinct value per
   environment; `Key Vault Secrets User` for the notebook identity only.
6. **Gateway / connections:** read-only source logins; restrict connection
   users.
7. **Fabric connections** (`fabric_items/README.md` placeholders): owned by a
   platform group; shared only with the pipeline identities.

## Credentials must not be placed in

notebooks · metadata tables · pipeline parameters · source code · audit
tables. Current status: none found in the repo. Enforce through review and
the placeholder test.
