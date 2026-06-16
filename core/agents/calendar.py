"""Calendar agent — natural language over the local-first calendar (§ Phase 7).

Same contract as the other agents: `run_agent(command) -> dict` with a top-level
`synthesis.answer` the HUD renders directly. An LLM parses intent into a small
JSON schema; everything after that is deterministic CRUD against
`core.calendar.store`, so answers are built from real rows (no hallucinated
events). Relative dates ("tomorrow 3pm") are resolved by giving the model the
current local date/time, the same trick the Gmail agent uses.
"""
from __future__ import annotations

import json
import os
import re
import textwrap
from datetime import date, datetime, timedelta
from typing import Any

import requests

from core.calendar import store

OLLAMA_BASE = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
CAL_MODEL = os.getenv("JARVIS_CAL_MODEL", "qwen2.5:7b")


def _ollama(messages: list[dict], model: str = CAL_MODEL) -> str:
    r = requests.post(
        f"{OLLAMA_BASE}/api/chat",
        json={"model": model, "messages": messages, "stream": False,
              "options": {"temperature": 0}},
        timeout=120,
    )
    r.raise_for_status()
    return r.json()["message"]["content"]


def parse_intent(command: str) -> dict[str, Any]:
    now = datetime.now()
    system = textwrap.dedent(f"""
        You extract calendar intent. Today is {now:%A %Y-%m-%d}. The current time
        is {now:%H:%M}. Output ONLY one JSON object (no markdown) with keys:

        action (required): one of
          "add"        - create an event
          "list"       - show events (an agenda)
          "find_free"  - find free time slots in a day
          "cancel"     - cancel/delete an event by name

        For action "add":
          title     (string, required)
          start     (string "YYYY-MM-DDTHH:MM", required) - resolve relative dates
                    like "tomorrow", "next Monday", "tonight" to an ABSOLUTE value
          end       (string "YYYY-MM-DDTHH:MM" | null)
          all_day   (bool, default false)
          location  (string | null)
          notes     (string | null)

        For action "list":
          range      one of "today" (default), "tomorrow", "week", "upcoming"
          start_date (string "YYYY-MM-DD" | null)  - only for an explicit range
          end_date   (string "YYYY-MM-DD" | null)

        For action "find_free":
          day        (string "YYYY-MM-DD", default today)

        For action "cancel":
          query      (string, required) - words from the event title

        Resolve ALL relative dates to absolute using today's date above.
        Output ONLY the JSON object.
    """).strip()

    raw = _ollama([{"role": "system", "content": system},
                   {"role": "user", "content": command}])
    raw = re.sub(r"```json|```", "", raw).strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(0))
            except json.JSONDecodeError:
                pass
        # Safe default: just show today's agenda.
        return {"action": "list", "range": "today"}


# --------------------------------------------------------------------------- #
# Deterministic execution + rendering
# --------------------------------------------------------------------------- #
def _result(answer: str, action: str, **extra) -> dict[str, Any]:
    return {"action": action, "synthesis": {"answer": answer}, **extra}


def _render_agenda(events: list[dict], header: str) -> str:
    if not events:
        return f"{header} — nothing scheduled."
    lines = [header, ""]
    cur_day = None
    for ev in events:
        d = store.parse_dt(ev["start_ts"]).date()
        if d != cur_day:
            cur_day = d
            lines.append(f"**{d:%a %b %d}**")
        lines.append(f"  • {store.describe(ev)}")
    return "\n".join(lines)


def _do_list(intent: dict) -> dict[str, Any]:
    rng = (intent.get("range") or "today").lower()
    if intent.get("start_date"):
        s = store.parse_dt(intent["start_date"])
        e = store.parse_dt(intent.get("end_date")) or (s + timedelta(days=1))
        events = store.list_events(s, e)
        header = f"📅 {s:%b %d} – {e:%b %d}"
    elif rng == "tomorrow":
        d = date.today() + timedelta(days=1)
        events = store.events_on(d)
        header = f"📅 Tomorrow ({d:%a %b %d})"
    elif rng == "week":
        s = datetime.combine(date.today(), datetime.min.time())
        events = store.list_events(s, s + timedelta(days=7))
        header = "📅 Next 7 days"
    elif rng == "upcoming":
        events = store.upcoming(limit=15)
        header = "📅 Upcoming"
    else:
        events = store.today()
        header = f"📅 Today ({date.today():%a %b %d})"
    return _result(_render_agenda(events, header), "list", events=events)


def _do_add(intent: dict) -> dict[str, Any]:
    title = (intent.get("title") or "").strip()
    if not title or not intent.get("start"):
        return _result("I need at least a title and a start time to add an event.",
                       "add")
    ev = store.add_event(
        title=title,
        start=intent["start"],
        end=intent.get("end"),
        all_day=bool(intent.get("all_day")),
        location=intent.get("location"),
        notes=intent.get("notes"),
    )
    return _result(f"✅ Added **{ev['title']}** — {store.describe(ev)}.", "add",
                   event=ev)


def _do_find_free(intent: dict) -> dict[str, Any]:
    d = store.parse_dt(intent.get("day")) or datetime.now()
    slots = store.free_slots(d.date())
    if not slots:
        return _result(f"No open slots on {d:%a %b %d} (within working hours).",
                       "find_free", slots=[])
    lines = [f"🕓 Free on {d:%a %b %d}:", ""]
    for sl in slots:
        s, e = store.parse_dt(sl["start"]), store.parse_dt(sl["end"])
        lines.append(f"  • {s:%H:%M}–{e:%H:%M}")
    return _result("\n".join(lines), "find_free", slots=slots)


def _do_cancel(intent: dict) -> dict[str, Any]:
    query = (intent.get("query") or "").strip()
    if not query:
        return _result("Which event should I cancel? Give me part of its title.",
                       "cancel")
    matches = store.find_events(query)
    if not matches:
        return _result(f"No event matching “{query}”.", "cancel")
    if len(matches) > 1:
        listing = "\n".join(f"  • {store.describe(m)}" for m in matches[:6])
        return _result(f"Found {len(matches)} events matching “{query}”:\n\n{listing}"
                       f"\n\nBe more specific and I'll cancel the right one.", "cancel",
                       events=matches)
    ev = matches[0]
    store.cancel_event(ev["id"])
    return _result(f"🗑️ Cancelled **{ev['title']}** ({store.describe(ev)}).",
                   "cancel", event=ev)


_DISPATCH = {
    "add": _do_add,
    "list": _do_list,
    "find_free": _do_find_free,
    "cancel": _do_cancel,
}


def run_agent(command: str) -> dict[str, Any]:
    intent = parse_intent(command)
    action = (intent.get("action") or "list").lower()
    handler = _DISPATCH.get(action, _do_list)
    out = handler(intent)
    out["command"] = command
    out["intent"] = intent
    return out


if __name__ == "__main__":
    import sys

    cmd = " ".join(sys.argv[1:]) or "what's on my calendar today"
    print(json.dumps(run_agent(cmd), indent=2, default=str))
