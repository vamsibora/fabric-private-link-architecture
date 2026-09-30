"""Landing Manager: the optional Storage Account landing layer (spec
sections 5-7, 48).

When entity.landing_enabled (ANDed with framework_configuration
landing_globally_enabled), the extract pipeline's Copy activity writes the
raw source extract as JSON to the ADLS Gen2 landing container:

    <landing container>/<source_system>/<table_name>/<table_name>_<yyyyMMddHHmmss>.json
    e.g. landing/SQLServer/Customer/Customer_20260930081205.json

The timestamp is the FRAMEWORK RUN's timestamp (run_manager), so every file
of a run shares it and the file name alone identifies the run. Files are
never overwritten: the pipeline checks existence first (Get Metadata ->
Fail) and this module enforces the same rule on the notebook side.

The Bronze Lakehouse reads the container through a OneLake shortcut
(framework_configuration.landing_lakehouse_path, default Files/landing) --
the same pattern as the working Dev reference notebook
(spark.read.json("Files/landing/<dir>/<table>/*.json")). The Storage
Account itself stays private (private endpoint / trusted workspace access).

When landing is disabled nothing is written to the Storage Account; the
copy goes straight to staging (see staging_manager).
"""

import re
from dataclasses import dataclass
from typing import Callable, Iterable, List, Optional

from notebooks.bronze.error_manager import STAGE_LANDING, LandingFileExistsError
from notebooks.bronze.models import EntityConfig
from notebooks.bronze.run_manager import RUN_TIMESTAMP_PATTERN

_SAFE_SEGMENT = re.compile(r"^[A-Za-z0-9_.\-]+$")


def _segment(value: str, what: str) -> str:
    if not value or not _SAFE_SEGMENT.match(value) or value in (".", ".."):
        raise ValueError(f"{what} {value!r} is not a safe landing path segment")
    return value


def landing_folder(entity: EntityConfig) -> str:
    """<source_system>/<table_name> (relative to the landing container)."""
    return f"{_segment(entity.source_system, 'source_system')}/{_segment(entity.source_table, 'table_name')}"


def landing_file_name(entity: EntityConfig, run_ts: str) -> str:
    if not RUN_TIMESTAMP_PATTERN.match(run_ts or ""):
        raise ValueError(f"run timestamp must be yyyyMMddHHmmss, got {run_ts!r}")
    return f"{_segment(entity.source_table, 'table_name')}_{run_ts}.json"


def landing_relative_path(entity: EntityConfig, run_ts: str) -> str:
    """<source_system>/<table>/<table>_<ts>.json -- the value recorded in
    audit.entity_run.landing_path and audit.file.file_path."""
    return f"{landing_folder(entity)}/{landing_file_name(entity, run_ts)}"


def lakehouse_path(lakehouse_root: str, relative_path: str) -> str:
    """Path Spark reads through the OneLake shortcut, e.g.
    Files/landing/SQLServer/Customer/Customer_20260930081205.json."""
    return f"{lakehouse_root.rstrip('/')}/{relative_path.lstrip('/')}"


def parse_run_timestamp(file_name: str, table_name: str) -> Optional[str]:
    match = re.fullmatch(re.escape(table_name) + r"_(\d{14})\.json", file_name)
    return match.group(1) if match else None


@dataclass(frozen=True)
class LandingFile:
    relative_path: str
    file_name: str
    run_timestamp: str
    size_bytes: Optional[int] = None


def replayable_files(entity: EntityConfig, file_names: Iterable[str], since_run_ts: Optional[str] = None,
                     sizes: Optional[dict] = None) -> List[LandingFile]:
    """Landing files for the entity, oldest first, optionally from a run
    timestamp onwards -- the replay order."""
    files = []
    for name in file_names:
        ts = parse_run_timestamp(name, entity.source_table)
        if ts is None or (since_run_ts and ts < since_run_ts):
            continue
        files.append(LandingFile(f"{landing_folder(entity)}/{name}", name, ts, (sizes or {}).get(name)))
    return sorted(files, key=lambda f: f.run_timestamp)


class LandingManager:
    """notebookutils.fs adapter (injectable for tests)."""

    def __init__(self, lakehouse_root: str, container: str, fs=None):
        self.lakehouse_root = lakehouse_root
        self.container = container
        self._fs = fs

    @property
    def fs(self):
        if self._fs is None:
            import notebookutils  # Fabric-injected runtime module

            self._fs = notebookutils.fs
        return self._fs

    def path_for(self, entity: EntityConfig, run_ts: str) -> str:
        return lakehouse_path(self.lakehouse_root, landing_relative_path(entity, run_ts))

    def exists(self, path: str) -> bool:
        try:
            return bool(self.fs.exists(path))
        except Exception:
            return False

    def assert_not_exists(self, entity: EntityConfig, run_ts: str) -> str:
        path = self.path_for(entity, run_ts)
        if self.exists(path):
            raise LandingFileExistsError(f"landing file already exists, refusing to overwrite: {path}",
                                         stage=STAGE_LANDING)
        return path

    def file_size(self, path: str) -> Optional[int]:
        try:
            parent, _, name = path.rpartition("/")
            for info in self.fs.ls(parent):
                if getattr(info, "name", None) == name:
                    return int(getattr(info, "size", 0))
        except Exception:
            return None
        return None

    def list_replayable(self, entity: EntityConfig, since_run_ts: Optional[str] = None) -> List[LandingFile]:
        folder = lakehouse_path(self.lakehouse_root, landing_folder(entity))
        try:
            infos = list(self.fs.ls(folder))
        except Exception:
            return []
        names = [getattr(i, "name", "") for i in infos]
        sizes = {getattr(i, "name", ""): getattr(i, "size", None) for i in infos}
        return replayable_files(entity, names, since_run_ts, sizes)

    def resolve(self, entity: EntityConfig, run_ts: str, recorded_path: Optional[str] = None) -> str:
        """Lakehouse path of this run's landing file. Prefers the path the
        pipeline recorded in audit (entity_run.landing_path)."""
        if recorded_path:
            return lakehouse_path(self.lakehouse_root, recorded_path)
        return self.path_for(entity, run_ts)


def default_fs_writer() -> Callable[[str, str], None]:  # pragma: no cover - Fabric runtime only
    import notebookutils

    return lambda path, content: notebookutils.fs.put(path, content, overwrite=False)
