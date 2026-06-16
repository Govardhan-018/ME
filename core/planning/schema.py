"""Typed Plan / Step — explicit, inspectable plans (§4.2).

A plan is a list of ordered steps; each step is a standalone natural-language
sub-command that the executor routes through the normal agent dispatch — so
every step reuses route_intent + the permission gateway + the existing agents.
Plans are persisted (store.py), making them resumable after a crash or a
mid-plan confirmation, and renderable in the HUD.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

# ---- step status ----
PENDING = "pending"
RUNNING = "running"
DONE = "done"
FAILED = "failed"
AWAITING = "awaiting_confirmation"

# ---- plan status ----
ACTIVE = "active"
PAUSED = "paused"        # waiting on a human confirmation (§4.4)
COMPLETE = "complete"
# (a plan can also be FAILED, reusing the "failed" string above)


@dataclass
class Step:
    description: str
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    status: str = PENDING
    domain: str | None = None   # optional planner hint; execution re-routes anyway
    answer: str = ""
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "description": self.description, "status": self.status,
                "domain": self.domain, "answer": self.answer, "error": self.error}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Step":
        return cls(description=d.get("description", ""),
                   id=d.get("id") or uuid.uuid4().hex[:8],
                   status=d.get("status", PENDING), domain=d.get("domain"),
                   answer=d.get("answer", ""), error=d.get("error"))


@dataclass
class Plan:
    goal: str
    steps: list[Step] = field(default_factory=list)
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    status: str = ACTIVE
    cursor: int = 0                       # index of the next step to run
    replans: int = 0
    final_answer: str = ""
    pending_confirmation: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "goal": self.goal, "status": self.status,
                "cursor": self.cursor, "replans": self.replans,
                "final_answer": self.final_answer,
                "pending_confirmation": self.pending_confirmation,
                "steps": [s.to_dict() for s in self.steps]}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Plan":
        p = cls(goal=d.get("goal", ""), id=d.get("id") or uuid.uuid4().hex[:12],
                status=d.get("status", ACTIVE), cursor=int(d.get("cursor", 0)),
                replans=int(d.get("replans", 0)), final_answer=d.get("final_answer", ""),
                pending_confirmation=d.get("pending_confirmation"))
        p.steps = [Step.from_dict(s) for s in d.get("steps", [])]
        return p

    def completed(self) -> list[Step]:
        return [s for s in self.steps if s.status == DONE]
