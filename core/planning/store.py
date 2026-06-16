"""Persist/resume plans in SQLite — checkpointing for durable jobs (§4.4)."""
from __future__ import annotations

import json
from datetime import datetime, timezone

from core.db import get_conn, rows_to_dicts
from core.planning.schema import Plan

SESSION = "default"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def save(plan: Plan) -> None:
    steps_json = json.dumps([s.to_dict() for s in plan.steps])
    now = _now()
    with get_conn() as conn:
        exists = conn.execute("SELECT 1 FROM plan WHERE id=?", (plan.id,)).fetchone()
        if exists:
            conn.execute(
                "UPDATE plan SET status=?, cursor=?, replans=?, final_answer=?, "
                "pending_confirmation=?, steps=?, updated_at=? WHERE id=?",
                (plan.status, plan.cursor, plan.replans, plan.final_answer,
                 plan.pending_confirmation, steps_json, now, plan.id))
        else:
            conn.execute(
                "INSERT INTO plan (id, session_id, goal, status, cursor, replans, "
                "final_answer, pending_confirmation, steps, created_at, updated_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (plan.id, SESSION, plan.goal, plan.status, plan.cursor, plan.replans,
                 plan.final_answer, plan.pending_confirmation, steps_json, now, now))


def load(plan_id: str) -> Plan | None:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM plan WHERE id=?", (plan_id,)).fetchone()
    return _row_to_plan(row) if row else None


def plan_for_confirmation(confirmation_id: str) -> Plan | None:
    """The paused plan whose blocking step is waiting on this confirmation, if any."""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM plan WHERE pending_confirmation=? AND status='paused'",
            (confirmation_id,)).fetchone()
    return _row_to_plan(row) if row else None


def recent(limit: int = 20) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id, goal, status, cursor, updated_at FROM plan "
            "ORDER BY updated_at DESC LIMIT ?", (limit,)).fetchall()
    return rows_to_dicts(rows)


def _row_to_plan(row) -> Plan:
    d = dict(row)
    d["steps"] = json.loads(d.get("steps") or "[]")
    return Plan.from_dict(d)
