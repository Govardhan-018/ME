import os
import tempfile

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel
from typing import Any, Dict

from fastapi.middleware.cors import CORSMiddleware
from core.agents import orchestrator

app = FastAPI(title="JARVIS Core API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ChatRequest(BaseModel):
    command: str

class ChatResponse(BaseModel):
    status: str
    domain: str
    result: Dict[str, Any] | None = None
    answer: str | None = None
    error: str | None = None

@app.post("/api/chat", response_model=ChatResponse)
async def chat_endpoint(req: ChatRequest):
    """
    Main entry point for JARVIS. Takes a natural language command and routes it.
    """
    if not req.command.strip():
        raise HTTPException(status_code=400, detail="Command cannot be empty")
    
    res = orchestrator.orchestrate(req.command)
    
    return ChatResponse(
        status=res.get("status", "error"),
        domain=res.get("domain", "unknown"),
        result=res.get("result"),
        answer=res.get("answer"),
        error=res.get("error")
    )

@app.post("/api/voice/transcribe")
async def transcribe_endpoint(request: Request):
    """
    Local speech-to-text. Body is raw audio bytes (e.g. webm/opus from the
    browser MediaRecorder). Returns {"text": "..."}.
    """
    from core.voice import stt

    data = await request.body()
    if not data:
        return {"text": ""}
    try:
        return {"text": stt.transcribe_bytes(data, "audio.webm")}
    except Exception as e:
        return {"text": "", "error": str(e)}

class TTSRequest(BaseModel):
    text: str

@app.post("/api/voice/tts")
async def tts_endpoint(req: TTSRequest):
    import requests
    from fastapi.responses import Response
    api_key = os.getenv("ELEVENLABS_API_KEY")
    voice_id = os.getenv("ELEVENLABS_VOICE_ID", "21m00Tcm4TlvDq8ikWAM")
    if not api_key:
        raise HTTPException(status_code=500, detail="ELEVENLABS_API_KEY not set")
    
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
    headers = {
        "Accept": "audio/mpeg",
        "Content-Type": "application/json",
        "xi-api-key": api_key
    }
    data = {
        "text": req.text,
        "model_id": "eleven_turbo_v2_5",
        "voice_settings": {
            "stability": 0.5,
            "similarity_boost": 0.5
        }
    }
    
    try:
        response = requests.post(url, json=data, headers=headers)
        response.raise_for_status()
        return Response(content=response.content, media_type="audio/mpeg")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/voice/state")
async def voice_state():
    """Live state of the always-on voice service (for the UI to mirror)."""
    from core.voice.service import get_state

    return get_state()


class SkillName(BaseModel):
    name: str


@app.get("/api/skills")
async def list_skills_endpoint():
    """Built-in faculties + active (approved) skills + staged ones awaiting approval."""
    from core.skills import registry as skill_registry

    return {
        "builtin": orchestrator.list_faculties(),
        "skills": skill_registry.list_skills(),
        "staged": skill_registry.list_staged(),
    }


@app.post("/api/skills/approve")
async def approve_skill_endpoint(req: SkillName):
    """The trust gate: promote a staged, validated skill into the registry."""
    from core.skills import synthesizer as skill_synth

    try:
        return {"status": "success", "skill": skill_synth.approve_skill(req.name)}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/skills/discard")
async def discard_skill_endpoint(req: SkillName):
    """Drop a staged proposal, or remove an active skill."""
    from core.skills import registry as skill_registry

    removed = skill_registry.discard_staged(req.name) or skill_registry.remove_skill(req.name)
    return {"status": "success" if removed else "not_found", "name": req.name}


# --------------------------------------------------------------------------- #
# Permission & Audit Gateway (§15)
# --------------------------------------------------------------------------- #
class ModeReq(BaseModel):
    mode: str


class ConfirmId(BaseModel):
    confirmation_id: str


@app.get("/api/gateway")
async def gateway_state():
    """Current autonomy mode + any actions awaiting confirmation."""
    from core.security import gateway

    return {"mode": gateway.get_mode().value, "pending": gateway.pending()}


@app.post("/api/gateway/mode")
async def gateway_set_mode(req: ModeReq):
    from core.security import gateway

    try:
        return {"status": "success", "mode": gateway.set_mode(req.mode).value}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Unknown mode '{req.mode}': {e}")


@app.post("/api/gateway/approve")
async def gateway_approve(req: ConfirmId):
    """Approve a pending high-risk action; the gateway runs the stashed handler."""
    from core.security import gateway

    return gateway.approve(req.confirmation_id)


@app.post("/api/gateway/deny")
async def gateway_deny(req: ConfirmId):
    from core.security import gateway

    return gateway.deny(req.confirmation_id)


@app.get("/api/audit")
async def audit_log(limit: int = 50):
    """The append-only audit trail — every gated action and its decision."""
    from core.security import audit

    return {"events": audit.recent(limit)}


# --------------------------------------------------------------------------- #
# MCP tool bus (§7) — connected servers, their tools, and gateway-gated calls
# --------------------------------------------------------------------------- #
class MCPCall(BaseModel):
    tool: str
    arguments: Dict[str, Any] = {}


@app.get("/api/mcp")
async def mcp_state():
    """Connected MCP servers + per-server tool counts and health (§7.3)."""
    from core import mcp as mcp_bus

    return mcp_bus.health()


@app.get("/api/mcp/tools")
async def mcp_tools():
    """The flat registry of every connected tool, with its static risk tier."""
    from core import mcp as mcp_bus

    return {"tools": mcp_bus.tools()}


@app.post("/api/mcp/call")
async def mcp_call(req: MCPCall):
    """Invoke a tool by name — STILL through the gateway with the per-tool tier
    (§15). A high-risk tool comes back as a confirmation to approve via
    /api/gateway/approve, exactly like any other gated action."""
    from core import mcp as mcp_bus
    from core.security import gateway
    from core.security.tiers import ActionRequest

    if not mcp_bus.available():
        raise HTTPException(status_code=503, detail="MCP SDK not installed")
    tier = mcp_bus.tier_for(req.tool)
    server = mcp_bus.server_for(req.tool) or "?"
    action = ActionRequest(
        tool=f"mcp:{server}", action=req.tool, risk_tier=tier,
        summary=f"MCP {req.tool}", args=req.arguments,
    )
    return gateway.guard(action, lambda: mcp_bus.call(req.tool, req.arguments))


# --------------------------------------------------------------------------- #
# Memory (§5)
# --------------------------------------------------------------------------- #
@app.get("/api/memory")
async def memory_view(query: str | None = None):
    """What JARVIS knows about you + recent conversation. Optional semantic query."""
    from core.memory import episodic, semantic

    facts = semantic.search(query, limit=10) if query else semantic.all_facts()
    return {"facts": facts, "recent": episodic.recent_messages(limit=12)}


@app.post("/api/memory/reflect")
async def memory_reflect():
    """Run the consolidation pass: distil recent episodes into durable facts."""
    from core.memory import reflection

    return reflection.consolidate()


# --------------------------------------------------------------------------- #
# Plans (§4) — multi-step jobs, resumable
# --------------------------------------------------------------------------- #
@app.get("/api/plans")
async def list_plans(limit: int = 20):
    from core.planning import store

    return {"plans": store.recent(limit)}


@app.get("/api/plan/{plan_id}")
async def get_plan(plan_id: str):
    from core.planning import store

    plan = store.load(plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail=f"No plan '{plan_id}'")
    return plan.to_dict()


@app.post("/api/plan/{plan_id}/resume")
async def resume_plan_endpoint(plan_id: str):
    """Continue a plan that was interrupted (e.g. the process restarted)."""
    from core.agents import orchestrator

    return orchestrator.resume_plan(plan_id)


# --------------------------------------------------------------------------- #
# Calendar (§ Phase 7) — local-first; the proactive engine reads this
# --------------------------------------------------------------------------- #
class CalendarEventReq(BaseModel):
    title: str
    start: str
    end: str | None = None
    all_day: bool = False
    location: str | None = None
    notes: str | None = None


@app.get("/api/calendar")
async def calendar_view():
    """Today's agenda, the upcoming horizon, and today's free blocks."""
    from datetime import date
    from core.calendar import store as cal

    return {
        "today": cal.today(),
        "upcoming": cal.upcoming(limit=15),
        "free_today": cal.free_slots(date.today()),
    }


@app.post("/api/calendar/event")
async def calendar_add(req: CalendarEventReq):
    from core.calendar import store as cal

    try:
        return {"status": "success", "event": cal.add_event(**req.model_dump())}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.delete("/api/calendar/event/{event_id}")
async def calendar_delete(event_id: str):
    from core.calendar import store as cal

    return {"status": "success" if cal.cancel_event(event_id) else "not_found"}


# --------------------------------------------------------------------------- #
# Proactive engine (§ Phase 7) — feed, schedules/workflows, briefings
# --------------------------------------------------------------------------- #
class ScheduleReq(BaseModel):
    name: str
    kind: str = "workflow"          # briefing | reflection | workflow
    trigger: str = "manual"         # daily@HH:MM | every@Nm | manual
    goal: str | None = None
    enabled: bool = True


@app.get("/api/proactive/feed")
async def proactive_feed(limit: int = 30):
    from core.proactive import store as ps

    return {"items": ps.list_feed(limit), "unread": ps.unread_count()}


@app.post("/api/proactive/feed/{item_id}/read")
async def proactive_feed_read(item_id: str):
    from core.proactive import store as ps

    return {"status": "success", "item": ps.mark_feed(item_id, "read")}


@app.post("/api/proactive/brief")
async def proactive_brief():
    """Generate a briefing right now and post it to the feed."""
    from core.proactive import briefing

    return briefing.post(source="manual")


@app.get("/api/proactive/schedules")
async def proactive_schedules():
    from core.proactive import store as ps

    return {"schedules": ps.list_schedules()}


@app.post("/api/proactive/schedules")
async def proactive_create_schedule(req: ScheduleReq):
    from core.proactive import store as ps

    try:
        return {"status": "success", "schedule": ps.add_schedule(
            req.name, req.kind, req.trigger, req.goal, req.enabled)}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/proactive/schedules/{sid}/run")
async def proactive_run_schedule(sid: str):
    from core.proactive import scheduler

    return scheduler.run_schedule_now(sid)


@app.post("/api/proactive/schedules/{sid}/toggle")
async def proactive_toggle_schedule(sid: str, enabled: bool = True):
    from core.proactive import store as ps

    sched = ps.set_enabled(sid, enabled)
    if sched is None:
        raise HTTPException(status_code=404, detail=f"No schedule '{sid}'")
    return {"status": "success", "schedule": sched}


@app.delete("/api/proactive/schedules/{sid}")
async def proactive_delete_schedule(sid: str):
    from core.proactive import store as ps

    return {"status": "success" if ps.delete_schedule(sid) else "not_found"}


# --------------------------------------------------------------------------- #
# Observability + unified OS snapshot (§ Phase 7 — dashboard)
# --------------------------------------------------------------------------- #
@app.get("/api/observe")
async def observe(limit: int = 20):
    """Metrics + recent turn traces."""
    from core import observability

    return observability.summary(limit)


@app.get("/api/system")
async def system_snapshot():
    """One call that powers the Integrated OS panel: autonomy, calendar, feed,
    schedules, plans, pending approvals, and live metrics."""
    from datetime import date
    from core import observability
    from core.calendar import store as cal
    from core.planning import store as plan_store
    from core.proactive import store as ps
    from core.security import gateway

    return {
        "mode": gateway.get_mode().value,
        "pending": gateway.pending(),
        "calendar": {"today": cal.today(), "free_today": cal.free_slots(date.today())},
        "feed": {"items": ps.list_feed(15), "unread": ps.unread_count()},
        "schedules": ps.list_schedules(),
        "plans": [p for p in plan_store.recent(10)
                  if p.get("status") in ("active", "paused")],
        "observability": observability.metrics(),
    }


@app.get("/api/health")
async def health_check():
    return {"status": "ok", "message": "JARVIS Core is running"}


@app.on_event("startup")
def _start_voice_service():
    """Init the datastore, then launch the always-on 'Hey Jarvis' voice loop."""
    import os
    import threading

    try:
        from core.db import init_db
        init_db()
        print("[db] SQLite spine ready")
    except Exception as e:
        print(f"[db] could not init datastore: {e}")

    # MCP tool bus (§7) — connect declared servers in the background so a
    # first-run `npx` download doesn't block startup. Disable with JARVIS_NO_MCP=1.
    if os.environ.get("JARVIS_NO_MCP") == "1":
        print("[mcp] disabled via JARVIS_NO_MCP=1")
    else:
        def _mcp_boot():
            try:
                from core import mcp as mcp_bus

                h = mcp_bus.start()
                print(f"[mcp] tool bus ready — {h.get('tool_count', 0)} tool(s) "
                      f"across {len(h.get('servers', []))} server(s)")
            except Exception as e:
                print(f"[mcp] could not start tool bus: {e}")

        threading.Thread(target=_mcp_boot, name="jarvis-mcp-boot", daemon=True).start()

    # Proactive scheduler — briefings, reflection, scheduled workflows (§ Phase 7).
    if os.environ.get("JARVIS_NO_SCHEDULER") == "1":
        print("[scheduler] disabled via JARVIS_NO_SCHEDULER=1")
    else:
        try:
            from core.proactive import scheduler

            scheduler.start()
        except Exception as e:
            print(f"[scheduler] could not start: {e}")

    if os.environ.get("JARVIS_NO_VOICE") == "1":
        print("[voice] disabled via JARVIS_NO_VOICE=1")
        return
    try:
        from core.voice import service

        threading.Thread(target=service.run, name="jarvis-voice", daemon=True).start()
        print("[voice] always-on voice service starting — say 'Hey Jarvis'")
    except Exception as e:
        print(f"[voice] could not start voice service: {e}")


@app.on_event("shutdown")
def _stop_mcp():
    """Tear down MCP child processes cleanly on brain shutdown."""
    try:
        from core import mcp as mcp_bus

        mcp_bus.stop()
    except Exception:
        pass

def start():
    print("Starting JARVIS Agent Core on port 8000...")
    uvicorn.run("core.app.main:app", host="127.0.0.1", port=8000, reload=True)

if __name__ == "__main__":
    start()
