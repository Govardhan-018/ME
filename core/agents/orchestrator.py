import json
import re
import requests
import textwrap

from typing import Dict, Any
from dotenv import load_dotenv

load_dotenv()

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from core.agents import notion
from core.agents import gmail
from core.agents import browser
from core.agents import files
from core.agents import coder
from core.agents import calendar as calendar_agent
from core.agents import mcp_agent

from core.skills import registry as skill_registry
from core.skills import synthesizer as skill_synth
from core.skills import runner as skill_runner

from core.security import gateway
from core.security.tiers import ActionRequest, RiskTier
from core.memory import manager as memory
from core import planning
from core import observability

# Global kill switch for code execution. Set JARVIS_CODER_NO_RUN=1 to disable.
CODER_ALLOW_RUN = os.environ.get("JARVIS_CODER_NO_RUN") != "1"

# Builtin (hand-written) domains. Anything else routed is a learned skill.
BUILTIN_DOMAINS = {"notion", "gmail", "browser", "files", "coder", "calendar", "mcp", "general"}

# The built-in faculties JARVIS ships with — its hand-written agents, as opposed
# to the skills it writes for itself. Surfaced to the HUD so the Skills ledger can
# show "what I can already do" alongside the self-learned skills. tier hints how
# the gateway treats it by default (sharpened per-command by _classify).
FACULTIES = [
    {"name": "calendar", "label": "Calendar", "tier": "write",
     "description": "View your agenda, schedule events, find free time, cancel meetings."},
    {"name": "gmail", "label": "Email", "tier": "read",
     "description": "Read, summarize, and prioritize email; send with your approval."},
    {"name": "notion", "label": "Notion", "tier": "write",
     "description": "Create and organize pages, databases, study and research plans."},
    {"name": "browser", "label": "Web", "tier": "read",
     "description": "Search the web and fetch the contents of a page."},
    {"name": "files", "label": "Files", "tier": "read",
     "description": "Read and analyze local files, documents, and folders."},
    {"name": "coder", "label": "Coder", "tier": "write",
     "description": "Write, edit, and run code in a sandboxed workspace."},
    {"name": "mcp", "label": "Tools (MCP)", "tier": "write",
     "description": "Act through connected MCP servers — scoped filesystem read/write and other external tools."},
    {"name": "general", "label": "Reasoning", "tier": "read",
     "description": "General knowledge, writing, explanations, and conversation."},
]


def list_faculties() -> list[Dict[str, str]]:
    """The built-in agents, for the HUD's capability view."""
    return FACULTIES

# When a gap is hit and a skill is synthesized + validated, do we auto-register
# it, or just use-it-once and wait for an explicit "approve skill X"? Default:
# wait for approval (the trust gate). Set JARVIS_SKILLS_AUTOLEARN=1 to auto-keep.
SKILLS_AUTOLEARN = os.environ.get("JARVIS_SKILLS_AUTOLEARN") == "1"

OLLAMA_BASE = "http://localhost:11434"
ROUTER_MODEL = "gemma3:12b"
GENERAL_MODEL = "qwen2.5:7b"

_ROUTER_BASE = textwrap.dedent("""
    You are the Master Orchestrator (JARVIS).
    Your job is to read the user's intent and decide which sub-agent or skill should handle it.

    You must output ONLY a JSON object with two keys:
    - "domain": string, one of [{enum}]
    - "reasoning": string, short explanation of your choice.

    Builtin domains:
    - "notion": Creating, searching, or organizing Notion pages, databases, study plans, research pages, etc.
    - "gmail": Reading, summarizing, sending, or prioritizing emails.
    - "browser": Searching the web, looking up current information, or fetching a web page's contents.
    - "files": Reading and ANALYZING the content of existing local files (PDFs, docs, spreadsheets) or summarizing a folder. Read-only — use "mcp" to create or modify files.
    - "coder": Writing new code/scripts/programs, editing or fixing an existing code file, explaining a code file, or generating and running code (Python, C/STM32, JavaScript, etc.).
    - "mcp": Acting through connected external tools (MCP servers) — creating, writing, editing, or moving files in the workspace, and any capability an attached tool server exposes. Use this for file CREATION/MODIFICATION and external tool actions.
    - "calendar": Anything about the user's schedule — viewing today's/upcoming events or agenda, adding/scheduling/booking an event or meeting, finding free time, or cancelling an event.
    - "general": General knowledge, writing, explanations, or chat that doesn't need to create files or run tools.
    - "learn": Choose this when NONE of the builtin domains and NONE of the learned skills below fit, BUT the request is a self-contained, deterministic computation or text transformation a small Python function could do (math, unit/number conversions, parsing, formatting, encoding, date arithmetic, etc.). Picking "learn" lets JARVIS build the skill for itself. Do NOT pick "learn" for anything needing the web, files, email, code-file creation, or external accounts — those belong to their agents.
{learned_block}
    Output pure JSON only. No markdown formatting blocks.
""").strip()


def _build_router_system() -> tuple[str, set[str]]:
    """Assemble the router prompt, injecting any learned skills as routable domains."""
    skills = skill_registry.list_skills()
    learned_names = {s["name"] for s in skills}
    if skills:
        lines = ["", "    Learned skills (self-built — prefer these when they clearly fit):"]
        for s in skills:
            ex = "; ".join(s.get("examples", [])[:2])
            tail = f" (e.g. {ex})" if ex else ""
            lines.append(f'    - "{s["name"]}": {s.get("description", "")}{tail}')
        learned_block = "\n".join(lines) + "\n"
    else:
        learned_block = ""
    domains = sorted(BUILTIN_DOMAINS | {"learn"} | learned_names)
    enum = ", ".join(f'"{d}"' for d in domains)
    return _ROUTER_BASE.format(enum=enum, learned_block=learned_block), learned_names

def _ollama(messages: list, model: str) -> str:
    url = f"{OLLAMA_BASE}/api/chat"
    payload = {"model": model, "messages": messages, "stream": False}
    try:
        r = requests.post(url, json=payload, timeout=120)
        r.raise_for_status()
        return r.json()["message"]["content"].strip()
    except Exception as e:
        raise RuntimeError(f"Ollama error: {e}")

def route_intent(command: str) -> Dict[str, str]:
    system, learned = _build_router_system()
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": command}
    ]
    raw = _ollama(messages, ROUTER_MODEL)
    raw = re.sub(r"```json|```", "", raw).strip()

    try:
        routing = json.loads(raw)
    except Exception:
        # Fallback if json parsing fails
        return {"domain": "general", "reasoning": "Fallback due to parse error."}

    # Guard against the router inventing a domain that doesn't exist.
    domain = routing.get("domain", "general")
    if domain not in (BUILTIN_DOMAINS | {"learn"} | learned):
        routing["domain"] = "general"
        routing["reasoning"] = f"Unknown domain '{domain}', defaulting to general."
    return routing


# --------------------------------------------------------------------------- #
# Skill management (deterministic shortcuts — no LLM needed)
# --------------------------------------------------------------------------- #
def _skill_answer(answer: str, status: str = "success", **extra) -> Dict[str, Any]:
    result = {"synthesis": {"answer": answer}}
    result.update(extra)
    return {"status": status, "domain": "skill", "result": result}


def _handle_skill_command(command: str) -> Dict[str, Any] | None:
    """Catch 'list skills' / 'approve skill X' / 'forget skill X' before routing."""
    c = command.strip().lower()

    if c in {"list skills", "show skills", "what skills do you have",
             "what skills have you learned"}:
        active = skill_registry.list_skills()
        staged = skill_registry.list_staged()
        lines = ["**Learned skills:**"]
        lines += [f"- `{s['name']}` — {s.get('description', '')}" for s in active] or ["- (none yet)"]
        if staged:
            lines.append("\n**Awaiting your approval:**")
            lines += [f"- `{s['name']}` — {s.get('description', '')} "
                      f"(say \"approve skill {s['name']}\")" for s in staged]
        return _skill_answer("\n".join(lines))

    m = re.match(r"(?:approve|keep)\s+skill\s+([a-z0-9_]+)", c)
    if m:
        name = m.group(1)
        try:
            skill_synth.approve_skill(name)
            return _skill_answer(f"Approved — `{name}` is now a permanent skill I can use anytime.")
        except Exception as e:
            return _skill_answer(f"Couldn't approve '{name}': {e}", status="error")

    m = re.match(r"(?:discard|forget|delete|remove)\s+skill\s+([a-z0-9_]+)", c)
    if m:
        name = m.group(1)
        removed = skill_registry.discard_staged(name) or skill_registry.remove_skill(name)
        return _skill_answer(f"Removed skill '{name}'." if removed else f"No skill named '{name}'.")

    return None


def _handle_learn(command: str) -> Dict[str, Any]:
    """Capability gap: synthesize + validate a skill, use it once, gate keeping it."""
    print("[Orchestrator] Capability gap — trying to synthesize a new skill...")
    try:
        prop = skill_synth.propose_skill(command)
    except Exception as e:
        return {"status": "error", "domain": "learn", "error": str(e),
                "result": {"synthesis": {"answer": f"I tried to build a new skill but couldn't reach the model: {e}"}}}

    name = prop.get("name", "?")
    if not prop.get("passed"):
        val = prop.get("validation", {}) or {}
        reason = val.get("reason") or (val.get("stderr") or "").strip()[:600] or "it failed its own tests"
        answer = (f"I didn't have a skill for that, so I wrote one (`{name}`) and tested it — "
                  f"but it didn't pass validation, so I threw it away rather than keep something broken.\n\n"
                  f"Reason: {reason}")
        return {"status": "error", "domain": "learn",
                "result": {"skill_proposal": prop, "synthesis": {"answer": answer}}}

    # It passed validation. Run it once to answer this turn (same code we just tested).
    run = skill_runner.run_staged(name, command)

    if SKILLS_AUTOLEARN:
        try:
            skill_synth.approve_skill(name)
            kept = f"\n\n_I added `{name}` to my skills (autolearn on)._"
        except Exception as e:
            kept = f"\n\n_(Could not auto-register `{name}`: {e})_"
    else:
        kept = (f"\n\n_New skill `{name}` is written and tested but not kept yet. "
                f"Say **\"approve skill {name}\"** to make it permanent._")

    answer = f"{run['answer']}{kept}"
    keep_keys = ("name", "description", "examples", "code", "validation", "attempts")
    return {
        "status": "success", "domain": "learn",
        "result": {
            "skill": name,
            "skill_proposal": {k: prop[k] for k in keep_keys if k in prop},
            "synthesis": {"answer": answer},
        },
    }

def handle_general_query(command: str) -> Dict[str, Any]:
    # Recall durable facts + recent conversation so JARVIS remembers you (§5.6).
    mem = memory.recall(command)
    system = ("You are JARVIS, a helpful and highly capable AI assistant. "
              "Answer the user's query clearly and concisely.")
    if mem["facts"]:
        facts = "\n".join(f"- {f['fact']}" for f in mem["facts"])
        system += f"\n\nWhat you know about the user (use only if relevant):\n{facts}"

    messages = [{"role": "system", "content": system}]
    # recent_messages already ends with the just-recorded current command, so we
    # feed the history as-is rather than appending `command` again.
    for t in mem["recent"]:
        if t["role"] in ("user", "assistant") and t["content"]:
            messages.append({"role": t["role"], "content": t["content"]})

    response = _ollama(messages, GENERAL_MODEL)
    return {
        "status": "success",
        "domain": "general",
        "answer": response
    }

# --------------------------------------------------------------------------- #
# Permission & Audit Gateway integration (§15) — every dispatch flows through it
# --------------------------------------------------------------------------- #
# A coarse per-domain default tier. notion writes to your own workspace
# (in-scope WRITE, auto in copilot); browser/files are READ. gmail and coder are
# mixed, so _classify sharpens them by the verb in the command.
_DOMAIN_TIER = {
    "notion":   RiskTier.WRITE,
    "gmail":    RiskTier.READ,
    "browser":  RiskTier.READ,
    "files":    RiskTier.READ,
    "coder":    RiskTier.WRITE,
    "calendar": RiskTier.WRITE,
}

_DOMAIN_VERB = {
    "notion":   "update your Notion workspace",
    "gmail":    "act on your email",
    "browser":  "search the web",
    "files":    "read local files",
    "coder":    "write code in the workspace",
    "calendar": "manage your calendar",
}

# Verbs that escalate a mixed-tier agent to a confirm-by-default action. This is
# a first-pass heuristic; the precise fix is per-tool tiers once the agents are
# refactored onto the single tool-emitting loop (§3.1).
_SEND_RE = re.compile(r"\b(send|reply|forward|compose|email\s+\w+@)\b", re.I)
_RUN_RE  = re.compile(r"\b(run|execute|exec|and run|then run|run it|test it)\b", re.I)
_CAL_WRITE_RE = re.compile(
    r"\b(add|create|schedule|book|set up|put|new event|cancel|delete|remove|"
    r"move|reschedule|remind me to)\b", re.I)


def _classify(domain: str, command: str) -> tuple[RiskTier, str]:
    """(tier, verb) for a domain, sharpened by the command for gmail/coder/calendar."""
    if domain == "gmail" and _SEND_RE.search(command):
        return RiskTier.OUTWARD, "send email on your behalf"
    if domain == "coder" and _RUN_RE.search(command):
        return RiskTier.IRREVERSIBLE, "write AND execute code"
    if domain == "calendar":
        # Viewing the schedule is a READ; only changing it is a WRITE.
        if _CAL_WRITE_RE.search(command):
            return RiskTier.WRITE, "change your calendar"
        return RiskTier.READ, "read your calendar"
    return _DOMAIN_TIER.get(domain, RiskTier.READ), _DOMAIN_VERB.get(domain, domain)


def _guarded(domain: str, command: str, handler, *,
             tier: RiskTier | None = None, verb: str | None = None,
             tool: str | None = None) -> Dict[str, Any]:
    """Run an agent dispatch through the permission gateway.

    tier/verb/tool let a caller (e.g. the MCP bus) supply a precise PER-TOOL tier
    instead of the coarse per-domain default — the §6.2 granularity MCP unlocks.
    """
    if tier is None or verb is None:
        ctier, cverb = _classify(domain, command)
        tier = tier or ctier
        verb = verb or cverb
    action = ActionRequest(
        tool=tool or domain, action=verb, risk_tier=tier,
        summary=f'{verb.capitalize()} — "{command}"',
        args={"command": command},
    )
    try:
        outcome = gateway.guard(action, handler)
    except Exception as e:
        observability.event("gateway:error", tool=domain)
        return {"status": "error", "domain": domain, "error": str(e)}

    observability.event(f"gateway:{outcome['decision']}", tool=domain, tier=tier.value)

    if outcome["executed"]:
        return {"status": "success", "domain": domain, "result": outcome["result"]}

    if outcome["decision"] == "confirm":
        cid = outcome["confirmation_id"]
        answer = (f"⚠️ That needs your go-ahead — it would **{verb}**.\n\n"
                  f"Reply `approve {cid}` to proceed, `deny {cid}` to cancel, "
                  f"or `set mode autopilot`.")
        return {"status": "needs_confirmation", "domain": domain,
                "confirmation": outcome,
                "result": {"synthesis": {"answer": answer}}}

    # denied (e.g. observe mode)
    return {"status": "blocked", "domain": domain,
            "result": {"synthesis": {"answer": outcome.get("reason", "Blocked by policy.")}}}


def _handle_gateway_command(command: str) -> Dict[str, Any] | None:
    """Catch 'approve <id>' / 'deny <id>' / 'set mode X' before routing."""
    c = command.strip().lower()

    m = re.match(r"(?:approve|confirm)\s+([a-f0-9]{8,16})$", c)
    if m:
        cid = m.group(1)
        out = gateway.approve(cid)
        if not out.get("executed"):
            return _skill_answer(out.get("reason", "Nothing to approve."), status="error")
        # If this confirmation was a paused plan's blocking step, resume the plan.
        resumed = planning.resume_after_confirmation(cid, out.get("result", {}), _dispatch_one)
        if resumed is not None:
            return planning.to_response(resumed)
        return {"status": "success", "domain": out.get("tool", "gateway"),
                "result": out.get("result")}

    m = re.match(r"(?:deny|reject|cancel)\s+([a-f0-9]{8,16})$", c)
    if m:
        out = gateway.deny(m.group(1))
        msg = "Cancelled." if out.get("decision") == "denied" else out.get("reason", "Nothing to cancel.")
        return _skill_answer(msg)

    m = re.match(r"(?:set mode|switch to|mode)\s+(observe|copilot|autopilot)$", c)
    if m:
        gateway.set_mode(m.group(1))
        return _skill_answer(f"Autonomy mode set to **{m.group(1)}**.")

    return None


def _proactive_answer(answer: str, status: str = "success", **extra) -> Dict[str, Any]:
    result = {"synthesis": {"answer": answer}}
    result.update(extra)
    return {"status": status, "domain": "proactive", "result": result}


_BRIEF_PHRASES = {
    "brief me", "brief me now", "my briefing", "give me my briefing",
    "give me a briefing", "daily briefing", "morning briefing", "brief me on today",
    "what's my briefing", "whats my briefing", "brief me on my day",
    "what's my day look like", "whats my day look like", "how does my day look",
}


def _handle_proactive_command(command: str) -> Dict[str, Any] | None:
    """Catch 'brief me' / 'run workflow X' / 'list schedules' before routing."""
    c = command.strip().lower().rstrip("?.!").strip()

    if c in _BRIEF_PHRASES:
        from core import proactive

        out = proactive.briefing.post(source="manual")
        return _proactive_answer(out["feed_item"]["body"])

    if c in {"list schedules", "list workflows", "my schedules", "show schedules",
             "my workflows", "what's scheduled", "whats scheduled"}:
        from core import proactive

        rows = proactive.list_schedules()
        if not rows:
            return _proactive_answer("No schedules yet.")
        lines = ["**Scheduled jobs:**"]
        for s in rows:
            on = "on" if s["enabled"] else "off"
            nxt = f" · next {s['next_run'][:16].replace('T', ' ')}" if s.get("next_run") else ""
            lines.append(f"- **{s['name']}** ({s['kind']}, {proactive.triggers.describe(s['trigger'])}, {on}){nxt}")
        return _proactive_answer("\n".join(lines))

    m = re.match(r"(?:run|trigger|execute)\s+(?:workflow|schedule|job)\s+(.+)$", c)
    if m:
        from core import proactive

        sched = proactive.store.find_schedule_by_name(m.group(1).strip())
        if not sched:
            return _proactive_answer(f"No workflow named “{m.group(1).strip()}”.", status="error")
        res = proactive.run_schedule_now(sched["id"])
        item = proactive.store.get_feed(res.get("feed_item", "")) if res.get("feed_item") else None
        body = item["body"] if item else f"Ran **{sched['name']}** → {res.get('status')}."
        return _proactive_answer(body)

    return None


def _mcp_answer(answer: str, status: str = "success", **extra) -> Dict[str, Any]:
    result = {"synthesis": {"answer": answer}}
    result.update(extra)
    return {"status": status, "domain": "mcp", "result": result}


_MCP_LIST_PHRASES = {
    "list tools", "mcp tools", "list mcp tools", "what tools do you have",
    "list mcp servers", "mcp servers", "mcp health", "mcp status", "tool bus",
}


def _handle_mcp_command(command: str) -> Dict[str, Any] | None:
    """Catch 'list tools' / 'mcp health' before routing — inspect the bus (§7.3)."""
    c = command.strip().lower().rstrip("?.!").strip()
    if c not in _MCP_LIST_PHRASES:
        return None
    from core import mcp as mcp_bus

    h = mcp_bus.health()
    if not h.get("available"):
        return _mcp_answer("The MCP tool bus isn't available — the `mcp` SDK isn't "
                           "installed.", status="error")
    marks = {"connected": "🟢", "failed": "🔴", "disabled": "⚪", "pending": "🟡"}
    lines = [f"**MCP tool bus** — {h['tool_count']} tool(s) across "
             f"{len(h['servers'])} server(s):"]
    for s in h["servers"]:
        line = (f"- {marks.get(s['status'], '•')} **{s['name']}** "
                f"({s['status']}, {s['tool_count']} tools)")
        if s.get("error"):
            line += f" — {str(s['error'])[:120]}"
        lines.append(line)
    tools = mcp_bus.tools()
    if tools:
        lines.append("\n**Tools:**")
        lines += [f"- `{t['name']}` [{t['tier']}] — {(t.get('description') or '')[:80]}"
                  for t in tools[:40]]
    return _mcp_answer("\n".join(lines))


def _dispatch(command: str) -> Dict[str, Any]:
    """Route a command to the right agent/skill (memory-wrapped by orchestrate)."""
    print(f"\n[Orchestrator] Routing command: '{command}'...")

    # Deterministic shortcuts: skills ("approve skill X") and gateway ("approve <id>").
    managed = _handle_skill_command(command)
    if managed is not None:
        return managed
    gate = _handle_gateway_command(command)
    if gate is not None:
        return gate
    pro = _handle_proactive_command(command)
    if pro is not None:
        return pro
    mcpc = _handle_mcp_command(command)
    if mcpc is not None:
        return mcpc

    # Multi-step goals get decomposed into a plan (§4); single-step asks pass through.
    planned = _maybe_plan(command)
    if planned is not None:
        return planned

    return _dispatch_one(command)


def _maybe_plan(command: str) -> Dict[str, Any] | None:
    """If the request looks multi-step, decompose + execute a plan; else None."""
    if os.environ.get("JARVIS_NO_PLANNER") == "1":
        return None
    try:
        if not planning.looks_multi_step(command):
            return None
        plan = planning.decompose(command)
        if len(plan.steps) <= 1:
            return None   # the planner agreed it's a single step -> reactive
        observability.event("plan", steps=len(plan.steps))
        print(f"[Planner] {len(plan.steps)}-step plan for: {command!r}")
        plan = planning.execute(plan, _dispatch_one)
        return planning.to_response(plan)
    except Exception as e:
        print(f"[Planner] error ({e}); falling back to single dispatch.")
        return None


def resume_plan(plan_id: str) -> Dict[str, Any]:
    """Continue a persisted plan that was interrupted (e.g. after a restart)."""
    plan = planning.store.load(plan_id)
    if plan is None:
        return {"status": "error", "domain": "plan", "error": f"No plan '{plan_id}'."}
    if plan.status in ("complete", "failed"):
        return planning.to_response(plan)
    return planning.to_response(planning.execute(plan, _dispatch_one))


def _dispatch_one(command: str) -> Dict[str, Any]:
    """Single-shot: route one command to the right agent/skill (the step runner)."""
    routing = route_intent(command)
    domain = routing.get("domain", "general")
    observability.event("route", domain=domain)
    print(f"[Orchestrator] Domain selected: {domain} ({routing.get('reasoning')})")

    # Capability gap -> build a new skill for it.
    if domain == "learn":
        return _handle_learn(command)

    # A previously learned skill was selected.
    if domain not in BUILTIN_DOMAINS and skill_registry.get_skill(domain):
        print(f"[Orchestrator] Handing off to learned skill '{domain}'...")
        run = skill_runner.run_skill(domain, command)
        return {
            "status": "success" if run["ok"] else "error",
            "domain": "skill",
            "result": {"skill": domain, "synthesis": {"answer": run["answer"]}},
            "error": None if run["ok"] else run.get("error"),
        }

    if domain == "notion":
        print("[Orchestrator] Handing off to Notion Agent...")
        return _guarded("notion", command, lambda: notion.run_agent(command))

    elif domain == "gmail":
        print("[Orchestrator] Handing off to Gmail Agent...")
        return _guarded("gmail", command, lambda: gmail.run_agent(command))

    elif domain == "browser":
        print("[Orchestrator] Handing off to Browser Agent...")
        return _guarded("browser", command, lambda: browser.run_agent(command))

    elif domain == "files":
        print("[Orchestrator] Handing off to Files Agent...")
        return _guarded("files", command, lambda: files.run_agent(command))

    elif domain == "coder":
        print("[Orchestrator] Handing off to Coding Agent...")
        return _guarded("coder", command, lambda: coder.run_agent(command, allow_run=CODER_ALLOW_RUN))

    elif domain == "calendar":
        print("[Orchestrator] Handing off to Calendar Agent...")
        return _guarded("calendar", command, lambda: calendar_agent.run_agent(command))

    elif domain == "mcp":
        print("[Orchestrator] Handing off to MCP tool bus...")
        pick = mcp_agent.select(command)
        if not pick.get("tool"):
            return _mcp_answer(pick.get("reason") or "No connected MCP tool fits that request.")
        # Per-tool tier (§6.2): the gateway gates THIS tool, not the whole domain.
        return _guarded(
            "mcp", command, lambda: mcp_agent.run_tool(pick, command),
            tier=pick["tier"], verb=pick["verb"], tool=f"mcp:{pick['server']}",
        )

    else:
        print("[Orchestrator] Handling via General Knowledge...")
        return handle_general_query(command)


def _extract_answer(resp: Dict[str, Any]) -> str:
    """Pull the user-facing answer text out of any response shape."""
    if resp.get("answer"):
        return resp["answer"]
    syn = (resp.get("result") or {}).get("synthesis") or {}
    return syn.get("answer", "")


def orchestrate(command: str, actor: str = "user") -> Dict[str, Any]:
    """Public entry point: record the turn in memory, dispatch, record the reply.

    `actor` is "user" for chat/voice and "scheduler" for proactive/autonomous
    runs — observability and audit use it to tell autonomous actions apart.
    """
    memory.record_user(command)
    with observability.trace(actor=actor, command=command) as tr:
        response = _dispatch(command)
        tr.set(domain=response.get("domain", "unknown"),
               status=response.get("status", "unknown"),
               error=response.get("error"))
    memory.record_answer(_extract_answer(response), response.get("domain", "unknown"))
    return response


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        cmd = " ".join(sys.argv[1:])
        res = orchestrate(cmd)
        print(json.dumps(res, indent=2))
    else:
        print("==================================================")
        print("    JARVIS Master Brain (Interactive Mode)        ")
        print("==================================================")
        print("Type 'exit' or 'quit' to stop.\n")
        while True:
            try:
                cmd = input("You: ").strip()
                if not cmd:
                    continue
                if cmd.lower() in ['exit', 'quit']:
                    print("Goodbye!")
                    break
                
                res = orchestrate(cmd)
                print("\n-- JARVIS Response ---------------------------------")
                if res.get("domain") == "general":
                    print(res.get("answer"))
                else:
                    print(json.dumps(res.get("result", res), indent=2))
                print("----------------------------------------------------\n")
            except (KeyboardInterrupt, EOFError):
                print("\nGoodbye!")
                break
