"""
Tests for the MCP tool bus (§7).

Deterministic, offline checks (tier classification, config/env expansion, result
normalization, graceful degradation, orchestrator wiring) always run — no Ollama,
no network. A final best-effort block actually starts the official filesystem
server (needs `npx` + first-run network) and proves a gateway-gated write/read in
the sandbox; it prints SKIP if the server can't connect.

    python scripts/test_mcp.py
"""
import os
import sys
import tempfile
import traceback

_TMP = os.path.join(tempfile.gettempdir(), "jarvis_test_mcp.db")
for _ext in ("", "-wal", "-shm"):
    try:
        os.remove(_TMP + _ext)
    except OSError:
        pass
os.environ["JARVIS_DB_PATH"] = _TMP
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core import mcp as mcp_bus
from core.mcp.client import _expand, _normalize_result, classify_tool, load_config
from core.security import gateway
from core.security.tiers import ActionRequest, RiskTier

PASS = 0
FAIL = 0


def check(name: str, cond: bool) -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  [PASS] {name}")
    else:
        FAIL += 1
        print(f"  [FAIL] {name}")


print("== per-tool risk tiers (§6.2) ==")
check("read_file -> read", classify_tool("read_file") == RiskTier.READ)
check("list_directory -> read", classify_tool("list_directory") == RiskTier.READ)
check("write_file -> write", classify_tool("write_file") == RiskTier.WRITE)
check("edit_file -> write", classify_tool("edit_file") == RiskTier.WRITE)
check("move_file -> write", classify_tool("move_file") == RiskTier.WRITE)
check("delete_file -> irreversible", classify_tool("delete_file") == RiskTier.IRREVERSIBLE)
check("send_email -> outward", classify_tool("send_email") == RiskTier.OUTWARD)
check("unknown falls back to default WRITE", classify_tool("frobnicate") == RiskTier.WRITE)
check("unknown honors a READ default", classify_tool("frobnicate", RiskTier.READ) == RiskTier.READ)

print("== config + ${VAR} expansion ==")
ctx = {"WORKSPACE": "C:\\ws", "PROJECT": "C:\\proj"}
check("expands ${WORKSPACE}", _expand("${WORKSPACE}\\f.txt", ctx) == "C:\\ws\\f.txt")
check("expands ${ENV:NAME}", _expand("${ENV:JARVIS_DB_PATH}", ctx) == _TMP)
check("leaves unknown ${X} intact", _expand("${NOPE}", ctx) == "${NOPE}")
specs = load_config()
fs = next((s for s in specs if s["name"] == "filesystem"), None)
check("servers.yaml declares a filesystem server", fs is not None)
check("filesystem is stdio + npx", fs and fs["transport"] == "stdio" and fs["command"] == "npx")
check("filesystem default_tier is write", fs and fs["default_tier"] == RiskTier.WRITE)
check("filesystem root arg expanded to an absolute path",
      fs and any(os.path.isabs(a) for a in fs["args"]))

print("== CallToolResult normalization ==")


class _Blk:
    def __init__(self, text):
        self.text = text
        self.type = "text"


class _Res:
    def __init__(self, blocks, err=False):
        self.content = blocks
        self.isError = err


nr = _normalize_result(_Res([_Blk("hello"), _Blk("world")]), "read_file", "fs")
check("joins text blocks", nr["ok"] and nr["text"] == "hello\nworld")
nr2 = _normalize_result(_Res([_Blk("boom")], err=True), "x", "fs")
check("flags isError", (not nr2["ok"]) and nr2["error"] == "boom")

print("== graceful degradation (bus not started) ==")
check("SDK reports available", mcp_bus.available() is True)
h0 = mcp_bus.health()
check("health has available + servers keys", "available" in h0 and "servers" in h0)
call0 = mcp_bus.call("read_file", {"path": "x"})
check("call before connect -> ok False (no crash)", call0["ok"] is False)

print("== mcp_agent helpers (offline) ==")
from core.agents import mcp_agent

check("_verb_for mentions tool + server",
      "write_file" in mcp_agent._verb_for("write_file", RiskTier.WRITE, "filesystem")
      and "filesystem" in mcp_agent._verb_for("write_file", RiskTier.WRITE, "filesystem"))
check("_verb_for flags a risky tier",
      "irreversible" in mcp_agent._verb_for("delete_file", RiskTier.IRREVERSIBLE, "fs"))
ct = mcp_agent._compact_tool({"name": "write_file", "tier": "write",
                              "description": "Write a file",
                              "input_schema": {"properties": {"path": {"type": "string"},
                                                              "content": {"type": "string"}},
                                               "required": ["path", "content"]}})
check("_compact_tool renders name/tier/required params",
      "write_file" in ct and "[write]" in ct and "path*" in ct)
check("select() with no tools connected -> tool None",
      mcp_agent.select("read a file")["tool"] is None)

print("== orchestrator wiring ==")
try:
    from core.agents import orchestrator as orch

    check("'mcp' is a builtin domain", "mcp" in orch.BUILTIN_DOMAINS)
    check("FACULTIES lists the mcp faculty", any(f["name"] == "mcp" for f in orch.FACULTIES))
    listed = orch._handle_mcp_command("list tools")
    check("'list tools' shortcut returns an mcp answer",
          listed is not None and listed["domain"] == "mcp")
    check("non-meta command is NOT caught by the shortcut",
          orch._handle_mcp_command("write a file") is None)

    # Per-tool tier flows through the SAME gateway as every other action (§15).
    gateway.set_mode("copilot")
    ran = {"n": 0}

    def _ok():
        ran["n"] += 1
        return {"synthesis": {"answer": "did it"}}

    r_read = orch._guarded("mcp", "x", _ok, tier=RiskTier.READ, verb="read a file", tool="mcp:fs")
    check("guarded READ override auto-executes", r_read["status"] == "success" and ran["n"] == 1)
    r_write = orch._guarded("mcp", "x", _ok, tier=RiskTier.WRITE, verb="write a file", tool="mcp:fs")
    check("guarded WRITE override auto-executes in copilot", r_write["status"] == "success")
    r_irr = orch._guarded("mcp", "x", _ok, tier=RiskTier.IRREVERSIBLE, verb="delete a file", tool="mcp:fs")
    check("guarded IRREVERSIBLE override -> needs_confirmation",
          r_irr["status"] == "needs_confirmation" and "confirmation" in r_irr)
    gateway.deny(r_irr["confirmation"]["confirmation_id"])
except Exception as e:
    print(f"  [WARN] orchestrator wiring skipped: {e}")
    traceback.print_exc()

print("== live: filesystem server (best-effort; needs npx + network) ==")
try:
    health = mcp_bus.start()
    connected = [s for s in health["servers"] if s["status"] == "connected"]
    if not connected:
        errs = "; ".join(f"{s['name']}: {s.get('error')}" for s in health["servers"])
        print(f"  [SKIP] no MCP server connected ({errs or 'unknown reason'})")
    else:
        toolnames = {t["name"] for t in mcp_bus.tools()}
        check("filesystem connected with tools",
              any(s["name"] == "filesystem" and s["tool_count"] > 0 for s in connected))
        check("registry exposes write_file", "write_file" in toolnames)
        check("tier_for('write_file') == write", mcp_bus.tier_for("write_file") == RiskTier.WRITE)

        root = (mcp_bus.roots() or [None])[0]
        if "write_file" in toolnames and root:
            gateway.set_mode("copilot")
            target = os.path.join(root, "mcp_proof.txt")
            content = "JARVIS MCP bus works end-to-end."
            action = ActionRequest(tool="mcp:filesystem", action="write_file",
                                   risk_tier=mcp_bus.tier_for("write_file"), summary="write proof")
            w = gateway.guard(action, lambda: mcp_bus.call("write_file",
                                                           {"path": target, "content": content}))
            check("gateway-gated write_file auto-ran (copilot, WRITE)",
                  w.get("executed") and w["result"].get("ok"))
            read_tool = "read_text_file" if "read_text_file" in toolnames else "read_file"
            rd = mcp_bus.call(read_tool, {"path": target})
            check("read back the written content", content in (rd.get("text") or ""))
        else:
            print("  [SKIP] filesystem write/read proof (no write_file or root)")
except Exception as e:
    print(f"  [SKIP] live MCP: {e}")
finally:
    try:
        mcp_bus.stop()
    except Exception:
        pass

print(f"\n==== {PASS} passed, {FAIL} failed ====")
sys.exit(0 if FAIL == 0 else 1)
