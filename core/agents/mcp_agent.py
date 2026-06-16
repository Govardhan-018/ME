"""
MCP tool-use agent — the brain's hands on the MCP bus (§7).

This is the single-agent, MCP-tools pattern the design argues for (§8): one loop
that, given a request, picks the right tool from whatever servers are connected
and calls it. It does NOT decide its own permission — it returns the chosen tool
+ its static risk tier, and the orchestrator runs the call through the Permission
& Audit Gateway (§15). That keeps gating centralized and per-tool (§6.2).

Slice 1 does one tool call per turn (the common case: read/write a file). Multi-
tool sequences are handled by the planner (§4) decomposing into per-step asks.
"""
from __future__ import annotations

import json
import os
import re
import textwrap
from typing import Any

import requests

from core import mcp as mcp_bus
from core.security.tiers import RiskTier

OLLAMA_BASE = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
MODEL = os.getenv("JARVIS_MCP_MODEL", "qwen2.5:7b")
_MAX_TEXT = 4000


def _ollama(messages: list[dict], model: str = MODEL) -> str:
    resp = requests.post(
        f"{OLLAMA_BASE}/api/chat",
        json={"model": model, "messages": messages, "stream": False},
        timeout=120,
    )
    resp.raise_for_status()
    return resp.json()["message"]["content"].strip()


def _compact_tool(t: dict[str, Any]) -> str:
    schema = t.get("input_schema") or {}
    props = schema.get("properties") or {}
    required = set(schema.get("required") or [])
    params = []
    for name, spec in props.items():
        ptype = spec.get("type", "any") if isinstance(spec, dict) else "any"
        params.append(f"{name}{'*' if name in required else ''}:{ptype}")
    desc = (t.get("description") or "").strip().replace("\n", " ")[:160]
    return f'- {t["name"]} [{t["tier"]}] — {desc} | params: {", ".join(params) or "(none)"}'


def _verb_for(tool: str, tier: RiskTier, server: str) -> str:
    """A short human phrase for the gateway's confirmation prompt."""
    if tier in (RiskTier.IRREVERSIBLE, RiskTier.OUTWARD):
        return f"run `{tool}` (a {tier.value} action) on the {server} server"
    return f"run `{tool}` on the {server} server"


def select(command: str) -> dict[str, Any]:
    """Pick a single MCP tool + arguments for `command`.

    Returns {tool, arguments, server, tier, verb, reason}. tool is None (with a
    reason) when nothing connected fits — the orchestrator surfaces that as a
    plain answer rather than calling anything.
    """
    if not mcp_bus.available():
        return {"tool": None, "reason": "The MCP tool bus isn't available "
                "(the `mcp` SDK isn't installed)."}
    tools = mcp_bus.tools()
    if not tools:
        return {"tool": None, "reason": "No MCP tools are connected right now."}

    roots = mcp_bus.roots()
    roots_line = (f"Allowed filesystem root(s) (put any new/target file UNDER one of "
                  f"these, as an ABSOLUTE path): {roots}") if roots else ""
    system = textwrap.dedent(f"""
        You operate a set of connected MCP tools for JARVIS. Choose AT MOST ONE
        tool that best accomplishes the user's request, and fill its arguments
        from the request.

        {roots_line}

        Rules:
        - Use ONLY a tool name from the list below. Do not invent tools or params.
        - Fill every required (*) parameter. Use absolute paths under an allowed root.
        - If NO listed tool fits the request, return {{"tool": null, "reason": "..."}}.

        Available tools:
        {chr(10).join(_compact_tool(t) for t in tools)}

        Output ONLY a JSON object, no markdown:
        {{"tool": "<name or null>", "arguments": {{...}}, "reason": "<one line>"}}
    """).strip()

    try:
        raw = _ollama([
            {"role": "system", "content": system},
            {"role": "user", "content": command},
        ])
    except Exception as e:
        return {"tool": None, "reason": f"Could not reach the model to pick a tool: {e}"}

    raw = re.sub(r"```json|```", "", raw).strip()
    try:
        pick = json.loads(raw)
    except Exception:
        return {"tool": None, "reason": "The model did not return a valid tool choice."}

    name = pick.get("tool")
    if not name:
        return {"tool": None, "reason": pick.get("reason") or "No suitable tool."}

    # Guard against a hallucinated tool name.
    if name not in {t["name"] for t in tools}:
        return {"tool": None, "reason": f"Picked an unknown tool '{name}'."}

    server = mcp_bus.server_for(name) or "?"
    tier = mcp_bus.tier_for(name)
    return {
        "tool": name,
        "arguments": pick.get("arguments") or {},
        "server": server,
        "tier": tier,
        "verb": _verb_for(name, tier, server),
        "reason": pick.get("reason", ""),
    }


def run_tool(pick: dict[str, Any], command: str) -> dict[str, Any]:
    """Execute the chosen tool (already gateway-approved) and shape the result
    into the standard agent response body (result.synthesis.answer)."""
    tool = pick["tool"]
    args = pick.get("arguments") or {}
    out = mcp_bus.call(tool, args)
    text = (out.get("text") or "").strip()

    if not out.get("ok"):
        answer = f"The `{tool}` tool failed: {out.get('error') or 'unknown error'}"
    elif text:
        body = text if len(text) <= _MAX_TEXT else text[:_MAX_TEXT] + "\n…(truncated)"
        answer = f"Done — ran `{tool}` via the {pick['server']} server.\n\n{body}"
    else:
        answer = f"Done — ran `{tool}` via the {pick['server']} server."

    return {
        "synthesis": {"answer": answer},
        "tool_call": {
            "tool": tool, "server": pick.get("server"),
            "tier": pick["tier"].value if isinstance(pick.get("tier"), RiskTier) else pick.get("tier"),
            "arguments": args,
        },
        "ok": out.get("ok", False),
        "raw": text,
    }


# Convenience for an interactive sanity check: python -m core.agents.mcp_agent "list files"
if __name__ == "__main__":
    import sys

    from core.security import gateway
    from core.security.tiers import ActionRequest

    mcp_bus.start()
    cmd = " ".join(sys.argv[1:]) or "list the files in the workspace"
    chosen = select(cmd)
    print("PICK:", json.dumps({**chosen, "tier": getattr(chosen.get("tier"), "value", None)}, indent=2))
    if chosen.get("tool"):
        action = ActionRequest(tool=f"mcp:{chosen['server']}", action=chosen["verb"],
                               risk_tier=chosen["tier"], summary=chosen["verb"])
        result = gateway.guard(action, lambda: run_tool(chosen, cmd))
        print("RESULT:", json.dumps(result, indent=2, default=str))
    mcp_bus.stop()
