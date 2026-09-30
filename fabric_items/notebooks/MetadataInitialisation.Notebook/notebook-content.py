# Fabric notebook source

# METADATA ********************

# META {
# META   "kernel_info": {
# META     "name": "synapse_pyspark"
# META   },
# META   "dependencies": {}
# META }

# MARKDOWN ********************

# # MetadataInitialisation
#
# Creates (idempotently) the Bronze Lakehouse schemas and Delta tables for
# every active entity in `control.entity`: `staging.<table>` (source-shaped,
# plus `_staging_run_id`) and `<target_schema>.<table>` (business columns plus
# the `bronze_*` technical columns; history columns only for HISTORY entities).
#
# Safe to re-run after adding entities or columns: tables are created if
# missing and new columns are added; nothing is ever dropped or retyped.
#
# **Attach before first run:** the Bronze Lakehouse (schema-enabled) as the
# default Lakehouse, and the `CicdFramework` Environment.

# PARAMETERS CELL ********************

environment = "DEV"
warehouse_connection_string = ""   # pipeline parameter / Variable Library, never hard-coded
entity_ids = ""                    # optional comma-separated filter

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

from notebooks.bronze.config_loader import load_anonymisation_rules, load_entities, load_framework_config
from notebooks.bronze.schema_manager import SchemaManager
from notebooks.framework.fabric_connection import get_connection_notebookutils

if not warehouse_connection_string:
    raise ValueError("warehouse_connection_string parameter is required")

conn = get_connection_notebookutils(warehouse_connection_string)
try:
    cursor = conn.cursor()
    config = load_framework_config(cursor, environment)
    entities = load_entities(
        cursor,
        entity_ids=[int(i) for i in entity_ids.split(",") if i.strip()] or None,
        anonymisation_rules=load_anonymisation_rules(cursor),
    )
finally:
    conn.close()

spark.conf.set("spark.sql.session.timeZone", config.spark_timezone)
manager = SchemaManager(spark)
for entity in entities:
    changes = manager.ensure_entity_tables(entity)
    print(f"{entity.entity_id:>6} {entity.source_system}.{entity.source_table:<30} "
          f"-> {entity.staging_fqn} / {entity.target_fqn} [{entity.write_strategy}] {changes}")

print(f"{len(entities)} entities initialised for {config.environment}")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }
