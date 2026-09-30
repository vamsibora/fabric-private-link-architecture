# RB-02 — Maintaining the Bronze framework metadata

All framework behaviour comes from the Warehouse `control` schema. This
runbook covers how to change it safely. Table and column definitions are in
[02_Metadata_Model.md](../bronze_framework/02_Metadata_Model.md).

## How metadata is managed

- **Metadata is code.** Every row in `control.*` is written by a script in
  `warehouse/metadata/` and deployed by the `SchemaMigration` pipeline. The
  only exceptions are the environment-owned values in § *Environment
  connection values*.
  - Do not edit `control` tables by hand in the Warehouse. The next deploy of
    that script silently reverts the edit.
  - Unlike DDL, metadata scripts **are** meant to be edited in place. They are
    *repeatable*: the runner re-applies a script whenever its checksum
    changes.
- **Each script owns explicit ids.** It deletes and re-inserts those ids in
  one transaction. Follow the id ranges in `warehouse/metadata/README.md`.
  Never reuse an id, including a retired one: audit history references
  `entity_id`.
- **Runtime and environment-owned rows are insert-only.**
  `control.watermark` and `control.source_connection` are inserted only when
  missing, and never updated or deleted by a script.
  `tests/bronze/test_sql_contracts.py` enforces this.
- **Environment differences live in rows keyed by `environment`.** They are
  never branches in code. The Python never contains an entity name.

## The standard change procedure

Use this for every metadata change. The sections below say what to put in
the script and what extra steps a change needs.

1. **Branch.** `git switch -c metadata/<ticket>-<short-name>`.
2. **Edit or add the script** in `warehouse/metadata/`. Keep one entity per
   script, named `<entity_id>_entity_<source>_<table>.sql`.
3. **Local checks.**
   ```bash
   pytest -q tests/bronze/test_sql_contracts.py
   pytest -q
   ```
   The contract tests catch:
   - Fabric DW T-SQL violations (NVARCHAR, DEFAULT, IDENTITY, GO, …)
   - watermark or `source_connection` resets
   - missing watermark rows
   - duplicate entity ids.
4. **Pull request.** In the description, state the **impact class** from the
   change-impact table below.
5. **Deploy to DEV.** Merging to `main` makes CI run `SchemaMigration`, which
   re-applies only the scripts whose checksum changed. To run it by hand, use
   `fabric_run_item_job.py` (see `docs/runbook.md`).
6. **Validate in DEV.**
   1. Run `warehouse/checks/metadata_health_checks.sql` in the Warehouse SQL
      editor. Every check must return no rows.
   2. Query 16 shows the resolved `source_query` for each entity. Read it for
      the entity you changed.
   3. If tables or columns changed, run `MetadataInitialisation` (or let the
      next run add columns; see the change-impact table).
   4. Run the entity: `BronzeOrchestrator` with its `entity_group`. Then
      check `audit.vw_entity_status` and `audit.vw_validation_failures`.
7. **Promote.** Approve `promote-uat`, repeat step 6 in UAT, then `promote-prod`
   with explicit approval.

## Change-impact table

"Next run" means the change takes effect on the entity's next run with no
other action. "Rebuild" means the Bronze table must be rebuilt: see
§ *Rebuild an entity*.

| Change | Impact class | What happens / what to do |
|---|---|---|
| Add a validation rule; change `severity`, `failure_action` or `expression` | Next run | Safe. A new FAIL rule can start failing loads; consider deploying it as `WARN` first. |
| Change `entity_group` or `processing_priority` | Next run | Safe. Affects scheduling only. |
| Change `load_configuration` retry settings or `row_count_anomaly_threshold_pct` | Next run | Safe. |
| Toggle `landing_enabled` | Next run | Safe between runs. Both paths overwrite staging, and the watermark is unaffected. Replay is only possible for runs that landed a file. |
| Change `source_filter` / `source_query_override` | Next run | The filter narrows what is extracted; rows already in Bronze stay. Check query 16. |
| **Add a column** | Next run + re-version | Bronze gets the column automatically (`ensure_bronze_table` runs before every write; the copy recreates staging). Existing rows hold NULL until the key is next loaded. If `hash_flag = 1`, every record's hash changes when it is next loaded: MERGE updates each key once, and HISTORY writes one new version per key. Expected, but tell downstream consumers. |
| **Deactivate a column** (`active_flag = 0`) | Next run + re-version | The column is no longer extracted. The Bronze column is **not** dropped: MERGE keeps its last value, and new rows get NULL. The hash changes (see above). To physically drop the column, use RB-04. |
| Rename a column (`target_column`) | Rebuild, or treat as add + deactivate | The Bronze column name is part of the table. Prefer adding the new name and deactivating the old one. |
| **Change `target_data_type`** | Rebuild | Delta keeps the original column type, and the framework never retypes. Changing it without a rebuild makes writes fail, or silently narrow the data. |
| **Change `primary_key`** | Rebuild | MERGE and HISTORY matching changes meaning; existing rows would be orphaned or duplicated. |
| **Change the write strategy** (`history_required`, `merge_required`, or `load_type` in a way that changes MERGE/HISTORY/APPEND/REPLACE) | Rebuild | For example, MERGE → HISTORY adds the history columns, but existing rows have `bronze_is_current = NULL` and are invisible to the history engine, so every key is inserted again. APPEND → REPLACE overwrites the table on the next run. |
| Change `watermark_column` / `watermark_type` | Watermark reset | The stored watermark is in the old column's format. Reset it (RB-03 § *Reset a watermark*) in the same change. |
| Change `target_schema` / `target_table` | New table | A new Bronze table is created; the old one remains. Downstream must switch. Treat it as a new entity plus retiring the old one. |
| Change an anonymisation rule, or rotate the salt | Re-version (DEV/UAT) | Every anonymised value changes, so every hash changes (see *Add a column*). PROD is unaffected when `anonymisation_enabled = false` there. See RB-03 § *Rotate the salt*. |
| Change `framework_configuration` | Next run | Takes effect for runs that start after the deploy. `anonymisation_enabled = false` must only ever be set for PROD. |

## Add an entity (a new source table)

1. **Pick the next free `entity_id`.** Search `warehouse/metadata/` and
   `SELECT MAX(entity_id) FROM control.entity` in every environment.
2. **Copy the template:**
   `warehouse/metadata/templates/1xx_entity_template.sql.template` →
   `warehouse/metadata/<id>_entity_<source>_<table>.sql`. Replace every
   `<…>` placeholder.
3. **Decide the behaviour:**

   | Question | Set |
   |---|---|
   | Only the latest state is needed | `merge_required = 1`, `history_required = 0` |
   | Source history must be preserved | `history_required = 1` (needs `change_detection_method = 'HASH'` and a primary key) |
   | Source has a reliable modified column | `load_type = 'INCREMENTAL'`, `watermark_column`, `watermark_type` |
   | No reliable change column, small table | `load_type = 'FULL'`; add `delete_detection_enabled = 1` if deletions must be reflected (soft delete) |
   | Raw archive / replay / regulatory retention needed | `landing_enabled = 1` |
   | Contains personal data | `anonymisation_required = 1`, and on each sensitive column `anonymisation_flag = 1` plus a rule id |

4. **Columns.** Add one `entity_column` row per source column you want:
   - The `target_data_type` must be a Spark SQL type.
   - Key columns: `primary_key_flag = 1`, `hash_flag = 0`.
   - Watermark column: `watermark_flag = 1`, `hash_flag = 0`.
   - Business columns: `hash_flag = 1`.
   - Keep `target_column` equal to the source name unless there is a reason
     not to. Bronze keeps source names recognisable.
5. **Landing-enabled entities only.** Landing JSON is read as STRING and cast
   to `target_data_type`. Add a `column_mapping` row only when a plain CAST is
   not enough, for example a non-ISO date format.
6. **Validation.** Built-ins are automatic: PK null, duplicate PK, missing
   column, and type mismatch. Add business rules as needed.
7. **Keep the watermark `INSERT … WHERE NOT EXISTS` block** from the template.
8. **Follow the standard change procedure.** Then run `MetadataInitialisation`
   for the new `entity_ids`, and run the entity's `entity_group`.

No pipeline, notebook or Python change is needed, as long as the source type
already has an extract pipeline (`SQLSERVER` today). See RB-04 for a new
source type.

## Add a source system

- **Same kind of source, same server, another database.** Add a
  `source_system` row in `010_source_system.sql` (next id, unique
  `source_system_name` and `bronze_schema`), plus its three
  `source_connection` rows (`WHERE NOT EXISTS`) with the `database_name`.
  `fn_active_entities` passes `source_database` to the copy.
- **Same kind of source, different server.**
  1. Create a Fabric connection to the new server, in every environment
     (RB-01 step 6a).
  2. Add a `source_system` row and its three `source_connection` rows,
     exactly as above.
  3. Set each environment's `fabric_connection_id` (§ *Environment connection
     values*).

  No pipeline change is needed. The extract pipeline's Copy source connection
  is **parameterised**: `control.fn_active_entities` returns the entity's
  `source_connection_id`, and the Copy binds to it at run time.
- **New kind of source** (Oracle, REST, ServiceNow, …): RB-04 § *Add a
  source type*.

`source_system_name` appears in landing paths
(`landing/<source_system_name>/<table>/...`). Choose it once, and never rename
it: renaming breaks replay of existing files.

## Environment connection values

`control.source_connection` rows are created by the seed with NULL
`fabric_connection_id` and `gateway_name`. An operator sets the
environment-specific values once per environment. The seed never
overwrites them.

**`fabric_connection_id` is required.** The extract pipeline binds its Copy
source to this connection GUID. Until it is set, every entity of that
source system fails fast in that environment with
`SOURCE_CONNECTION_NOT_CONFIGURED` (in `audit.error`), and health check 15
lists the missing rows.

To find the GUID, go to Settings → Manage connections and gateways, then the
connection's ⋯ → Settings, and copy the **Connection ID**. Use the id, not the
connection name: name-based parameterisation is reported not to work for
gateway connections.

The pipeline identity must have access to the connection. Share it with the
identity; nothing in metadata grants access. Because a `control` writer can
point extraction at any connection that identity can use, restrict write
access to `control` to the deployment identity and the platform team.

```sql
-- Warehouse of the target environment; record the change in the ticket.
UPDATE control.source_connection
SET fabric_connection_id = '<Fabric connection id>',   -- USED: the extract Copy binds its source connection to this GUID
    gateway_name         = '<gateway name>',
    database_name        = '<source database>',        -- USED: passed to the copy as source_database
    updated_datetime     = SYSUTCDATETIME(),
    updated_by           = '<your UPN>'
WHERE source_connection_id = <id> AND environment = '<ENV>';
```

- To change a *default* for future environments, edit the `VALUES` in
  `010_source_system.sql`. That only affects rows that do not exist yet.
- **Never** store credentials here: only ids, names and Key Vault secret
  *names*.

## Anonymisation rules

- **Add a rule:** a new id in `015_anonymisation_rule.sql`, using a type from
  `08_Anonymisation.md` (HASH / MASK / REDACT / TOKENIZE / NULLIFY / CUSTOM).
  A rule must be **deterministic**, or hash change detection stops working in
  DEV/UAT.
- **Assign a rule to a column:** in the entity script set
  `anonymisation_flag = 1` and `anonymisation_rule_id`, and set
  `entity.anonymisation_required = 1`. Health check 10 flags a mismatch.
- **Salted rules** (HASH, TOKENIZE) name a Key Vault secret in
  `salt_secret_name`. The secret must exist in every environment where
  anonymisation is enabled; otherwise the run fails fast with `MetadataError`.
- **Changing a rule re-versions data** (see the change-impact table).

## Validation rules

| rule_type | Needs | Typical use |
|---|---|---|
| `MANDATORY_COLUMN_NULL` | `column_name` | business-mandatory fields |
| `CUSTOM` | `expression`: Spark SQL predicate every row must satisfy | ranges, formats: `Quantity > 0` |
| `DATA_TYPE_MISMATCH` | `column_name` | a column-specific action on top of the built-in FAIL check |
| `WATERMARK_INVALID` | optional `column_name` | watermark NULL, or older than the stored value |
| `ROW_COUNT_ANOMALY` | `load_configuration.row_count_anomaly_threshold_pct` | FULL loads, or stable feeds |
| `PRIMARY_KEY_NULL` / `DUPLICATE_PRIMARY_KEY` / `COLUMN_MISSING` | none | only to **override** the built-in action for one entity |

- `failure_action`: `FAIL` stops the entity when `fail_on_validation_error`
  is true; `WARN` records and continues; `IGNORE` records as IGNORED.
- `validation_stage`: `PRE` runs on staging; `POST` runs on the Bronze
  table, after the write and before the watermark commit.
- Ids: `<entity_id>*10 + n`. For more than 9 rules, use the next free block
  and note it in the script header.

## Framework and pipeline configuration

- Edit `020_framework_configuration.sql`. Keep **every key present for every
  environment**; health check 13 flags a missing key.
- The known keys and their defaults are documented on
  `notebooks/bronze/models.py` `FrameworkConfig`. An unknown key is ignored,
  so check the spelling.
- `max_parallel_entities` is the real processing concurrency. The pipeline
  ForEach `batchCount` (20) only bounds extraction concurrency.

## Retire an entity

1. In its script, set `active_flag = 0` on the `entity` row. Keep the script
   and its rows: audit history and ids must stay resolvable.
2. Deploy, following the standard procedure. The entity disappears from
   `fn_active_entities` and from the framework.
3. The Bronze table, landing files and audit rows are **kept**. Dropping the
   Bronze table is a separate, approved data change (RB-04).
4. Never delete the script. If you do, the rows stay in the Warehouse, but
   nothing in git describes them any more.

## Rebuild an entity

Use this after a change classed "Rebuild". Rebuilds are hard to reverse, so
agree the approach with the data owner first, and get approval for UAT and
PROD.

1. **Pause** the entity: `active_flag = 0`, then deploy.
2. **Preserve.** Note the current Delta version
   (`DESCRIBE HISTORY <schema>.<table>`) for rollback, and the watermark from
   `audit.vw_watermark_status`.
3. **Drop or rename the Bronze table**, for example
   `ALTER TABLE sqlserver.customer RENAME TO sqlserver.customer_bak_<date>`
   in a notebook.
4. **Apply the metadata change** and set `active_flag = 1` again.
5. **Reset the watermark** (RB-03 § *Reset a watermark*) so the entity
   reloads.
6. **Run `MetadataInitialisation`** for the entity, then run the entity.
   - A FULL load reloads everything from the source.
   - An INCREMENTAL load from a NULL watermark extracts everything the
     source still has. Landing-enabled entities can instead replay retained
     landing files, oldest first (RB-03).
7. **Verify** row counts against the backup, then drop the backup table after
   the agreed retention.

## Validate (after any metadata deploy)

```text
warehouse/checks/metadata_health_checks.sql   every check returns no rows
query 16                                      the entity resolves, and source_query is correct
MetadataInitialisation                        run when tables or columns were added
BronzeOrchestrator (entity_group)             entity SUCCEEDED in audit.vw_entity_status
```

The framework applies the same validation at run time
(`config_loader.validate_entity`), and fails the run with a non-retryable
`MetadataError` that lists every problem. So a bad deploy fails loudly
instead of loading bad data.

## Rollback

Revert the metadata script in git and redeploy. The runner re-applies it,
because the checksum changed, which restores the previous rows.

Watermarks and connection values are not touched by a rollback. Bronze data
written in between stays; use Delta time travel if it must go (RB-03).
