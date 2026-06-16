"""
JARVIS memory layer (§5) — what turns a chatbot into JARVIS.

Four tiers, mirroring human memory:
  * working    — the live context window + recent turns (held in-process)
  * episodic   — `episodic.py`: the conversation transcript + tool outcomes
  * semantic   — `semantic.py`: durable facts about the user (+ optional vectors)
  * procedural — the skills registry (core/skills) — already has its writer

`manager.py` is the façade the orchestrator talks to (recall before a turn,
record after). `reflection.py` is the consolidation job that distils episodic
memory into durable semantic facts (§5.5).
"""
