# Fabric notebook source

# METADATA ********************

# META {
# META   "kernel_info": {
# META     "name": "synapse_pyspark"
# META   },
# META   "dependencies": {}
# META }

# MARKDOWN ********************

# # BronzeFramework
#
# Thin wrapper around the tested `notebooks.bronze` package (installed from the
# `CicdFramework.Environment` custom library). All processing logic lives in the
# package; this notebook only binds parameters and reports the result.
#
# **Attach before first run:** the Bronze Lakehouse as the default Lakehouse
# (staging/Bronze tables are addressed as `schema.table`), and the
# `CicdFramework` Environment. Lakehouse/Environment ids are intentionally not
# hard-coded in this file.
#
# Invoked by the `BronzeOrchestrator` pipeline (`mode = PIPELINE`), or by hand
# with `mode = REPLAY` to reprocess landing files without reconnecting to the source.

# PARAMETERS CELL ********************

environment = "DEV"
warehouse_connection_string = ""   # Warehouse SQL endpoint -- pipeline parameter / Variable Library, never hard-coded
audit_connection_string = ""       # central audit SQL Database -- pipeline parameter / Variable Library
key_vault_uri = ""                 # Key Vault holding anonymisation salts (secret NAMES are in control metadata)
run_id = ""                        # set by the pipeline; empty = new run (REPLAY / manual)
run_timestamp = ""                 # yyyyMMddHHmmss, set by the pipeline
pipeline_name = ""
pipeline_run_id = ""
trigger_type = "MANUAL"
entity_group = ""
entity_ids = ""                    # optional comma-separated filter, e.g. "101,103"
mode = "PIPELINE"                  # PIPELINE | REPLAY
replay_run_timestamp = ""          # REPLAY: landing files of this run timestamp; empty = latest per entity

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

import json
import logging

from notebooks.bronze.bootstrap import build_framework

logging.basicConfig(level=logging.INFO)

framework = build_framework(
    spark,
    environment=environment,
    warehouse_connection_string=warehouse_connection_string,
    audit_connection_string=audit_connection_string,
    run_id=run_id or None,
    run_timestamp=run_timestamp or None,
    key_vault_uri=key_vault_uri or None,
    pipeline_name=pipeline_name or None,
    pipeline_run_id=pipeline_run_id or None,
    trigger_type=trigger_type or "MANUAL",
    entity_group=entity_group or None,
    entity_ids=[int(i) for i in entity_ids.split(",") if i.strip()] or None,
)

if mode.upper() == "REPLAY":
    summary = framework.replay(landing_run_timestamp=replay_run_timestamp or None)
else:
    summary = framework.run_pipeline_mode()

result = summary.to_dict()
print(json.dumps({k: v for k, v in result.items() if k != "entities"}, indent=2))

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# Fail the notebook (and so the pipeline activity) unless every entity
# succeeded -- the audit run has already been completed with the precise
# status; this only makes failures visible in pipeline monitoring.
if result["status"] != "SUCCEEDED":
    raise RuntimeError(
        f"Bronze run {result['run_id']} finished {result['status']}: "
        f"{result['succeeded']} succeeded, {result['failed']} failed, {result['cancelled']} cancelled. "
        "See audit.vw_entity_status / audit.vw_recent_errors."
    )

notebookutils.notebook.exit(json.dumps({k: v for k, v in result.items() if k != "entities"}))

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }
