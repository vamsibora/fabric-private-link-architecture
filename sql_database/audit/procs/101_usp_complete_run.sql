-- audit.usp_complete_run: close an audit.run row.
--
-- @status NULL  -> derive the status from the run's entity_run rows, using
--                  the same roll-up as notebooks/bronze/orchestrator.rollup_status:
--                  no failures -> SUCCEEDED; no successes but failures -> FAILED;
--                  both -> PARTIAL_SUCCESS.
-- @status given -> used as-is, BUT only if the run is not already in a
--                  terminal state. This lets the pipeline's on-failure branch
--                  call it with 'FAILED' without clobbering a status the
--                  framework notebook already wrote.
-- Entity counts are always recomputed from audit.entity_run.
CREATE OR ALTER PROCEDURE [audit].[usp_complete_run]
    @run_id  VARCHAR(64),
    @status  VARCHAR(20)    = NULL,
    @message NVARCHAR(4000) = NULL
AS
BEGIN
    SET NOCOUNT ON;

    DECLARE @succeeded INT, @failed INT, @skipped INT, @total INT;

    SELECT
        @succeeded = SUM(CASE WHEN status = 'SUCCEEDED' THEN 1 ELSE 0 END),
        @failed    = SUM(CASE WHEN status = 'FAILED' THEN 1 ELSE 0 END),
        @skipped   = SUM(CASE WHEN status IN ('SKIPPED', 'CANCELLED') THEN 1 ELSE 0 END),
        @total     = COUNT(*)
    FROM [audit].[entity_run]
    WHERE run_id = @run_id;

    DECLARE @derived VARCHAR(20) =
        CASE
            WHEN COALESCE(@failed, 0) = 0 THEN 'SUCCEEDED'
            WHEN COALESCE(@succeeded, 0) = 0 THEN 'FAILED'
            ELSE 'PARTIAL_SUCCESS'
        END;

    UPDATE [audit].[run]
    SET status              = COALESCE(@status, @derived),
        end_datetime        = SYSUTCDATETIME(),
        total_entities      = COALESCE(total_entities, @total),
        successful_entities = COALESCE(@succeeded, 0),
        failed_entities     = COALESCE(@failed, 0),
        skipped_entities    = COALESCE(@skipped, 0),
        message             = COALESCE(@message, message),
        updated_datetime    = SYSUTCDATETIME()
    WHERE run_id = @run_id
      AND (@status IS NULL OR status NOT IN ('SUCCEEDED', 'PARTIAL_SUCCESS', 'FAILED', 'CANCELLED'));

    SELECT run_id, status FROM [audit].[run] WHERE run_id = @run_id;
END;
