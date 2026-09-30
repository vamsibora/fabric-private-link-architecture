-- control.entity: the central metadata table -- one row per source table the
-- framework ingests into Bronze.
--
-- Write strategy is derived, not stored (see notebooks/bronze/models.py):
--   history_required = 1               -> HISTORY  (append changed versions)
--   merge_required   = 1               -> MERGE    (current-state upsert)
--   load_type = 'FULL' (neither flag)  -> REPLACE
--   otherwise                          -> APPEND
CREATE TABLE [control].[entity]
(
    entity_id               BIGINT        NOT NULL,
    source_system_id        BIGINT        NOT NULL,
    source_schema           VARCHAR(128)  NULL,
    source_table            VARCHAR(256)  NOT NULL,   -- also the landing <table_name>
    target_schema           VARCHAR(128)  NOT NULL,   -- Bronze Lakehouse schema
    target_table            VARCHAR(256)  NOT NULL,
    staging_schema          VARCHAR(128)  NOT NULL,   -- normally 'staging'
    staging_table           VARCHAR(256)  NOT NULL,   -- normally <source_system>_<table>, lower case
    entity_group            VARCHAR(100)  NULL,       -- optional scheduling group filter
    load_type               VARCHAR(20)   NOT NULL,   -- FULL | INCREMENTAL
    landing_enabled         BIT           NOT NULL,   -- 1 = Storage Account JSON landing, 0 = copy straight to staging
    history_required        BIT           NOT NULL,
    merge_required          BIT           NOT NULL,
    primary_key             VARCHAR(1000) NULL,       -- comma-separated; supports composite keys
    watermark_column        VARCHAR(128)  NULL,       -- required when load_type = INCREMENTAL
    watermark_type          VARCHAR(20)   NULL,       -- DATETIME | NUMERIC | STRING
    change_detection_method VARCHAR(20)   NOT NULL,   -- HASH | NONE
    anonymisation_required  BIT           NOT NULL,   -- entity has columns carrying anonymisation rules
    processing_priority     INT           NOT NULL,   -- lower runs first
    active_flag             BIT           NOT NULL,
    created_datetime        DATETIME2(6)  NOT NULL,
    created_by              VARCHAR(256)  NOT NULL,
    updated_datetime        DATETIME2(6)  NULL,
    updated_by              VARCHAR(256)  NULL
);
