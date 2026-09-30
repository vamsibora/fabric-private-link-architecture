-- Creates the control schema: framework METADATA only (what should happen).
-- Operational audit history (what actually happened) lives in the central
-- cross-workspace Fabric SQL Database (sql_database/audit/), never here.
--
-- Lowercase on purpose: Fabric Warehouse identifiers are case-sensitive
-- (Latin1_General_100_BIN2_UTF8), so [control] and [CONTROL] would be two
-- different schemas. The old PascalCase CONTROL model was retired before it
-- was ever deployed.
CREATE SCHEMA [control];
