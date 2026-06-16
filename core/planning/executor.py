"""
Plan -> Act -> Observe -> Re-plan executor (§4.2, §4.4).

Runs a Plan's steps in order, each through an injected `step_runner` (the
orchestrator's single dispatch — so every step still flows through route_intent
and the permission gateway). Checkpoints after each step (resumable). Pauses
when a step needs human confirmation; re-plans (capped) when a step fails.
"""
from __future__ import annotations

from typing import Any, Callable

from core.planning import planner as _planner
from core.planning import schema, store
from core.planning.schema import Plan

MAX_REPLANS = 2

StepRunner = Callable[[str], dict]


def _answer_of(resp: dict) -> str:
    """Pull answer text from either the orchestrator response shape or a raw
    agent dict (which carries synthesis at the top level)."""
    if not isinstance(resp, dict):
        return ""
    if resp.get("answer"):
        return resp["answer"]
    syn = resp.get("synthesis") or (resp.get("result") or {}).get("synthesis") or {}
    return syn.get("answer", "") or (resp.get("error") or "")


def execute(plan: Plan, step_runner: StepRunner,
            replan_fn=_planner.replan, synth_fn=_planner.synthesize) -> Plan:
    store.save(plan)

    while plan.cursor < len(plan.steps):
        step = plan.steps[plan.cursor]
        step.status = schema.RUNNING
        resp = step_runner(step.description)
        status = resp.get("status")
        answer = _answer_of(resp)

        # ---- a step needs human approval -> pause and checkpoint (§4.4) ----
        if status == "needs_confirmation":
            step.status = schema.AWAITING
            step.answer = answer
            plan.status = schema.PAUSED
            plan.pending_confirmation = (resp.get("confirmation") or {}).get("confirmation_id")
            store.save(plan)
            return plan

        # ---- a step failed -> Reflexion: re-plan the remainder (capped) ----
        if status in ("error", "blocked"):
            step.status = schema.FAILED
            step.error = answer or resp.get("error") or "failed"
            if plan.replans < MAX_REPLANS:
                plan.replans += 1
                new_steps = replan_fn(plan.goal, plan.completed(), step, step.error)
                if new_steps:
                    plan.steps = plan.steps[:plan.cursor] + new_steps
                    store.save(plan)
                    continue   # retry at the same cursor with the revised step
            plan.status = schema.FAILED
            store.save(plan)
            break

        # ---- success -> checkpoint and advance ----
        step.status = schema.DONE
        step.answer = answer
        plan.cursor += 1
        store.save(plan)
    else:
        plan.status = schema.COMPLETE

    if plan.status == schema.COMPLETE:
        plan.final_answer = synth_fn(plan)
        store.save(plan)
    return plan


def resume_after_confirmation(confirmation_id: str, approve_result: dict,
                              step_runner: StepRunner,
                              replan_fn=_planner.replan,
                              synth_fn=_planner.synthesize) -> Plan | None:
    """Continue a paused plan once its blocking step has been approved."""
    plan = store.plan_for_confirmation(confirmation_id)
    if plan is None:
        return None
    if plan.cursor < len(plan.steps):
        step = plan.steps[plan.cursor]
        step.status = schema.DONE
        step.answer = _answer_of(approve_result) or "approved"
        plan.cursor += 1
    plan.pending_confirmation = None
    plan.status = schema.ACTIVE
    store.save(plan)
    return execute(plan, step_runner, replan_fn, synth_fn)


def to_response(plan: Plan) -> dict[str, Any]:
    """Standard orchestrator response describing a plan's outcome."""
    if plan.status == schema.PAUSED:
        cid = plan.pending_confirmation
        step = plan.steps[plan.cursor] if plan.cursor < len(plan.steps) else None
        answer = (f"📋 Plan: {plan.cursor}/{len(plan.steps)} steps done. "
                  f"The next step needs your go-ahead:\n\n"
                  f"**{step.description if step else ''}**\n\n"
                  f"Reply `approve {cid}` to continue the plan, or `deny {cid}` to stop.")
        return {"status": "needs_confirmation", "domain": "plan",
                "confirmation": {"confirmation_id": cid},
                "result": {"plan": plan.to_dict(), "synthesis": {"answer": answer}}}

    if plan.status == schema.COMPLETE:
        return {"status": "success", "domain": "plan",
                "result": {"plan": plan.to_dict(),
                           "synthesis": {"answer": plan.final_answer}}}

    failed = next((s for s in plan.steps if s.status == schema.FAILED), None)
    answer = (f"❌ I couldn't finish the plan for: {plan.goal}\n\n"
              f"Failed at: {failed.description if failed else '?'}\n"
              f"Reason: {failed.error if failed else 'unknown'}")
    return {"status": "error", "domain": "plan",
            "result": {"plan": plan.to_dict(), "synthesis": {"answer": answer}}}
