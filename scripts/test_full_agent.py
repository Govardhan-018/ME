"""Quick end-to-end test of the Notion agent pipeline (Ollama + Notion).

Run from the project root:  python scripts/test_full_agent.py
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

# Load .env from the project root (no python-dotenv dependency).
_envp = os.path.join(ROOT, ".env")
if os.path.exists(_envp):
    for _line in open(_envp, encoding="utf-8"):
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _, _v = _line.partition("=")
            os.environ.setdefault(_k.strip(), _v.strip().strip('"').strip("'"))

from core.agents.notion import run_agent

print("=" * 60)
print("  JARVIS — Full Notion Agent Test (Ollama + Notion)")
print("=" * 60)
print("\nCommand: 'Create a study plan for Machine Learning course'\n")

result = run_agent("Create a study plan for Machine Learning course")

r = result["result"]
print("\n" + "=" * 60)
if r.get("status") == "created":
    print("  SUCCESS!")
    print(f"  Page   : {r['page']['title']}")
    print(f"  Blocks : {r.get('blocks_added', '?')} blocks")
    print(f"  URL    : {r['url']}")
elif r.get("error"):
    print(f"  ERROR  : {r['error']}")
else:
    print(f"  Result : {r}")
print("=" * 60)
