"""Direct Notion tool test — no Ollama needed. Creates a real JARVIS page.

Reads NOTION_TOKEN from .env (no hardcoded secrets).
Optionally set NOTION_TEST_PARENT_ID in .env to target a specific parent page.
Run from the project root:  python scripts/test_notion.py
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

_envp = os.path.join(ROOT, ".env")
if os.path.exists(_envp):
    for _line in open(_envp, encoding="utf-8"):
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _, _v = _line.partition("=")
            os.environ.setdefault(_k.strip(), _v.strip().strip('"').strip("'"))

from core.tools.notion_tool import NotionClient, B

TOKEN = os.environ.get("NOTION_TOKEN")
PARENT_ID = os.environ.get("NOTION_TEST_PARENT_ID", "")

if not TOKEN:
    sys.exit("Set NOTION_TOKEN in your .env first.")
if not PARENT_ID:
    sys.exit("Set NOTION_TEST_PARENT_ID in your .env to the page you want to create under.")

client = NotionClient(token=TOKEN)

print("=" * 55)
print("  JARVIS — Notion Tool Live Test")
print("=" * 55)

blocks = [
    B.callout("JARVIS is connected and operational.", emoji="🤖", color="blue_background"),
    B.divider(),
    B.heading1("JARVIS — Project Overview"),
    B.paragraph("This page was created automatically by the JARVIS Notion agent. No cloud, no manual work."),
    B.heading2("System Status"),
    B.bullet("Notion API — connected"),
    B.bullet("Token authenticated"),
    B.bullet("Page read/write — working"),
    B.divider(),
    B.heading2("Planned Modules"),
    B.numbered("Gmail Agent — summarise & prioritise emails"),
    B.numbered("Notion Agent — create, search, organise pages"),
    B.numbered("Voice Interface — wake word + STT + TTS"),
    B.numbered("Research Agent — find papers, build pages"),
    B.divider(),
    B.heading2("Architecture"),
    B.code(
        "User -> Electron HUD\n"
        "     -> FastAPI Brain (Python)\n"
        "         -> Notion Tool  (this!)\n"
        "         -> Gmail Tool\n"
        "         -> Voice Pipeline\n"
        "         -> Ollama / Claude (LLM router)",
        language="plain text",
    ),
    B.divider(),
    B.quote("Tools are the product. The model is a commodity you can swap. — JARVIS Design Doc"),
]

print("\nCreating page in your Notion...")
page = client.create_page(
    title="JARVIS — Live Test",
    blocks=blocks,
    parent_page_id=PARENT_ID,
    icon_emoji="🤖",
)

print(f"\n{'=' * 55}")
print("  Page created successfully!")
print(f"  URL   : {page['url']}")
print(f"  ID    : {page['id']}")
print(f"  Blocks: {len(blocks)} blocks written")
print(f"{'=' * 55}\n")
