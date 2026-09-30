# warehouse/metadata

Seed and reference metadata for the `control` schema. This folder is a
**repeatable** migration root: `migration_runner` (target `WAREHOUSE`) re-applies
a script whenever its checksum changes, after all CREATE-once DDL has run.

Rules for scripts in this folder:

- **Idempotent.** Each script deletes then re-inserts the ids it owns, inside
  one transaction. Re-running a script leaves the same state.
- **Scoped deletes.** Only delete the explicit ids the script inserts. Never
  `DELETE` a whole table, because rows added through other scripts must survive.
- **Never reset runtime state.** `control.watermark` rows are
  `INSERT … WHERE NOT EXISTS` only. An existing watermark is never overwritten
  by a metadata deploy.
- **No secrets and no environment endpoints.** Connection strings, Key Vault
  URIs and workspace ids come from notebook/pipeline parameters (Variable
  Library or deployment rules), not from these scripts. Key Vault secret
  *names* are fine.
- **Id ranges** (explicit BIGINTs keep ids identical across DEV, UAT and PROD):

  | Table | Range |
  |---|---|
  | source_system | 1–99 |
  | source_connection | `<source_system_id>*10 + env` (DEV=1, UAT=2, PROD=3) |
  | entity | 100–9999 |
  | entity_column | `<entity_id>*100 + ordinal` |
  | load_configuration | = entity_id |
  | anonymisation_rule | 1–999 |
  | validation_rule | `<entity_id>*10 + n` |
  | column_mapping | `<entity_id>*100 + n` |
  | framework_configuration | DEV 1000s, UAT 2000s, PROD 3000s |
  | pipeline_configuration | DEV 1000s, UAT 2000s, PROD 3000s |

Adding a new source table means adding a new numbered script here, with
entity, column, load configuration, validation and watermark rows. No new
pipeline or notebook is needed.
