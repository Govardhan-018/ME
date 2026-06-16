"""
The Permission & Audit Gateway — the single chokepoint every action passes
through (§15.1). The model proposes; the gateway disposes.

    decision = policy(action.tier, autonomy_mode)
        ALLOW   -> run the handler, audit, return its result
        CONFIRM -> stash a pending confirmation, return {needs confirmation}
        DENY    -> audit, return blocked

Pending confirmations live in-process (the brain is a long-lived service); the
HUD calls approve()/deny() in a follow-up request. This realizes the confirm
loop in the §2.2 sequence diagram.
"""
from __future__ import annotations

import os
import threading
import uuid
from typing import Any, Callable

from core.security import audit, policy
from core.security.tiers import ActionRequest, AutonomyMode, Decision

_lock = threading.Lock()
_mode: AutonomyMode = AutonomyMode(os.getenv("JARVIS_AUTONOMY", "copilot").lower())
_pending: dict[str, dict[str, Any]] = {}


def get_mode() -> AutonomyMode:
    return _mode


def set_mode(mode: str | AutonomyMode) -> AutonomyMode:
    global _mode
    _mode = mode if isinstance(mode, AutonomyMode) else AutonomyMode(str(mode).lower())
    return _mode


def guard(action: ActionRequest, handler: Callable[[], Any]) -> dict[str, Any]:
    """Run `handler` iff policy allows. Otherwise stash (confirm) or deny.
    Every outcome is audited before anything executes."""
    decision = policy.evaluate(action, _mode)
    audit.record(action, decision, _mode.value)

    if decision == Decision.ALLOW:
        return {"executed": True, "decision": "allow", "result": handler()}

    if decision == Decision.DENY:
        return {
            "executed": False, "decision": "deny",
            "reason": f"'{action.action}' is blocked in {_mode.value} mode "
                      f"({action.risk_tier.value}-tier action).",
        }

    # CONFIRM — stash the closure for a follow-up approve()/deny().
    cid = uuid.uuid4().hex[:12]
    with _lock:
        _pending[cid] = {"action": action, "handler": handler}
    return {
        "executed": False, "decision": "confirm", "confirmation_id": cid,
        "summary": action.summary or action.action,
        "risk_tier": action.risk_tier.value, "tool": action.tool,
    }


def pending() -> list[dict[str, Any]]:
    with _lock:
        return [
            {"confirmation_id": cid, "tool": p["action"].tool,
             "action": p["action"].action, "risk_tier": p["action"].risk_tier.value,
             "summary": p["action"].summary or p["action"].action}
            for cid, p in _pending.items()
        ]


def approve(confirmation_id: str) -> dict[str, Any]:
    with _lock:
        p = _pending.pop(confirmation_id, None)
    if p is None:
        return {"executed": False, "decision": "expired",
                "reason": f"No pending action '{confirmation_id}'."}
    action: ActionRequest = p["action"]
    audit.record(action, Decision.ALLOW, _mode.value, detail=f"confirmed:{confirmation_id}")
    return {"executed": True, "decision": "approved", "tool": action.tool,
            "result": p["handler"]()}


def deny(confirmation_id: str) -> dict[str, Any]:
    with _lock:
        p = _pending.pop(confirmation_id, None)
    if p is None:
        return {"executed": False, "decision": "expired",
                "reason": f"No pending action '{confirmation_id}'."}
    audit.record(p["action"], Decision.DENY, _mode.value, detail=f"denied:{confirmation_id}")
    return {"executed": False, "decision": "denied"}
