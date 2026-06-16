"""Persistence for the proactive engine: `schedule` + `feed_item` tables.

`schedule` rows are the cron-like jobs (briefings, reflection, named workflows).
`feed_item` rows are what JARVIS surfaces back to you unprompted — a briefing, a
suggestion awaiting approval, or the result of an autonomous run. The HUD's
proactive feed is just `list_feed()`.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Optional

from core.db import get_conn, rows_to_dicts
from core.proactive import triggers


def _now() -> str:
    return datetime.now().replace(microsecond=0).isoformat()


def _id() -> str:
    return uuid.uuid4().hex[:12]


# --------------------------------------------------------------------------- #
# Schedules
# --------------------------------------------------------------------------- #
def add_schedule(name: str, kind: str, trigger: str, goal: str | None = None,
                 enabled: bool = True) -> dict[str, Any]:
    if not triggers.validate(trigger):
        raise ValueError(f"Invalid trigger: {trigger!r}")
    sid = _id()
    now = datetime.now().replace(microsecond=0)
    nxt = triggers.compute_next_run(trigger, now)
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO schedule
               (id, name, kind, trigger, goal, enabled, last_run, next_run,
                last_status, created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (sid, name, kind, trigger, goal, int(enabled), None,
             nxt.isoformat() if nxt else None, None, now.isoformat()),
        )
    return get_schedule(sid)


def get_schedule(sid: str) -> Optional[dict[str, Any]]:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM schedule WHERE id = ?", (sid,)).fetchone()
    return dict(row) if row else None


def find_schedule_by_name(name: str) -> Optional[dict[str, Any]]:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM schedule WHERE lower(name) = ?", (name.strip().lower(),)
        ).fetchone()
    return dict(row) if row else None


def list_schedules(enabled_only: bool = False) -> list[dict[str, Any]]:
    sql = "SELECT * FROM schedule"
    if enabled_only:
        sql += " WHERE enabled = 1"
    sql += " ORDER BY created_at ASC"
    with get_conn() as conn:
        return rows_to_dicts(conn.execute(sql).fetchall())


def set_enabled(sid: str, enabled: bool) -> Optional[dict[str, Any]]:
    sched = get_schedule(sid)
    if not sched:
        return None
    # Re-arm next_run when re-enabling so it doesn't fire for missed windows.
    nxt = triggers.compute_next_run(sched["trigger"], datetime.now()) if enabled else None
    with get_conn() as conn:
        conn.execute(
            "UPDATE schedule SET enabled = ?, next_run = ? WHERE id = ?",
            (int(enabled), nxt.isoformat() if nxt else None, sid),
        )
    return get_schedule(sid)


def mark_run(sid: str, status: str, when: datetime | None = None) -> None:
    """Record an execution and advance next_run from the trigger."""
    sched = get_schedule(sid)
    if not sched:
        return
    when = when or datetime.now().replace(microsecond=0)
    nxt = triggers.compute_next_run(sched["trigger"], when)
    with get_conn() as conn:
        conn.execute(
            "UPDATE schedule SET last_run = ?, last_status = ?, next_run = ? WHERE id = ?",
            (when.isoformat(), status, nxt.isoformat() if nxt else None, sid),
        )


def delete_schedule(sid: str) -> bool:
    with get_conn() as conn:
        return conn.execute("DELETE FROM schedule WHERE id = ?", (sid,)).rowcount > 0


# --------------------------------------------------------------------------- #
# Feed (proactive outputs)
# --------------------------------------------------------------------------- #
def add_feed(kind: str, title: str, body: str = "", source: str | None = None,
             confirmation_id: str | None = None) -> dict[str, Any]:
    fid = _id()
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO feed_item
               (id, kind, title, body, source, status, confirmation_id, created_at)
               VALUES (?,?,?,?,?,?,?,?)""",
            (fid, kind, title, body, source, "unread", confirmation_id, _now()),
        )
    return get_feed(fid)


def get_feed(fid: str) -> Optional[dict[str, Any]]:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM feed_item WHERE id = ?", (fid,)).fetchone()
    return dict(row) if row else None


def list_feed(limit: int = 30, status: str | None = None) -> list[dict[str, Any]]:
    sql, params = "SELECT * FROM feed_item", []
    if status:
        sql += " WHERE status = ?"
        params.append(status)
    sql += " ORDER BY created_at DESC LIMIT ?"
    params.append(limit)
    with get_conn() as conn:
        return rows_to_dicts(conn.execute(sql, params).fetchall())


def mark_feed(fid: str, status: str) -> Optional[dict[str, Any]]:
    with get_conn() as conn:
        conn.execute("UPDATE feed_item SET status = ? WHERE id = ?", (status, fid))
    return get_feed(fid)


def unread_count() -> int:
    with get_conn() as conn:
        return conn.execute(
            "SELECT COUNT(*) AS n FROM feed_item WHERE status = 'unread'"
        ).fetchone()["n"]
