"""Semantic memory (§5.3): durable facts about the user — prefs, projects,
people, goals. Stored in SQLite with an optional embedding for vector recall.

Recall uses vector cosine when embeddings are available, and falls back to a
keyword/recency query otherwise (see embeddings.py).
"""
from __future__ import annotations

from datetime import datetime, timezone

from core.db import get_conn, rows_to_dicts
from core.memory import embeddings

_WEAK_MATCH_FLOOR = 0.2  # vector scores below this aren't worth surfacing


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def add_fact(fact: str, subject: str | None = None, confidence: float = 0.7,
             source: str = "reflection") -> int:
    emb = embeddings.embed(fact)
    now = _now()
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO memory_fact "
            "(subject, fact, confidence, source, created_at, last_seen, embedding) "
            "VALUES (?,?,?,?,?,?,?)",
            (subject, fact, confidence, source, now, now, emb),
        )
        return cur.lastrowid


def all_facts() -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id, subject, fact, confidence, source, last_seen FROM memory_fact "
            "ORDER BY confidence DESC, id DESC"
        ).fetchall()
    return rows_to_dicts(rows)


def fact_texts() -> set[str]:
    with get_conn() as conn:
        rows = conn.execute("SELECT fact FROM memory_fact").fetchall()
    return {r["fact"] for r in rows}


def search(query: str, limit: int = 5) -> list[dict]:
    """Vector search when embeddings are available; else keyword + recency."""
    qemb = embeddings.embed(query)
    if qemb is not None:
        with get_conn() as conn:
            rows = conn.execute(
                "SELECT id, subject, fact, confidence, source, embedding FROM memory_fact"
            ).fetchall()
        scored = [
            (embeddings.cosine(qemb, r["embedding"]), r)
            for r in rows if r["embedding"] is not None
        ]
        scored.sort(key=lambda x: x[0], reverse=True)
        out = []
        for score, r in scored[:limit]:
            if score <= _WEAK_MATCH_FLOOR:
                continue
            d = {k: r[k] for k in ("id", "subject", "fact", "confidence", "source")}
            d["score"] = round(score, 3)
            out.append(d)
        if out:
            return out
        # nothing cleared the floor -> fall through to keyword search

    like = f"%{query.strip()}%"
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id, subject, fact, confidence, source FROM memory_fact "
            "WHERE fact LIKE ? OR subject LIKE ? ORDER BY confidence DESC, id DESC LIMIT ?",
            (like, like, limit),
        ).fetchall()
    return rows_to_dicts(rows)
