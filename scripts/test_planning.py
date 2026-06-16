"""
Deterministic tests for the planning layer (§4): schema round-trip, the
heuristic gate, and the Plan -> Act -> Observe -> Re-plan executor including
pause-on-confirmation + resume and re-plan-on-failure.

The executor's `step_runner`, `replan_fn`, and `synth_fn` are injected as fakes,
so NONE of this needs Ollama — it tests the loop logic, not the LLM.

    python scripts/test_planning.py
"""
import os
import sys
import tempfile

_TMP = os.path.join(tempfile.gettempdir(), "jarvis_test_planning.db")
for _ext in ("", "-wal", "-shm"):
    try:
        os.remove(_TMP + _ext)
    except OSError:
        pass
os.environ["JARVIS_DB_PATH"] = _TMP
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.planning import executor, schema, store
from core.planning.planner import looks_multi_step
from core.planning.schema import Plan, Step

PASS = 0
FAIL = 0


def check(name: str, cond: bool) -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  [PASS] {name}")
    else:
        FAIL += 1
        print(f"  [FAIL] {name}")


def ok(answer: str) -> dict:
    return {"status": "success", "domain": "x", "result": {"synthesis": {"answer": answer}}}


def fail(reason: str) -> dict:
    return {"status": "error", "domain": "x", "result": {"synthesis": {"answer": reason}}}


def confirm(cid: str) -> dict:
    return {"status": "needs_confirmation", "domain": "x",
            "confirmation": {"confirmation_id": cid},
            "result": {"synthesis": {"answer": "needs ok"}}}


class Runner:
    """Fake step_runner that returns a scripted response per call."""
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def __call__(self, desc):
        self.calls.append(desc)
        return self.responses.pop(0) if self.responses else ok("default")


fake_synth = lambda plan: "SYNTH:" + " | ".join(s.description for s in plan.steps if s.status == schema.DONE)
fake_replan = lambda goal, done, failed, err: [Step(description="recovered step")]


print("== schema round-trip ==")
p = Plan(goal="g", steps=[Step(description="a"), Step(description="b")])
p2 = Plan.from_dict(p.to_dict())
check("plan survives to_dict/from_dict", p2.goal == "g" and len(p2.steps) == 2 and p2.steps[1].description == "b")

print("== heuristic gate (looks_multi_step) ==")
check("short ask -> not multi", looks_multi_step("what is my name") is False)
check("'and then' -> multi", looks_multi_step("search the web for X and then make a notion page about it") is True)
check("single coder ask -> not multi", looks_multi_step("write a fibonacci script") is False)

print("== executor: happy path ==")
plan = Plan(goal="do A then B", steps=[Step(description="A"), Step(description="B")])
runner = Runner([ok("did A"), ok("did B")])
done = executor.execute(plan, runner, replan_fn=fake_replan, synth_fn=fake_synth)
check("both steps ran", runner.calls == ["A", "B"])
check("plan complete", done.status == schema.COMPLETE)
check("all steps done", all(s.status == schema.DONE for s in done.steps))
check("final answer synthesized", done.final_answer == "SYNTH:A | B")
check("persisted + reloadable", store.load(done.id) is not None and store.load(done.id).status == schema.COMPLETE)

print("== executor: pause on confirmation + resume ==")
plan = Plan(goal="read then send", steps=[Step(description="read"), Step(description="send email")])
runner = Runner([ok("read it"), confirm("abc123def456")])
paused = executor.execute(plan, runner, replan_fn=fake_replan, synth_fn=fake_synth)
check("plan paused", paused.status == schema.PAUSED)
check("pending confirmation recorded", paused.pending_confirmation == "abc123def456")
check("awaiting step marked", paused.steps[1].status == schema.AWAITING)
check("store finds plan by confirmation", store.plan_for_confirmation("abc123def456") is not None)

runner2 = Runner([])  # no more steps to run after the approved one
resumed = executor.resume_after_confirmation("abc123def456", ok("email sent"), runner2,
                                             replan_fn=fake_replan, synth_fn=fake_synth)
check("resume completes the plan", resumed is not None and resumed.status == schema.COMPLETE)
check("approved step now done with its answer", resumed.steps[1].status == schema.DONE and resumed.steps[1].answer == "email sent")
check("no stale pending confirmation", resumed.pending_confirmation is None)

print("== executor: re-plan on failure ==")
plan = Plan(goal="A then B", steps=[Step(description="A"), Step(description="B")])
# A ok; B fails once -> replan injects 'recovered step' which then succeeds.
runner = Runner([ok("did A"), fail("B blew up"), ok("recovered ok")])
done = executor.execute(plan, runner, replan_fn=fake_replan, synth_fn=fake_synth)
check("re-plan was attempted", done.replans == 1)
check("recovered step ran", "recovered step" in runner.calls)
check("plan complete after recovery", done.status == schema.COMPLETE)

print("== executor: give up after MAX_REPLANS ==")
plan = Plan(goal="always fails", steps=[Step(description="X")])
runner = Runner([fail("nope"), fail("nope"), fail("nope"), fail("nope")])
give_up = lambda goal, d, f, e: [Step(description="try again")]
done = executor.execute(plan, runner, replan_fn=give_up, synth_fn=fake_synth)
check("plan failed", done.status == schema.FAILED)
check("stopped at MAX_REPLANS", done.replans == executor.MAX_REPLANS)

print("== to_response shapes ==")
r_complete = executor.to_response(done) if False else None
plan_c = Plan(goal="g", steps=[Step(description="a", status=schema.DONE)], status=schema.COMPLETE, final_answer="all done")
check("complete -> success", executor.to_response(plan_c)["status"] == "success")
plan_p = Plan(goal="g", steps=[Step(description="a", status=schema.AWAITING)], status=schema.PAUSED, pending_confirmation="zzz")
rp = executor.to_response(plan_p)
check("paused -> needs_confirmation", rp["status"] == "needs_confirmation" and rp["confirmation"]["confirmation_id"] == "zzz")

print(f"\n==== {PASS} passed, {FAIL} failed ====")
sys.exit(0 if FAIL == 0 else 1)
