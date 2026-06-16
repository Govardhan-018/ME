"""
JARVIS planning layer (§4) — Plan -> Act -> Observe -> Re-plan.

Turns the orchestrator from single-shot routing into multi-step agency: a goal
is decomposed into ordered steps, each executed through the normal agent
dispatch (so every step still flows through the permission gateway), with
checkpointing (resumable), pause-on-confirmation (human-in-the-loop), and capped
re-planning on failure.

Reactive (single-step) requests skip all of this — `looks_multi_step` plus a
conservative decomposer keep simple asks on the fast path.

This is the design's "small plan_store" (§21.3): enough durable, inspectable
planning to be useful now, without paying LangGraph's complexity tax before
Phase 6 demands it.
"""
from core.planning.executor import execute, resume_after_confirmation, to_response
from core.planning.planner import decompose, looks_multi_step, replan, synthesize
from core.planning.schema import Plan, Step
from core.planning import store

__all__ = ["execute", "resume_after_confirmation", "to_response",
           "decompose", "looks_multi_step", "replan", "synthesize",
           "Plan", "Step", "store"]
