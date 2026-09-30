# Fabric notebook source

# METADATA ********************

# META {
# META   "kernel_info": {
# META     "name": "synapse_pyspark"
# META   },
# META   "dependencies": {}
# META }

# MARKDOWN ********************

# # SchemaMigrationRunner
#
# Thin wrapper around the tested `notebooks.framework.migration_runner`
# (installed from the `CicdFramework.Environment` custom library, which also
# bundles every migration script).
#
# Order matters:
# 1. **Audit SQL Database** (`AUDIT_DB` target): `audit` schema, tables,
#    indexes, stored procedures and monitoring views. It runs first so the
#    Warehouse migration can itself be audited.
# 2. **Warehouse** (`WAREHOUSE` target): `control` schema, `SECURITY`/RLS,
#    `control.fn_active_entities` and the control metadata seed.
#
# CREATE-once scripts never re-run; repeatable scripts (procs, views,
# functions, metadata) re-apply when their checksum changes.

# PARAMETERS CELL ********************

target_environment = "DEV"
warehouse_connection_string = ""   # resolved per stage (deployment rule / Variable Library), never hard-coded
audit_connection_string = ""       # resolved per stage (deployment rule / Variable Library), never hard-coded

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

import importlib.resources
from pathlib import Path

from notebooks.bronze.audit_manager import AuditManager
from notebooks.bronze.error_manager import ErrorInfo, classify
from notebooks.bronze.run_manager import RunContext
from notebooks.framework import migration_runner as mr

if not warehouse_connection_string or not audit_connection_string:
    raise ValueError("warehouse_connection_string and audit_connection_string parameters are required")

bundled_repo_root = Path(importlib.resources.files("notebooks.framework")) / "_bundled_repo"
applied_by = f"schema_migration:{target_environment}"

# 1. Audit database first -- nothing can be audited until it exists.
audit_result = mr.run_migrations(
    audit_connection_string, bundled_repo_root, applied_by=applied_by, target=mr.AUDIT_DB_TARGET,
)
print(f"AUDIT_DB: applied {len(audit_result.applied)}, already-applied {len(audit_result.already_applied)}, "
      f"drift {len(audit_result.checksum_drift)}")

# 2. Warehouse, audited as a run in the central audit database.
context = RunContext.create(environment=target_environment, framework_name="SchemaMigration",
                            trigger_type="DEPLOYMENT").with_notebook_context()
audit = AuditManager(audit_connection_string, context)
audit.start_run()


def _drift_warning(message: str) -> None:
    audit.log_error(ErrorInfo("CHECKSUM_DRIFT", message, False, "SCHEMA_MIGRATION", None))


try:
    result = mr.run_migrations(
        warehouse_connection_string, bundled_repo_root, applied_by=applied_by, run_id=context.run_id,
        target=mr.WAREHOUSE_TARGET, on_warning=_drift_warning,
    )
    audit.log_activity(None, "SCHEMA_MIGRATION_COMPLETED", "SUCCEEDED", activity_name="WAREHOUSE",
                       rows_affected=len(result.applied),
                       message=f"applied={len(result.applied)} already={len(result.already_applied)} "
                               f"templates={len(result.skipped_templates)} drift={len(result.checksum_drift)}")
    audit.complete_run("SUCCEEDED")
    print(f"WAREHOUSE: applied {len(result.applied)}, already-applied {len(result.already_applied)}, "
          f"templates skipped {len(result.skipped_templates)}, checksum drift {len(result.checksum_drift)}")
except Exception as ex:
    audit.log_error(classify(ex, "SCHEMA_MIGRATION"))
    audit.complete_run("FAILED", message="warehouse schema migration failed")
    raise

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }
