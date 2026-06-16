"""
Skill runner — execute a registered (or staged) skill module.

A skill module exposes  def run(query: str) -> str.  We import it dynamically
and call it. The static safety check is re-applied at load time (defense in
depth: a registry file could have been hand-edited since synthesis), and the
module is cached by mtime so repeated calls don't re-import.

Note (v0): skills run IN-PROCESS. They are pure-compute by construction (the
synthesizer's static check forbids IO/network/subprocess), so this is bounded —
but a future hardening step is to run each call in a subprocess with a wall-clock
timeout, the same way validation already does.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

from core.skills import registry
from core.skills.synthesizer import static_safety

# path -> (mtime, module)
_cache: dict[str, tuple[float, Any]] = {}


def _load(path: Path):
    path = path.resolve()
    mtime = path.stat().st_mtime
    key = str(path)
    cached = _cache.get(key)
    if cached and cached[0] == mtime:
        return cached[1]

    code = path.read_text(encoding="utf-8")
    ok, why = static_safety(code)
    if not ok:
        raise PermissionError(f"Skill '{path.name}' failed the safety check at load: {why}")

    spec = importlib.util.spec_from_file_location(path.stem, str(path))
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not load skill module: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if not hasattr(module, "run") or not callable(module.run):
        raise AttributeError(f"Skill '{path.name}' has no callable run(query).")

    _cache[key] = (mtime, module)
    return module


def run_module_file(path: Path | str, query: str) -> dict[str, Any]:
    try:
        module = _load(Path(path))
        answer = module.run(query)
        return {"ok": True, "answer": answer if isinstance(answer, str) else str(answer)}
    except Exception as exc:
        return {"ok": False, "answer": f"Skill error: {exc}", "error": str(exc)}


def run_skill(name: str, query: str) -> dict[str, Any]:
    """Run an ACTIVE (approved) skill by name."""
    if registry.get_skill(name) is None:
        return {"ok": False, "answer": f"No registered skill named '{name}'.", "error": "not found"}
    return run_module_file(registry.skill_path(name), query)


def run_staged(name: str, query: str) -> dict[str, Any]:
    """Run a STAGED (validated, not yet approved) skill by name — used to answer
    the turn that triggered the gap, before the user has approved keeping it."""
    p = registry.staging_path(name) / f"{name}.py"
    if not p.exists():
        return {"ok": False, "answer": f"No staged skill named '{name}'.", "error": "not found"}
    return run_module_file(p, query)
