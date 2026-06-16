"""
Reflection / consolidation (§5.5) — the "secret sauce".

Reads recent conversation, asks a local model to extract durable facts worth
keeping for months, dedups against what's already known, and writes the new ones
into semantic memory. This is what turns a raw episodic log into a stable model
of the user.

v1 is triggered on demand (POST /api/memory/reflect or this module's CLI).
Wiring it to a nightly scheduler is Phase 7.
"""
from __future__ import annotations

import json
import os
import re

import requests

from core.memory import episodic, semantic

OLLAMA_BASE = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
REFLECT_MODEL = os.getenv("JARVIS_REFLECT_MODEL", "qwen2.5:7b")

_SYSTEM = """You extract durable, long-term facts about the user from a conversation.
Return ONLY a JSON array of short factual strings worth remembering for months:
stable preferences, projects, tools they use, people, goals, constraints.
Ignore one-off task details, pleasantries, and anything ephemeral.
If there is nothing worth keeping, return [].
Output ONLY the JSON array, no prose, no markdown."""


def consolidate(max_turns: int = 30) -> dict:
    turns = episodic.recent_messages(limit=max_turns)
    if not turns:
        return {"added": 0, "facts": [], "note": "no conversation to reflect on"}

    convo = "\n".join(f"{t['role']}: {t['content']}" for t in turns)
    try:
        r = requests.post(f"{OLLAMA_BASE}/api/chat", json={
            "model": REFLECT_MODEL, "stream": False,
            "messages": [{"role": "system", "content": _SYSTEM},
                         {"role": "user", "content": convo}],
        }, timeout=120)
        r.raise_for_status()
        raw = r.json()["message"]["content"]
    except Exception as e:
        return {"added": 0, "facts": [], "error": str(e)}

    raw = re.sub(r"```json|```", "", raw).strip()
    try:
        candidates = json.loads(raw)
    except Exception:
        candidates = []
    if not isinstance(candidates, list):
        candidates = []

    known = {f.lower().strip() for f in semantic.fact_texts()}
    added: list[str] = []
    for fact in candidates:
        if not isinstance(fact, str):
            continue
        f = fact.strip()
        if len(f) < 4 or f.lower() in known:
            continue
        semantic.add_fact(f, source="reflection")
        known.add(f.lower())
        added.append(f)

    return {"added": len(added), "facts": added}


if __name__ == "__main__":
    print(json.dumps(consolidate(), indent=2))
