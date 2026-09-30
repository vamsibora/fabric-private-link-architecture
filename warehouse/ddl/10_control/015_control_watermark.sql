-- control.watermark: RUNTIME watermark state, kept separate from entity
-- config. Only notebooks/bronze/watermark_manager.py updates it, and only
-- after the entity's Bronze write and post-validation succeeded. Metadata
-- scripts only ever INSERT missing rows -- they must never reset an existing
-- watermark.
CREATE TABLE [control].[watermark]
(
    entity_id                 BIGINT       NOT NULL,
    last_successful_watermark VARCHAR(100) NULL,     -- canonical string form (watermark_manager.format_watermark)
    last_run_id               VARCHAR(64)  NULL,
    last_entity_run_id        VARCHAR(80)  NULL,
    updated_datetime          DATETIME2(6) NOT NULL
);
