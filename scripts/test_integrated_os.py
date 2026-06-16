"""End-to-end tests for the Integrated OS (Phase 7): calendar, observability,
the proactive scheduler/briefings/workflows, and autopilot surfacing.

Deterministic by design — uses a throwaway DB and injected fakes for anything
that would otherwise need Ollama or Google, so it runs offline in CI. Live
LLM/agent behaviour is verified separately by running the app.

    python scripts/test_integrated_os.py
"""
import os
import sys
import tempfile
from datetime import date, datetime, time, timedelta

# Isolate everything in a temp DB BEFORE importing core.* (db path is read at import).
os.environ["JARVIS_DB_PATH"] = os.path.join(tempfile.mkdtemp(), "os_test.db")
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import core.db as db  # noqa: E402
from core import observability  # noqa: E402
from core.agents import calendar as cal_agent  # noqa: E402
from core.calendar import store as cal  # noqa: E402
from core.proactive import briefing, scheduler, triggers  # noqa: E402
from core.proactive import store as ps  # noqa: E402
from core.security import gateway, policy  # noqa: E402
from core.security.tiers import ActionRequest, AutonomyMode, Decision, RiskTier  # noqa: E402

_passed = 0
_failed = 0


def check(name: str, cond: bool, extra: str = "") -> None:
    global _passed, _failed
    if cond:
        _passed += 1
        print(f"  [PASS] {name}")
    else:
        _failed += 1
        print(f"  [FAIL] {name}  {extra}")


def section(title: str) -> None:
    print(f"\n=== {title} ===")


ISO = "%Y-%m-%dT%H:%M"


# --------------------------------------------------------------------------- #
section("1. Calendar store — CRUD + free slots")
d = date.today()
e1 = cal.add_event("Standup", f"{d}T09:30", f"{d}T10:00", location="Zoom")
e2 = cal.add_event("Lunch", f"{d}T12:30", f"{d}T13:30")
e3 = cal.add_event("Deep work", f"{d}T15:00", f"{d}T17:00")
check("3 events created today", len(cal.today()) == 3)
check("events ordered by start", [x["title"] for x in cal.today()] == ["Standup", "Lunch", "Deep work"])
slots = cal.free_slots(d)
check("free slots computed", len(slots) == 4, str(slots))
check("first free block is 09:00-09:30",
      slots[0]["start"].endswith("09:00:00") and slots[0]["end"].endswith("09:30:00"))
check("find by title", [m["title"] for m in cal.find_events("lunch")] == ["Lunch"])
check("cancel removes event", cal.cancel_event(e2["id"]) and len(cal.today()) == 2)
check("default 1h duration when end omitted",
      (lambda ev: cal.parse_dt(ev["end_ts"]) - cal.parse_dt(ev["start_ts"]) == timedelta(hours=1))
      (cal.add_event("Quick", f"{d}T20:00")))
check("all-day event blocks free slots",
      (lambda: (cal.add_event("Holiday", f"{d+timedelta(days=2)}", all_day=True),
                cal.free_slots(d + timedelta(days=2)) == [])[1])())


# --------------------------------------------------------------------------- #
section("2. Calendar agent — deterministic dispatch (no LLM)")
add_out = cal_agent._do_add({"title": "Dentist", "start": f"{d+timedelta(days=1)}T15:00",
                             "end": f"{d+timedelta(days=1)}T16:00"})
check("add action returns confirmation", "Added" in add_out["synthesis"]["answer"])
check("add persisted to tomorrow",
      any(x["title"] == "Dentist" for x in cal.events_on(d + timedelta(days=1))))
list_out = cal_agent._do_list({"range": "today"})
check("list renders today's agenda", "Today" in list_out["synthesis"]["answer"])
free_out = cal_agent._do_find_free({"day": str(d)})
check("find_free renders slots", "Free on" in free_out["synthesis"]["answer"])
cancel_out = cal_agent._do_cancel({"query": "Dentist"})
check("cancel removes the event", "Cancelled" in cancel_out["synthesis"]["answer"])
check("cancel of missing reports cleanly", "No event" in cal_agent._do_cancel({"query": "zzz"})["synthesis"]["answer"])


# --------------------------------------------------------------------------- #
section("3. Trigger grammar")
seven = datetime.combine(d, time(7, 0))
nine = datetime.combine(d, time(9, 0))
check("daily before time -> today", triggers.compute_next_run("daily@08:00", seven) == datetime.combine(d, time(8, 0)))
check("daily after time -> tomorrow", triggers.compute_next_run("daily@08:00", nine) == datetime.combine(d + timedelta(days=1), time(8, 0)))
check("every@30m -> +30m", triggers.compute_next_run("every@30m", nine) == nine + timedelta(minutes=30))
check("manual -> None", triggers.compute_next_run("manual", nine) is None)
check("validate good/bad", triggers.validate("daily@08:00") and triggers.validate("every@5m") and not triggers.validate("hourly"))
check("describe is human", triggers.describe("daily@08:00") == "every day at 08:00")


# --------------------------------------------------------------------------- #
section("4. Schedule + feed store")
sc = ps.add_schedule("Test Brief", "briefing", "every@1h")
check("schedule created with next_run", sc["next_run"] is not None)
check("find by name", ps.find_schedule_by_name("test brief") is not None)
ps.mark_run(sc["id"], "ok", datetime.now())
check("mark_run advanced next_run forward",
      datetime.fromisoformat(ps.get_schedule(sc["id"])["next_run"]) > datetime.now())
check("disable clears next_run", ps.set_enabled(sc["id"], False)["next_run"] is None)
check("re-enable re-arms next_run", ps.set_enabled(sc["id"], True)["next_run"] is not None)
fi = ps.add_feed("result", "Hello", "body text")
check("feed item created unread", fi["status"] == "unread" and ps.unread_count() == 1)
ps.mark_feed(fi["id"], "read")
check("mark_feed read drops unread count", ps.unread_count() == 0)


# --------------------------------------------------------------------------- #
section("5. Briefing assembly (templated, no LLM)")
b = briefing.build()
check("briefing has today's events", "Standup" in b["text"])
check("briefing shows a free block", "First free block" in b["text"])
check("briefing reports autonomy mode", "autonomy" in b["text"])
check("briefing data is structured", isinstance(b["data"]["events_today"], list))
posted = briefing.post(source="manual")
check("briefing posted to feed", posted["feed_item"]["kind"] == "briefing")


# --------------------------------------------------------------------------- #
section("6. Scheduler tick — fires due, skips not-due")
due_sched = ps.add_schedule("DueBrief", "briefing", "every@2h")
notdue_sched = ps.add_schedule("Later", "briefing", "every@2h")
# Force one due, leave the other in the future.
with db.get_conn() as conn:
    conn.execute("UPDATE schedule SET next_run=? WHERE id=?",
                 ((datetime.now() - timedelta(minutes=1)).isoformat(), due_sched["id"]))
    conn.execute("UPDATE schedule SET next_run=? WHERE id=?",
                 ((datetime.now() + timedelta(hours=1)).isoformat(), notdue_sched["id"]))
before = ps.unread_count()
fired = scheduler.tick()
fired_names = {f["name"] for f in fired}
check("only the due schedule fired", "DueBrief" in fired_names and "Later" not in fired_names, str(fired_names))
check("firing produced a feed item", ps.unread_count() > before)
check("fired schedule next_run advanced to future",
      datetime.fromisoformat(ps.get_schedule(due_sched["id"])["next_run"]) > datetime.now())


# --------------------------------------------------------------------------- #
section("7. Workflow + autopilot surfacing (injected orchestrate)")
from core.agents import orchestrator  # noqa: E402

_real_orchestrate = orchestrator.orchestrate

# Case A: an outward step hard-stops -> surfaced as a suggestion with its cid.
orchestrator.orchestrate = lambda goal, actor="user": {
    "status": "needs_confirmation", "domain": "gmail",
    "confirmation": {"confirmation_id": "deadbeef0001"},
    "result": {"synthesis": {"answer": "Would email Sam the summary."}},
}
wf = scheduler.run_workflow("email sam the summary", "Email Sam", "src1")
check("workflow needing approval reported", wf["status"] == "needs_confirmation")
check("confirmation id captured", wf["confirmation_id"] == "deadbeef0001")
sugg = ps.get_feed(wf["feed_item"])
check("surfaced as a suggestion in the feed", sugg["kind"] == "suggestion")
check("suggestion carries the confirmation id", sugg["confirmation_id"] == "deadbeef0001")

# Case B: a clean autonomous run -> posted as a result.
orchestrator.orchestrate = lambda goal, actor="user": {
    "status": "success", "domain": "calendar", "answer": "Scheduled it.",
    "result": {"synthesis": {"answer": "Scheduled it."}},
}
wf2 = scheduler.run_workflow("schedule a focus block", "Focus", "src2")
check("clean run posts a result", ps.get_feed(wf2["feed_item"])["kind"] == "result")
orchestrator.orchestrate = _real_orchestrate


# --------------------------------------------------------------------------- #
section("8. Autopilot policy posture")
check("autopilot auto-runs irreversible",
      policy.evaluate(ActionRequest("coder", "run", RiskTier.IRREVERSIBLE), AutonomyMode.AUTOPILOT) == Decision.ALLOW)
check("autopilot still hard-stops outward",
      policy.evaluate(ActionRequest("gmail", "send", RiskTier.OUTWARD), AutonomyMode.AUTOPILOT) == Decision.CONFIRM)
check("autopilot still hard-stops spend",
      policy.evaluate(ActionRequest("shop", "buy", RiskTier.SPEND), AutonomyMode.AUTOPILOT) == Decision.CONFIRM)
check("observe denies a write",
      policy.evaluate(ActionRequest("calendar", "add", RiskTier.WRITE), AutonomyMode.OBSERVE) == Decision.DENY)


# --------------------------------------------------------------------------- #
section("9. Observability tracer + metrics")
observability.reset()
with observability.trace(actor="scheduler", command="proactive run") as tr:
    tr.event("route", domain="gmail")
    tr.event("gateway:confirm", tier="outward")
    tr.set(domain="gmail", status="needs_confirmation")
with observability.trace(actor="user", command="hi") as tr:
    tr.set(domain="general", status="success")
m = observability.metrics()
check("counts both turns", m["turns"] == 2)
check("distinguishes actor", m["by_actor"].get("scheduler") == 1 and m["by_actor"].get("user") == 1)
check("tallies gateway decisions from spans", m["by_decision"].get("confirm") == 1)
check("groups by domain", m["by_domain"].get("gmail") == 1)
check("recent traces exposed newest-first", observability.recent_traces(1)[0]["command"] == "hi")
check("latency captured", "avg" in m["latency_ms"])


# --------------------------------------------------------------------------- #
section("10. Orchestrator proactive shortcuts (no LLM)")
r = orchestrator.orchestrate("brief me")
check("'brief me' returns a briefing", r["domain"] == "proactive" and "Today" in r["result"]["synthesis"]["answer"])
r = orchestrator.orchestrate("list schedules")
check("'list schedules' lists jobs", r["domain"] == "proactive" and "Test Brief" in r["result"]["synthesis"]["answer"])
r = orchestrator.orchestrate("run workflow nonexistent")
check("'run workflow X' handles missing", r["domain"] == "proactive" and "No workflow" in r["result"]["synthesis"]["answer"])


# --------------------------------------------------------------------------- #
print(f"\n{'='*52}\nRESULT: {_passed} passed, {_failed} failed\n{'='*52}")
sys.exit(1 if _failed else 0)
