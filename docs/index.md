# Documentation

## Specification

- [Fabric_Metadata_Driven_Bronze_Ingestion_Framework.md](Fabric_Metadata_Driven_Bronze_Ingestion_Framework.md): the target spec (architecture, metadata, audit, agent prompts)

## Runbooks (step-by-step)

| Runbook | Use it to |
|---|---|
| [runbooks/01_platform_setup](runbooks/01_platform_setup.md) | Create every Fabric/Azure artifact for an environment, through to the first successful run |
| [runbooks/02_metadata_maintenance](runbooks/02_metadata_maintenance.md) | Add or change source systems, entities, columns, rules and configuration; change-impact table; retire or rebuild an entity |
| [runbooks/03_operations_procedures](runbooks/03_operations_procedures.md) | Run, replay, re-run, reset or backfill watermarks, rotate the salt, recover from an audit outage |
| [runbooks/04_framework_changes](runbooks/04_framework_changes.md) | Change DDL, procs and views, add a source type, release framework code |

Supporting files: `warehouse/metadata/templates/1xx_entity_template.sql.template` (new-entity
template) and `warehouse/checks/metadata_health_checks.sql` (read-only post-deploy checks).

## Bronze framework

| Doc | Topic |
|---|---|
| [01_Architecture](bronze_framework/01_Architecture.md) | Overall design, decisions, "verify live before production" risks |
| [02_Metadata_Model](bronze_framework/02_Metadata_Model.md) | `control` schema tables and columns, `fn_active_entities`, id ranges |
| [03_Bronze_Framework](bronze_framework/03_Bronze_Framework.md) | `notebooks.bronze` processing chain, write strategies, technical columns |
| [04_Landing_Design](bronze_framework/04_Landing_Design.md) | Optional landing layer, staging, replay |
| [05_Audit_Design](bronze_framework/05_Audit_Design.md) | Central audit SQL Database: tables, procs, views |
| [06_Incremental_Loading](bronze_framework/06_Incremental_Loading.md) | Watermarks and hash change detection |
| [07_Historical_Loading](bronze_framework/07_Historical_Loading.md) | Source-history Bronze |
| [08_Anonymisation](bronze_framework/08_Anonymisation.md) | Environment-based anonymisation |
| [09_Validation](bronze_framework/09_Validation.md) | Validation rules and actions |
| [10_Error_Handling](bronze_framework/10_Error_Handling.md) | Failure flow, classification, retry |
| [11_Deployment](bronze_framework/11_Deployment.md) | DEV/UAT/PROD deployment, smoke tests, rollback |
| [12_Operations](bronze_framework/12_Operations.md) | Daily checks, replay, re-run, watermark reset |
| [13_Troubleshooting](bronze_framework/13_Troubleshooting.md) | Symptom → cause → fix |
| [14_Testing](bronze_framework/14_Testing.md) | Test layers and spec §59 scenario coverage |
| [test_results](bronze_framework/test_results.md) | Latest test run: what passed, what was skipped, what is unproven |
| [security_review](bronze_framework/security_review.md) | Security findings and required configuration |
| [performance_review](bronze_framework/performance_review.md) | Bottlenecks, limits, defaults |

## Platform and CI/CD

- [control_framework.md](control_framework.md): control vs audit planes, key strategy, audit boundaries, RLS
- [cicd_pipeline.md](cicd_pipeline.md): Fabric-native hybrid CI/CD design
- [runbook.md](runbook.md): CI/CD commands and troubleshooting
- [service_principal_requirements.md](service_principal_requirements.md): SPN setup for a Fabric/Entra admin
- [../fabric_items/README.md](../fabric_items/README.md): Fabric items and placeholders to bind
- [../warehouse/metadata/README.md](../warehouse/metadata/README.md): metadata script rules and id ranges

## AI-agent build prompts

- [agent_prompts/README.md](agent_prompts/README.md): per-phase prompts for building the framework from scratch

## Session context

- [context_prompt.md](context_prompt.md): paste at the start of a working session
