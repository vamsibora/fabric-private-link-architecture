# 13 — Troubleshooting

Start with `audit.vw_recent_errors`, filtered by `run_id`/`entity_run_id`.
`error_stage` tells you where the failure happened, and `error_code` holds
the original code.

| Symptom (error_code / stage) | Cause | Fix |
|---|---|---|
| `LANDING_FILE_EXISTS` (LANDING) | A file for this run timestamp already exists, usually from a manual re-trigger with the same TriggerTime or a copied file | Never overwrite. Leave the file, replay it if needed, and re-trigger (a new TriggerTime gives a new timestamp). |
| `STAGING_INTEGRITY` (STAGING) | Staging holds rows from another run, or the count differs from `rowsCopied`. Typically a copy that failed half-way with a non-atomic sink, or a manual write to staging. | Confirm the Copy sink `tableActionOption` is `Overwrite` and `additionalColumns` stamps `_staging_run_id`. Re-run the extract. `StagingManager.truncate()` is the manual reset. |
| `VALIDATION_FAILED` (VALIDATION) | A FAIL-action rule failed | `audit.vw_validation_failures` for the rule and failed_row_count. Fix the source data, or change the rule's `failure_action` through metadata. The watermark was not advanced. |
| `INVALID_METADATA` (METADATA) | `config_loader.validate_entity` found problems. The message lists every entity and problem. | Fix the metadata script and redeploy. One invalid entity stops the metadata load, so deploys should be validated in DEV first. |
| `WATERMARK_CONFLICT` (WATERMARK) | Two runs processed the same entity concurrently | Don't schedule overlapping runs of the same `entity_group`. The first commit wins; re-run the loser. |
| `AUDIT_UNAVAILABLE` (notebook fails at start) | A fail-fast audit call (`start_run`, `start_entity_run`, `get_run_entities`) could not reach the audit database | Check the audit connection string parameter, the cross-workspace connectivity (outbound access protection / private endpoints), and the identity's user in the audit database. Check the `audit_sql_token_audience` value. |
| `AUDIT_WRITE_FAILED` | A fail-soft write failed with `audit_failure_is_critical = true` | As above. Events are also in `Files/_framework_fallback/audit/`. |
| Missing audit rows, no error | Fail-soft writes fell back while `audit_failure_is_critical = false` | Read `Files/_framework_fallback/audit/**/*.json` and the notebook log (`CRITICAL AUDIT fallback logged`). |
| Entity stays `EXTRACTING` | The extract child pipeline died before its failure handlers ran (timeout or cancellation) | Check the pipeline run. The entity is not processed by the notebook (not EXTRACTED). Re-trigger. |
| `UNSUPPORTED_SOURCE_TYPE` (EXTRACT) | `source_system.source_type` has no Switch case | Add a child extract pipeline and Switch case, or fix the metadata |
| `UNRESOLVED_COLUMN` / `DATATYPE_MISMATCH` (Spark) | A source column was renamed/removed, or a `column_mapping` expression is wrong | Non-retryable. Update `entity_column`/`column_mapping`. Schema evolution is additive only. |
| Login failed / token errors on SQL | Wrong token audience, or the identity is not a database user | Try `sql_token_audience`/`audit_sql_token_audience` = `https://database.windows.net/.default` vs `pbi`. `CREATE USER … FROM EXTERNAL PROVIDER` in the target database. |
| Notebook fails on `import notebooks.bronze` | The Environment library is not published or not attached | [runbook.md §6.5](../runbook.md) |
| `ModuleNotFoundError: notebookutils` in local tests | New test file without the stub | [runbook.md §6.1](../runbook.md) |
| Migration `FAILED` in a ledger | T-SQL error in a script | Read `error_message` in `control.`/`audit.schema_migration_history`, fix in a **new** file (CREATE-once) or in place (repeatable), and re-run |
| Checksum drift warning | An applied CREATE-once file was edited | Revert it, or express the change as a new numbered file ([runbook.md §6.6](../runbook.md)) |
