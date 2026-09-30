-- Row-Level Security predicate function: returns one row when the calling
-- user (USER_NAME()) is entitled to see data for the given Region/Country/
-- BusinessUnit combination, per SECURITY.UserAccess.
--
-- USER_NAME() vs SESSION_CONTEXT: Fabric Warehouse SQL endpoint connections
-- are per-user Entra pass-through (there is no trusted pooled middle tier
-- that could SET SESSION_CONTEXT on behalf of an end user), so USER_NAME()
-- is the reliable way to identify the caller.
--
-- NULL on a UserAccess key column is a wildcard (that user sees every value
-- on that dimension) -- this is a security-relevant convention, not enforced
-- by the database, so document it wherever UserAccess rows are maintained.
--
-- SCHEMABINDING means this function only ever depends on SECURITY.UserAccess,
-- so no changes are needed here when new fact/dimension tables adopt the
-- policy in 002_security_policy_template.sql.
CREATE FUNCTION [SECURITY].[fn_SecurityPredicate]
(
    @RegionKey       INT,
    @CountryKey      INT,
    @BusinessUnitKey INT
)
RETURNS TABLE
WITH SCHEMABINDING
AS
RETURN
    SELECT 1 AS IsAccessible
    WHERE EXISTS (
        SELECT 1
        FROM [SECURITY].[UserAccess] AS ua
        WHERE ua.UserPrincipalName = USER_NAME()
          AND ua.IsActive = 1
          AND (ua.RegionKey       IS NULL OR ua.RegionKey       = @RegionKey)
          AND (ua.CountryKey      IS NULL OR ua.CountryKey      = @CountryKey)
          AND (ua.BusinessUnitKey IS NULL OR ua.BusinessUnitKey = @BusinessUnitKey)
    );
