-- MIGRATION_RUNNER: SKIP
--
-- Row-Level Security policy TEMPLATE.
--
-- This repo has no fact/dimension tables yet, so there is nothing real to
-- bind a policy to. Once a table with RegionKey/CountryKey/BusinessUnitKey
-- (INT) columns exists, replace <SchemaName>.<TableName> below, REMOVE the
-- "MIGRATION_RUNNER: SKIP" marker above (migration_runner.py checks for it
-- to decide whether this is still a template), and run this as the FIRST
-- policy statement (CREATE), then use the ALTER pattern for every additional
-- table.
--
-- Testing note: RLS is bypassed for workspace Admin/Member/Contributor roles.
-- Always test by connecting AS the target user (a Viewer, or a role with no
-- elevated workspace permission), not as the deploying/admin identity.

/*
CREATE SECURITY POLICY [SECURITY].[FactFilterPolicy]
ADD FILTER PREDICATE [SECURITY].[fn_SecurityPredicate](RegionKey, CountryKey, BusinessUnitKey)
ON [<SchemaName>].[<TableName>]
WITH (STATE = ON);
*/

-- Attaching another table to the same policy later:
/*
ALTER SECURITY POLICY [SECURITY].[FactFilterPolicy]
ADD FILTER PREDICATE [SECURITY].[fn_SecurityPredicate](RegionKey, CountryKey, BusinessUnitKey)
ON [<SchemaName>].[<AnotherTableName>]
WITH (STATE = ON);
*/
