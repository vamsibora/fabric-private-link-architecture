# Fabric Notebook — SchemaMigrationRunner
#
# DRAFT content -- see fabric_items/README.md. This is a thin wrapper only;
# all real logic lives in the tested notebooks.framework.migration_runner
# module, installed via this workspace's CicdFramework.Environment custom
# library (see scripts/ci/fabric_publish_environment_library.py).
#
# Notebook parameters (set by the SchemaMigration.DataPipeline Notebook
# activity that invokes this notebook):
#   target_environment: str   -- "dev" | "uat" | "prod", for logging only
#   connection_string: str    -- Warehouse SQL endpoint, resolved per stage
#                                 via a Deployment Pipeline deployment rule,
#                                 never hardcoded here

# PARAMETERS CELL
target_environment = ""
connection_string = ""

# CODE CELL
import importlib.resources
from pathlib import Path

from notebooks.framework import utils_logging as ul
from notebooks.framework import migration_runner as mr

if not connection_string:
    raise ValueError("connection_string parameter is required")

bundled_repo_root = Path(importlib.resources.files("notebooks.framework")) / "_bundled_repo"

pipeline_run_id = ul.start_pipeline_run(
    connection_string,
    pipeline_name="schema_migration",
    source_system=target_environment,
)
try:
    result = mr.run_migrations(
        connection_string,
        repo_root=bundled_repo_root,
        applied_by=target_environment or "unknown",
        pipeline_run_id=pipeline_run_id,
    )
    ul.end_pipeline_run(
        connection_string,
        pipeline_run_id,
        status="SUCCEEDED",
        rows_processed=len(result.applied),
    )
    print(f"Applied {len(result.applied)}, already-applied {len(result.already_applied)}, "
          f"templates skipped {len(result.skipped_templates)}, checksum drift {len(result.checksum_drift)}")
except Exception as ex:
    ul.log_error(
        connection_string,
        f"schema_migration failed: {ex}",
        severity="CRITICAL",
        pipeline_run_id=pipeline_run_id,
        source_stage="schema_migration",
        exception=ex,
    )
    ul.end_pipeline_run(connection_string, pipeline_run_id, status="FAILED")
    raise
