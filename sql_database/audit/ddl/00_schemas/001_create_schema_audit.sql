-- Central cross-workspace audit database (Fabric SQL Database
-- "BronzeFrameworkAudit", in the Audit / Operations workspace).
--
-- Every ingestion workspace writes here. This is a full SQL Server T-SQL
-- surface (unlike the Fabric Warehouse): enforced PK/FK, DEFAULT, CHECK,
-- IDENTITY, NVARCHAR and nonclustered indexes are all available and used.
--
-- Control metadata defines what should happen (Warehouse control schema).
-- Audit records what actually happened (this database).
CREATE SCHEMA [audit];
