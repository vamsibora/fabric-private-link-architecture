-- SECURITY.UserAccess: source of truth for Row-Level Security. Each row grants
-- a UserPrincipalName access to one Region/Country/BusinessUnit combination.
-- NULL on a key column means "wildcard" -- that user sees all values on that
-- dimension. See security/rls/001_security_predicate_function.sql for how
-- this is enforced.
CREATE TABLE [SECURITY].[UserAccess]
(
    UserAccessID      BIGINT       IDENTITY(1,1) NOT NULL,
    UserPrincipalName VARCHAR(256) NOT NULL,
    SecurityRole      VARCHAR(100) NOT NULL,
    RegionKey         INT          NULL,   -- NULL = all regions
    CountryKey        INT          NULL,   -- NULL = all countries
    BusinessUnitKey   INT          NULL,   -- NULL = all business units
    IsActive          BIT          NOT NULL,
    CreatedDate       DATETIME2(6) NOT NULL,
    CreatedBy         VARCHAR(256) NOT NULL,
    ModifiedDate      DATETIME2(6) NULL,
    ModifiedBy        VARCHAR(256) NULL
);
