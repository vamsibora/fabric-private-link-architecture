"""Wires the framework together inside a Fabric notebook.

The BronzeFramework notebook is a thin wrapper around:

    framework = build_framework(spark, environment=..., warehouse_connection_string=...,
                                audit_connection_string=..., run_id=..., ...)
    summary = framework.run_pipeline_mode()      # or framework.replay(...)

Environment-specific values (connection strings, Key Vault URI) arrive as
notebook parameters from the pipeline (Variable Library / deployment rules)
and are never hard-coded here. Behaviour comes from control.* metadata.

Modes
  PIPELINE  the orchestration pipeline already started the run and
            extracted each entity (audit status EXTRACTED); process exactly
            those entities.
  REPLAY    reprocess existing landing files (landing_enabled entities)
            under a NEW run, without reconnecting to the source -- e.g.
            after a Bronze failure. Files are chosen by their run timestamp.
"""

import logging
from dataclasses import dataclass
from typing import List, Optional, Sequence

from notebooks.bronze import orchestrator
from notebooks.bronze.anonymisation_engine import AnonymisationEngine, key_vault_secret_resolver
from notebooks.bronze.audit_manager import AuditManager
from notebooks.bronze.config_loader import load_anonymisation_rules, load_entities, load_framework_config
from notebooks.bronze.dedup_engine import DedupEngine
from notebooks.bronze.error_manager import STAGE_ANONYMISATION, FrameworkError
from notebooks.bronze.hash_engine import HashEngine
from notebooks.bronze.history_engine import HistoryEngine
from notebooks.bronze.landing_manager import LandingManager
from notebooks.bronze.merge_engine import MergeEngine
from notebooks.bronze.models import EntityConfig, FrameworkConfig
from notebooks.bronze.run_manager import RunContext
from notebooks.bronze.schema_manager import SchemaManager
from notebooks.bronze.staging_manager import StagingManager
from notebooks.bronze.validation_engine import ValidationEngine
from notebooks.bronze.watermark_manager import WatermarkManager, batch_max_watermark

logger = logging.getLogger("fabric_medallion.bronze")


@dataclass
class Framework:
    context: RunContext
    config: FrameworkConfig
    entities: List[EntityConfig]
    services: orchestrator.FrameworkServices

    @property
    def audit(self) -> AuditManager:
        return self.services.audit

    def run_pipeline_mode(self) -> orchestrator.RunSummary:
        self.audit.start_run()  # idempotent: reopens the pipeline-created run as RUNNING
        extracted = self.audit.get_run_entities("EXTRACTED")
        items = orchestrator.work_items_from_audit(self.entities, extracted)
        logger.info("run %s: %d extracted entities to process", self.context.run_id, len(items))
        return orchestrator.run(self.context, items, self.services)

    def replay(self, landing_run_timestamp: Optional[str] = None,
               entity_ids: Optional[Sequence[int]] = None) -> orchestrator.RunSummary:
        """Reprocess landing files under this (new) run. landing_run_timestamp
        selects the files of one earlier run; None = each entity's latest file."""
        candidates = [e for e in self.entities if e.landing_enabled
                      and (not entity_ids or e.entity_id in set(entity_ids))]
        self.audit.start_run(total_entities=len(candidates), trigger_type="REPLAY")
        items = []
        for entity in candidates:
            files = self.services.landing.list_replayable(entity, since_run_ts=landing_run_timestamp)
            if landing_run_timestamp:
                files = [f for f in files if f.run_timestamp == landing_run_timestamp]
            if not files:
                logger.warning("no landing file to replay for entity %s", entity.entity_id)
                continue
            chosen = files[-1]
            erid = self.audit.start_entity_run(entity, status="EXTRACTED")
            self.audit.update_entity_run(erid, "EXTRACTED", landing_path=chosen.relative_path)
            items.append(orchestrator.WorkItem(entity, erid, chosen.relative_path, None))
        return orchestrator.run(self.context, items, self.services)


def build_framework(
    spark,
    environment: str,
    warehouse_connection_string: str,
    audit_connection_string: str,
    run_id: Optional[str] = None,
    run_timestamp: Optional[str] = None,
    key_vault_uri: Optional[str] = None,
    pipeline_name: Optional[str] = None,
    pipeline_run_id: Optional[str] = None,
    trigger_type: str = "MANUAL",
    entity_group: Optional[str] = None,
    entity_ids: Optional[Sequence[int]] = None,
    warehouse_token_audience: Optional[str] = None,
) -> Framework:
    from notebooks.framework.fabric_connection import get_connection_notebookutils

    if not warehouse_connection_string or not audit_connection_string:
        raise FrameworkError("warehouse_connection_string and audit_connection_string are required",
                             stage="ORCHESTRATION", error_code="MISSING_PARAMETER")

    def warehouse_connection():
        return get_connection_notebookutils(warehouse_connection_string, warehouse_token_audience)

    conn = warehouse_connection()
    try:
        cursor = conn.cursor()
        config = load_framework_config(cursor, environment)
        rules = load_anonymisation_rules(cursor)
        entities = load_entities(cursor, entity_ids=entity_ids, entity_group=entity_group,
                                 anonymisation_rules=rules)
    finally:
        conn.close()

    # Apply the environment-wide landing switch to every entity once, here.
    if not config.landing_globally_enabled:
        from dataclasses import replace

        entities = [replace(e, landing_enabled=False) for e in entities]

    spark.conf.set("spark.sql.session.timeZone", config.spark_timezone)

    context = RunContext.create(
        environment=environment, run_id=run_id, run_ts=run_timestamp, pipeline_name=pipeline_name,
        pipeline_run_id=pipeline_run_id, trigger_type=trigger_type, entity_group=entity_group,
    ).with_notebook_context()

    audit = AuditManager(
        audit_connection_string, context,
        critical=config.audit_failure_is_critical, enabled=config.audit_enabled,
        connect=lambda cs: get_connection_notebookutils(cs, config.audit_sql_token_audience),
    )
    needs_salt = any(e.anonymisation_required for e in entities) and config.anonymisation_enabled
    if needs_salt and not key_vault_uri:
        raise FrameworkError("anonymisation is enabled but no key_vault_uri parameter was supplied",
                             stage=STAGE_ANONYMISATION, error_code="MISSING_PARAMETER")
    resolver = key_vault_secret_resolver(key_vault_uri) if key_vault_uri else None

    services = orchestrator.FrameworkServices(
        spark=spark,
        config=config,
        audit=audit,
        landing=LandingManager(config.landing_lakehouse_path, config.landing_container),
        staging=StagingManager(spark),
        schema=SchemaManager(spark),
        validation=ValidationEngine(spark),
        dedup=DedupEngine(),
        anonymisation=AnonymisationEngine(rules, resolver),
        hashing=HashEngine(),
        merge=MergeEngine(spark),
        history=HistoryEngine(spark),
        watermarks=WatermarkManager(warehouse_connection),
        batch_max_watermark=batch_max_watermark,
    )
    return Framework(context, config, entities, services)
