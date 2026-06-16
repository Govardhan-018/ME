"""
The MCP client bus (§7) — the universal tool bus that decouples the brain from
any specific integration SDK.

The Agent Core is an **MCP client**. It connects to declared MCP **servers**
(separate child processes — `servers.yaml`), discovers their tools, and exposes
them as a flat registry. Every tool call still flows through the Permission &
Audit Gateway (§15) with a *per-tool* risk tier — which is the whole reason MCP
matters for us: it finally gives precise per-call gating instead of one coarse
decision per agent (the §14.3 "dispatch-granularity" gap).

Concurrency model
-----------------
The MCP SDK is asyncio + anyio; the orchestrator is synchronous. We bridge with
ONE dedicated event-loop thread that owns every session. Each server runs in its
own long-lived task that enters the stdio/session context, signals ready, then
parks on a stop event and exits the context **in the same task** — this avoids
the anyio "cancel scope in a different task" trap you hit if you enter a context
in one task and exit it in another. Synchronous callers marshal coroutines onto
the loop with `run_coroutine_threadsafe(...).result(timeout=...)`.

Trust (§7.4): tool descriptions from servers are untrusted input. We never let a
tool run without the gateway; unknown tools fall back to a server's conservative
`default_tier`.
"""
from __future__ import annotations

import asyncio
import os
import re
import shutil
import threading
from pathlib import Path
from typing import Any, Callable, Optional

from core.security.tiers import RiskTier

# The SDK is imported lazily/defensively so the whole brain still boots if `mcp`
# isn't installed (rule #3: a missing optional bus must not take down the core).
try:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    _HAVE_MCP = True
    _IMPORT_ERROR: str | None = None
except Exception as _e:  # pragma: no cover - exercised only without the SDK
    _HAVE_MCP = False
    _IMPORT_ERROR = repr(_e)

try:
    import yaml
except Exception:  # pragma: no cover
    yaml = None  # type: ignore

CONNECT_TIMEOUT = float(os.getenv("JARVIS_MCP_CONNECT_TIMEOUT", "60"))
CALL_TIMEOUT = float(os.getenv("JARVIS_MCP_CALL_TIMEOUT", "45"))

_PROJECT_ROOT = Path(__file__).resolve().parents[2]   # core/mcp/ -> core/ -> ME AI/
_DEFAULT_WORKSPACE = os.getenv("JARVIS_WORKSPACE") or str(_PROJECT_ROOT / "workspace")


# --------------------------------------------------------------------------- #
# Per-tool risk tiers (§6.2). Explicit names win; then verb heuristics; then the
# server's declared default_tier. This is deliberately conservative — a tool we
# don't recognize from an unknown server should never silently auto-run as READ.
# --------------------------------------------------------------------------- #
_READ_TOOLS = {
    "read_file", "read_text_file", "read_media_file", "read_multiple_files",
    "list_directory", "list_directory_with_sizes", "directory_tree",
    "search_files", "get_file_info", "list_allowed_directories",
}
_WRITE_TOOLS = {"write_file", "edit_file", "create_directory", "move_file"}
_IRREVERSIBLE_TOOLS = {"delete_file", "delete", "remove_file", "rmdir", "unlink"}

_IRREVERSIBLE_HINTS = ("delete", "remove", "drop", "rmdir", "unlink", "destroy", "overwrite")
_WRITE_HINTS = ("write", "edit", "create", "move", "rename", "append", "update", "put", "mkdir", "save")
_READ_HINTS = ("read", "list", "get", "search", "tree", "info", "stat", "fetch", "query", "find", "describe")
_OUTWARD_HINTS = ("send", "post", "email", "message", "publish", "tweet", "notify")


def classify_tool(name: str, default: RiskTier = RiskTier.WRITE) -> RiskTier:
    """Map an MCP tool name to a static risk tier (the gateway crosses it with
    the autonomy mode). Pure function — unit-tested offline."""
    n = (name or "").lower()
    if name in _IRREVERSIBLE_TOOLS or any(h in n for h in _IRREVERSIBLE_HINTS):
        return RiskTier.IRREVERSIBLE
    if any(h in n for h in _OUTWARD_HINTS):
        return RiskTier.OUTWARD
    if name in _WRITE_TOOLS or any(h in n for h in _WRITE_HINTS):
        return RiskTier.WRITE
    if name in _READ_TOOLS or any(h in n for h in _READ_HINTS):
        return RiskTier.READ
    return default


def _expand(value: Any, ctx: dict[str, str]) -> Any:
    """Substitute ${WORKSPACE} / ${PROJECT} / ${HOME} / ${ENV:NAME} in config."""
    if not isinstance(value, str):
        return value

    def repl(m: re.Match) -> str:
        key = m.group(1)
        if key.startswith("ENV:"):
            return os.environ.get(key[4:], "")
        return ctx.get(key, os.environ.get(key, m.group(0)))

    return re.sub(r"\$\{([^}]+)\}", repl, value)


def load_config(path: str | os.PathLike | None = None) -> list[dict[str, Any]]:
    """Parse servers.yaml into normalized server specs. Returns [] if missing."""
    cfg_path = Path(path or os.getenv("JARVIS_MCP_CONFIG") or (Path(__file__).parent / "servers.yaml"))
    if yaml is None or not cfg_path.exists():
        return []
    data = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
    ctx = {
        "WORKSPACE": _DEFAULT_WORKSPACE,
        "PROJECT": str(_PROJECT_ROOT),
        "HOME": str(Path.home()),
    }
    specs: list[dict[str, Any]] = []
    for raw in data.get("servers", []) or []:
        if not raw.get("name"):
            continue
        try:
            default_tier = RiskTier(str(raw.get("default_tier", "write")).lower())
        except ValueError:
            default_tier = RiskTier.WRITE
        specs.append({
            "name": raw["name"],
            "enabled": bool(raw.get("enabled", True)),
            "transport": str(raw.get("transport", "stdio")).lower(),
            "command": _expand(raw.get("command", ""), ctx),
            "args": [_expand(a, ctx) for a in (raw.get("args") or [])],
            "default_tier": default_tier,
            "description": raw.get("description", ""),
        })
    return specs


def _normalize_result(res: Any, tool: str, server: str) -> dict[str, Any]:
    """Flatten an MCP CallToolResult into a plain, JSON-safe dict."""
    parts: list[str] = []
    for block in (getattr(res, "content", None) or []):
        text = getattr(block, "text", None)
        if text:
            parts.append(text)
        elif getattr(block, "type", None) == "resource":
            parts.append(str(getattr(block, "resource", block)))
        else:
            parts.append(str(block))
    text = "\n".join(p for p in parts if p)
    is_error = bool(getattr(res, "isError", False))
    return {
        "ok": not is_error,
        "tool": tool,
        "server": server,
        "text": text,
        "error": text if is_error else None,
    }


class _Server:
    def __init__(self, spec: dict[str, Any]):
        self.name: str = spec["name"]
        self.spec = spec
        self.default_tier: RiskTier = spec["default_tier"]
        self.description: str = spec.get("description", "")
        self.session: Optional["ClientSession"] = None
        self.tools: list[dict[str, Any]] = []
        self.roots: list[str] = [
            a for a in spec.get("args", [])
            if os.path.isabs(str(a)) and Path(str(a)).exists()
        ]
        self.status: str = "pending"   # pending | connected | failed | disabled
        self.error: Optional[str] = None


class MCPManager:
    """Owns the background loop and every server session. Singleton (`manager`)."""

    def __init__(self) -> None:
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self._stop: Optional[asyncio.Event] = None
        self._tasks: list[asyncio.Task] = []
        self._servers: dict[str, _Server] = {}
        self._tool_index: dict[str, _Server] = {}
        self._started = False
        self._lock = threading.Lock()

    # -- lifecycle --------------------------------------------------------- #
    def start(self, config_path: str | None = None) -> dict[str, Any]:
        """Connect to every enabled server. Blocks until ready-or-timeout.
        Best-effort: a failed server is recorded, not raised. Idempotent."""
        with self._lock:
            if self._started:
                return self.health()
            if not _HAVE_MCP:
                self._started = True   # 'started' but empty; health shows why
                return self.health()

            specs = load_config(config_path)
            # Make sure scoped roots exist before a server tries to open them.
            for spec in specs:
                for a in spec.get("args", []):
                    if os.path.isabs(str(a)) and str(a).startswith(str(_PROJECT_ROOT)):
                        Path(str(a)).mkdir(parents=True, exist_ok=True)

            self._loop = asyncio.new_event_loop()
            self._thread = threading.Thread(
                target=self._run_loop, name="jarvis-mcp", daemon=True)
            self._thread.start()

            try:
                fut = asyncio.run_coroutine_threadsafe(self._startup(specs), self._loop)
                fut.result(timeout=CONNECT_TIMEOUT + 10)
            except Exception as e:
                print(f"[mcp] startup error: {e!r}")
            self._started = True
            return self.health()

    def _run_loop(self) -> None:
        assert self._loop is not None
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()

    async def _startup(self, specs: list[dict[str, Any]]) -> None:
        self._stop = asyncio.Event()
        readies: list[asyncio.Event] = []
        for spec in specs:
            srv = _Server(spec)
            self._servers[srv.name] = srv
            if not spec["enabled"]:
                srv.status = "disabled"
                continue
            if spec["transport"] != "stdio":
                srv.status = "failed"
                srv.error = (f"transport '{spec['transport']}' not supported yet "
                             f"(stdio only in this build)")
                continue
            ready = asyncio.Event()
            readies.append(ready)
            self._tasks.append(asyncio.create_task(self._serve(srv, ready, self._stop)))

        if readies:
            await asyncio.wait(
                [asyncio.create_task(r.wait()) for r in readies],
                timeout=CONNECT_TIMEOUT,
            )
        # Build the flat tool registry from whatever connected (first server wins
        # a name collision; later servers are still reachable via their session).
        for srv in self._servers.values():
            for t in srv.tools:
                self._tool_index.setdefault(t["name"], srv)

    async def _serve(self, srv: _Server, ready: asyncio.Event, stop: asyncio.Event) -> None:
        """One task per server: open the session, keep it open until shutdown."""
        try:
            cmd = shutil.which(srv.spec["command"]) or srv.spec["command"]
            params = StdioServerParameters(
                command=cmd,
                args=srv.spec["args"],
                # Full env: npx needs PATH + npm cache dirs (APPDATA/USERPROFILE)
                # to resolve & download official servers on Windows.
                env=os.environ.copy(),
            )
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    listed = await session.list_tools()
                    srv.session = session
                    srv.tools = [{
                        "name": t.name,
                        "description": (t.description or "").strip(),
                        "input_schema": getattr(t, "inputSchema", None) or {},
                        "server": srv.name,
                        "tier": classify_tool(t.name, srv.default_tier).value,
                    } for t in listed.tools]
                    srv.status = "connected"
                    print(f"[mcp] '{srv.name}' connected — {len(srv.tools)} tool(s)")
                    ready.set()
                    await stop.wait()        # park here; context stays open
        except Exception as e:
            srv.status = "failed"
            srv.error = repr(e)
            srv.session = None
            print(f"[mcp] '{srv.name}' failed: {e!r}")
        finally:
            ready.set()

    def stop(self) -> None:
        if not self._started or self._loop is None:
            return

        async def _shutdown() -> None:
            if self._stop is not None:
                self._stop.set()
            if self._tasks:
                await asyncio.wait(self._tasks, timeout=8)

        try:
            asyncio.run_coroutine_threadsafe(_shutdown(), self._loop).result(timeout=12)
        except Exception:
            pass
        try:
            self._loop.call_soon_threadsafe(self._loop.stop)
        except Exception:
            pass
        self._started = False

    # -- query / call ------------------------------------------------------ #
    def available(self) -> bool:
        return _HAVE_MCP

    def is_ready(self) -> bool:
        return any(s.status == "connected" for s in self._servers.values())

    def tools(self) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for srv in self._servers.values():
            out.extend(srv.tools)
        return out

    def roots(self) -> list[str]:
        roots: list[str] = []
        for srv in self._servers.values():
            roots.extend(srv.roots)
        return roots

    def tier_for(self, tool_name: str) -> RiskTier:
        srv = self._tool_index.get(tool_name)
        default = srv.default_tier if srv else RiskTier.WRITE
        return classify_tool(tool_name, default)

    def server_for(self, tool_name: str) -> str | None:
        srv = self._tool_index.get(tool_name)
        return srv.name if srv else None

    def health(self) -> dict[str, Any]:
        return {
            "available": _HAVE_MCP,
            "import_error": _IMPORT_ERROR,
            "started": self._started,
            "tool_count": len(self._tool_index),
            "roots": self.roots(),
            "servers": [{
                "name": s.name,
                "status": s.status,
                "tool_count": len(s.tools),
                "description": s.description,
                "roots": s.roots,
                "error": s.error,
            } for s in self._servers.values()],
        }

    def call(self, tool_name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        """Invoke an MCP tool. NOTE: callers must gate this via the gateway —
        the orchestrator/endpoints wrap it in gateway.guard() with tier_for()."""
        if not _HAVE_MCP:
            return {"ok": False, "tool": tool_name, "error": "mcp SDK not installed"}
        srv = self._tool_index.get(tool_name)
        if srv is None or srv.session is None or self._loop is None:
            return {"ok": False, "tool": tool_name,
                    "error": f"No connected tool '{tool_name}'."}

        async def _call() -> Any:
            return await srv.session.call_tool(tool_name, arguments or {})

        try:
            res = asyncio.run_coroutine_threadsafe(_call(), self._loop).result(timeout=CALL_TIMEOUT)
        except Exception as e:
            return {"ok": False, "tool": tool_name, "server": srv.name,
                    "error": f"MCP call failed: {e!r}"}
        return _normalize_result(res, tool_name, srv.name)


# Module-level singleton — the brain has exactly one bus.
manager = MCPManager()
