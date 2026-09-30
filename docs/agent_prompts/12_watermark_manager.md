# 12 — Watermark Manager (spec §15, §24, §54)

```text
Context: 00_master_context.md. Reference: notebooks/bronze/watermark_manager.py,
warehouse/programmability/100_control_fn_active_entities.sql.

1. Read control.watermark.last_successful_watermark. The same value feeds the pipeline's source
   query through control.fn_active_entities.
2. Capture the batch max from staging BEFORE anonymisation (batch_max_watermark).
3. After the Bronze write AND post-validation succeed, commit
   resolve_watermark_after(before, batch_max): never backwards; an empty batch keeps the old
   value.
4. The commit is a single-row UPDATE guarded by the value read in step 1 (optimistic
   concurrency).
   - 0 rows and no row at all -> INSERT.
   - 0 rows and a different value -> WatermarkConflictError (never overwrite).
5. Canonical strings (must match fn_active_entities):
   DATETIME yyyy-MM-dd HH:mm:ss.ffffff UTC; NUMERIC plain decimal; STRING as-is.
6. Record watermark_before/after in audit.entity_run. On failure,
   watermark_after = the unchanged previous value.
Failure: preserve the watermark, mark the entity FAILED, write audit.error, and leave the
entity retryable.

Tests: tests/bronze/test_watermark_manager.py (fake cursor with rowcount) covers parse/format
for each type (timezone-aware -> UTC), never-backwards, an empty batch, a no-op commit, the
guarded update, insert-when-missing, and a conflict raising.
Report: what you could NOT verify live (pyodbc rowcount on Fabric DW UPDATE; a DATETIME2(7)
literal against the source datetime column).
```
