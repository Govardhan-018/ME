"""The proactive scheduler — JARVIS's cron-like spine (design §758, Phase 7).

A daemon thread (mirrors the always-on voice service) that wakes every tick,
finds due schedules, and fires them. The loop is deliberately split from the
mechanism so tests can drive it synchronously:

    due_schedules(now) -> fire(sched) -> mark_run(...)
    tick(now)          = fire everything due at `now`
    run()              = tick + sleep, forever (the thread target)

**Autopilot integration (the load-bearing bit):** workflow jobs run through the
*same* `orchestrator.orchestrate(...)` path users hit, tagged `actor="scheduler"`,
so every proactive action flows through the permission gateway. In autopilot
mode read/write/irreversible run unattended; an `outward`/`spend` step still
hard-stops — and instead of being lost, it's surfaced as a **suggestion** in the
feed with its confirmation id, so you can approve it from the HUD.
"""
from __future__ import annotations

import os
import threading
from datetime import datetime
from typing import Any, Optional

from core.proactive import briefing, store

TICK_SECONDS = int(os.getenv("JARVIS_SCHEDULER_TICK", "30"))
_NARRATE = os.getenv("JARVIS_BRIEFING_NARRATE") == "1"

_stop = threading.Event()
_thread: Optional[threading.Thread] = None

_DEFAULTS = [
    ("Morning briefing", "briefing", "daily@08:00", None),
    ("Nightly reflection", "reflection", "daily@03:00", None),
]


def seed_defaults() -> None:
    """Ensure the standing jobs exist (idempotent — matched by name)."""
    existing = {s["name"].lower() for s in store.list_schedules()}
    for name, kind, trig, goal in _DEFAULTS:
        if name.lower() not in existing:
            store.add_schedule(name, kind, trig, goal)


# --------------------------------------------------------------------------- #
# Firing
# --------------------------------------------------------------------------- #
def run_workflow(goal: str, name: str, source: str) -> dict[str, Any]:
    """Run a goal through the orchestrator as the scheduler, surfacing the result
    (or an approval request) into the feed."""
    from core.agents import orchestrator

    resp = orchestrator.orchestrate(goal, actor="scheduler")
    answer = orchestrator._extract_answer(resp) or "(no output)"
    status = resp.get("status", "ok")

    if status == "needs_confirmation":
        cid = (resp.get("confirmation") or {}).get("confirmation_id")
        item = store.add_feed("suggestion", f"Needs approval: {name}", answer,
                              source=source, confirmation_id=cid)
        return {"status": "needs_confirmation", "confirmation_id": cid,
                "feed_item": item["id"]}

    item = store.add_feed("result", name, answer, source=source)
    return {"status": status, "feed_item": item["id"]}


def fire(sched: dict[str, Any], now: datetime | None = None,
         advance: bool = True) -> dict[str, Any]:
    """Execute one schedule. `advance=False` runs it without moving its cadence
    (used by 'run now')."""
    now = now or datetime.now()
    sid, kind, name = sched["id"], sched["kind"], sched["name"]
    status, detail = "ok", {}

    try:
        if kind == "briefing":
            out = briefing.post(source=sid, narrate_lead=_NARRATE)
            detail = {"feed_item": out["feed_item"]["id"]}
        elif kind == "reflection":
            from core.memory import reflection

            res = reflection.consolidate()
            n = res.get("added", 0) if isinstance(res, dict) else 0
            store.add_feed("result", "Nightly reflection",
                           f"Consolidated memory — {n} new durable fact(s).", source=sid)
            detail = {"reflection": res}
        elif kind == "workflow":
            detail = run_workflow(sched.get("goal") or name, name, sid)
            status = detail.get("status", "ok")
        else:
            status = "skipped"
    except Exception as e:
        status = "error"
        detail = {"error": str(e)}
        store.add_feed("alert", f"Job failed: {name}", str(e), source=sid)

    if advance:
        store.mark_run(sid, status, now)
    return {"schedule": sid, "name": name, "kind": kind, "status": status, **detail}


def due_schedules(now: datetime | None = None) -> list[dict[str, Any]]:
    now = now or datetime.now()
    due = []
    for s in store.list_schedules(enabled_only=True):
        nr = s.get("next_run")
        if not nr:
            continue
        try:
            if datetime.fromisoformat(nr) <= now:
                due.append(s)
        except ValueError:
            continue
    return due


def tick(now: datetime | None = None) -> list[dict[str, Any]]:
    """One scheduler pass: fire everything due. Returns what fired."""
    now = now or datetime.now()
    return [fire(s, now) for s in due_schedules(now)]


def run_schedule_now(sid: str) -> dict[str, Any]:
    """Fire a schedule immediately on demand, leaving its cadence intact."""
    sched = store.get_schedule(sid)
    if not sched:
        return {"status": "error", "error": f"No schedule '{sid}'."}
    return fire(sched, advance=False)


# --------------------------------------------------------------------------- #
# Daemon
# --------------------------------------------------------------------------- #
def run() -> None:
    """Thread target: seed defaults, then tick forever."""
    seed_defaults()
    print(f"[scheduler] proactive engine online (tick {TICK_SECONDS}s)")
    while not _stop.is_set():
        try:
            fired = tick()
            for f in fired:
                print(f"[scheduler] fired {f['name']} -> {f['status']}")
        except Exception as e:
            print(f"[scheduler] tick error: {e}")
        _stop.wait(TICK_SECONDS)


def start() -> None:
    global _thread
    if _thread and _thread.is_alive():
        return
    _stop.clear()
    _thread = threading.Thread(target=run, name="jarvis-scheduler", daemon=True)
    _thread.start()


def stop() -> None:
    _stop.set()
