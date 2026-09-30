# fabric_items/

Git-sync root for the **Dev** Fabric workspace. UAT and Prod are not
git-connected — they only receive content via the Fabric Deployment
Pipeline's "deploy" action (see `docs/cicd_pipeline.md`).

## Status: draft content, not yet reconciled with Fabric

The files under `notebooks/`, `pipelines/`, and `environments/` here are
**hand-authored drafts** of the intended item content — they are **not**
real Fabric item exports and deliberately do **not** include `.platform`
metadata files, which Fabric generates itself and must not be hand-authored.

Per `docs/cicd_pipeline.md` § Order of Implementation, the real setup
sequence is:

1. Create the Warehouse (confirm it doesn't already exist first), Notebook,
   Data Pipeline, and Environment as empty/skeleton items in the **Dev**
   workspace via the Fabric portal.
2. Connect the Dev workspace's Git integration to this repo, branch `main`,
   root folder `/fabric_items`.
3. Use the workspace's "Commit to Git" action once to have Fabric serialize
   its own correct `.platform`/content files into this folder — replacing
   the drafts below. That commit becomes the real baseline for future PRs
   (e.g. editing `pipeline-content.json`'s activities or
   `notebook-content.py`'s cell body).

The Warehouse item itself is intentionally **not** part of this git-sync
root — its schema is managed entirely by `notebooks/framework/
migration_runner.py`, not Fabric's native item sync.
