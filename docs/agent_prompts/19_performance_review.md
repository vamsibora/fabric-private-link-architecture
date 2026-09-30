# 19 — Performance review (spec §61)

```text
Context: 00_master_context.md.

Assess:
- Copy parallelism: the ForEach batchCount vs gateway throughput vs source load.
- Incremental extraction and indexes on source watermark columns.
- Landing JSON size and small files. Use JSON lines (setOfObjects); read with an explicit
  schema, not inference.
- Delta writes: MERGE cost on large tables, the history staged-union MERGE, V-Order, OPTIMIZE,
  and file sizing.
- Concurrency: max_parallel_entities vs Spark cores; the one-notebook-per-run design.
- Audit write volume: activity rows per entity, per-thread connections, proc latency, and SQL
  DB index usage.
- Warehouse metadata reads: one query per table; fn_active_entities cost; the Lookup
  5000-row limit.

Do NOT recommend partitioning by default. Justify it only where query/write patterns demand it.

Output docs/bronze_framework/performance_review.md: bottlenecks, scaling limits, recommended
defaults per environment, and which control.framework_configuration /
pipeline_configuration keys tune them (add keys only as metadata-script changes).
Report: what you could NOT measure live.
```
