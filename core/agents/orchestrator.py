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

OLLAMA_BASE = "http://localhost:11434"
ROUTER_MODEL = "gemma3:12b"
GENERAL_MODEL = "qwen2.5:7b"

_ROUTER_SYSTEM = textwrap.dedent("""
    You are the Master Orchestrator (JARVIS).
    Your job is to read the user's intent and decide which sub-agent should handle it.

    You must output ONLY a JSON object with two keys:
    - "domain": string, one of ["notion", "gmail", "browser", "files", "general"]
    - "reasoning": string, short explanation of your choice.

    Domains:
    - "notion": Creating, searching, or organizing Notion pages, databases, study plans, research pages, etc.
    - "gmail": Reading, summarizing, sending, or prioritizing emails.
    - "browser": Searching the web, looking up current information, or fetching a web page's contents.
    - "files": Reading local files (PDFs, docs), analyzing folders, or looking for local system files.
    - "general": General knowledge, coding, writing, or chat that doesn't need external tools.

    Output pure JSON only. No markdown formatting blocks.
""").strip()

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
    messages = [
        {"role": "system", "content": _ROUTER_SYSTEM},
        {"role": "user", "content": command}
    ]
    raw = _ollama(messages, ROUTER_MODEL)
    raw = re.sub(r"```json|```", "", raw).strip()
    
    try:
        return json.loads(raw)
    except Exception:
        # Fallback if json parsing fails
        return {"domain": "general", "reasoning": "Fallback due to parse error."}

def handle_general_query(command: str) -> Dict[str, Any]:
    messages = [
        {"role": "system", "content": "You are JARVIS, a helpful and highly capable AI assistant. Answer the user's query clearly and concisely."},
        {"role": "user", "content": command}
    ]
    response = _ollama(messages, GENERAL_MODEL)
    return {
        "status": "success",
        "domain": "general",
        "answer": response
    }

def orchestrate(command: str) -> Dict[str, Any]:
    """Main entry point for the brain."""
    print(f"\n[Orchestrator] Routing command: '{command}'...")
    routing = route_intent(command)
    domain = routing.get("domain", "general")
    print(f"[Orchestrator] Domain selected: {domain} ({routing.get('reasoning')})")

    if domain == "notion":
        print("[Orchestrator] Handing off to Notion Agent...")
        try:
            result = notion.run_agent(command)
            return {"status": "success", "domain": "notion", "result": result}
        except Exception as e:
            return {"status": "error", "domain": "notion", "error": str(e)}

    elif domain == "gmail":
        print("[Orchestrator] Handing off to Gmail Agent...")
        try:
            result = gmail.run_agent(command)
            return {"status": "success", "domain": "gmail", "result": result}
        except Exception as e:
            return {"status": "error", "domain": "gmail", "error": str(e)}

    elif domain == "browser":
        print("[Orchestrator] Handing off to Browser Agent...")
        try:
            result = browser.run_agent(command)
            return {"status": "success", "domain": "browser", "result": result}
        except Exception as e:
            return {"status": "error", "domain": "browser", "error": str(e)}

    elif domain == "files":
        print("[Orchestrator] Handing off to Files Agent...")
        try:
            result = files.run_agent(command)
            return {"status": "success", "domain": "files", "result": result}
        except Exception as e:
            return {"status": "error", "domain": "files", "error": str(e)}

    else:
        print("[Orchestrator] Handling via General Knowledge...")
        return handle_general_query(command)

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
