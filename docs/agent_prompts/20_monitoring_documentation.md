# 20 — Operational monitoring and documentation (spec §62, §63)

```text
Context: 00_master_context.md. Reference views: sql_database/audit/views/*.

Monitoring: repeatable CREATE OR ALTER views in the audit SQL DB. Map each operator question:
 1 executing runs           -> audit.vw_run_summary (is_executing)
 2/3 failed/succeeded       -> audit.vw_entity_status
 4/5 source/Bronze counts   -> audit.vw_entity_status
 6 not loaded recently      -> audit.vw_watermark_status (is_not_loaded_recently)
 7 latest watermark         -> audit.vw_watermark_status
 8 repeated failures        -> audit.vw_repeated_failures
 9 failing validations      -> audit.vw_validation_failures
10 slow pipelines           -> audit.vw_load_performance
11 extraction problems      -> audit.vw_recent_errors WHERE error_stage = 'EXTRACT'
12 landing files            -> audit.vw_landing_files
13 stale watermarks         -> audit.vw_watermark_status (is_watermark_stale)
Add sample operator queries. Optionally add a Direct Lake / SQL-endpoint report in the
reporting workspace.

Documentation: docs/bronze_framework/
01_Architecture 02_Metadata_Model 03_Bronze_Framework 04_Landing_Design 05_Audit_Design
06_Incremental_Loading 07_Historical_Loading 08_Anonymisation 09_Validation 10_Error_Handling
11_Deployment 12_Operations 13_Troubleshooting 14_Testing
Include diagrams, every metadata field, the processing and error flows, configuration examples,
deployment dependencies, the security model, and operational and recovery procedures (replay,
re-running a failed entity, a stuck RUNNING run, fallback files). Every path, table and proc
cited must exist. Update docs/index.md, docs/runbook.md and docs/context_prompt.md.
Report: what you could NOT verify live.
```
