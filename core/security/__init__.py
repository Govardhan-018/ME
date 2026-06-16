"""
JARVIS security package — the Permission & Audit Gateway (§15).

Every action the brain wants to take passes through one chokepoint
(`gateway.guard`). The model proposes; the gateway disposes, based on the tool's
static risk tier (`tiers`) crossed with the user's autonomy mode (`policy`), and
records the outcome to an append-only audit log (`audit`).

This is design rule #2: every action through the gateway, no exceptions.
"""
