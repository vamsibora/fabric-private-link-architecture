"""Structural checks for fabric_items/ against the working Dev reference
item shapes (ito_dp_fabric_dev/rio): valid JSON, .platform schema 2.0.0,
known activity types, only placeholder ids, resolvable item references,
Fabric notebook source format, and the landing/staging contracts."""

import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2] / "fabric_items"
PLATFORM_SCHEMA = "https://developer.microsoft.com/json-schemas/fabric/gitIntegration/platformProperties/2.0.0/schema.json"
PLACEHOLDER_GUIDS = {
    "00000000-0000-0000-0000-000000000000",
    "00000000-0000-0000-0000-00000000a001",
    "00000000-0000-0000-0000-00000000a002",
    "00000000-0000-0000-0000-00000000a003",
    "00000000-0000-0000-0000-00000000a004",
    "00000000-0000-0000-0000-00000000b001",
    "00000000-0000-0000-0000-00000000b002",
}
KNOWN_ACTIVITY_TYPES = {
    "Copy", "InvokePipeline", "TridentNotebook", "InvokeCopyJob", "SetVariable",  # seen in the reference items
    "Lookup", "ForEach", "IfCondition", "Switch", "GetMetadata", "Fail", "SqlServerStoredProcedure",
}
GUID = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")

PLATFORMS = sorted(ROOT.rglob(".platform"))
PIPELINES = sorted(ROOT.rglob("pipeline-content.json"))
NOTEBOOKS = sorted(ROOT.rglob("notebook-content.py"))


def _logical_ids():
    return {json.loads(p.read_text(encoding="utf-8"))["config"]["logicalId"]: p.parent.name for p in PLATFORMS}


def _activities(activities):
    for activity in activities:
        yield activity
        props = activity.get("typeProperties", {})
        for key in ("ifTrueActivities", "ifFalseActivities", "activities", "defaultActivities"):
            yield from _activities(props.get(key, []))
        for case in props.get("cases", []):
            yield from _activities(case["activities"])


def _load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def test_every_item_folder_has_a_platform_file():
    item_dirs = {p.parent for p in PIPELINES + NOTEBOOKS}
    assert item_dirs <= {p.parent for p in PLATFORMS}
    assert len(PLATFORMS) == 7


@pytest.mark.parametrize("path", PLATFORMS, ids=lambda p: p.parent.name)
def test_platform_files_follow_schema(path):
    platform = _load(path)
    assert platform["$schema"] == PLATFORM_SCHEMA
    assert platform["config"]["version"] == "2.0"
    name, _, item_type = path.parent.name.rpartition(".")
    assert platform["metadata"] == {"type": item_type, "displayName": name}
    assert GUID.fullmatch(platform["config"]["logicalId"])


def test_logical_ids_are_unique():
    ids = [_load(p)["config"]["logicalId"] for p in PLATFORMS]
    assert len(ids) == len(set(ids))


@pytest.mark.parametrize("path", PIPELINES, ids=lambda p: p.parent.name)
def test_pipelines_use_known_activities_unique_names_and_resolvable_refs(path):
    activities = list(_activities(_load(path)["properties"]["activities"]))
    names = [a["name"] for a in activities]
    assert len(names) == len(set(names)), "activity names must be unique within a pipeline"
    logical = _logical_ids()
    for activity in activities:
        assert activity["type"] in KNOWN_ACTIVITY_TYPES, activity["type"]
        for dependency in activity.get("dependsOn", []):
            assert dependency["activity"] in names
        props = activity.get("typeProperties", {})
        if activity["type"] == "TridentNotebook":
            assert logical.get(props["notebookId"], "").endswith(".Notebook")
        if activity["type"] == "InvokePipeline":
            assert props["operationType"] == "InvokeFabricPipeline"
            assert logical.get(props["pipelineId"], "").endswith(".DataPipeline")
            assert "connection" in activity["externalReferences"]


@pytest.mark.parametrize("path", PIPELINES + NOTEBOOKS + PLATFORMS, ids=lambda p: f"{p.parent.name}/{p.name}")
def test_only_placeholder_or_logical_ids_are_committed(path):
    allowed = PLACEHOLDER_GUIDS | set(_logical_ids())
    for guid in GUID.findall(path.read_text(encoding="utf-8")):
        assert guid.lower() in allowed, f"hard-coded id {guid} in {path.relative_to(ROOT)}"


@pytest.mark.parametrize("path", NOTEBOOKS, ids=lambda p: p.parent.name)
def test_notebooks_use_fabric_source_format_without_pinned_lakehouse(path):
    text = path.read_text(encoding="utf-8")
    assert text.startswith("# Fabric notebook source\n")
    assert '"name": "synapse_pyspark"' in text
    assert "# PARAMETERS CELL ********************" in text
    assert text.count("# CELL ********************") >= 1
    assert "default_lakehouse" not in text          # attach per workspace, never pin Dev ids
    for line in text.splitlines():
        if line.startswith(("# META", "# CELL", "# METADATA", "# PARAMETERS", "# MARKDOWN")):
            continue
    assert "connection_string = \"\"" in text or "connection_string = ''" in text


def _extract():
    return list(_activities(_load(ROOT / "pipelines/BronzeExtractSqlServerEntity.DataPipeline/pipeline-content.json")
                            ["properties"]["activities"]))


def test_landing_copy_writes_json_to_source_system_table_timestamp_path():
    copy = next(a for a in _extract() if a["name"] == "CopyToLanding")
    sink = copy["typeProperties"]["sink"]
    location = sink["datasetSettings"]["typeProperties"]["location"]
    assert sink["type"] == "JsonSink" and location["type"] == "AzureBlobFSLocation"
    assert location["fileName"]["value"] == (
        "@concat(pipeline().parameters.source_table,'_',pipeline().parameters.run_timestamp,'.json')")
    assert location["folderPath"]["value"] == "@pipeline().parameters.landing_folder"   # <source_system>/<table>
    exists = next(a for a in _extract() if a["name"] == "CheckLandingFileExists")
    assert exists["typeProperties"]["fieldList"] == ["exists"]
    assert [d["activity"] for d in copy["dependsOn"]] == ["IfLandingFileExists"]    # never overwrite


def test_staging_copy_truncates_staging_and_stamps_run_id():
    copy = next(a for a in _extract() if a["name"] == "CopyToStaging")
    sink = copy["typeProperties"]["sink"]
    assert sink["type"] == "LakehouseTableSink" and sink["tableActionOption"] == "Overwrite"
    assert sink["datasetSettings"]["typeProperties"]["schema"]["value"] == "@pipeline().parameters.staging_schema"
    assert copy["typeProperties"]["source"]["additionalColumns"] == [
        {"name": "_staging_run_id", "value": {"value": "@pipeline().parameters.run_id", "type": "Expression"}}]


def test_every_copy_failure_is_audited_then_fails_the_pipeline():
    activities = _extract()
    for copy_name in ("CopyToLanding", "CopyToStaging"):
        handlers = [a for a in activities if any(d == {"activity": copy_name, "dependencyConditions": ["Failed"]}
                                                 for d in a.get("dependsOn", []))]
        assert handlers and handlers[0]["typeProperties"]["storedProcedureName"] == "[audit].[usp_log_error]"
    assert sum(1 for a in activities if a["type"] == "Fail") == 4


def test_source_connection_is_parameterised_from_metadata():
    """One extract pipeline serves any SQL Server instance: the Copy source
    connection is the Fabric connection GUID from
    control.source_connection.fabric_connection_id (via fn_active_entities)."""
    activities = _extract()
    for copy_name in ("CopyToLanding", "CopyToStaging"):
        copy = next(a for a in activities if a["name"] == copy_name)
        connection = copy["typeProperties"]["source"]["datasetSettings"]["externalReferences"]["connection"]
        assert connection == {"value": "@pipeline().parameters.source_connection_id", "type": "Expression"}
    guard = next(a for a in activities if a["name"] == "IfSourceConnectionMissing")
    assert guard["typeProperties"]["expression"]["value"] == "@empty(pipeline().parameters.source_connection_id)"
    assert [a["type"] for a in guard["typeProperties"]["ifTrueActivities"]] == [
        "SqlServerStoredProcedure", "SqlServerStoredProcedure", "Fail"]
    landing_if = next(a for a in activities if a["name"] == "IfLandingEnabled")
    assert landing_if["dependsOn"] == [{"activity": "IfSourceConnectionMissing", "dependencyConditions": ["Succeeded"]}]

    pipeline = _load(ROOT / "pipelines/BronzeOrchestrator.DataPipeline/pipeline-content.json")["properties"]
    invoke = next(a for a in _activities(pipeline["activities"]) if a["name"] == "ExtractSqlServerEntity")
    assert invoke["typeProperties"]["parameters"]["source_connection_id"]["value"] == (
        "@coalesce(item().source_connection_id, '')")


def test_orchestrator_run_ids_match_run_manager_format():
    pipeline = _load(ROOT / "pipelines/BronzeOrchestrator.DataPipeline/pipeline-content.json")["properties"]
    by_name = {a["name"]: a for a in _activities(pipeline["activities"])}
    assert "formatDateTime(pipeline().TriggerTime,'yyyyMMdd-HHmmss')" in by_name["SetRunId"]["typeProperties"]["value"]["value"]
    assert by_name["SetRunTimestamp"]["typeProperties"]["value"]["value"] == (
        "@formatDateTime(pipeline().TriggerTime,'yyyyMMddHHmmss')")
    extract = by_name["ExtractSqlServerEntity"]["typeProperties"]["parameters"]
    assert extract["entity_run_id"]["value"] == "@concat(variables('run_id'), '-E', string(item().entity_id))"
    assert by_name["RunBronzeFramework"]["dependsOn"] == [{"activity": "ForEachEntity",
                                                           "dependencyConditions": ["Completed"]}]
    assert by_name["ForEachEntity"]["typeProperties"]["isSequential"] is False
    for param in ("warehouse_connection_string", "audit_connection_string", "key_vault_uri"):
        assert pipeline["parameters"][param]["defaultValue"] == ""      # bound per environment, never committed
