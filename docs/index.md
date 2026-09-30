# Documentation Index

Entry point for the docs in this repo. Keep this file updated whenever a doc is added, removed, or renamed.

| Document | Description |
|---|---|
| [`context_prompt.md`](context_prompt.md) | Session context primer for Phase 1 (CONTROL/SECURITY framework scaffold) — paste at the start of a session in place of reading the raw DDL/Python files. |
| [`control_framework.md`](control_framework.md) | Design rationale for the CONTROL/SECURITY schema framework: ingestion config, pipeline/table run tracing, error/quarantine handling, and Row-Level Security. |
| [`cicd_pipeline.md`](cicd_pipeline.md) | Design and architecture of the Fabric-native CI/CD deployment pipeline (Dev → UAT → Prod), including warehouse schema migration handling. |
| [`runbook.md`](runbook.md) | Operational runbook: commands and failure-mode fixes for running/troubleshooting the CI/CD pipeline. Companion to `cicd_pipeline.md`. |
| [`service_principal_requirements.md`](service_principal_requirements.md) | Standalone deliverable for a Fabric/Entra admin: SPN naming and permissions needed by the CI/CD pipeline. |

## Suggested reading order

1. `context_prompt.md` — orient on what exists and repo conventions.
2. `control_framework.md` — understand the warehouse metadata framework.
3. `cicd_pipeline.md` — understand how changes get deployed.
4. `service_principal_requirements.md` — set up the SPN the pipeline depends on.
5. `runbook.md` — day-to-day commands and troubleshooting.
