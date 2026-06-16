"""
Skill synthesizer — the "synthesize + validate" stages of self-extension.

Given a capability gap (a natural-language need), this module asks the local
model to WRITE a skill, then validates it against a DETERMINISTIC smoke test
(built in code, NOT by the model) in isolation, and — only if it passes —
STAGES the skill for approval. Nothing reaches the active registry here; that
requires an explicit approval (registry.activate_staged), the trust gate where
you see the real output and confirm correctness.

Safety model (v0 — the deliberately narrow "pure-Python, no-network" slice):
  * Generated code may import ONLY the safe stdlib compute modules in
    ALLOWED_IMPORTS. A static check rejects filesystem, network, subprocess,
    os/sys, eval/exec, and stdin access — in BOTH the skill and its test.
  * The test runs in a throwaway temp dir as a subprocess with a hard timeout.
  * "Passed" requires exit 0 AND the success sentinel in stdout, so a test that
    silently does nothing can't count as a pass.

Tuning knobs (env): JARVIS_SKILL_MODEL, JARVIS_SKILL_ATTEMPTS.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import textwrap
from pathlib import Path
from typing import Any

import requests

from core.skills import registry

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
MODEL           = os.getenv("JARVIS_SKILL_MODEL", "qwen2.5:7b")
MAX_ATTEMPTS    = int(os.getenv("JARVIS_SKILL_ATTEMPTS", "3"))
VALIDATE_TIMEOUT = 20  # seconds, hard cap on a skill's test run
SENTINEL = "ALL TESTS PASSED"

# Safe, pure compute corners of the standard library. Anything else is rejected.
ALLOWED_IMPORTS = frozenset({
    "math", "cmath", "re", "json", "datetime", "calendar", "time",
    "statistics", "random", "decimal", "fractions", "numbers",
    "itertools", "functools", "operator", "collections", "heapq", "bisect",
    "string", "textwrap", "unicodedata", "typing", "enum", "dataclasses",
    "abc", "copy", "array", "unittest", "__future__",
})


# --------------------------------------------------------------------------- #
# Static safety check
# --------------------------------------------------------------------------- #
_FORBIDDEN = [
    (re.compile(r"\b(eval|exec|compile|__import__|input|open|globals|locals|"
                r"vars|getattr|setattr|delattr|memoryview|breakpoint)\s*\("),
     "dynamic-exec / IO / introspection call"),
    (re.compile(r"\bos\s*\."), "os module access"),
    (re.compile(r"\bsys\s*\.\s*(exit|argv|stdin|modules|path)\b"), "sys internals"),
    (re.compile(r"\bsubprocess\b"), "subprocess use"),
    (re.compile(r"\bsocket\b"), "socket use"),
]


def _imported_modules(code: str) -> set[str]:
    mods: set[str] = set()
    for m in re.finditer(r"^\s*import\s+(.+)$", code, re.M):
        for part in m.group(1).split(","):
            top = part.strip().split(" as ")[0].strip().split(".")[0]
            if top:
                mods.add(top)
    for m in re.finditer(r"^\s*from\s+([a-zA-Z0-9_\.]+)\s+import\b", code, re.M):
        mods.add(m.group(1).strip().split(".")[0])
    return mods


def static_safety(code: str, extra_allowed: frozenset[str] = frozenset()) -> tuple[bool, str]:
    """Return (ok, reason). `extra_allowed` lets a test import its own skill module."""
    for pat, why in _FORBIDDEN:
        if pat.search(code):
            return False, f"forbidden {why}"
    bad = _imported_modules(code) - ALLOWED_IMPORTS - extra_allowed
    if bad:
        return False, f"import(s) not allowed: {', '.join(sorted(bad))}"
    return True, "ok"


# --------------------------------------------------------------------------- #
# Ollama plumbing
# --------------------------------------------------------------------------- #
def _ollama(messages: list[dict], model: str) -> str:
    r = requests.post(
        f"{OLLAMA_BASE_URL}/api/chat",
        json={"model": model, "messages": messages, "stream": False},
        timeout=300,
    )
    r.raise_for_status()
    return r.json()["message"]["content"]


def _clean_json(raw: str) -> str:
    return re.sub(r"```json|```", "", raw).strip()


def _extract_code(text: str) -> str:
    m = re.search(r"```[a-zA-Z0-9_+-]*\n(.*?)```", text, re.DOTALL)
    return m.group(1).rstrip("\n") if m else ""


def _slug(s: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", (s or "").lower()).strip("_")
    s = "_".join(p for p in s.split("_") if p)[:40] or "skill"
    if not s[0].isalpha():
        s = f"skill_{s}"[:40]
    return s


def _unique_name(name: str) -> str:
    if not registry.get_skill(name):
        return name
    i = 2
    while registry.get_skill(f"{name}_{i}"):
        i += 1
    return f"{name}_{i}"


# --------------------------------------------------------------------------- #
# Generation
# --------------------------------------------------------------------------- #
def _spec(need: str, model: str) -> dict[str, Any]:
    system = textwrap.dedent("""
        You design a small, single-purpose, PURE-PYTHON skill for an AI agent.

        Output ONLY one JSON object (no markdown) with keys:
          "name":        snake_case python identifier, 3-40 chars (e.g. "celsius_to_fahrenheit")
          "description": one sentence describing what the skill does
          "examples":    2-3 commands a user might really say, PHRASED DIFFERENTLY
                         from each other, each containing the actual input it acts on
                         (a number, text, date...). Where units/keywords have short
                         forms, include at least one abbreviated phrasing (e.g. both
                         "10 kilometers" and "10 km") so the skill must parse flexibly

        The skill must be doable with pure computation (math, parsing, formatting,
        conversions, date arithmetic, string/encoding work). No web, files, or accounts.
    """).strip()
    raw = _clean_json(_ollama(
        [{"role": "system", "content": system}, {"role": "user", "content": need}],
        model,
    ))
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        data = {}
    name = _slug(str(data.get("name") or need))
    if not registry.valid_name(name):
        name = _slug(need)
    examples = data.get("examples") or [need]
    if isinstance(examples, str):
        examples = [examples]
    return {
        "name": _unique_name(name),
        "description": str(data.get("description") or need).strip(),
        "examples": [str(e) for e in examples][:3],
    }


_CODE_RULES = textwrap.dedent("""
    Hard constraints (a static checker enforces these — violations are rejected):
      - Define EXACTLY ONE public function:  def run(query: str) -> str
      - `query` is the user's raw natural-language request. Parse what you need
        from it yourself (use `re`). Return a concise human-readable string.
      - PURE function: standard library only, and ONLY these modules are importable:
        math, cmath, re, json, datetime, calendar, statistics, random, decimal,
        fractions, itertools, functools, operator, collections, string, typing.
      - IMPORT every module you use (e.g. write `import re` if you call re.search).
      - PARSE TOLERANTLY. Pull the number(s) out with a permissive search like
        re.search(r'-?\\d+(?:\\.\\d+)?', query); never hard-require particular
        words or a fixed word order around it. Match keywords/units case-
        INSENSITIVELY and accept common ABBREVIATIONS as well as full names
        (km = kilometre(s), kg = kilogram(s), mi = mile(s), c/°c = celsius,
        f = fahrenheit, etc.). Handle varied phrasings, not one fixed sentence.
      - NO file I/O, NO network, NO subprocess, NO os/sys, no eval/exec/open/input.
      - Be robust: if the query can't be parsed, RETURN a helpful message — never raise.
""").strip()


def _gen_code(name: str, description: str, need: str, feedback: str, model: str) -> str:
    system = (
        "You are an expert Python engineer writing one tiny, self-contained skill module.\n\n"
        + _CODE_RULES
        + "\n\nRespond with a one-line note then the COMPLETE module in ONE fenced ``` block."
    )
    user = f"Skill name: {name}\nWhat it must do: {description}\nOriginal request: {need}"
    if feedback:
        user += f"\n\nYour previous attempt FAILED its test. Fix it:\n{feedback}"
    return _extract_code(_ollama(
        [{"role": "system", "content": system}, {"role": "user", "content": user}],
        model,
    ))


def _smoke_test(name: str, examples: list[str]) -> str:
    """
    Build a DETERMINISTIC smoke test for the skill — in code, not by the model.

    It deliberately encodes NO expected answer (the model's arithmetic is the
    unreliable part), so a correct skill can never be discarded over a bad
    guess. It only asserts properties that must hold for ANY working skill:
      * imports and exposes run(query) -> str
      * returns a non-empty string for every example, without raising
      * tolerates garbage input (returns a string, no crash)
      * actually PARSES its examples — their output differs from the response to
        a nonsense query, which catches an over-strict regex or a skill that
        ignores its input entirely.
    Correctness of the numbers is confirmed by the human at the approval gate.
    """
    payload = json.dumps(list(examples))
    return textwrap.dedent(f"""
        from {name} import run

        _examples = {payload}
        _garbage = "zxqw plover frobnicate gizmo wibble"
        _g = run(_garbage)
        assert isinstance(_g, str), "run(garbage) must return a string"

        _outs = []
        for _ex in _examples:
            _o = run(_ex)
            assert isinstance(_o, str), "run() must return a string for: " + repr(_ex)
            assert _o.strip(), "run() returned an empty string for: " + repr(_ex)
            _outs.append(_o)

        assert any(_o != _g for _o in _outs), (
            "run() gives the same answer for its own examples as for nonsense "
            "input -- the parsing is too strict (or it ignores the input); "
            "accept the example phrasings and use the value from the query."
        )
        print("{SENTINEL}")
    """).strip()


# --------------------------------------------------------------------------- #
# Validation
# --------------------------------------------------------------------------- #
def _validate(name: str, code: str, test_code: str) -> dict[str, Any]:
    ok, why = static_safety(code)
    if not ok:
        return {"passed": False, "stage": "static-skill", "reason": why}
    ok, why = static_safety(test_code, extra_allowed=frozenset({name}))
    if not ok:
        return {"passed": False, "stage": "static-test", "reason": why}

    d = Path(tempfile.mkdtemp(prefix=f"jarvis_skill_{name}_"))
    try:
        (d / f"{name}.py").write_text(code, encoding="utf-8")
        (d / f"test_{name}.py").write_text(test_code, encoding="utf-8")
        proc = subprocess.run(
            [sys.executable, f"test_{name}.py"],
            cwd=str(d), capture_output=True, text=True, timeout=VALIDATE_TIMEOUT,
        )
        passed = proc.returncode == 0 and SENTINEL in proc.stdout
        return {
            "passed": passed, "stage": "run", "exit_code": proc.returncode,
            "stdout": proc.stdout[-3000:], "stderr": proc.stderr[-3000:],
        }
    except subprocess.TimeoutExpired:
        return {"passed": False, "stage": "run",
                "reason": f"test timed out after {VALIDATE_TIMEOUT}s"}
    finally:
        shutil.rmtree(d, ignore_errors=True)


def _failure_feedback(val: dict[str, Any]) -> str:
    if val.get("reason"):
        return val["reason"]
    err = (val.get("stderr") or "").strip()
    out = (val.get("stdout") or "").strip()
    return (err or out or "the test failed")[-1500:]


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #
def propose_skill(need: str, model: str = MODEL, max_attempts: int = MAX_ATTEMPTS) -> dict[str, Any]:
    """
    Try to write + validate a skill for `need`. On success, STAGE it (awaiting
    approval) and return {passed: True, name, code, ...}. On failure, return
    {passed: False, ...} and stage nothing.
    """
    spec = _spec(need, model)
    name, description, examples = spec["name"], spec["description"], spec["examples"]

    # Deterministic smoke test — built in code, NOT by the model. It encodes no
    # guessed expected value, so a correct skill can't be thrown away over the
    # 7B's own bad arithmetic (the old "assertion failed" false-negative).
    test_code = _smoke_test(name, examples)

    last: dict[str, Any] = {}
    feedback = ""
    for attempt in range(1, max_attempts + 1):
        code = _gen_code(name, description, need, feedback, model)
        if not code:
            last = {"passed": False, "reason": "model produced no code block"}
            continue

        val = _validate(name, code, test_code)
        last = val
        if val["passed"]:
            registry.stage(name, code, test_code, {
                "description": description, "examples": examples,
                "need": need, "validation": val,
            })
            return {
                "passed": True, "name": name, "description": description,
                "examples": examples, "code": code, "test": test_code,
                "validation": val, "attempts": attempt,
            }
        feedback = _failure_feedback(val)

    return {
        "passed": False, "name": name, "description": description,
        "examples": examples, "validation": last, "attempts": max_attempts,
    }


def approve_skill(name: str) -> dict[str, Any]:
    """The trust gate: promote a staged, validated skill into the active registry."""
    return registry.activate_staged(name)
