"""
Skill registry — persistence for self-built skills.

This module is ONLY storage + naming rules. Synthesis (writing/testing a new
skill) lives in `synthesizer.py`; execution lives in `runner.py`.

Layout (under SKILLS_DIR, default <project>/skills; override JARVIS_SKILLS_DIR):

    registry.json              index of ACTIVE (approved) skills
    <name>.py                  an active skill module  ->  def run(query) -> str
    _staging/<name>/           a proposed skill awaiting approval (the trust gate)
        <name>.py
        test_<name>.py
        meta.json
"""
from __future__ import annotations

import json
import os
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
SKILLS_DIR    = Path(os.getenv("JARVIS_SKILLS_DIR", _PROJECT_ROOT / "skills")).resolve()
REGISTRY_PATH = SKILLS_DIR / "registry.json"
STAGING_DIR   = SKILLS_DIR / "_staging"

# A skill name must not shadow a builtin orchestrator domain.
RESERVED_NAMES = {
    "notion", "gmail", "browser", "files", "coder", "general", "learn", "skill",
}
_NAME_RE = re.compile(r"^[a-z][a-z0-9_]{2,40}$")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ensure_dirs() -> None:
    SKILLS_DIR.mkdir(parents=True, exist_ok=True)
    STAGING_DIR.mkdir(parents=True, exist_ok=True)


def valid_name(name: str) -> bool:
    return bool(_NAME_RE.match(name or "")) and name not in RESERVED_NAMES


# --------------------------------------------------------------------------- #
# Active registry
# --------------------------------------------------------------------------- #
def load_registry() -> dict[str, Any]:
    _ensure_dirs()
    if not REGISTRY_PATH.exists():
        return {"version": 1, "skills": []}
    try:
        return json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"version": 1, "skills": []}


def save_registry(reg: dict[str, Any]) -> None:
    _ensure_dirs()
    REGISTRY_PATH.write_text(json.dumps(reg, indent=2), encoding="utf-8")


def list_skills() -> list[dict[str, Any]]:
    return load_registry().get("skills", [])


def get_skill(name: str) -> dict[str, Any] | None:
    return next((s for s in list_skills() if s.get("name") == name), None)


def skill_path(name: str) -> Path:
    return SKILLS_DIR / f"{name}.py"


def _upsert(entry: dict[str, Any]) -> None:
    reg = load_registry()
    reg["skills"] = [s for s in reg.get("skills", []) if s.get("name") != entry["name"]]
    reg["skills"].append(entry)
    save_registry(reg)


def remove_skill(name: str) -> bool:
    reg = load_registry()
    before = len(reg.get("skills", []))
    reg["skills"] = [s for s in reg.get("skills", []) if s.get("name") != name]
    save_registry(reg)
    p = skill_path(name)
    if p.exists():
        p.unlink()
    return len(reg["skills"]) < before


# --------------------------------------------------------------------------- #
# Staging (proposed, not yet trusted)
# --------------------------------------------------------------------------- #
def staging_path(name: str) -> Path:
    return STAGING_DIR / name


def stage(name: str, code: str, test_code: str, meta: dict[str, Any]) -> Path:
    """Write a proposed skill + its test into the staging area."""
    _ensure_dirs()
    d = staging_path(name)
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{name}.py").write_text(code, encoding="utf-8")
    (d / f"test_{name}.py").write_text(test_code, encoding="utf-8")
    full_meta = {**meta, "name": name, "staged_at": _now()}
    (d / "meta.json").write_text(json.dumps(full_meta, indent=2), encoding="utf-8")
    return d


def list_staged() -> list[dict[str, Any]]:
    if not STAGING_DIR.exists():
        return []
    out: list[dict[str, Any]] = []
    for d in sorted(STAGING_DIR.iterdir()):
        meta = d / "meta.json"
        if d.is_dir() and meta.exists():
            try:
                out.append(json.loads(meta.read_text(encoding="utf-8")))
            except Exception:
                continue
    return out


def get_staged(name: str) -> dict[str, Any] | None:
    meta = staging_path(name) / "meta.json"
    if not meta.exists():
        return None
    try:
        return json.loads(meta.read_text(encoding="utf-8"))
    except Exception:
        return None


def discard_staged(name: str) -> bool:
    d = staging_path(name)
    if d.exists():
        shutil.rmtree(d, ignore_errors=True)
        return True
    return False


def activate_staged(name: str) -> dict[str, Any]:
    """Promote a validated staged skill into the active registry (the approval)."""
    d = staging_path(name)
    meta = get_staged(name)
    if meta is None:
        raise ValueError(f"No staged skill named '{name}'.")
    src = d / f"{name}.py"
    if not src.exists():
        raise FileNotFoundError(f"Staged skill code missing for '{name}'.")
    _ensure_dirs()
    shutil.copy2(src, skill_path(name))
    entry = {
        "name":        name,
        "description": meta.get("description", ""),
        "examples":    meta.get("examples", []),
        "file":        f"{name}.py",
        "created":     _now(),
        "validation":  meta.get("validation", {}),
        "status":      "active",
    }
    _upsert(entry)
    discard_staged(name)
    return entry
