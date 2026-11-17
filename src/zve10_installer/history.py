"""Summaries of the latest install/WBI run for the GUI and diagnostics."""

from __future__ import annotations

import json
from pathlib import Path

STAGE_LABELS = {
    "idle": "准备中",
    "env_ready": "准备中",
    "connected": "已连接",
    "inspected": "已读取状态",
    "scope_confirmed": "已确认区域",
    "backup_done": "备份完成",
    "prewrite_inspected": "写前检查完成",
    "patched": "写入后中断，结果未知",
    "props_done": "属性写入后中断，结果未知",
    "write_closed": "写入完成，待冷启动验收",
    "post_verified": "已验收",
    "wbi_available": "需要 WBI",
    "wbi_prepared": "WBI 已准备",
    "wbi_confirmed": "WBI 写入中",
    "wbi_dropped": "WBI 已写入，待冷启动",
    "done": "已完成",
    "stopped": "已停止（未完成）",
    "unknown": "结果未知，需要复核",
    "recovery_required": "需要恢复",
}

UNFINISHED_STAGES = {
    "patched",
    "props_done",
    "wbi_confirmed",
    "unknown",
    "recovery_required",
}


def latest(runs_dir: Path) -> dict | None:
    runs_dir = Path(runs_dir).expanduser().resolve()
    if not runs_dir.is_dir():
        return None
    runs = sorted(
        (path for path in runs_dir.iterdir() if (path / "state.json").is_file()),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    if not runs:
        return None
    run = runs[0]
    try:
        data = json.loads((run / "state.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    stage = str(data.get("stage", "unknown"))
    facts = data.get("facts") or {}
    error = facts.get("error") or facts.get("last_error")
    return {
        "run_dir": str(run),
        "stage": stage,
        "label": STAGE_LABELS.get(stage, stage),
        "error": error,
        "updated": data.get("updated"),
        "history": len(data.get("history") or []),
        "unfinished": stage in UNFINISHED_STAGES,
    }
