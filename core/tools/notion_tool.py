"""
notion_tool.py  —  Low-level Notion API client for J.A.R.V.I.S.
=================================================================
This is the TOOL layer.  The brain/orchestrator imports and calls
these methods directly.  No LLM lives here — just clean Notion API
wrappers plus a rich block-builder so the agent can express any
content structure Notion supports.

Set NOTION_TOKEN in your environment (or .env file) before use.
"""

from __future__ import annotations

import os
import re
import textwrap
from typing import Any

import requests

# ── Config ────────────────────────────────────────────────────────────────────

NOTION_VERSION = "2022-06-28"
NOTION_BASE    = "https://api.notion.com/v1"


# ── Client ────────────────────────────────────────────────────────────────────

class NotionClient:
    """Thin, typed wrapper around the Notion REST API."""

    def __init__(self, token: str | None = None) -> None:
        token = token or os.environ.get("NOTION_TOKEN")
        if not token:
            raise EnvironmentError(
                "NOTION_TOKEN not set.  Add it to your .env or export it before running."
            )
        self._headers = {
            "Authorization":  f"Bearer {token}",
            "Notion-Version": NOTION_VERSION,
            "Content-Type":   "application/json",
        }

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _get(self, path: str, params: dict | None = None) -> dict:
        r = requests.get(f"{NOTION_BASE}{path}", headers=self._headers,
                         params=params, timeout=30)
        r.raise_for_status()
        return r.json()

    def _post(self, path: str, body: dict) -> dict:
        r = requests.post(f"{NOTION_BASE}{path}", headers=self._headers,
                          json=body, timeout=30)
        r.raise_for_status()
        return r.json()

    def _patch(self, path: str, body: dict) -> dict:
        r = requests.patch(f"{NOTION_BASE}{path}", headers=self._headers,
                           json=body, timeout=30)
        r.raise_for_status()
        return r.json()

    # ── Search ────────────────────────────────────────────────────────────────

    def search(
        self,
        query: str = "",
        filter_type: str | None = None,   # "page" | "database"
        max_results: int = 10,
    ) -> list[dict]:
        """Full-text search across all pages/databases the integration can see."""
        body: dict[str, Any] = {
            "query":      query,
            "page_size":  min(max_results, 100),
            "sort":       {"direction": "descending", "timestamp": "last_edited_time"},
        }
        if filter_type:
            body["filter"] = {"value": filter_type, "property": "object"}

        data = self._post("/search", body)
        return data.get("results", [])

    def find_page_by_title(self, title: str) -> dict | None:
        """Return the first page whose title matches (case-insensitive)."""
        results = self.search(query=title, filter_type="page")
        title_lower = title.lower().strip()
        for r in results:
            t = _extract_title(r)
            if t.lower().strip() == title_lower:
                return r
        # soft match — substring
        for r in results:
            if title_lower in _extract_title(r).lower():
                return r
        return None

    def find_database_by_title(self, title: str) -> dict | None:
        """Return the first database whose title matches (case-insensitive)."""
        results = self.search(query=title, filter_type="database")
        title_lower = title.lower().strip()
        for r in results:
            t = _extract_title(r)
            if title_lower in t.lower():
                return r
        return None

    # ── Read ──────────────────────────────────────────────────────────────────

    def get_page(self, page_id: str) -> dict:
        return self._get(f"/pages/{_clean_id(page_id)}")

    def get_block_children(self, block_id: str, max_results: int = 50) -> list[dict]:
        data = self._get(
            f"/blocks/{_clean_id(block_id)}/children",
            params={"page_size": max_results},
        )
        return data.get("results", [])

    def query_database(
        self,
        db_id: str,
        filter_obj: dict | None = None,
        sorts: list[dict] | None = None,
        max_results: int = 20,
    ) -> list[dict]:
        """Query a database with optional filter + sort."""
        body: dict[str, Any] = {"page_size": min(max_results, 100)}
        if filter_obj:
            body["filter"] = filter_obj
        if sorts:
            body["sorts"] = sorts

        data = self._post(f"/databases/{_clean_id(db_id)}/query", body)
        return data.get("results", [])

    # ── Create ────────────────────────────────────────────────────────────────

    def create_page(
        self,
        title: str,
        blocks: list[dict] | None = None,
        parent_page_id: str | None = None,
        parent_db_id: str | None = None,
        properties: dict | None = None,
        icon_emoji: str | None = None,
        cover_url: str | None = None,
    ) -> dict:
        """
        Create a new page.
        - Supply parent_page_id OR parent_db_id (not both).
        - blocks: list of Notion block objects (use BlockBuilder helpers below).
        - properties: extra property map for database entries.
        """
        if parent_db_id:
            parent = {"type": "database_id", "database_id": _clean_id(parent_db_id)}
        elif parent_page_id:
            parent = {"type": "page_id", "page_id": _clean_id(parent_page_id)}
        else:
            raise ValueError("Provide either parent_page_id or parent_db_id.")

        # Title property
        props: dict[str, Any] = {
            "title": {"title": [{"type": "text", "text": {"content": title}}]}
        }
        if properties:
            props.update(properties)

        body: dict[str, Any] = {"parent": parent, "properties": props}
        if blocks:
            body["children"] = blocks
        if icon_emoji:
            body["icon"] = {"type": "emoji", "emoji": icon_emoji}
        if cover_url:
            body["cover"] = {"type": "external", "external": {"url": cover_url}}

        return self._post("/pages", body)

    def create_database_entry(
        self,
        db_id: str,
        title: str,
        extra_properties: dict | None = None,
        blocks: list[dict] | None = None,
        icon_emoji: str | None = None,
    ) -> dict:
        """Shorthand: create a row in a database with an optional page body."""
        return self.create_page(
            title=title,
            parent_db_id=db_id,
            properties=extra_properties,
            blocks=blocks,
            icon_emoji=icon_emoji,
        )

    # ── Append ────────────────────────────────────────────────────────────────

    def append_blocks(self, page_or_block_id: str, blocks: list[dict]) -> dict:
        """Append content blocks to an existing page or block."""
        return self._patch(
            f"/blocks/{_clean_id(page_or_block_id)}/children",
            {"children": blocks},
        )

    # ── Update ────────────────────────────────────────────────────────────────

    def update_page_properties(self, page_id: str, properties: dict) -> dict:
        """Update named properties of an existing page (title, status, tags, etc.)."""
        return self._patch(f"/pages/{_clean_id(page_id)}", {"properties": properties})

    def rename_page(self, page_id: str, new_title: str) -> dict:
        return self.update_page_properties(page_id, {
            "title": {"title": [{"type": "text", "text": {"content": new_title}}]}
        })

    def archive_page(self, page_id: str) -> dict:
        """Soft-delete (archive) a page. Can be restored from Notion UI."""
        return self._patch(f"/pages/{_clean_id(page_id)}", {"archived": True})

    # ── Convenience ───────────────────────────────────────────────────────────

    def list_workspace_pages(self, max_results: int = 20) -> list[dict]:
        """Return top-level pages the integration can see."""
        return self.search(query="", filter_type="page", max_results=max_results)

    def list_databases(self, max_results: int = 10) -> list[dict]:
        return self.search(query="", filter_type="database", max_results=max_results)


# ── Block Builder ─────────────────────────────────────────────────────────────

class B:
    """
    Static factory for Notion block objects.
    Use these to construct the `blocks` list for create_page / append_blocks.

    Example:
        blocks = [
            B.heading1("My Plan"),
            B.paragraph("Here's the outline:"),
            B.bullet("Week 1 — foundations"),
            B.todo("Read chapter 1", checked=False),
            B.divider(),
            B.callout("⚠️ Important note", emoji="⚠️"),
        ]
    """

    @staticmethod
    def _rich(text: str, bold: bool = False, italic: bool = False,
               code: bool = False, color: str = "default") -> list[dict]:
        ann: dict[str, Any] = {
            "bold": bold, "italic": italic, "strikethrough": False,
            "underline": False, "code": code, "color": color,
        }
        return [{"type": "text", "text": {"content": text}, "annotations": ann}]

    @staticmethod
    def paragraph(text: str, color: str = "default") -> dict:
        return {
            "object": "block", "type": "paragraph",
            "paragraph": {"rich_text": B._rich(text, color=color)},
        }

    @staticmethod
    def heading1(text: str) -> dict:
        return {
            "object": "block", "type": "heading_1",
            "heading_1": {"rich_text": B._rich(text, bold=True)},
        }

    @staticmethod
    def heading2(text: str) -> dict:
        return {
            "object": "block", "type": "heading_2",
            "heading_2": {"rich_text": B._rich(text, bold=True)},
        }

    @staticmethod
    def heading3(text: str) -> dict:
        return {
            "object": "block", "type": "heading_3",
            "heading_3": {"rich_text": B._rich(text)},
        }

    @staticmethod
    def bullet(text: str) -> dict:
        return {
            "object": "block", "type": "bulleted_list_item",
            "bulleted_list_item": {"rich_text": B._rich(text)},
        }

    @staticmethod
    def numbered(text: str) -> dict:
        return {
            "object": "block", "type": "numbered_list_item",
            "numbered_list_item": {"rich_text": B._rich(text)},
        }

    @staticmethod
    def todo(text: str, checked: bool = False) -> dict:
        return {
            "object": "block", "type": "to_do",
            "to_do": {"rich_text": B._rich(text), "checked": checked},
        }

    @staticmethod
    def toggle(text: str, children: list[dict] | None = None) -> dict:
        block: dict[str, Any] = {
            "object": "block", "type": "toggle",
            "toggle": {"rich_text": B._rich(text)},
        }
        if children:
            block["toggle"]["children"] = children
        return block

    @staticmethod
    def callout(text: str, emoji: str = "💡", color: str = "blue_background") -> dict:
        return {
            "object": "block", "type": "callout",
            "callout": {
                "rich_text": B._rich(text),
                "icon": {"type": "emoji", "emoji": emoji},
                "color": color,
            },
        }

    @staticmethod
    def code(text: str, language: str = "python") -> dict:
        return {
            "object": "block", "type": "code",
            "code": {
                "rich_text": B._rich(text),
                "language": language,
            },
        }

    @staticmethod
    def quote(text: str) -> dict:
        return {
            "object": "block", "type": "quote",
            "quote": {"rich_text": B._rich(text)},
        }

    @staticmethod
    def divider() -> dict:
        return {"object": "block", "type": "divider", "divider": {}}

    @staticmethod
    def table_of_contents() -> dict:
        return {"object": "block", "type": "table_of_contents",
                "table_of_contents": {"color": "default"}}


# ── Markdown → Blocks converter ───────────────────────────────────────────────

def markdown_to_blocks(md: str) -> list[dict]:
    """
    Convert a simple markdown string into a list of Notion blocks.
    Supports: # H1, ## H2, ### H3, - bullet, 1. numbered,
              [ ] / [x] todo, > quote, ``` code, ***, ---, plain paragraph.
    The LLM content generator writes markdown; this converts it to Notion.
    """
    blocks: list[dict] = []
    lines = md.strip().splitlines()
    in_code = False
    code_lines: list[str] = []
    code_lang = "plain text"

    for line in lines:
        raw = line.rstrip()

        # ── Code fence ───────────────────────────────────────────────────────
        if raw.startswith("```"):
            if in_code:
                blocks.append(B.code("\n".join(code_lines), language=code_lang))
                code_lines = []
                in_code = False
            else:
                in_code = True
                lang = raw[3:].strip()
                code_lang = lang if lang else "plain text"
            continue
        if in_code:
            code_lines.append(raw)
            continue

        # ── Divider ──────────────────────────────────────────────────────────
        if re.match(r"^(\*{3,}|-{3,}|_{3,})$", raw):
            blocks.append(B.divider())
            continue

        # ── Headings ─────────────────────────────────────────────────────────
        if raw.startswith("### "):
            blocks.append(B.heading3(raw[4:].strip()))
        elif raw.startswith("## "):
            blocks.append(B.heading2(raw[3:].strip()))
        elif raw.startswith("# "):
            blocks.append(B.heading1(raw[2:].strip()))

        # ── Todo ─────────────────────────────────────────────────────────────
        elif re.match(r"^- \[x\] ", raw, re.IGNORECASE):
            blocks.append(B.todo(raw[6:].strip(), checked=True))
        elif re.match(r"^- \[ \] ", raw):
            blocks.append(B.todo(raw[6:].strip(), checked=False))

        # ── Bullet ───────────────────────────────────────────────────────────
        elif re.match(r"^[-*] ", raw):
            blocks.append(B.bullet(raw[2:].strip()))

        # ── Numbered ─────────────────────────────────────────────────────────
        elif re.match(r"^\d+\. ", raw):
            text = re.sub(r"^\d+\. ", "", raw)
            blocks.append(B.numbered(text.strip()))

        # ── Quote ────────────────────────────────────────────────────────────
        elif raw.startswith("> "):
            blocks.append(B.quote(raw[2:].strip()))

        # ── Empty line ───────────────────────────────────────────────────────
        elif raw.strip() == "":
            pass  # skip blank lines

        # ── Paragraph ────────────────────────────────────────────────────────
        else:
            blocks.append(B.paragraph(raw.strip()))

    if in_code and code_lines:            # unclosed fence
        blocks.append(B.code("\n".join(code_lines), language=code_lang))

    return blocks


# ── Utilities ─────────────────────────────────────────────────────────────────

def _clean_id(raw_id: str) -> str:
    """Strip dashes so IDs from URLs or copy-paste work."""
    return raw_id.replace("-", "").strip()


def _extract_title(obj: dict) -> str:
    """Pull the plain-text title from any page or database object."""
    try:
        props = obj.get("properties", {})
        # pages: property named 'title' or 'Name'
        for key in ("title", "Name", "name"):
            if key in props:
                t = props[key].get("title", [])
                if t:
                    return t[0]["plain_text"]
        # databases: top-level 'title' array
        title_arr = obj.get("title", [])
        if title_arr:
            return title_arr[0]["plain_text"]
    except (KeyError, IndexError):
        pass
    return "(untitled)"


def summarise_page(page: dict) -> dict:
    """Return a compact summary dict for display / logging."""
    return {
        "id":           page.get("id", ""),
        "title":        _extract_title(page),
        "object":       page.get("object", ""),
        "url":          page.get("url", ""),
        "last_edited":  page.get("last_edited_time", ""),
        "created":      page.get("created_time", ""),
    }
