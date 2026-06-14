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
    # Lazy import so faster-whisper (heavy) doesn't slow brain startup.
    from core.voice import stt

    data = await request.body()
    if not data:
        return {"text": ""}

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".webm")
    try:
        tmp.write(data)
        tmp.close()
        text = stt.transcribe_file(tmp.name)
        return {"text": text}
    except Exception as e:
        return {"text": "", "error": str(e)}
    finally:
        try:
            os.remove(tmp.name)
        except OSError:
            pass


@app.get("/api/health")
async def health_check():
    return {"status": "ok", "message": "JARVIS Core is running"}

def start():
    print("Starting JARVIS Agent Core on port 8000...")
    uvicorn.run("core.app.main:app", host="127.0.0.1", port=8000, reload=True)

if __name__ == "__main__":
    start()
