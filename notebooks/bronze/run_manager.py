"""Run Manager: framework run identity.

  run_id         yyyyMMdd-HHmmss-XXXXXX      (spec section 40)
  entity_run_id  <run_id>-E<entity_id>       deterministic, so the extract
                                             pipeline and the framework
                                             notebook address the same audit
                                             row without a lookup
  run_timestamp  yyyyMMddHHmmss              landing file-name timestamp

The pipeline builds the same values with expressions (see
fabric_items/pipelines/BronzeOrchestrator.DataPipeline); these functions
are the notebook-side equivalents and the reference for the format.
"""

import re
import secrets
import string
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from typing import Optional

RUN_ID_PATTERN = re.compile(r"^\d{8}-\d{6}-[0-9A-Z]{6}$")
RUN_TIMESTAMP_PATTERN = re.compile(r"^\d{14}$")
_SUFFIX_ALPHABET = string.ascii_uppercase + string.digits


def _utc(now: Optional[datetime]) -> datetime:
    now = now or datetime.now(timezone.utc)
    return now.astimezone(timezone.utc) if now.tzinfo else now.replace(tzinfo=timezone.utc)


def new_run_id(now: Optional[datetime] = None, suffix: Optional[str] = None) -> str:
    now = _utc(now)
    suffix = suffix or "".join(secrets.choice(_SUFFIX_ALPHABET) for _ in range(6))
    run_id = f"{now:%Y%m%d-%H%M%S}-{suffix.upper()}"
    if not RUN_ID_PATTERN.match(run_id):
        raise ValueError(f"invalid run_id suffix: {suffix!r}")
    return run_id


def run_timestamp(now: Optional[datetime] = None) -> str:
    """yyyyMMddHHmmss (UTC). The spec's literal 'yyyymmddhhss' omits minutes
    and would collide within an hour; minutes and seconds are both kept."""
    return f"{_utc(now):%Y%m%d%H%M%S}"


def run_timestamp_from_run_id(run_id: str) -> str:
    if not RUN_ID_PATTERN.match(run_id):
        raise ValueError(f"not a framework run_id: {run_id!r}")
    return run_id[:8] + run_id[9:15]


def entity_run_id(run_id: str, entity_id: int) -> str:
    return f"{run_id}-E{int(entity_id)}"


@dataclass(frozen=True)
class RunContext:
    """Everything that identifies one framework run, threaded through every
    component and every audit row."""

    run_id: str
    run_timestamp: str
    environment: str
    framework_name: str = "BronzeFramework"
    workspace_id: Optional[str] = None
    workspace_name: Optional[str] = None
    pipeline_name: Optional[str] = None
    pipeline_run_id: Optional[str] = None
    notebook_name: Optional[str] = None
    trigger_type: str = "MANUAL"
    trigger_name: Optional[str] = None
    initiated_by: Optional[str] = None
    entity_group: Optional[str] = None

    def __post_init__(self):
        if not RUN_TIMESTAMP_PATTERN.match(self.run_timestamp):
            raise ValueError(f"run_timestamp must be yyyyMMddHHmmss, got {self.run_timestamp!r}")
        if self.environment.upper() != self.environment:
            object.__setattr__(self, "environment", self.environment.upper())

    def entity_run_id(self, entity_id: int) -> str:
        return entity_run_id(self.run_id, entity_id)

    @classmethod
    def create(cls, environment: str, run_id: Optional[str] = None, run_ts: Optional[str] = None,
               now: Optional[datetime] = None, **kwargs) -> "RunContext":
        """New context. When only run_id is given, the timestamp is derived
        from it so landing file names and the run id always agree."""
        if run_id and not run_ts:
            run_ts = run_timestamp_from_run_id(run_id) if RUN_ID_PATTERN.match(run_id) else run_timestamp(now)
        run_id = run_id or new_run_id(now)
        run_ts = run_ts or run_timestamp_from_run_id(run_id)
        return cls(run_id=run_id, run_timestamp=run_ts, environment=environment, **kwargs)

    def with_notebook_context(self, notebookutils_module=None) -> "RunContext":
        """Fill workspace/notebook identity from notebookutils.runtime.context
        when running inside Fabric; a no-op elsewhere."""
        try:
            if notebookutils_module is None:
                import notebookutils as notebookutils_module  # Fabric-injected runtime module
            ctx = dict(notebookutils_module.runtime.context)
        except Exception:
            return self
        return replace(
            self,
            workspace_id=self.workspace_id or ctx.get("currentWorkspaceId"),
            workspace_name=self.workspace_name or ctx.get("currentWorkspaceName"),
            notebook_name=self.notebook_name or ctx.get("currentNotebookName"),
            initiated_by=self.initiated_by or ctx.get("userName") or ctx.get("userId"),
        )
