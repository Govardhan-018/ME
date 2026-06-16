"""
SQLite spine for JARVIS — the single local datastore.

This is §18 of the design ("Postgres is the spine") realized in **SQLite** for a
single-user, local-first v1. One file holds everything the brain must remember
and be accountable for:

  * audit_event     — append-only log of every gated action (security backbone
                      AND episodic memory, per §15.4)
  * message         — conversation transcript (episodic recall: "what did we do")
  * episodic_event  — tool/agent outcomes and decisions
  * memory_fact     — durable semantic facts about the user, with an optional
                      embedding blob for vector recall
  * calendar_event  — local-first calendar (source of truth; optional Google sync)
  * schedule        — proactive scheduled jobs/workflows (the cron-like spine)
  * feed_item       — proactive outputs JARVIS surfaces (briefings, suggestions)
  * trace           — observability: one row per orchestrated turn, with spans

Why SQLite, not Postgres+Qdrant (the documented production target)? Rule #3:
add a component only when a real failure demands it. For one principal on one
machine, SQLite is zero-install, transactional, and good for years. The access
functions here are the seam — swap the backend later without touching callers.
Override the location with JARVIS_DB_PATH.
"""
from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
DB_PATH = Path(os.getenv("JARVIS_DB_PATH", _PROJECT_ROOT / "data" / "jarvis.db")).resolve()

_SCHEMA = """
CREATE TABLE IF NOT EXISTS audit_event (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    ts         TEXT NOT NULL,
    actor      TEXT NOT NULL,
    tool       TEXT,
    action     TEXT,
    risk_tier  TEXT,
    decision   TEXT NOT NULL,
    mode       TEXT,
    scope      TEXT,
    detail     TEXT
);
CREATE TABLE IF NOT EXISTS message (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    role       TEXT NOT NULL,
    content    TEXT NOT NULL,
    domain     TEXT,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS episodic_event (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT,
    kind       TEXT NOT NULL,
    summary    TEXT,
    detail     TEXT,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS memory_fact (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    subject    TEXT,
    fact       TEXT NOT NULL,
    confidence REAL DEFAULT 0.7,
    source     TEXT,
    created_at TEXT NOT NULL,
    last_seen  TEXT NOT NULL,
    embedding  BLOB
);
CREATE TABLE IF NOT EXISTS plan (
    id                   TEXT PRIMARY KEY,
    session_id           TEXT,
    goal                 TEXT NOT NULL,
    status               TEXT NOT NULL,
    cursor               INTEGER DEFAULT 0,
    replans              INTEGER DEFAULT 0,
    final_answer         TEXT,
    pending_confirmation TEXT,
    steps                TEXT,
    created_at           TEXT NOT NULL,
    updated_at           TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS calendar_event (
    id          TEXT PRIMARY KEY,
    title       TEXT NOT NULL,
    start_ts    TEXT NOT NULL,
    end_ts      TEXT,
    all_day     INTEGER DEFAULT 0,
    location    TEXT,
    notes       TEXT,
    source      TEXT DEFAULT 'local',
    external_id TEXT,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS schedule (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    kind        TEXT NOT NULL,
    trigger     TEXT NOT NULL,
    goal        TEXT,
    enabled     INTEGER DEFAULT 1,
    last_run    TEXT,
    next_run    TEXT,
    last_status TEXT,
    created_at  TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS feed_item (
    id              TEXT PRIMARY KEY,
    kind            TEXT NOT NULL,
    title           TEXT,
    body            TEXT,
    source          TEXT,
    status          TEXT DEFAULT 'unread',
    confirmation_id TEXT,
    created_at      TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS trace (
    id          TEXT PRIMARY KEY,
    actor       TEXT NOT NULL,
    command     TEXT,
    domain      TEXT,
    status      TEXT,
    duration_ms INTEGER,
    spans       TEXT,
    created_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_message_session ON message(session_id, id);
CREATE INDEX IF NOT EXISTS idx_fact_subject ON memory_fact(subject);
CREATE INDEX IF NOT EXISTS idx_plan_pending ON plan(pending_confirmation);
CREATE INDEX IF NOT EXISTS idx_calendar_start ON calendar_event(start_ts);
CREATE INDEX IF NOT EXISTS idx_feed_created ON feed_item(created_at);
CREATE INDEX IF NOT EXISTS idx_trace_created ON trace(created_at);
"""

_initialized = False


@contextmanager
def get_conn() -> Iterator[sqlite3.Connection]:
    """Yield a fresh connection (thread-safe: one per call). Commits on success.

    Tables are created lazily on first use so every entrypoint — the API, the
    voice daemon thread, the CLI, tests — gets a ready database without a
    separate bootstrap step.
    """
    global _initialized
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), timeout=30.0)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        if not _initialized:
            conn.executescript(_SCHEMA)
            _initialized = True
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    """Explicitly ensure the schema exists (optional — get_conn does this lazily)."""
    with get_conn():
        pass


def rows_to_dicts(rows) -> list[dict]:
    return [dict(r) for r in rows]
