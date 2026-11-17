"""Single-direction run state with atomic persistence.

The state file is the installer's memory. It records facts and evidence paths,
never device secrets. A run can only advance through the transitions below; any
unexpected write state becomes UNKNOWN and blocks a new session until a
read-only review resolves it.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path

from .errors import InstallerError


class Stage(str, Enum):
    IDLE = "idle"
    ENV_READY = "env_ready"
    CONNECTED = "connected"
    INSPECTED = "inspected"
    SCOPE_CONFIRMED = "scope_confirmed"
    BACKUP_DONE = "backup_done"
    PREWRITE_INSPECTED = "prewrite_inspected"
    PATCHED = "patched"
    PROPS_DONE = "props_done"
    WRITE_CLOSED = "write_closed"
    POST_VERIFIED = "post_verified"
    WBI_AVAILABLE = "wbi_available"
    WBI_PREPARED = "wbi_prepared"
    WBI_CONFIRMED = "wbi_confirmed"
    WBI_DROPPED = "wbi_dropped"
    DONE = "done"
    STOPPED = "stopped"
    UNKNOWN = "unknown"
    RECOVERY_REQUIRED = "recovery_required"


ALLOWED: dict[Stage, set[Stage]] = {
    Stage.IDLE: {Stage.ENV_READY, Stage.STOPPED},
    Stage.ENV_READY: {Stage.CONNECTED, Stage.STOPPED},
    Stage.CONNECTED: {Stage.INSPECTED, Stage.WBI_PREPARED, Stage.STOPPED},
    Stage.INSPECTED: {Stage.SCOPE_CONFIRMED, Stage.STOPPED},
    Stage.SCOPE_CONFIRMED: {Stage.BACKUP_DONE, Stage.STOPPED},
    Stage.BACKUP_DONE: {Stage.PREWRITE_INSPECTED, Stage.STOPPED},
    Stage.PREWRITE_INSPECTED: {Stage.PATCHED, Stage.STOPPED, Stage.UNKNOWN},
    Stage.PATCHED: {Stage.PROPS_DONE, Stage.UNKNOWN},
    Stage.PROPS_DONE: {Stage.WRITE_CLOSED, Stage.UNKNOWN},
    Stage.WRITE_CLOSED: {Stage.POST_VERIFIED, Stage.UNKNOWN},
    Stage.POST_VERIFIED: {Stage.DONE, Stage.WBI_AVAILABLE, Stage.STOPPED},
    Stage.WBI_AVAILABLE: {Stage.WBI_PREPARED, Stage.STOPPED},
    Stage.WBI_PREPARED: {Stage.WBI_CONFIRMED, Stage.STOPPED},
    Stage.WBI_CONFIRMED: {Stage.WBI_DROPPED, Stage.UNKNOWN},
    Stage.WBI_DROPPED: {Stage.DONE, Stage.UNKNOWN},
    Stage.STOPPED: set(),
    Stage.UNKNOWN: {Stage.RECOVERY_REQUIRED},
    Stage.RECOVERY_REQUIRED: set(),
    Stage.DONE: set(),
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class RunState:
    path: Path
    stage: Stage = Stage.IDLE
    facts: dict = field(default_factory=dict)
    history: list[dict] = field(default_factory=list)
    created: str = field(default_factory=_now)
    updated: str = field(default_factory=_now)

    def to_dict(self) -> dict:
        return {
            "schema": 1,
            "stage": self.stage.value,
            "facts": self.facts,
            "history": self.history,
            "created": self.created,
            "updated": self.updated,
        }

    def save(self) -> None:
        self.updated = _now()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(json.dumps(self.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, self.path)

    def advance(self, stage: Stage, facts: dict | None = None) -> None:
        if stage not in ALLOWED[self.stage]:
            raise InstallerError(f"Invalid state transition: {self.stage.value} -> {stage.value}")
        self.history.append({"at": _now(), "from": self.stage.value, "to": stage.value})
        self.stage = stage
        if facts:
            self.facts.update(facts)
        self.save()

    @classmethod
    def load_or_create(cls, path: Path) -> "RunState":
        if not path.is_file():
            state = cls(path=path)
            state.save()
            return state
        raw = json.loads(path.read_text(encoding="utf-8"))
        if raw.get("schema") != 1:
            raise InstallerError(f"Unsupported state schema in {path}")
        return cls(
            path=path,
            stage=Stage(raw["stage"]),
            facts=raw.get("facts", {}),
            history=raw.get("history", []),
            created=raw.get("created", _now()),
            updated=raw.get("updated", _now()),
        )
