-- audit.usp_get_run_entities: the entities of a run in a given status --
-- used by the framework notebook to find what the extract pipelines
-- successfully staged/landed in this run (status EXTRACTED).
CREATE OR ALTER PROCEDURE [audit].[usp_get_run_entities]
    @run_id VARCHAR(64),
    @status VARCHAR(20) = 'EXTRACTED'
AS
BEGIN
    SET NOCOUNT ON;

    SELECT entity_run_id, entity_id, landing_enabled, landing_path, source_row_count, attempt_number
    FROM [audit].[entity_run]
    WHERE run_id = @run_id
      AND status = @status
    ORDER BY entity_id;
END;
