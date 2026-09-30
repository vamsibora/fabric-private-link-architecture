# AI-agent build prompts — Bronze ingestion framework

These prompts let an AI agent build the metadata-driven Bronze framework from
scratch in this repo, following the phase order in
`docs/Fabric_Metadata_Driven_Bronze_Ingestion_Framework.md` §66.

## How to use

1. Start every session by pasting `00_master_context.md`. It holds the
   principles, confirmed decisions, repo conventions and the risks that must
   be verified live.
2. Run `01` … `21` in order, one prompt per session or per step. Each prompt
   depends on the contracts the earlier ones created.
3. Where this repo already contains the implementation, the prompt names it
   as the **reference**. The agent should extend or verify it rather than
   write a competing version.

## What "done" means for a prompt

- Every file the prompt lists exists, and no file outside its allowed paths
  was changed.
- `pytest -q` passes: all mocked, no Fabric connection needed.
- Where the prompt asks for Spark tests, `pytest -m spark` passes on a machine
  with Java and pyspark/delta-spark. Without them the tests skip, and the
  agent says so.
- The agent ends with a **"Not verified live"** list: every behaviour that
  depends on a real Fabric workspace, SQL endpoint, gateway or Storage
  Account and was not exercised.

## File → spec mapping

| File | Spec section(s) | Phase (§66) |
|---|---|---|
| 00_master_context.md | §1–§44, §68 | all |
| 01_architecture.md | §45 | 1 |
| 02_control_metadata.md | §20–§27, §46 | 2 |
| 03_central_audit_db.md | §28–§35, §47 | 3 |
| 04_bronze_lakehouse_schema.md | §10–§11, §41 | 4 |
| 05_config_loader.md | §14, §40, §42 | 5 |
| 06_landing_manager.md | §5–§7, §48 | 6 |
| 07_staging_manager.md | §8–§9, §49 | 7 |
| 08_validation_engine.md | §26, §50 | 8 |
| 09_anonymisation_engine.md | §19, §25, §51 | 9 |
| 10_hash_engine.md | §52 | 10 |
| 11_merge_history_engine.md | §16–§18, §53 | 11 |
| 12_watermark_manager.md | §15, §24, §54 | 12 |
| 13_audit_manager.md | §38, §55 | 13 |
| 14_orchestrator.md | §13, §37, §39, §56 | 14 |
| 15_fabric_pipelines.md | §4, §57 | 15 |
| 16_sample_entity.md | §58 | 16 |
| 17_testing_framework.md | §59 | 16 |
| 18_security_review.md | §60 | 17 |
| 19_performance_review.md | §61 | 18 |
| 20_monitoring_documentation.md | §62, §63 | 19 |
| 21_deployment_final_acceptance.md | §64, §65 | 20 |
