"""Proactive briefing assembler (§ Phase 7 — "today's schedule each morning").

Pulls the real state of your world — today's calendar, your next free slot,
anything awaiting your approval, paused plans, unread proactive items — and
renders a single markdown briefing. It is **templated, not generated**: built
from real rows so an unattended 8am run can never hallucinate a meeting. An
optional LLM narration pass (`narrate=True`) adds a friendly sentence on top,
but always falls back to the template if the model is unreachable.
"""
from __future__ import annotations

import os
from datetime import date, datetime
from typing import Any

from core.calendar import store as cal
from core.proactive import store as feed_store
from core.security import gateway

_REFLECT_MODEL = os.getenv("JARVIS_REFLECT_MODEL", "qwen2.5:7b")
_OLLAMA = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")


def _greeting(now: datetime) -> str:
    h = now.hour
    if h < 12:
        return "Good morning"
    if h < 18:
        return "Good afternoon"
    return "Good evening"


def _paused_plans() -> list[dict[str, Any]]:
    try:
        from core.planning import store as plan_store

        return [p for p in plan_store.recent(20)
                if p.get("status") in ("paused", "active")]
    except Exception:
        return []


def build() -> dict[str, Any]:
    """Gather state -> {data, text}. Pure read; safe to call anytime."""
    now = datetime.now()
    today_events = cal.today()
    upcoming = cal.upcoming(limit=1)
    free = cal.free_slots(date.today())
    pending = gateway.pending()
    paused = _paused_plans()
    unread = feed_store.unread_count()

    data = {
        "now": now.replace(microsecond=0).isoformat(),
        "events_today": today_events,
        "next_event": upcoming[0] if upcoming else None,
        "free_slots": free,
        "pending_confirmations": pending,
        "paused_plans": paused,
        "unread_feed": unread,
        "mode": gateway.get_mode().value,
    }

    lines = [f"## {_greeting(now)} — {now:%A, %B %d}", ""]

    if today_events:
        lines.append(f"**Today ({len(today_events)} event"
                     f"{'s' if len(today_events) != 1 else ''}):**")
        lines += [f"- {cal.describe(ev)}" for ev in today_events]
    else:
        lines.append("**Today:** nothing on the calendar.")
    lines.append("")

    nxt = data["next_event"]
    if nxt and cal.parse_dt(nxt["start_ts"]).date() != date.today():
        lines.append(f"**Next up:** {cal.describe(nxt)} "
                     f"on {cal.parse_dt(nxt['start_ts']):%a %b %d}.")
        lines.append("")

    if free:
        first = free[0]
        s, e = cal.parse_dt(first["start"]), cal.parse_dt(first["end"])
        lines.append(f"**First free block:** {s:%H:%M}–{e:%H:%M} "
                     f"({len(free)} open slot{'s' if len(free) != 1 else ''} today).")
        lines.append("")

    if pending:
        lines.append(f"**⚠️ Awaiting your approval ({len(pending)}):**")
        lines += [f"- {p['summary']}  ·  `approve {p['confirmation_id']}`"
                  for p in pending]
        lines.append("")

    if paused:
        lines.append(f"**⏸ Plans in progress ({len(paused)}):**")
        lines += [f"- {p.get('goal', '')[:80]}" for p in paused[:5]]
        lines.append("")

    tail = []
    if unread:
        tail.append(f"{unread} unread item{'s' if unread != 1 else ''} in your feed")
    tail.append(f"autonomy: **{data['mode']}**")
    lines.append("_" + " · ".join(tail) + "_")

    return {"data": data, "text": "\n".join(lines).strip()}


def narrate(text: str, data: dict[str, Any]) -> str:
    """Optional: a one-line friendly lead-in via the local LLM (best-effort)."""
    try:
        import requests

        n_ev = len(data.get("events_today", []))
        n_pending = len(data.get("pending_confirmations", []))
        prompt = (
            "You are JARVIS giving a spoken morning briefing. In ONE warm, concise "
            f"sentence (max 25 words), greet the user and set up their day. "
            f"They have {n_ev} event(s) today and {n_pending} thing(s) needing "
            "approval. Do not list specifics; the details follow. No emoji.")
        r = requests.post(f"{_OLLAMA}/api/chat", timeout=30, json={
            "model": _REFLECT_MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False, "options": {"temperature": 0.4},
        })
        r.raise_for_status()
        lead = r.json()["message"]["content"].strip().strip('"')
        if lead:
            return f"_{lead}_\n\n{text}"
    except Exception:
        pass
    return text


def post(source: str = "manual", narrate_lead: bool = False) -> dict[str, Any]:
    """Build a briefing and drop it into the proactive feed; returns the item."""
    built = build()
    text = built["text"]
    if narrate_lead:
        text = narrate(text, built["data"])
    item = feed_store.add_feed(
        kind="briefing",
        title=f"Briefing · {datetime.now():%a %b %d, %H:%M}",
        body=text,
        source=source,
    )
    return {"feed_item": item, "data": built["data"]}
