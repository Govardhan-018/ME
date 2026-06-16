"""
Decompose a goal into ordered steps, and re-plan on failure (§4.2, §4.3).

All local (Ollama qwen2.5:7b by default). Decomposition is deliberately
conservative: if one agent can do the whole job in a single pass, it returns ONE
step and the orchestrator treats the request as reactive (no plan overhead).
Steps are phrased as standalone sub-commands so the executor can route each one
through the normal agent dispatch.
"""
from __future__ import annotations

import json
import os
import re

import requests

from core.planning.schema import DONE, Plan, Step

OLLAMA_BASE = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
PLANNER_MODEL = os.getenv("JARVIS_PLANNER_MODEL", "qwen2.5:7b")

# Cheap gate: only attempt decomposition when the request looks like it spans
# multiple actions. Keeps single-step asks on the fast path (no planner call).
_MULTI = re.compile(r"(\bthen\b|\bafter\b|\bafterwards\b|\bnext\b|\bfinally\b|"
                    r"\balso\b|\bplus\b|;|\b\d\.\s|\bstep\b)", re.I)


def looks_multi_step(command: str) -> bool:
    words = command.split()
    if len(words) < 7:
        return False
    if _MULTI.search(command):
        return True
    # two-ish clauses joined by "and" in a reasonably long sentence
    return command.lower().count(" and ") >= 1 and len(words) >= 9


def _chat(messages: list[dict]) -> str:
    r = requests.post(f"{OLLAMA_BASE}/api/chat",
                      json={"model": PLANNER_MODEL, "messages": messages, "stream": False},
                      timeout=120)
    r.raise_for_status()
    return r.json()["message"]["content"]


def _parse_steps(raw: str) -> list[Step]:
    raw = re.sub(r"```json|```", "", raw).strip()
    arr: object = None
    try:
        arr = json.loads(raw)
    except Exception:
        m = re.search(r"\[.*\]", raw, re.DOTALL)
        if m:
            try:
                arr = json.loads(m.group(0))
            except Exception:
                arr = None
    steps: list[Step] = []
    if isinstance(arr, list):
        for item in arr:
            if isinstance(item, str) and item.strip():
                steps.append(Step(description=item.strip()))
            elif isinstance(item, dict) and item.get("description"):
                steps.append(Step(description=str(item["description"]).strip(),
                                  domain=(item.get("domain") or None)))
    return [s for s in steps if s.description]


_DECOMPOSE_SYS = """You are JARVIS's planner. Break the user's GOAL into the
SMALLEST number of ordered steps, where each step is one whole job handled by ONE
specialist agent. The agents act through APIs and code — they are NOT a person
clicking a GUI.

Available agents (a step maps to one of these):
- coder    : writes/edits/runs a code file in one go
- files    : reads/analyzes local files and folders
- browser  : searches the web / fetches a page
- notion   : creates or updates Notion pages
- gmail    : reads or sends email
- calendar : views/adds/cancels calendar events, finds free time
- general  : answers from knowledge, writes prose

HARD RULES:
- One agent doing one job = ONE step. "Write hello.py that prints hello world" is
  ONE coder step — NOT separate "open editor", "create file", "type code", "save"
  steps. NEVER emit GUI/manual actions like open/type/click/save/close.
- If a SINGLE agent can satisfy the whole goal, return exactly ONE step.
- Use MULTIPLE steps only when the goal genuinely spans DIFFERENT agents in
  sequence (e.g. browser search -> notion page -> gmail send).
- Each step is a standalone imperative command with its own context (never
  "it"/"that" pointing at another step). At most 5 steps.

Example GOAL: "search the web for the latest SpaceX launch and save a summary to Notion, then email it to me"
Example output:
[{"description":"Search the web for the latest SpaceX launch and gather the key facts","domain":"browser"},
 {"description":"Create a Notion page titled 'Latest SpaceX Launch' summarizing those facts","domain":"notion"},
 {"description":"Email me the SpaceX launch summary","domain":"gmail"}]

Output ONLY a JSON array of step objects:
[{"description": "...", "domain": "coder|files|browser|notion|gmail|calendar|general"}]
No prose, no markdown."""


def decompose(goal: str) -> Plan:
    raw = _chat([{"role": "system", "content": _DECOMPOSE_SYS},
                 {"role": "user", "content": f"GOAL: {goal}"}])
    steps = _parse_steps(raw)
    if not steps:
        steps = [Step(description=goal)]   # safe fallback: treat as single step
    return Plan(goal=goal, steps=steps[:6])


_REPLAN_SYS = """A step in JARVIS's plan just FAILED. Given the GOAL, the steps
already completed, and the failure, propose the revised REMAINING steps to still
reach the goal. Don't repeat what already worked. If the goal is no longer
achievable, return [].

Output ONLY a JSON array of step objects:
[{"description": "...", "domain": "..."}]"""


def replan(goal: str, completed: list[Step], failed: Step, error: str) -> list[Step]:
    done = "\n".join(f"- (done) {s.description}" for s in completed) or "- (none)"
    ctx = (f"GOAL: {goal}\n\nCompleted:\n{done}\n\n"
           f"FAILED step: {failed.description}\nError: {error}")
    try:
        return _parse_steps(_chat([{"role": "system", "content": _REPLAN_SYS},
                                   {"role": "user", "content": ctx}]))
    except Exception:
        return []


_SYNTH_SYS = """You are JARVIS. In 2-5 sentences, tell the user what was
accomplished, based ONLY on the step results shown below. Be concrete — name the
artifacts that were actually produced (files, pages, results). Do NOT invent or
assume any result that isn't in the step outputs. Plain prose, first person."""


def synthesize(plan: Plan) -> str:
    lines = [f"- {s.description}\n  -> {s.answer[:500]}"
             for s in plan.steps if s.status == DONE]
    if not lines:
        return "I couldn't complete the plan."
    body = f"GOAL: {plan.goal}\n\nSteps completed:\n" + "\n".join(lines)
    try:
        return _chat([{"role": "system", "content": _SYNTH_SYS},
                      {"role": "user", "content": body}]).strip()
    except Exception:
        return f"Done — completed {len(lines)} step(s) toward: {plan.goal}."
