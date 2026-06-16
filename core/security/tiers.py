"""Risk tiers, autonomy modes, and the action/decision value objects (§6.2, §15.2).

The model never sets its own permission. A tool carries a STATIC risk tier; the
user sets a global autonomy mode; the policy engine (policy.py) crosses the two.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class RiskTier(str, Enum):
    READ = "read"                 # list files, read calendar, web search
    WRITE = "write"               # create a page, write a file in-scope
    IRREVERSIBLE = "irreversible"  # delete/overwrite, execute generated code
    OUTWARD = "outward"           # send email, post, message a person
    SPEND = "spend"               # anything that costs money / places orders


class AutonomyMode(str, Enum):
    OBSERVE = "observe"      # read-only; propose actions but execute nothing
    COPILOT = "copilot"      # default: auto read + in-scope write; confirm the rest
    AUTOPILOT = "autopilot"  # auto through irreversible; still hard-stop outward/spend


class Decision(str, Enum):
    ALLOW = "allow"
    CONFIRM = "confirm"
    DENY = "deny"


@dataclass
class ActionRequest:
    """A single proposed action, handed to the gateway."""
    tool: str                          # e.g. "notion", "coder", "gmail"
    action: str                        # human-readable verb, e.g. "create page"
    risk_tier: RiskTier
    summary: str = ""                  # one line shown to the user on confirm
    scope: str | None = None           # which resource/path/account it touches
    args: dict[str, Any] = field(default_factory=dict)
