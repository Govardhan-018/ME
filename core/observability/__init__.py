"""Observability (§ Phase 7 — full observability dashboard; design §697).

A lightweight, in-process tracer + metrics so you can *see what the agent did*:
one trace per orchestrated turn, sub-step spans (routing, gateway decisions,
plan steps), rolling metrics, and a persisted history. This is the local-first
stand-in for the design's OpenTelemetry/Langfuse stack — same idea (traces +
metrics), zero external services. The façade is the seam to swap OTel in later.
"""
from core.observability.tracer import (  # noqa: F401
    Trace,
    current,
    event,
    metrics,
    recent_traces,
    reset,
    set_actor,
    summary,
    trace,
)
