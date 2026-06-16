"""Append-only audit log (§15.4).

We only ever INSERT here — never update, never delete. This table is both the
security backbone (who proposed/approved/denied what, and which mode was active)
and a slice of episodic memory.
"""
from __future__ import annotations

from datetime import datetime, timezone

from core.db import get_conn, rows_to_dicts
from core.security.tiers import ActionRequest, Decision


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def record(action: ActionRequest, decision: Decision, mode: str,
           actor: str = "orchestrator", detail: str = "") -> int:
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO audit_event "
            "(ts, actor, tool, action, risk_tier, decision, mode, scope, detail) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (_now(), actor, action.tool, action.action, action.risk_tier.value,
             decision.value, mode, action.scope, detail),
        )
        return cur.lastrowid


def recent(limit: int = 50) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM audit_event ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
    return rows_to_dicts(rows)
