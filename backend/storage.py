"""Run persistence: in-memory dict (fast reads for polling) + JSON file per run."""

from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from typing import Any

from backend import config
from backend.schemas import ProgrammeState

_LOCK = threading.RLock()
_RUNS: dict[str, ProgrammeState] = {}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def new_id() -> str:
    from uuid import uuid4

    return f"run_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}_{uuid4().hex[:6]}"


def record(state: ProgrammeState, agent: str, event: str, detail: str = "") -> None:
    state.history.append(
        {
            "agent": agent,
            "event": event,
            "revision": state.revision_count,
            "detail": detail,
            "timestamp": now_iso(),
        }
    )


def save(state: ProgrammeState) -> ProgrammeState:
    state.updated_at = now_iso()
    with _LOCK:
        _RUNS[state.run_id] = state
        config.ensure_dirs()
        path = config.RUNS_DIR / f"{state.run_id}.json"
        path.write_text(
            json.dumps(state.model_dump(), indent=2, default=str), encoding="utf-8"
        )
    return state


def get(run_id: str) -> ProgrammeState | None:
    with _LOCK:
        if run_id in _RUNS:
            return _RUNS[run_id]
    path = config.RUNS_DIR / f"{run_id}.json"
    if not path.exists():
        return None
    try:
        state = ProgrammeState(**json.loads(path.read_text(encoding="utf-8")))
    except Exception:
        return None
    with _LOCK:
        _RUNS[run_id] = state
    return state


def list_runs(limit: int = 25) -> list[dict[str, Any]]:
    config.ensure_dirs()
    rows: list[dict[str, Any]] = []
    for path in sorted(config.RUNS_DIR.glob("run_*.json"), reverse=True)[:limit]:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        rows.append(
            {
                "run_id": data.get("run_id"),
                "status": data.get("status"),
                "manager_request": (data.get("manager_request") or "")[:120],
                "revision_count": data.get("revision_count", 0),
                "updated_at": data.get("updated_at"),
            }
        )
    return rows
