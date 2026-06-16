"""
Deterministic tests for the Permission & Audit Gateway (§15) and the memory
layer (§5). Runs against a throwaway SQLite db so it never touches real data.

Most checks need NO Ollama (policy, gateway, audit, episodic, keyword search).
The embedding/reflection paths are best-effort and print SKIP when Ollama or the
models aren't available.

    python scripts/test_gateway_memory.py
"""
import os
import sys
import tempfile
import traceback

# Point the datastore at a temp file BEFORE importing core.db (DB_PATH is read
# at import time), and start from a clean slate.
_TMP = os.path.join(tempfile.gettempdir(), "jarvis_test_gw_mem.db")
for _ext in ("", "-wal", "-shm"):
    try:
        os.remove(_TMP + _ext)
    except OSError:
        pass
os.environ["JARVIS_DB_PATH"] = _TMP
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.security import audit, gateway, policy
from core.security.tiers import ActionRequest, AutonomyMode, Decision, RiskTier
from core.memory import embeddings, episodic, manager, semantic

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


def act(tier: RiskTier) -> ActionRequest:
    return ActionRequest(tool="t", action="a", risk_tier=tier)


print("== policy matrix (tier x mode -> decision) ==")
check("observe: read -> allow", policy.evaluate(act(RiskTier.READ), AutonomyMode.OBSERVE) == Decision.ALLOW)
check("observe: write -> deny", policy.evaluate(act(RiskTier.WRITE), AutonomyMode.OBSERVE) == Decision.DENY)
check("copilot: read -> allow", policy.evaluate(act(RiskTier.READ), AutonomyMode.COPILOT) == Decision.ALLOW)
check("copilot: write -> allow", policy.evaluate(act(RiskTier.WRITE), AutonomyMode.COPILOT) == Decision.ALLOW)
check("copilot: irreversible -> confirm", policy.evaluate(act(RiskTier.IRREVERSIBLE), AutonomyMode.COPILOT) == Decision.CONFIRM)
check("copilot: outward -> confirm", policy.evaluate(act(RiskTier.OUTWARD), AutonomyMode.COPILOT) == Decision.CONFIRM)
check("autopilot: irreversible -> allow", policy.evaluate(act(RiskTier.IRREVERSIBLE), AutonomyMode.AUTOPILOT) == Decision.ALLOW)
check("autopilot: outward -> confirm (hard stop)", policy.evaluate(act(RiskTier.OUTWARD), AutonomyMode.AUTOPILOT) == Decision.CONFIRM)

print("== gateway: allow / confirm / approve / deny ==")
gateway.set_mode("copilot")
ran = {"n": 0}


def handler():
    ran["n"] += 1
    return "did-it"


out = gateway.guard(ActionRequest("files", "read files", RiskTier.READ), handler)
check("read auto-executes", out["executed"] and out["result"] == "did-it" and ran["n"] == 1)

out = gateway.guard(ActionRequest("gmail", "send email", RiskTier.OUTWARD, summary="send"), handler)
check("outward -> confirm (not executed)", (not out["executed"]) and out["decision"] == "confirm" and "confirmation_id" in out)
check("handler NOT run on confirm", ran["n"] == 1)
check("one pending confirmation", len(gateway.pending()) == 1)
approved = gateway.approve(out["confirmation_id"])
check("approve runs the stashed handler", approved["executed"] and ran["n"] == 2)
check("pending cleared after approve", len(gateway.pending()) == 0)

out2 = gateway.guard(ActionRequest("gmail", "send email", RiskTier.OUTWARD), handler)
denied = gateway.deny(out2["confirmation_id"])
check("deny drops the pending action", denied["decision"] == "denied" and len(gateway.pending()) == 0)
check("deny did NOT run handler", ran["n"] == 2)

gateway.set_mode("observe")
out3 = gateway.guard(ActionRequest("coder", "write code", RiskTier.WRITE), handler)
check("observe mode blocks a write", (not out3["executed"]) and out3["decision"] == "deny")
gateway.set_mode("copilot")

print("== audit log (append-only) ==")
events = audit.recent(50)
check("audit captured >= 6 events", len(events) >= 6)
check("every audit row has a decision", all(e.get("decision") for e in events))
check("audit records the mode", any(e.get("mode") == "observe" for e in events))

print("== memory: episodic ==")
episodic.add_message("user", "hello jarvis")
episodic.add_message("assistant", "hi vipul", domain="general")
recent = episodic.recent_messages(limit=5)
check("messages persist oldest->newest", len(recent) >= 2 and recent[0]["role"] == "user" and recent[-1]["role"] == "assistant")

print("== memory: semantic ==")
semantic.add_fact("Vipul is building a personal AI OS called JARVIS", subject="vipul", source="test")
semantic.add_fact("Vipul uses STM32CubeIDE for embedded work", subject="vipul", source="test")
check("facts persist", len(semantic.all_facts()) >= 2)
hits = semantic.search("STM32")
check("search finds the STM32 fact", any("STM32" in r["fact"] for r in hits))
mem = manager.recall("STM32")
check("manager.recall returns facts + recent", "facts" in mem and "recent" in mem)
print(f"  (embedding backend available: {embeddings.available()} -> "
      f"{'vector' if embeddings.available() else 'keyword'} recall)")

print("== orchestrator wiring (mixed-tier classification) ==")
try:
    from core.agents import orchestrator as orch
    check("coder + 'run it' -> irreversible", orch._classify("coder", "write a script and run it")[0] == RiskTier.IRREVERSIBLE)
    check("coder write -> write", orch._classify("coder", "write a fibonacci script")[0] == RiskTier.WRITE)
    check("gmail 'send' -> outward", orch._classify("gmail", "send an email to bob@x.com")[0] == RiskTier.OUTWARD)
    check("gmail read -> read", orch._classify("gmail", "summarize my inbox")[0] == RiskTier.READ)
    check("orchestrate + _dispatch both callable", callable(orch.orchestrate) and callable(orch._dispatch))
except Exception as e:
    print(f"  [WARN] orchestrator import/classify skipped: {e}")
    traceback.print_exc()

print("== reflection (best-effort; needs Ollama) ==")
try:
    from core.memory import reflection
    r = reflection.consolidate()
    if r.get("error"):
        print(f"  [SKIP] reflection needs Ollama: {str(r['error'])[:80]}")
    else:
        print(f"  [INFO] reflection added {r.get('added')} fact(s): {r.get('facts')}")
except Exception as e:
    print(f"  [SKIP] reflection: {e}")

print(f"\n==== {PASS} passed, {FAIL} failed ====")
sys.exit(0 if FAIL == 0 else 1)
