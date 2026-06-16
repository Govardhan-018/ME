"""The memory façade the orchestrator talks to (§5.6).

Two jobs: recall what's relevant before a turn, and record the turn after. Ties
episodic + semantic together so callers don't touch the tiers directly.
"""
from __future__ import annotations

from core.memory import episodic, semantic


def recall(query: str, max_facts: int = 5, max_turns: int = 6) -> dict:
    """Pull facts + recent conversation relevant to this turn."""
    return {
        "facts": semantic.search(query, limit=max_facts),
        "recent": episodic.recent_messages(limit=max_turns),
    }


def record_user(command: str) -> None:
    episodic.add_message("user", command)


def record_answer(answer: str, domain: str) -> None:
    if answer:
        episodic.add_message("assistant", answer, domain=domain)


def record_action(summary: str, detail: dict | None = None) -> None:
    episodic.add_event("action", summary, detail)
