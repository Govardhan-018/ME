"""Episodic memory (§5.2): the conversation transcript + tool/agent outcomes.

Append-only by convention. This is both the audit-trail companion and the
"what did we do last Tuesday" recall surface.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from core.db import get_conn, rows_to_dicts

# Single principal (§1.3) -> one rolling session for v1. A session_id column
# already exists so multi-conversation can be added later without a migration.
DEFAULT_SESSION = "default"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def add_message(role: str, content: str, domain: str | None = None,
                session_id: str = DEFAULT_SESSION) -> int:
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO message (session_id, role, content, domain, created_at) "
            "VALUES (?,?,?,?,?)",
            (session_id, role, content, domain, _now()),
        )
        return cur.lastrowid


def recent_messages(limit: int = 10, session_id: str = DEFAULT_SESSION) -> list[dict]:
    """Most recent turns, returned oldest -> newest (ready to feed an LLM)."""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT role, content, domain, created_at FROM message "
            "WHERE session_id=? ORDER BY id DESC LIMIT ?", (session_id, limit),
        ).fetchall()
    return list(reversed(rows_to_dicts(rows)))


def add_event(kind: str, summary: str, detail: dict | None = None,
              session_id: str = DEFAULT_SESSION) -> int:
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO episodic_event (session_id, kind, summary, detail, created_at) "
            "VALUES (?,?,?,?,?)",
            (session_id, kind, summary, json.dumps(detail or {}), _now()),
        )
        return cur.lastrowid
