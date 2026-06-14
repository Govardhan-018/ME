import argparse
import json
import re
import sys
import textwrap
from datetime import datetime, timezone
from typing import Any
import requests
from core.tools.gmail_pull import (
    get_gmail_service,
    get_unread_emails,
    get_emails_by_date,
    get_latest_emails,
    get_emails_by_sender,
)

import os
from dotenv import load_dotenv

load_dotenv()

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
INTENT_MODEL    = os.getenv("OLLAMA_INTENT_MODEL", "gemma3:270m")
ANALYSIS_MODEL  = os.getenv("OLLAMA_ANALYSIS_MODEL", "llama3.2:latest")

def ollama_chat(messages: list[dict], model: str) -> str:
    payload = {
        "model": model,
        "messages": messages,
        "stream": False,
    }
    try:
        resp = requests.post(f"{OLLAMA_BASE_URL}/api/chat", json=payload, timeout=120)
        resp.raise_for_status()
        return resp.json()["message"]["content"]
    except requests.exceptions.ConnectionError:
        sys.exit("[ERROR] Cannot reach Ollama at localhost:11434. Make sure 'ollama serve' is running.")

def parse_intent(user_command: str, model: str) -> dict:
    today = datetime.now(timezone.utc).strftime("%Y/%m/%d")
    system_prompt = textwrap.dedent(f"""
        You are an intent-extraction assistant for a Gmail agent.
        Today's date is {today}.
        Given the user command, output ONLY a single JSON object (no markdown, no prose) with these keys:

        action        (string, required):
            "get_unread"    - fetch unread emails
            "get_latest"    - fetch the N most-recent emails (any read status)
            "get_by_date"   - fetch emails within a date range
            "get_by_sender" - fetch emails from a specific sender

        max_results   (integer, required): how many emails to fetch (default 5, max 20)
        start_date    (string | null):  "YYYY/MM/DD"
        end_date      (string | null):  "YYYY/MM/DD"
        sender_email  (string | null):  email address

        task (string, required):
            "summarize"               - produce a brief summary of each email
            "prioritize"              - rank emails by urgency / importance
            "summarize_and_prioritize"- both
            "list"                    - just list subjects + senders

        If the command mentions both summarising and prioritising, use "summarize_and_prioritize".
        Infer missing max_results from context (e.g. "last 3 emails" -> 3).
        Output ONLY the JSON object.
    """).strip()

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user",   "content": user_command},
    ]
    raw = ollama_chat(messages, model)
    raw = re.sub(r"```json|```", "", raw).strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Ollama returned invalid JSON for intent:\n{raw}") from exc

def fetch_emails(service, intent: dict) -> list[dict]:
    action = intent.get("action", "get_unread")
    max_results = int(intent.get("max_results") or 5)

    if action == "get_unread":
        return get_unread_emails(service, max_results=max_results)
    if action == "get_latest":
        return get_latest_emails(service, n=max_results)
    if action == "get_by_date":
        start = intent.get("start_date")
        end   = intent.get("end_date")
        if not start or not end:
            raise ValueError("Intent 'get_by_date' requires start_date and end_date.")
        return get_emails_by_date(service, start, end, max_results=max_results)
    if action == "get_by_sender":
        sender = intent.get("sender_email")
        if not sender:
            raise ValueError("Intent 'get_by_sender' requires sender_email.")
        return get_emails_by_sender(service, sender, max_results=max_results)

    raise ValueError(f"Unknown action: {action!r}")

def _email_blob(emails: list[dict]) -> str:
    parts = []
    for i, em in enumerate(emails, 1):
        parts.append(
            f"--- EMAIL {i} ---\n"
            f"ID:      {em['id']}\n"
            f"From:    {em['from']}\n"
            f"Subject: {em['subject']}\n"
            f"Date:    {em['date']}\n"
            f"Snippet: {em['snippet']}\n"
            f"Body:    {em['body'][:500]}"
        )
    return "\n\n".join(parts)

def _make_analysis_prompt(task: str) -> str:
    if task == "summarize":
        return textwrap.dedent("""
            For each email produce a concise 1-2 sentence summary.
            Return ONLY a JSON array of objects with keys: id, subject, from, summary
            No markdown, no prose outside the JSON.
        """).strip()
    if task == "prioritize":
        return textwrap.dedent("""
            Rank the emails by urgency and business importance. Assign priority: "high", "medium", or "low".
            Provide a one-sentence reason for the ranking.
            Return ONLY a JSON array (sorted high -> low) with keys: id, subject, from, priority, reason
            No markdown, no prose outside the JSON.
        """).strip()

    return textwrap.dedent("""
        For each email:
          1. Write a concise 1-2 sentence summary.
          2. Assign priority: "high", "medium", or "low".
          3. Provide a one-sentence reason for the priority.
        Return ONLY a JSON array (sorted high -> low priority) with keys: id, subject, from, summary, priority, reason
        No markdown, no prose outside the JSON.
    """).strip()

def analyse_emails(emails: list[dict], task: str, model: str) -> list[dict]:
    if not emails:
        return []

    system_prompt = "You receive raw email data and perform analysis tasks. Always return valid JSON - nothing else."
    user_prompt = f"{_make_analysis_prompt(task)}\n\nHere are the emails:\n\n{_email_blob(emails)}"

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user",   "content": user_prompt},
    ]
    raw = ollama_chat(messages, model)
    raw = re.sub(r"```json|```", "", raw).strip()

    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Ollama returned invalid JSON for analysis:\n{raw}") from exc

def run_agent(
    user_command: str,
    intent_model: str = INTENT_MODEL,
    analysis_model: str = ANALYSIS_MODEL,
    credentials_path: str = "credentials.json",
    token_path: str = "token.json",
) -> dict[str, Any]:
    intent = parse_intent(user_command, intent_model)
    service = get_gmail_service(credentials_path, token_path)
    emails = fetch_emails(service, intent)
    task = intent.get("task", "summarize_and_prioritize")
    
    if task == "list":
        results = [{"id": e["id"], "subject": e["subject"], "from": e["from"], "date": e["date"]} for e in emails]
    else:
        results = analyse_emails(emails, task, analysis_model)

    return {
        "command":        user_command,
        "intent":         intent,
        "emails_fetched": len(emails),
        "task":           task,
        "results":        results,
        "raw_emails":     emails,
        "timestamp":      datetime.now(timezone.utc).isoformat(),
    }

def main():
    parser = argparse.ArgumentParser(description="Natural-language Gmail agent (local Ollama)")
    parser.add_argument("--intent-model",   default=INTENT_MODEL,   help="Ollama model for intent parsing")
    parser.add_argument("--analysis-model", default=ANALYSIS_MODEL, help="Ollama model for analysis/summaries")
    parser.add_argument("--credentials", default="credentials.json", help="Path to Google OAuth credentials JSON")
    parser.add_argument("--token",       default="token.json",       help="Path to cached OAuth token")
    parser.add_argument("--output",      default=None,               help="Write JSON result to this file")
    parser.add_argument("--no-raw",      action="store_true",        help="Omit raw_emails from output (smaller JSON)")
    args = parser.parse_args()

    print("Gmail Agent  |  type 'exit' or Ctrl-C to quit\n")

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
            result = run_agent(
                command,
                intent_model=args.intent_model,
                analysis_model=args.analysis_model,
                credentials_path=args.credentials,
                token_path=args.token,
            )

            if args.no_raw:
                result.pop("raw_emails", None)

            pretty = json.dumps(result, indent=2, ensure_ascii=True)
            print("\n-- Agent Response -------------------------------------")
            print(pretty)
            print("-------------------------------------------------------\n")

            if args.output:
                with open(args.output, "w") as fh:
                    fh.write(pretty)
                print(f"[Agent] Result written to {args.output}\n")

        except Exception as exc:
            clean_exc = str(exc).encode('ascii', 'ignore').decode('ascii')
            print(f"[ERROR] {clean_exc}\n")

if __name__ == "__main__":
    main()