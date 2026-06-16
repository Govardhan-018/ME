"""Proactive engine (§ Phase 7) — the scheduler, briefings, workflows, and the
feed of things JARVIS surfaces to you unprompted. Façade over the submodules so
callers do `from core import proactive` and use the verbs below.
"""
from core.proactive import briefing, scheduler, store, triggers  # noqa: F401
from core.proactive.scheduler import (  # noqa: F401
    fire,
    run_schedule_now,
    run_workflow,
    seed_defaults,
    start,
    stop,
    tick,
)
from core.proactive.store import (  # noqa: F401
    add_feed,
    add_schedule,
    list_feed,
    list_schedules,
    mark_feed,
    unread_count,
)
