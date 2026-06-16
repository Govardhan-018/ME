"""The policy engine: (risk_tier x autonomy_mode) -> Decision (§15.1, §15.2).

This is the whole point of the gateway: the tool's static tier plus the user's
autonomy mode decide here, deterministically. The LLM has no say. That
separation is what makes autonomy safe.
"""
from __future__ import annotations

from core.security.tiers import ActionRequest, AutonomyMode, Decision, RiskTier

# outward/spend ALWAYS confirm regardless of mode — they leave your control or
# cost money. That's the hard stop described in §15.2.
_HARD_STOP = {RiskTier.OUTWARD, RiskTier.SPEND}


def evaluate(action: ActionRequest, mode: AutonomyMode) -> Decision:
    tier = action.risk_tier

    if mode == AutonomyMode.OBSERVE:
        # Reads only. Anything with a side effect is proposed, never executed.
        return Decision.ALLOW if tier == RiskTier.READ else Decision.DENY

    if mode == AutonomyMode.COPILOT:
        if tier in (RiskTier.READ, RiskTier.WRITE):
            return Decision.ALLOW          # auto read + in-scope write
        return Decision.CONFIRM            # irreversible / outward / spend

    if mode == AutonomyMode.AUTOPILOT:
        if tier in _HARD_STOP:
            return Decision.CONFIRM        # never auto-send / auto-spend
        return Decision.ALLOW              # read / write / irreversible auto (bounded task)

    return Decision.CONFIRM                # unknown mode -> safest posture
