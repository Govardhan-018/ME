"""
notion_agent.py  —  Natural-language Notion agent for J.A.R.V.I.S.
===================================================================
LLMs used (all LOCAL via Ollama — zero cloud):
  • Intent model  : gemma3:12b  (fast, parses what the user wants)
  • Content model : llama3.2:latest  (generates rich page content)

The brain/orchestrator can call run_agent() directly.
Run as a standalone REPL:  python notion_agent.py

Requires:
  • NOTION_TOKEN in environment  (from Notion integration)
  • Ollama running locally        (ollama serve)
"""

from __future__ import annotations

import json
import os
import re
import sys
import textwrap
from datetime import datetime, timezone
from typing import Any

import requests

from core.tools.notion_tool import (
    B,
    NotionClient,
    markdown_to_blocks,
    summarise_page,
    _clean_id,
    _extract_title,
)

# ── LLM config ────────────────────────────────────────────────────────────────

OLLAMA_BASE    = "http://localhost:11434"
INTENT_MODEL   = "gemma3:1b"        # fast, small — great for intent parsing
CONTENT_MODEL  = "llama3.2:latest"  # generates rich page content
# Upgrade intent to gemma3:12b later for better accuracy (ollama pull gemma3:12b)

# ── Default home for parentless page creation ────────────────────────────────
# Without this, "create X" used to nest inside the LAST page JARVIS made, so
# every new page burrowed one level deeper. New pages now land as siblings under
# one stable hub instead. Point it anywhere by setting NOTION_HOME_PAGE_ID, or
# rename the auto-created hub with NOTION_HOME_PAGE_TITLE.
HOME_PAGE_ID    = os.environ.get("NOTION_HOME_PAGE_ID") or os.environ.get("NOTION_PARENT_ID")
HOME_PAGE_TITLE = os.environ.get("NOTION_HOME_PAGE_TITLE", "JARVIS")

# ── Ollama helper ─────────────────────────────────────────────────────────────

def _ollama(messages: list[dict], model: str, temperature: float = 0.3) -> str:
    payload = {
        "model":    model,
        "messages": messages,
        "stream":   False,
        "options":  {"temperature": temperature},
    }
    try:
        r = requests.post(f"{OLLAMA_BASE}/api/chat", json=payload, timeout=120)
        r.raise_for_status()
        return r.json()["message"]["content"].strip()
    except requests.exceptions.ConnectionError:
        sys.exit("[JARVIS] Cannot reach Ollama at localhost:11434. Run: ollama serve")


# ── Stage 1: Intent parsing ───────────────────────────────────────────────────

_INTENT_SYSTEM = textwrap.dedent("""
    You are an intent-extraction assistant for a Notion AI agent called JARVIS.
    The user will tell you today's date in their message.

    Given the user command, output ONLY a single JSON object (no markdown, no prose).

    JSON keys:
      action         (string, required) — one of:
                       "create_page"       create a brand-new page
                       "create_db_entry"   add a row to a database / table
                       "append"            add content to an existing page
                       "search"            find pages or databases
                       "list"              list recent pages or databases
                       "organize"          rename, move, or tag existing pages
                       "query_db"          query a database with filters
                       "summarize_page"    read & summarize an existing page

      title          (string | null)  — title for the new page/entry
      parent_title   (string | null)  — title of the parent page or database to create inside
      target_title   (string | null)  — existing page/db to act on (for append/organize/query)
      content_hint   (string | null)  — what should be in the page (topic, bullet ideas, etc.)
      content_type   (string | null)  — "notes"|"study_plan"|"research"|"todo"|"outline"|"journal"|"general"
      icon_emoji     (string | null)  — suggest a fitting emoji icon for the page
      query          (string | null)  — search/filter query for search/query_db
      properties     (object | null)  — extra DB column values e.g. {"Status":"In Progress","Priority":"High"}
      max_results    (integer)        — how many results to show for search/list (default 5)

    Rules:
    - Set parent_title ONLY when the user explicitly names a page or database to
      create inside (e.g. "in my Travel page"). If no parent is named, parent_title
      MUST be null — never guess one or reuse a page mentioned earlier.
    - If the user says "add", "append", "write to" → action = "append"
    - If the user says "create", "make", "build", "write a new" → action = "create_page"
    - If the user says "show", "list", "find", "search" → action = "search" or "list"
    - If the user says "organize", "rename", "tag" → action = "organize"
    - Always pick a fitting icon_emoji for the content type.
    - Output ONLY the JSON object.
""").strip()

def parse_intent(command: str, model: str = INTENT_MODEL) -> dict:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    # Inject date in user message to avoid .format() conflicts with JSON braces in prompt
    messages = [
        {"role": "system",  "content": _INTENT_SYSTEM},
        {"role": "user",    "content": f"Today is {today}.\n\nCommand: {command}"},
    ]
    raw = _ollama(messages, model)
    raw = re.sub(r"```json|```", "", raw).strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Intent model returned invalid JSON:\n{raw}") from exc


# ── Stage 2: Content generation ───────────────────────────────────────────────

_CONTENT_SYSTEM = textwrap.dedent("""
    You are a structured content writer for Notion pages.
    Write content in clean Markdown that will be converted into Notion blocks.

    Markdown rules you must follow exactly:
      # Title        → big heading
      ## Section     → medium heading
      ### Sub        → small heading
      - item         → bullet point
      1. item        → numbered list
      - [ ] task     → unchecked todo
      - [x] done     → checked todo
      > note         → quote / callout
      ```lang\\n...``` → code block
      ---            → divider

    Content quality rules:
    - Be specific, structured, and genuinely useful.
    - Use headings to break sections clearly.
    - Use todos for actionable items.
    - Use bullets for lists of ideas or resources.
    - Keep it concise but complete.
    - Do NOT wrap the output in a code fence — output raw markdown only.
""").strip()

def generate_content(
    title: str,
    content_type: str,
    content_hint: str,
    model: str = CONTENT_MODEL,
) -> str:
    prompt = (
        f"Create a well-structured Notion page titled '{title}'.\n"
        f"Content type: {content_type}\n"
        f"Topic / context: {content_hint}\n\n"
        "Write the full page content in Markdown now:"
    )
    messages = [
        {"role": "system", "content": _CONTENT_SYSTEM},
        {"role": "user",   "content": prompt},
    ]
    return _ollama(messages, model, temperature=0.6)


# ── Default-parent resolution ─────────────────────────────────────────────────

def _find_exact_page(client: NotionClient, title: str) -> dict | None:
    """Exact (case-insensitive) title match only — no substring soft-match, so the
    hub never accidentally resolves to a child page like 'JARVIS — Japan Trip'.
    If duplicate hubs exist, return the OLDEST so everything converges on one."""
    target = title.lower().strip()
    matches = [
        r for r in client.search(query=title, filter_type="page")
        if _extract_title(r).lower().strip() == target
    ]
    if not matches:
        return None
    matches.sort(key=lambda r: r.get("created_time", ""))  # oldest = canonical hub
    return matches[0]


def _stable_anchor_id(client: NotionClient) -> str | None:
    """A stable place to create the hub under: the oldest top-level page, else the
    oldest visible page. 'Oldest' never resolves to a page JARVIS just created."""
    top = client.list_top_level_pages(max_results=10)
    if top:
        return top[0]["id"]
    pages = client.search(query="", filter_type="page", max_results=50)
    if pages:
        pages.sort(key=lambda p: p.get("created_time", ""))
        return pages[0]["id"]
    return None


# Process cache: once resolved, reuse the same hub id for the rest of the run so
# rapid back-to-back creates can't each spawn a duplicate hub before Notion's
# search index catches up. Cleared on restart (by then the hub is indexed).
_RESOLVED_HOME_ID: str | None = None


def resolve_home_parent(client: NotionClient, *, use_cache: bool = True) -> str | None:
    """
    Resolve the STABLE parent that parentless new pages should live under.

    Order: (0) process cache, (1) NOTION_HOME_PAGE_ID env, (2) an existing hub
    page named HOME_PAGE_TITLE, (3) create that hub once under a stable anchor.
    Never returns "the most recently edited page" — that recency fallback is what
    made every new page nest inside the previous one.
    """
    global _RESOLVED_HOME_ID
    if use_cache and _RESOLVED_HOME_ID:
        return _RESOLVED_HOME_ID

    if HOME_PAGE_ID:
        _RESOLVED_HOME_ID = _clean_id(HOME_PAGE_ID)
        return _RESOLVED_HOME_ID

    hub = _find_exact_page(client, HOME_PAGE_TITLE)
    if hub:
        _RESOLVED_HOME_ID = hub["id"]
        return _RESOLVED_HOME_ID

    anchor = _stable_anchor_id(client)
    if not anchor:
        return None  # nothing shared with the integration yet

    print(f"  [JARVIS] Creating Notion hub page '{HOME_PAGE_TITLE}' for new pages…")
    hub = client.create_page(
        title=HOME_PAGE_TITLE,
        blocks=[B.callout(
            "Home for pages JARVIS creates. New pages land here as siblings.",
            emoji="🤖",
        )],
        parent_page_id=anchor,
        icon_emoji="🤖",
    )
    _RESOLVED_HOME_ID = hub["id"]
    return _RESOLVED_HOME_ID


# ── Stage 3: Action executor ──────────────────────────────────────────────────

def execute_intent(
    intent: dict,
    client: NotionClient,
    content_model: str = CONTENT_MODEL,
) -> dict[str, Any]:
    action = intent.get("action", "search")

    # ── CREATE PAGE ───────────────────────────────────────────────────────────
    if action == "create_page":
        title        = intent.get("title") or "Untitled"
        content_hint = intent.get("content_hint") or title
        content_type = intent.get("content_type") or "general"
        icon         = intent.get("icon_emoji")
        parent_title = intent.get("parent_title")

        # Find parent page if given
        parent_id: str | None = None
        if parent_title:
            parent_page = client.find_page_by_title(parent_title)
            if parent_page:
                parent_id = parent_page["id"]
            else:
                # Maybe it's a database?
                parent_db = client.find_database_by_title(parent_title)
                if parent_db:
                    # Redirect to db-entry flow
                    intent["action"] = "create_db_entry"
                    intent["_resolved_db_id"] = parent_db["id"]
                    return execute_intent(intent, client, content_model)

        if not parent_id:
            # No explicit parent → use the stable hub, NOT the most-recent page.
            # (Picking the most-recent page is what made pages nest endlessly.)
            parent_id = resolve_home_parent(client)
            if not parent_id:
                return {"error": "No parent page found. Share at least one page with your Notion integration."}

        # Generate content
        print(f"  [JARVIS] Generating content for '{title}'…")
        md = generate_content(title, content_type, content_hint, model=content_model)
        blocks = markdown_to_blocks(md)

        # Create the page
        page = client.create_page(
            title=title,
            blocks=blocks,
            parent_page_id=parent_id,
            icon_emoji=icon,
        )
        return {
            "action":  "create_page",
            "status":  "created",
            "page":    summarise_page(page),
            "url":     page.get("url", ""),
            "blocks_added": len(blocks),
        }

    # ── CREATE DATABASE ENTRY ─────────────────────────────────────────────────
    elif action == "create_db_entry":
        title        = intent.get("title") or "Untitled Entry"
        target_title = intent.get("target_title") or intent.get("parent_title")
        content_hint = intent.get("content_hint") or ""
        content_type = intent.get("content_type") or "notes"
        icon         = intent.get("icon_emoji")
        extra_props  = intent.get("properties") or {}
        db_id        = intent.get("_resolved_db_id")

        if not db_id:
            if not target_title:
                return {"error": "Specify which database to add the entry to."}
            db = client.find_database_by_title(target_title)
            if not db:
                return {"error": f"Database '{target_title}' not found. Check the name matches Notion."}
            db_id = db["id"]

        blocks: list[dict] = []
        if content_hint:
            print(f"  [JARVIS] Generating page body for DB entry '{title}'…")
            md = generate_content(title, content_type, content_hint, model=content_model)
            blocks = markdown_to_blocks(md)

        page = client.create_database_entry(
            db_id=db_id,
            title=title,
            extra_properties=extra_props if extra_props else None,
            blocks=blocks if blocks else None,
            icon_emoji=icon,
        )
        return {
            "action":  "create_db_entry",
            "status":  "created",
            "entry":   summarise_page(page),
            "url":     page.get("url", ""),
        }

    # ── APPEND TO PAGE ────────────────────────────────────────────────────────
    elif action == "append":
        target_title = intent.get("target_title") or intent.get("title")
        content_hint = intent.get("content_hint") or ""
        content_type = intent.get("content_type") or "notes"

        if not target_title:
            return {"error": "Tell me which page to append content to."}

        page = client.find_page_by_title(target_title)
        if not page:
            return {"error": f"Page '{target_title}' not found."}

        print(f"  [JARVIS] Generating content to append to '{_extract_title(page)}'…")
        md = generate_content(
            title=_extract_title(page),
            content_type=content_type,
            content_hint=content_hint,
            model=content_model,
        )
        blocks = markdown_to_blocks(md)
        client.append_blocks(page["id"], blocks)

        return {
            "action":       "append",
            "status":       "appended",
            "page":         summarise_page(page),
            "blocks_added": len(blocks),
            "url":          page.get("url", ""),
        }

    # ── SEARCH ────────────────────────────────────────────────────────────────
    elif action == "search":
        query       = intent.get("query") or intent.get("target_title") or ""
        max_results = int(intent.get("max_results") or 5)

        results = client.search(query=query, max_results=max_results)
        return {
            "action":  "search",
            "query":   query,
            "count":   len(results),
            "results": [summarise_page(r) for r in results],
        }

    # ── LIST ──────────────────────────────────────────────────────────────────
    elif action == "list":
        max_results = int(intent.get("max_results") or 10)
        pages = client.list_workspace_pages(max_results=max_results)
        return {
            "action":  "list",
            "count":   len(pages),
            "pages":   [summarise_page(p) for p in pages],
        }

    # ── QUERY DATABASE ────────────────────────────────────────────────────────
    elif action == "query_db":
        target_title = intent.get("target_title") or intent.get("title")
        max_results  = int(intent.get("max_results") or 10)

        if not target_title:
            return {"error": "Specify which database to query."}

        db = client.find_database_by_title(target_title)
        if not db:
            return {"error": f"Database '{target_title}' not found."}

        rows = client.query_database(db["id"], max_results=max_results)
        return {
            "action":   "query_db",
            "database": _extract_title(db),
            "count":    len(rows),
            "rows":     [summarise_page(r) for r in rows],
        }

    # ── ORGANIZE ──────────────────────────────────────────────────────────────
    elif action == "organize":
        target_title = intent.get("target_title")
        new_title    = intent.get("title")

        if not target_title:
            return {"error": "Specify which page to organize/rename."}

        page = client.find_page_by_title(target_title)
        if not page:
            return {"error": f"Page '{target_title}' not found."}

        if new_title:
            client.rename_page(page["id"], new_title)
            return {
                "action": "organize",
                "status": "renamed",
                "old_title": target_title,
                "new_title": new_title,
                "url": page.get("url", ""),
            }

        return {"action": "organize", "status": "no_change", "note": "Specify a new title to rename."}

    # ── SUMMARIZE PAGE ────────────────────────────────────────────────────────
    elif action == "summarize_page":
        target_title = intent.get("target_title") or intent.get("title")

        if not target_title:
            return {"error": "Specify which page to summarize."}

        page = client.find_page_by_title(target_title)
        if not page:
            return {"error": f"Page '{target_title}' not found."}

        children = client.get_block_children(page["id"], max_results=50)
        # Extract plain text from blocks
        text_parts: list[str] = []
        for block in children:
            btype = block.get("type", "")
            rt = block.get(btype, {}).get("rich_text", [])
            for t in rt:
                text_parts.append(t.get("plain_text", ""))

        raw_text = " ".join(text_parts)[:3000]

        messages = [
            {"role": "system", "content": "Summarize the following Notion page content in 3-5 concise bullet points."},
            {"role": "user",   "content": f"Page title: {_extract_title(page)}\n\nContent:\n{raw_text}"},
        ]
        summary = _ollama(messages, content_model, temperature=0.3)

        return {
            "action":  "summarize_page",
            "page":    summarise_page(page),
            "summary": summary,
            "url":     page.get("url", ""),
        }

    return {"error": f"Unknown action: {action!r}"}


# ── Top-level entry point (used by the brain) ─────────────────────────────────

def run_agent(
    command: str,
    intent_model:  str = INTENT_MODEL,
    content_model: str = CONTENT_MODEL,
    notion_token:  str | None = None,
) -> dict[str, Any]:
    """
    Full pipeline:  NL command → intent → Notion action → result dict.
    This is the function the JARVIS brain/orchestrator calls.
    """
    client = NotionClient(token=notion_token)
    intent = parse_intent(command, model=intent_model)

    print(f"  [JARVIS] Intent: {json.dumps(intent, indent=2)}")

    result = execute_intent(intent, client, content_model=content_model)
    return {
        "command":   command,
        "intent":    intent,
        "result":    result,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


# ── REPL ──────────────────────────────────────────────────────────────────────

def main() -> None:
    # Load .env if present
    _load_dotenv()

    print("\n" + "=" * 60)
    print("  J.A.R.V.I.S  —  Notion Agent")
    print("  LLM  : Ollama local (no cloud, no API keys for LLM)")
    print("  Vault: NOTION_TOKEN from environment")
    print("  Type 'exit' or Ctrl-C to quit.")
    print("=" * 60 + "\n")

    while True:
        try:
            cmd = input("You → Notion: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\n[JARVIS] Goodbye.")
            break

        if not cmd:
            continue
        if cmd.lower() in {"exit", "quit", "q"}:
            print("[JARVIS] Goodbye.")
            break

        try:
            out = run_agent(cmd)
            print("\n── Result " + "─" * 50)
            print(json.dumps(out["result"], indent=2, ensure_ascii=False))
            if out["result"].get("url"):
                print(f"\n  🔗  {out['result']['url']}")
            print("─" * 60 + "\n")
        except Exception as exc:
            safe = str(exc).encode("ascii", "ignore").decode("ascii")
            print(f"[ERROR] {safe}\n")


def _load_dotenv(path: str = ".env") -> None:
    """Minimal .env loader — no dependency on python-dotenv."""
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            key = key.strip()
            val = val.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = val


if __name__ == "__main__":
    main()
