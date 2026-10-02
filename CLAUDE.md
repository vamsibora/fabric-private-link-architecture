# CLAUDE.md

Metadata-driven Bronze ingestion framework for Microsoft Fabric.

**Start every session by reading `docs/context_prompt.md`.** It holds what
exists, the decisions to preserve, where the work stands and the ordered next
steps. Keep its "Where the work stands" and "Next steps" sections current.

- Spec: `docs/Fabric_Metadata_Driven_Bronze_Ingestion_Framework.md`
- Procedures: `docs/runbooks/` (setup, metadata maintenance, operations, framework changes)
- Design: `docs/bronze_framework/`. AI build prompts: `docs/agent_prompts/`.
- Fabric item syntax reference (working Dev items, outside this repo):
  `C:\Work\Data_Platform\src\ito_dp_fabric_dev\rio`. Copy its structure, never its ids.

Commands:

```bash
pip install -r requirements-dev.txt
pytest -q                 # must pass before any commit
pytest -m spark -v        # needs Java 17 + pyspark/delta-spark
python -c "from scripts.ci.fabric_publish_environment_library import build_wheel; print(build_wheel())"
```

Hard rules:
- **Metadata changes follow `docs/runbooks/02_metadata_maintenance.md`.**
- **SQL files:** never edit an applied CREATE-once SQL file; add a new
  numbered file instead.
- **Secrets and ids:** no secrets, connection strings or real workspace or
  connection ids in any file. `tests/fabric_items` and
  `tests/bronze/test_sql_contracts.py` enforce this.
- **Deployment:** confirm with the user before any Fabric deployment, and
  never touch PROD without explicit, in-the-moment approval.
- **`main` runs CI/CD:** pushing or merging to `main` runs the deploy
  workflow, so don't do it without the user's go-ahead.
