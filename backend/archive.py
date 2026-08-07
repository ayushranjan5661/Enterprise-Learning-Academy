"""Durable archive of human-approved programmes.

Separate from `storage.py` on purpose. `storage` holds *live* run state: mutable, rewritten
on every agent step, and sitting on a filesystem that a host like Render's free tier discards
on restart. This module holds the opposite — an immutable snapshot taken at the moment a human
approved a programme, in a real database that outlives the container.

One code path serves both SQLite and Postgres via `DATABASE_URL`:
    sqlite:///.../data/archive.db      (default; fine locally, lost on an ephemeral host)
    postgresql://user:pass@host/db     (Neon / Supabase / Render Postgres — survives restarts)
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import (
    JSON,
    Column,
    Float,
    Index,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    create_engine,
    delete,
    func,
    insert,
    or_,
    select,
)
from sqlalchemy.engine import Engine

from backend import config, cost_tracker
from backend.schemas import ProgrammeState

log = logging.getLogger("archive")

metadata = MetaData()

# Summary columns are denormalised out of `state` so the list view can sort and search
# without deserialising every full programme.
approved_programmes = Table(
    "approved_programmes",
    metadata,
    Column("run_id", String(64), primary_key=True),
    Column("programme_title", String(500), nullable=False, default=""),
    Column("manager_request", Text, nullable=False, default=""),
    Column("approved_at", String(32), nullable=False, index=True),
    Column("created_at", String(32), nullable=False, default=""),
    Column("module_count", Integer, nullable=False, default=0),
    Column("total_duration_hours", Float, nullable=False, default=0.0),
    Column("revision_count", Integer, nullable=False, default=0),
    Column("human_revision_count", Integer, nullable=False, default=0),
    Column("cost_usd", Float, nullable=False, default=0.0),
    Column("total_tokens", Integer, nullable=False, default=0),
    # The complete ProgrammeState at approval time — curriculum, content plan, assessments,
    # quality review, full history and cost log. Everything needed to reproduce the PDF later.
    Column("state", JSON, nullable=False),
)

Index("ix_approved_programmes_title", approved_programmes.c.programme_title)

_engine: Engine | None = None

SUMMARY_COLUMNS = [
    approved_programmes.c.run_id,
    approved_programmes.c.programme_title,
    approved_programmes.c.manager_request,
    approved_programmes.c.approved_at,
    approved_programmes.c.created_at,
    approved_programmes.c.module_count,
    approved_programmes.c.total_duration_hours,
    approved_programmes.c.revision_count,
    approved_programmes.c.human_revision_count,
    approved_programmes.c.cost_usd,
    approved_programmes.c.total_tokens,
]


def engine() -> Engine:
    global _engine
    if _engine is None:
        url = config.DATABASE_URL
        kwargs: dict[str, Any] = {"future": True, "pool_pre_ping": True}
        if url.startswith("sqlite"):
            # Approval runs on Starlette's threadpool, not the thread that opened the
            # connection; SQLite rejects that by default.
            kwargs["connect_args"] = {"check_same_thread": False}
        _engine = create_engine(url, **kwargs)
    return _engine


def init() -> None:
    """Create the table if absent. Safe to call on every boot."""
    config.ensure_dirs()
    metadata.create_all(engine())


def _summarise(state: ProgrammeState) -> dict[str, Any]:
    curriculum = state.curriculum or {}
    modules = curriculum.get("modules") or []
    totals = cost_tracker.summarise(state.cost_log)["total"]
    return {
        "programme_title": (curriculum.get("programme_title") or "Untitled programme")[:500],
        "module_count": len(modules),
        "total_duration_hours": float(curriculum.get("total_duration_hours") or 0.0),
        "cost_usd": float(totals.get("cost_usd") or 0.0),
        "total_tokens": int(totals.get("total_tokens") or 0),
    }


def save_approved(state: ProgrammeState, approved_at: str) -> dict[str, Any]:
    """Snapshot an approved programme. Replaces any prior snapshot for the same run.

    A run can be approved, rejected by the human, revised and approved again, so `run_id`
    is not unique over time. The latest approval is the one that counts — earlier snapshots
    are superseded, not kept as versions.
    """
    row = {
        "run_id": state.run_id,
        "manager_request": state.manager_request,
        "approved_at": approved_at,
        "created_at": state.created_at or "",
        "revision_count": state.revision_count,
        "human_revision_count": state.human_revision_count,
        "state": state.model_dump(mode="json"),
        **_summarise(state),
    }

    with engine().begin() as conn:
        conn.execute(
            delete(approved_programmes).where(approved_programmes.c.run_id == state.run_id)
        )
        conn.execute(insert(approved_programmes).values(**row))

    log.info("archived approved programme %s (%s)", state.run_id, row["programme_title"])
    return {k: v for k, v in row.items() if k != "state"}


def list_approved(limit: int = 25, offset: int = 0, q: str | None = None) -> dict[str, Any]:
    """Newest-first page of archived programmes, without the heavy `state` blob."""
    where = None
    if q:
        pattern = f"%{q.strip()}%"
        where = or_(
            approved_programmes.c.programme_title.ilike(pattern),
            approved_programmes.c.manager_request.ilike(pattern),
        )

    count_stmt = select(func.count()).select_from(approved_programmes)
    stmt = select(*SUMMARY_COLUMNS).order_by(approved_programmes.c.approved_at.desc())
    if where is not None:
        count_stmt = count_stmt.where(where)
        stmt = stmt.where(where)

    with engine().connect() as conn:
        total = conn.execute(count_stmt).scalar_one()
        rows = conn.execute(stmt.limit(limit).offset(offset)).mappings().all()

    return {"total": total, "limit": limit, "offset": offset, "programmes": [dict(r) for r in rows]}


def get_approved(run_id: str) -> dict[str, Any] | None:
    """Full archived snapshot, including the complete programme state."""
    with engine().connect() as conn:
        row = conn.execute(
            select(approved_programmes).where(approved_programmes.c.run_id == run_id)
        ).mappings().first()
    return dict(row) if row else None


def get_state(run_id: str) -> ProgrammeState | None:
    """Rehydrate an archived snapshot back into a ProgrammeState (e.g. to re-render a PDF)."""
    row = get_approved(run_id)
    if row is None:
        return None
    try:
        return ProgrammeState(**row["state"])
    except Exception:
        log.exception("archived state for %s failed validation", run_id)
        return None


def count() -> int:
    try:
        with engine().connect() as conn:
            return conn.execute(select(func.count()).select_from(approved_programmes)).scalar_one()
    except Exception as exc:  # table missing / DB unreachable — surfaced in /api/health
        log.warning("archive count failed: %s", exc)
        return -1
