# Performance Review — Bronze Framework (spec §61)

A desk review of the design. No live load measurements exist yet. The
defaults below are starting points to measure against in Dev/UAT.

## Bottlenecks and scaling limits

| Area | Behaviour | Limit / risk | Recommendation |
|---|---|---|---|
| Copy parallelism | ForEach `batchCount` is **static** (20); pipeline expressions cannot set it | Up to 20 concurrent copies through one gateway | Size the gateway cluster for 20 concurrent queries, or lower batchCount in the item. Use `entity_group` schedules to spread load. |
| Gateway throughput | All on-premises extraction flows through the gateway | CPU/network on gateway hosts | Gateway cluster of ≥ 2 nodes. Monitor gateway performance counters. Prefer incremental loads. |
| Source queries | `fn_active_entities` generates `SELECT <cols> … WHERE wm > literal` | Full scans without an index on the watermark column | Index the watermark column at source. Use `source_filter` / `source_query_override` for partition-friendly predicates. |
| Lookup | `LookupActiveEntities` returns every active entity | Pipeline Lookup output limit (~5,000 rows / 4 MB) | Under ~5,000 entities per run. Beyond that, split by `entity_group`. |
| Notebook processing | One notebook, `ThreadPoolExecutor(max_parallel_entities)` (5/10/20), sharing one Spark session | Driver memory/CPU and Spark scheduler contention | Keep 10–20 on a medium pool. Enable the fair scheduler pool if long entities starve short ones. Scale the Spark pool before raising the parallelism. |
| Landing JSON | JSON lines (`setOfObjects`), read with an explicit all-STRING schema | JSON is ~3–5× larger than Parquet and slower to parse | Fine for moderate volumes. For very large tables (> ~10 GB per extract) consider disabling landing (straight to staging), or future Parquet landing (not implemented; the spec mandates JSON). |
| Staging | Copy overwrite into Delta; the framework reads it once projected | Small-file risk for many small entities | Default Copy settings are acceptable. Periodic `OPTIMIZE staging.*` is unnecessary (overwritten each run). |
| Bronze MERGE | Delta MERGE on PK, hash-guarded updates | Cost grows with target size; no partition pruning by default | **No automatic partitioning.** Add partitioning / liquid clustering only where query or write patterns justify it (e.g. > 1 B rows with a date-bounded update window). Keep `OPTIMIZE` scheduled. |
| History | One MERGE per batch plus a join against current rows | The current-row filter scans the table | Enable deletion vectors / Z-order on the PK for large history tables if measured necessary. |
| Counts | `df.count()` for dedup, `bronze.count()` for POST validation | Extra Spark jobs per entity | Acceptable for moderate sizes. For very large Bronze tables, make the POST `bronze_row_count` optional (a future config flag) or use Delta table stats. |
| Audit write volume | ~10–15 procedure calls per entity (activity, validation, entity updates) plus pipeline calls | Latency per call; audit DB DTU/vCore | One pyodbc connection per thread (reused). At hundreds of entities this is thousands of small inserts per run, fine for a Fabric SQL DB. Archive `audit.activity` periodically. |
| Audit connection | Per-thread connections via `threading.local`, reconnect once on failure | Connection count = worker threads | Keep `max_parallel_entities` within the SQL DB connection limits. |
| Warehouse metadata reads | 6 queries per run (not per entity) plus 1 watermark read and 1 commit per entity | Warehouse queueing under concurrency | Negligible. Watermark commits are single-row UPDATEs. |

## Recommended defaults

| Parameter | Where | Default |
|---|---|---|
| `max_parallel_entities` | framework_configuration | DEV 5 / UAT 10 / PROD 20 |
| ForEach `batchCount` | BronzeOrchestrator item | 20 |
| Copy `policy.retry` / interval | extract item | 2 / 60 s |
| `retry_enabled`, `max_retry_count`, `retry_delay_seconds` | load_configuration | 1, 3, 30 s |
| `row_count_anomaly_threshold_pct` | load_configuration | 50 (incremental), 80 (full) |
| `spark_timezone` | framework_configuration | UTC |
| Delta maintenance | scheduled notebook (not implemented) | `OPTIMIZE` weekly; `VACUUM` with the default 7-day retention |
| V-Order | Fabric default | Leave enabled for Bronze tables read by the SQL endpoint / Direct Lake downstream. Writes are slightly slower. |

## Configuration parameters affecting performance

`max_parallel_entities`, `continue_on_entity_failure`, `landing_enabled`,
`landing_globally_enabled`, `entity_group`, `processing_priority`,
`source_filter`, `source_query_override`, `change_detection_method`
(`NONE` = update every match, which is more expensive), and the retry
settings.
