"""Run directories and evidence writing.

Evidence is local-only. Large camera snapshots stay in the upstream session
directory; this module records their paths and hashes in a small summary.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class RunDir:
    path: Path

    @classmethod
    def create(cls, base: Path, kind: str) -> "RunDir":
        base = Path(base).expanduser().resolve()
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        run = base / f"{stamp}-{kind}-{uuid.uuid4().hex[:6]}"
        run.mkdir(parents=True, exist_ok=False)
        return cls(run)

    @property
    def session_dir(self) -> Path:
        return self.path / "session"

    @property
    def state_path(self) -> Path:
        return self.path / "state.json"

    def write_json(self, name: str, data: dict) -> Path:
        target = self.path / name
        target.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        return target

    def append_event(self, event: str, data: dict | None = None) -> None:
        record = {"at": _now(), "event": event}
        if data:
            record.update(data)
        with (self.path / "run.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
