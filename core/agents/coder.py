"""
JARVIS Coding Agent.

The write-capable counterpart to the read-only `files` agent. It can:

  - generate  : write a brand-new code file from a description
  - edit      : rewrite/modify an existing file per instructions
  - read      : read an existing file and explain it
  - run       : execute a script and capture its output

Safety model
------------
  * All writes / edits / runs are confined to a WORKSPACE sandbox
    (default: <project>/workspace). Paths that escape it are rejected.
    Point it somewhere real with the JARVIS_WORKSPACE env var.
  * Execution only happens when the user explicitly asks to run/test
    AND it is allowed (allow_run=True). The whole capability can be
    killed globally with JARVIS_CODER_NO_RUN=1 (honoured by the
    orchestrator).
  * Every run has a hard timeout (RUN_TIMEOUT).
"""

import argparse
import json
import os
import re
import subprocess
import sys
import textwrap
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv

load_dotenv()

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
DEFAULT_MODEL   = os.getenv("JARVIS_CODER_MODEL", "qwen2.5:7b")

# Sandbox root. Defaults to <project>/workspace; override with JARVIS_WORKSPACE.
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
WORKSPACE     = Path(os.getenv("JARVIS_WORKSPACE", _PROJECT_ROOT / "workspace")).resolve()

MAX_CHARS   = 12000   # cap on existing-file content fed to the model
RUN_TIMEOUT = 30      # seconds, hard cap on any execution

# Which interpreter runs which extension. Kept deliberately small: only
# things that are safe-ish and likely installed. C/STM32 builds are out of
# scope for auto-run (no toolchain assumption) -- we just write those files.
RUNNERS: dict[str, list[str]] = {
    ".py":  [sys.executable],
    ".js":  ["node"],
    ".mjs": ["node"],
}

# Fallback extension when the user didn't name a file.
EXT_BY_LANG = {
    "python": ".py", "py": ".py",
    "javascript": ".js", "js": ".js", "node": ".js",
    "typescript": ".ts", "ts": ".ts",
    "c": ".c", "c++": ".cpp", "cpp": ".cpp",
    "java": ".java", "rust": ".rs", "go": ".go",
    "bash": ".sh", "shell": ".sh", "sh": ".sh",
    "html": ".html", "css": ".css", "json": ".json",
    "sql": ".sql", "markdown": ".md",
}


# --------------------------------------------------------------------------- #
# Ollama plumbing
# --------------------------------------------------------------------------- #
def ollama_chat(messages: list[dict], model: str) -> str:
    payload = {"model": model, "messages": messages, "stream": False}
    try:
        resp = requests.post(f"{OLLAMA_BASE_URL}/api/chat", json=payload, timeout=300)
        resp.raise_for_status()
        return resp.json()["message"]["content"]
    except requests.exceptions.ConnectionError:
        sys.exit(
            "[ERROR] Cannot reach Ollama at localhost:11434. "
            "Make sure 'ollama serve' is running."
        )


def _clean_json(raw: str) -> str:
    return re.sub(r"```json|```", "", raw).strip()


def _extract_code(text: str) -> tuple[str, str]:
    """
    Split a model response into (code, explanation).

    Prefers the first fenced ```...``` block as the code and treats the
    surrounding prose as the explanation. This sidesteps the fragile job of
    embedding code (newlines/quotes) inside JSON.
    """
    fence = re.search(r"```[a-zA-Z0-9_+-]*\n(.*?)```", text, re.DOTALL)
    if fence:
        code = fence.group(1).rstrip("\n")
        explanation = (text[: fence.start()] + text[fence.end():]).strip()
        return code, explanation
    # No fence -> assume the whole thing is prose (no code produced).
    return "", text.strip()


# --------------------------------------------------------------------------- #
# Sandbox helpers
# --------------------------------------------------------------------------- #
def _safe_path(filename: str) -> Path:
    """Resolve `filename` inside the workspace sandbox, or raise."""
    WORKSPACE.mkdir(parents=True, exist_ok=True)
    candidate = Path(filename)
    if not candidate.is_absolute():
        candidate = WORKSPACE / candidate
    candidate = candidate.resolve()
    try:
        candidate.relative_to(WORKSPACE)
    except ValueError as exc:
        raise PermissionError(
            f"Path '{filename}' escapes the workspace sandbox ({WORKSPACE})."
        ) from exc
    return candidate


def _rel(path: Path) -> str:
    try:
        return str(path.relative_to(WORKSPACE))
    except ValueError:
        return str(path)


def _default_filename(language: str, task: str) -> str:
    ext = EXT_BY_LANG.get((language or "").lower().strip(), ".py")
    slug = re.sub(r"[^a-z0-9]+", "_", (task or "snippet").lower()).strip("_")
    slug = "_".join(slug.split("_")[:4]) or "snippet"
    return f"{slug}{ext}"


# --------------------------------------------------------------------------- #
# Intent
# --------------------------------------------------------------------------- #
def parse_intent(user_command: str, model: str) -> dict:
    system_prompt = textwrap.dedent("""
        You are the intent parser for a local coding agent.

        Given the user's request, output ONLY one JSON object (no markdown,
        no prose) with these keys:

        action (string, required) one of:
            "generate" - create a NEW code file from a description
            "edit"     - modify an EXISTING file per instructions
            "read"     - read and explain an existing file (no changes)
            "run"      - execute an existing file as-is

        filename (string): the file to create/edit/read/run if the user named
            one (e.g. "blink.py", "src/main.c"). Empty string if not specified.

        language (string): programming language if implied (e.g. "python",
            "c", "javascript"). Empty string if unknown.

        run_after (boolean): true ONLY if the user explicitly asked to run,
            execute, or test the code after writing it. Otherwise false.

        task (string, required): a clear restatement of what to build or change.

        Output ONLY the JSON object.
    """).strip()

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user",   "content": user_command},
    ]
    raw = _clean_json(ollama_chat(messages, model))
    try:
        intent = json.loads(raw)
    except json.JSONDecodeError:
        intent = {}
    # Defensive defaults.
    intent.setdefault("action", "generate")
    intent.setdefault("filename", "")
    intent.setdefault("language", "")
    intent.setdefault("run_after", False)
    intent.setdefault("task", user_command)
    return intent


# --------------------------------------------------------------------------- #
# Code generation / editing
# --------------------------------------------------------------------------- #
def generate_code(task: str, language: str, model: str) -> tuple[str, str]:
    system_prompt = textwrap.dedent("""
        You are an expert software engineer. Write clean, correct, runnable code.

        Respond with:
          1. A short (1-3 sentence) explanation of what the code does.
          2. The COMPLETE file contents in a single fenced code block.

        Put the entire program in ONE fenced ``` block. Do not split it.
        Include only code that belongs in the file -- no shell commands.
    """).strip()
    lang_hint = f" in {language}" if language else ""
    user_prompt = f"Write a complete program{lang_hint} for this task:\n\n{task}"

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user",   "content": user_prompt},
    ]
    text = ollama_chat(messages, model)
    return _extract_code(text)


def edit_code(task: str, current: str, path: Path, model: str) -> tuple[str, str]:
    system_prompt = textwrap.dedent("""
        You are an expert software engineer editing an existing file.

        Respond with:
          1. A short explanation of the changes you made.
          2. The COMPLETE updated file contents in a single fenced code block.

        Always return the WHOLE file, not a diff or a fragment.
    """).strip()
    user_prompt = (
        f"File: {path.name}\n\n"
        f"Current contents:\n```\n{current[:MAX_CHARS]}\n```\n\n"
        f"Requested change:\n{task}"
    )
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user",   "content": user_prompt},
    ]
    text = ollama_chat(messages, model)
    return _extract_code(text)


def explain_code(content: str, path: Path, model: str) -> str:
    system_prompt = (
        "You are a senior engineer. Explain the given code clearly and "
        "concisely: what it does, how it's structured, and anything notable "
        "(bugs, smells, TODOs). Plain prose, no JSON."
    )
    user_prompt = f"File: {path.name}\n\n```\n{content[:MAX_CHARS]}\n```"
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user",   "content": user_prompt},
    ]
    return ollama_chat(messages, model).strip()


# --------------------------------------------------------------------------- #
# Execution (sandboxed, gated)
# --------------------------------------------------------------------------- #
def run_file(path: Path) -> dict:
    ext = path.suffix.lower()
    runner = RUNNERS.get(ext)
    if runner is None:
        return {
            "ran": False,
            "reason": f"No safe runner for '{ext or '(no ext)'}'. "
                      f"Runnable: {', '.join(sorted(RUNNERS))}.",
        }
    if not path.exists():
        return {"ran": False, "reason": f"File does not exist: {_rel(path)}"}

    cmd = runner + [str(path)]
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(WORKSPACE),
            capture_output=True,
            text=True,
            timeout=RUN_TIMEOUT,
        )
        return {
            "ran": True,
            "command": " ".join(Path(c).name if i == 0 else c for i, c in enumerate(cmd)),
            "exit_code": proc.returncode,
            "stdout": proc.stdout[-4000:],
            "stderr": proc.stderr[-4000:],
        }
    except subprocess.TimeoutExpired:
        return {"ran": True, "exit_code": None,
                "reason": f"Killed after {RUN_TIMEOUT}s timeout."}
    except FileNotFoundError:
        return {"ran": False,
                "reason": f"Interpreter '{runner[0]}' not found on PATH."}


# --------------------------------------------------------------------------- #
# Answer assembly
# --------------------------------------------------------------------------- #
def _format_run(run: dict) -> str:
    if not run:
        return ""
    if not run.get("ran"):
        return f"\n\n_Not run: {run.get('reason', 'unknown')}_"
    if "reason" in run and run.get("exit_code") is None:
        return f"\n\n**Run:** {run['reason']}"
    parts = [f"\n\n**Run** (`{run.get('command','')}`, exit {run.get('exit_code')}):"]
    if run.get("stdout"):
        parts.append(f"```\n{run['stdout'].rstrip()}\n```")
    if run.get("stderr"):
        parts.append(f"stderr:\n```\n{run['stderr'].rstrip()}\n```")
    if not run.get("stdout") and not run.get("stderr"):
        parts.append("_(no output)_")
    return "\n".join(parts)


# --------------------------------------------------------------------------- #
# Main entry
# --------------------------------------------------------------------------- #
def run_agent(user_command: str, model: str = DEFAULT_MODEL,
              allow_run: bool = False) -> dict[str, Any]:
    print(f"[Coder] Parsing intent for: {user_command!r}")
    intent = parse_intent(user_command, model)
    print(f"[Coder] Intent -> {json.dumps(intent, indent=2)}")

    action    = intent.get("action", "generate")
    filename  = (intent.get("filename") or "").strip()
    language  = (intent.get("language") or "").strip()
    run_after = bool(intent.get("run_after"))
    task      = intent.get("task") or user_command

    result: dict[str, Any] = {
        "command":   user_command,
        "intent":    intent,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    synthesis: dict[str, Any] = {"action": action}

    try:
        # ---- READ ---------------------------------------------------------
        if action == "read":
            if not filename:
                raise ValueError("No filename given to read.")
            path = _safe_path(filename)
            if not path.exists():
                raise FileNotFoundError(f"File not found in workspace: {_rel(path)}")
            content = path.read_text(encoding="utf-8", errors="replace")
            explanation = explain_code(content, path, model)
            synthesis.update({
                "file": _rel(path),
                "explanation": explanation,
                "answer": f"**{_rel(path)}**\n\n{explanation}",
            })

        # ---- RUN ----------------------------------------------------------
        elif action == "run":
            if not filename:
                raise ValueError("No filename given to run.")
            path = _safe_path(filename)
            if not allow_run:
                synthesis.update({
                    "file": _rel(path),
                    "answer": f"Execution is disabled. I can run `{_rel(path)}` "
                              f"if you enable it (allow_run / unset JARVIS_CODER_NO_RUN).",
                })
            else:
                run = run_file(path)
                synthesis.update({
                    "file": _rel(path), "run": run,
                    "answer": f"Ran `{_rel(path)}`.{_format_run(run)}",
                })

        # ---- EDIT ---------------------------------------------------------
        elif action == "edit":
            if not filename:
                raise ValueError("No filename given to edit.")
            path = _safe_path(filename)
            if not path.exists():
                # Nothing to edit -> fall through to a fresh generate.
                print(f"[Coder] {_rel(path)} missing; generating instead.")
                action = "generate"
            else:
                current = path.read_text(encoding="utf-8", errors="replace")
                code, explanation = edit_code(task, current, path, model)
                if not code:
                    raise ValueError("Model returned no code block for the edit.")
                path.write_text(code, encoding="utf-8")
                print(f"[Coder] Updated {_rel(path)} ({len(code)} bytes)")
                run = run_file(path) if (run_after and allow_run) else None
                answer = f"Updated **{_rel(path)}**.\n\n{explanation}\n\n```\n{code}\n```"
                synthesis.update({
                    "file": _rel(path), "code": code, "explanation": explanation,
                    "run": run, "answer": answer + _format_run(run or {}),
                })

        # ---- GENERATE (also the edit-on-missing fallthrough) --------------
        if action == "generate":
            code, explanation = generate_code(task, language, model)
            if not code:
                raise ValueError("Model returned no code block.")
            if not filename:
                filename = _default_filename(language, task)
            path = _safe_path(filename)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(code, encoding="utf-8")
            print(f"[Coder] Wrote {_rel(path)} ({len(code)} bytes)")
            run = run_file(path) if (run_after and allow_run) else None
            answer = f"Created **{_rel(path)}**.\n\n{explanation}\n\n```\n{code}\n```"
            synthesis.update({
                "file": _rel(path), "code": code, "explanation": explanation,
                "run": run, "answer": answer + _format_run(run or {}),
            })

    except Exception as exc:
        synthesis["answer"] = f"Coding agent error: {exc}"
        synthesis["error"] = str(exc)

    result["synthesis"] = synthesis
    return result


def main():
    parser = argparse.ArgumentParser(description="JARVIS coding agent (Ollama-powered)")
    parser.add_argument("--model", default=DEFAULT_MODEL, help=f"Ollama model (default: {DEFAULT_MODEL})")
    parser.add_argument("--allow-run", action="store_true", help="Permit code execution")
    parser.add_argument("--output", default=None, help="Write JSON result to this file")
    args = parser.parse_args()

    print(f"Coding Agent  |  workspace: {WORKSPACE}")
    print("Examples:")
    print("  write a python script that prints the fibonacci sequence and run it")
    print("  edit fib.py to stop at 100")
    print("  explain fib.py")
    print("type 'exit' or Ctrl-C to quit\n")

    while True:
        try:
            command = input("You: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nBye!")
            break
        if not command:
            continue
        if command.lower() in {"exit", "quit", "q"}:
            print("Bye!")
            break

        try:
            result = run_agent(command, model=args.model, allow_run=args.allow_run)
            answer = result.get("synthesis", {}).get("answer", "")
            print("\n-- Coder Response -------------------------------------")
            print(answer.encode("ascii", "ignore").decode("ascii"))
            print("-------------------------------------------------------\n")
            if args.output:
                with open(args.output, "w", encoding="utf-8") as fh:
                    json.dump(result, fh, indent=2)
                print(f"[Coder] Result written to {args.output}\n")
        except Exception as exc:
            clean = str(exc).encode("ascii", "ignore").decode("ascii")
            print(f"[ERROR] {clean}\n")


if __name__ == "__main__":
    main()
