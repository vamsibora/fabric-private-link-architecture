-- audit.usp_start_run: create (or, on restart of the same run_id, reopen)
-- an audit.run row. Called by the BronzeOrchestrator pipeline and by
-- notebooks/bronze/audit_manager.AuditManager.start_run -- one code path for
-- both, so pipeline- and notebook-started runs look identical.
CREATE OR ALTER PROCEDURE [audit].[usp_start_run]
    @run_id          VARCHAR(64),
    @framework_name  VARCHAR(100),
    @environment     VARCHAR(10),
    @workspace_id    VARCHAR(64)    = NULL,
    @workspace_name  NVARCHAR(256)  = NULL,
    @pipeline_name   NVARCHAR(256)  = NULL,
    @pipeline_run_id VARCHAR(64)    = NULL,
    @notebook_name   NVARCHAR(256)  = NULL,
    @trigger_type    VARCHAR(30)    = NULL,
    @trigger_name    NVARCHAR(256)  = NULL,
    @initiated_by    NVARCHAR(256)  = NULL,
    @run_timestamp   CHAR(14)       = NULL,
    @entity_group    VARCHAR(100)   = NULL,
    @total_entities  INT            = NULL
AS
BEGIN
    SET NOCOUNT ON;

    IF EXISTS (SELECT 1 FROM [audit].[run] WHERE run_id = @run_id)
    BEGIN
        UPDATE [audit].[run]
        SET status           = 'RUNNING',
            end_datetime     = NULL,
            total_entities   = COALESCE(@total_entities, total_entities),
            notebook_name    = COALESCE(@notebook_name, notebook_name),
            updated_datetime = SYSUTCDATETIME()
        WHERE run_id = @run_id;
    END
    ELSE
    BEGIN
        INSERT INTO [audit].[run]
            (run_id, framework_name, environment, workspace_id, workspace_name, pipeline_name,
             pipeline_run_id, notebook_name, trigger_type, trigger_name, initiated_by, run_timestamp,
             entity_group, status, total_entities)
        VALUES
            (@run_id, @framework_name, @environment, @workspace_id, @workspace_name, @pipeline_name,
             @pipeline_run_id, @notebook_name, @trigger_type, @trigger_name, @initiated_by, @run_timestamp,
             @entity_group, 'STARTED', @total_entities);
    END

    SELECT @run_id AS run_id;
END;
