# fabric_medallion_architecture

A metadata-driven Bronze ingestion framework for Microsoft Fabric, plus its
control plane, central audit, schema migrations and CI/CD.

- **Optional landing layer.** Per entity, extracts go either to Storage
  Account JSON (`<source_system>/<table>/<table>_<yyyyMMddHHmmss>.json`) or
  straight to Bronze Lakehouse staging tables.
- **Warehouse `control` schema** holds all framework metadata. Adding a table
  means adding metadata, not a pipeline.
- **Central cross-workspace audit** in a Fabric SQL Database (`audit.*`).
- **Bronze processing** (`notebooks.bronze`): validation, deduplication,
  environment-based anonymisation, hash change detection, MERGE / source
  history / append / replace, and safe watermarks, with bounded parallelism.

> Status: repo code with mocked tests only. Nothing has been deployed to, or
> validated against, a live Fabric workspace yet. See
> [docs/bronze_framework/01_Architecture.md](docs/bronze_framework/01_Architecture.md)
> § Verify live before production.

## Layout

```
warehouse/          Warehouse DDL (control, SECURITY), programmability, seed metadata
security/rls/       Row-Level Security predicate + policy template
sql_database/audit/ Audit SQL Database: DDL, stored procedures, monitoring views, DEV samples
notebooks/bronze/   The Bronze framework package
notebooks/framework/ Connection helpers and the ledger-driven migration runner (Warehouse + audit DB)
fabric_items/       Dev git-sync root: pipelines, notebooks, environment (.platform included)
scripts/ci/         Fabric REST helpers used by CI (git sync, library publish, job run, stage deploy, verify)
tests/              pytest (Fabric dependencies mocked; Spark tests skip without Java)
docs/               Spec, framework docs, runbooks (docs/runbooks/), CI/CD, AI-agent build prompts
```

## Quick start (local)

```bash
pip install -r requirements-dev.txt
pytest -q
```

Documentation index: [docs/index.md](docs/index.md).
