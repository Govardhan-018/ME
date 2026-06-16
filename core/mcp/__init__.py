"""MCP tool bus (§7) — public surface.

The brain talks to the *protocol*, not to each integration's SDK. Import this
package; never poke the manager's internals.

    from core import mcp
    mcp.start()                 # connect declared servers (servers.yaml)
    mcp.tools()                 # flat tool registry [{name, description, tier, server, input_schema}]
    mcp.tier_for("write_file")  # -> RiskTier  (for the gateway)
    mcp.call("read_file", {"path": "..."})   # MUST be wrapped in gateway.guard()
    mcp.health()                # per-server status + tool counts
    mcp.stop()
"""
from core.mcp.client import classify_tool, load_config, manager
from core.security.tiers import RiskTier


def start(config_path: str | None = None) -> dict:
    return manager.start(config_path)


def stop() -> None:
    manager.stop()


def tools() -> list[dict]:
    return manager.tools()


def roots() -> list[str]:
    return manager.roots()


def health() -> dict:
    return manager.health()


def available() -> bool:
    return manager.available()


def is_ready() -> bool:
    return manager.is_ready()


def tier_for(tool_name: str) -> RiskTier:
    return manager.tier_for(tool_name)


def server_for(tool_name: str) -> str | None:
    return manager.server_for(tool_name)


def call(tool_name: str, arguments: dict | None = None) -> dict:
    return manager.call(tool_name, arguments)


__all__ = [
    "start", "stop", "tools", "roots", "health", "available", "is_ready",
    "tier_for", "server_for", "call", "classify_tool", "load_config", "manager",
]
