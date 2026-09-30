"""Cross-artifact contracts between the SQL, the Python and the pipelines.

No database is needed: the tests parse the repo's own SQL files and check that
- every audit procedure the AuditManager or a pipeline calls exists, with
  the parameter names used, and every required parameter supplied;
- the Warehouse DDL respects Fabric Warehouse T-SQL limits;
- metadata scripts never reset runtime watermark state;
- control.fn_active_entities exposes every column the pipeline reads.
"""

import json
import re
from pathlib import Path

import pytest

from notebooks.bronze.audit_manager import AuditManager
from notebooks.bronze.error_manager import ErrorInfo
from notebooks.bronze.run_manager import RunContext
from notebooks.bronze.validation_engine import ValidationResult
from tests.bronze.factories import make_entity

ROOT = Path(__file__).resolve().parents[2]
PROC_DIR = ROOT / "sql_database/audit/procs"


def _proc_signatures():
    """proc name -> {param: has_default}"""
    signatures = {}
    for path in PROC_DIR.glob("*.sql"):
        text = path.read_text(encoding="utf-8")
        name = re.search(r"CREATE OR ALTER PROCEDURE \[audit\]\.\[(\w+)\]", text).group(1)
        header = text.split("\nAS\n", 1)[0]
        params = {}
        for match in re.finditer(r"^\s*@(\w+)\s+[^,\n]+?(=\s*[^,\n]+)?,?\s*(--.*)?$", header, re.MULTILINE):
            params[match.group(1)] = match.group(2) is not None
        signatures[name] = params
    return signatures


SIGNATURES = _proc_signatures()


def test_every_proc_is_parsed():
    assert {"usp_start_run", "usp_complete_run", "usp_start_entity_run", "usp_update_entity_run",
            "usp_complete_entity_run", "usp_log_activity", "usp_log_error", "usp_log_validation",
            "usp_log_file", "usp_get_run_entities", "usp_get_entity_baseline"} <= set(SIGNATURES)
    assert SIGNATURES["usp_start_run"]["run_id"] is False and SIGNATURES["usp_start_run"]["workspace_id"] is True


def _recorded_audit_calls():
    calls = []

    class Cursor:
        def execute(self, sql, *params):
            calls.append((sql, params))

        def fetchall(self):
            return []

    class Conn:
        def cursor(self):
            return Cursor()

        def close(self):
            pass

    ctx = RunContext.create(environment="DEV", run_id="20260930-081205-ABC123")
    audit = AuditManager("x", ctx, connect=lambda cs: Conn(), fallback_writer=lambda p, c: None)
    entity = make_entity()
    audit.start_run()
    audit.complete_run("SUCCEEDED")
    audit.start_entity_run(entity)
    audit.update_entity_run("e", "PROCESSING")
    audit.complete_entity_run("e", "SUCCEEDED")
    audit.get_run_entities()
    audit.previous_row_count(entity)
    audit.log_activity("e", "X", "SUCCEEDED")
    audit.log_error(ErrorInfo("C", "m", False, "WRITE", None), entity, "e")
    audit.log_validation("e", ValidationResult(1, "r", "CUSTOM", "PRE", "PASSED", "FAIL", "HIGH", 0))
    audit.log_file(entity, "e", "p", "f", "landing", "CREATED")
    return calls


@pytest.mark.parametrize("sql,params", _recorded_audit_calls())
def test_audit_manager_calls_match_proc_signatures(sql, params):
    proc = re.search(r"\[audit\]\.\[(\w+)\]", sql).group(1)
    names = re.findall(r"@(\w+) = \?", sql)
    assert proc in SIGNATURES, proc
    assert set(names) <= set(SIGNATURES[proc]), set(names) - set(SIGNATURES[proc])
    required = {p for p, has_default in SIGNATURES[proc].items() if not has_default}
    assert required <= set(names), required - set(names)
    assert len(names) == len(params)


def _pipeline_sp_activities():
    found = []

    def walk(activities, pipeline):
        for activity in activities:
            if activity["type"] == "SqlServerStoredProcedure":
                found.append((pipeline, activity))
            props = activity.get("typeProperties", {})
            for key in ("ifTrueActivities", "ifFalseActivities", "activities", "defaultActivities"):
                walk(props.get(key, []), pipeline)
            for case in props.get("cases", []):
                walk(case["activities"], pipeline)

    for path in (ROOT / "fabric_items/pipelines").glob("*/pipeline-content.json"):
        walk(json.loads(path.read_text(encoding="utf-8"))["properties"]["activities"], path.parent.name)
    return found


@pytest.mark.parametrize("pipeline,activity", _pipeline_sp_activities(), ids=lambda x: x if isinstance(x, str) else x["name"])
def test_pipeline_stored_procedure_calls_match_signatures(pipeline, activity):
    proc = re.search(r"\[audit\]\.\[(\w+)\]", activity["typeProperties"]["storedProcedureName"]).group(1)
    supplied = set(activity["typeProperties"]["storedProcedureParameters"])
    assert supplied <= set(SIGNATURES[proc]), supplied - set(SIGNATURES[proc])
    required = {p for p, has_default in SIGNATURES[proc].items() if not has_default}
    assert required <= supplied, required - supplied


def _sql_files(*folders):
    for folder in folders:
        yield from sorted((ROOT / folder).rglob("*.sql"))


@pytest.mark.parametrize("path", list(_sql_files("warehouse/ddl/00_schemas", "warehouse/ddl/05_meta",
                                                 "warehouse/ddl/10_control", "warehouse/ddl/30_constraints",
                                                 "warehouse/programmability", "warehouse/metadata")),
                         ids=lambda p: p.name)
def test_warehouse_sql_respects_fabric_dw_limits(path):
    code = "\n".join(line.split("--", 1)[0] for line in path.read_text(encoding="utf-8").splitlines())
    code = re.sub(r"'(?:[^']|'')*'", "''", code)   # string literals (e.g. source_data_type 'nvarchar(100)') are data
    upper = code.upper()
    assert "NVARCHAR" not in upper
    assert not re.search(r"\bDATETIME\b(?!2)", upper)
    assert not re.search(r"\bDEFAULT\b", upper)
    assert not re.search(r"\bCHECK\s*\(", upper)
    assert "IDENTITY" not in upper, "control ids are explicit BIGINTs (see warehouse/metadata/README.md)"
    assert not re.search(r"^\s*GO\s*$", code, re.MULTILINE | re.IGNORECASE)
    if "/ddl/10_control/" in path.as_posix():
        assert "PRIMARY KEY" not in upper and "REFERENCES" not in upper   # constraints come last, NOT ENFORCED
    if "/30_constraints/" in path.as_posix():
        assert upper.count("ADD CONSTRAINT") == upper.count("NOT ENFORCED")


@pytest.mark.parametrize("path", list(_sql_files("warehouse/metadata")), ids=lambda p: p.name)
def test_metadata_scripts_never_reset_runtime_watermarks(path):
    text = path.read_text(encoding="utf-8")
    assert "DELETE FROM [control].[watermark]" not in text
    assert "UPDATE [control].[watermark]" not in text
    for insert in re.findall(r"INSERT INTO \[control\]\.\[watermark\].*?;", text, re.DOTALL):
        assert "WHERE NOT EXISTS" in insert
    if "BEGIN TRANSACTION" in text:
        assert "COMMIT TRANSACTION" in text


def test_seeded_entities_have_watermark_rows_and_distinct_ids():
    ids = []
    for path in _sql_files("warehouse/metadata"):
        text = path.read_text(encoding="utf-8")
        for entity_id in re.findall(r"INSERT INTO \[control\]\.\[entity\].*?VALUES\s*\(\s*(\d+)", text, re.DOTALL):
            ids.append(entity_id)
            assert f"WHERE entity_id = {entity_id});" in text, f"entity {entity_id} has no watermark row"
    assert ids and len(ids) == len(set(ids))


def test_fn_active_entities_exposes_every_column_the_pipeline_reads():
    function = (ROOT / "warehouse/programmability/100_control_fn_active_entities.sql").read_text(encoding="utf-8")
    select_list = function.split("FROM [control].[entity] AS e", 1)[0]
    pipeline = (ROOT / "fabric_items/pipelines/BronzeOrchestrator.DataPipeline/pipeline-content.json").read_text(
        encoding="utf-8")
    used = set(re.findall(r"item\(\)\.(\w+)", pipeline))
    assert used, "pipeline reads no entity columns?"
    for column in used:
        assert re.search(rf"(\.|AS\s+){column}\b", select_list), f"fn_active_entities does not return {column}"


def test_audit_sql_is_single_batch_and_procs_are_repeatable():
    for path in _sql_files("sql_database/audit"):
        text = path.read_text(encoding="utf-8")
        assert not re.search(r"^\s*GO\s*$", text, re.MULTILINE | re.IGNORECASE), path
        if "/procs/" in path.as_posix() or "/views/" in path.as_posix():
            assert "CREATE OR ALTER" in text, path


SECRET_PATTERNS = [
    re.compile(r"(password|pwd)\s*=\s*[^;\s\"'<{]", re.IGNORECASE),
    re.compile(r"AccountKey\s*=", re.IGNORECASE),
    re.compile(r"SharedAccessSignature|sig=[A-Za-z0-9%]{20,}"),
    re.compile(r"[a-z0-9-]+\.(datawarehouse\.fabric\.microsoft\.com|database\.windows\.net)", re.IGNORECASE),
]


@pytest.mark.parametrize("folder", ["notebooks", "fabric_items", "warehouse", "sql_database", "scripts"])
def test_no_secrets_or_hard_coded_endpoints(folder):
    for path in (ROOT / folder).rglob("*"):
        if not path.is_file() or path.suffix not in {".py", ".sql", ".json", ".yml", ".md", ".platform", ""}:
            continue
        if "__pycache__" in path.parts or "_bundled_repo" in path.parts:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for pattern in SECRET_PATTERNS:
            match = pattern.search(text)
            assert match is None, f"{path.relative_to(ROOT)}: {match.group(0) if match else ''}"
