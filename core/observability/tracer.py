"""The tracer: thread-local per-turn traces + global rolling metrics.

Usage (the orchestrator wraps every turn):

    with observability.trace(actor="user", command=cmd) as tr:
        ...
        observability.event("route", domain="calendar")   # attaches to tr
        tr.set(domain="calendar", status="success")

`event()` and `set_actor()` find the active trace via thread-local storage, so
deep call sites (route_intent, the gateway) can annotate the turn without anyone
threading a trace object through every signature. Metrics are *derived* at
finish-time from the trace, keeping instrumentation to one-liners.
"""
from __future__ import annotations

import json
import threading
import time
import uuid
from collections import defaultdict, deque
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Iterator, Optional

_lock = threading.Lock()
_local = threading.local()

_RECENT_MAX = 200
_recent: deque[dict] = deque(maxlen=_RECENT_MAX)
_latency: deque[float] = deque(maxlen=_RECENT_MAX)
_counters: dict[str, defaultdict] = {
    "by_domain": defaultdict(int),
    "by_status": defaultdict(int),
    "by_actor": defaultdict(int),
    "by_decision": defaultdict(int),
}
_totals = {"turns": 0, "errors": 0, "spans": 0}


# --------------------------------------------------------------------------- #
class Trace:
    def __init__(self, actor: str, command: str):
        self.id = uuid.uuid4().hex[:12]
        self.actor = actor
        self.command = (command or "")[:500]
        self.domain: Optional[str] = None
        self.status: Optional[str] = None
        self.error: Optional[str] = None
        self.spans: list[dict[str, Any]] = []
        self._t0 = time.perf_counter()
        self.created_at = datetime.now().replace(microsecond=0).isoformat()
        self.duration_ms = 0

    def event(self, name: str, **meta: Any) -> None:
        at = round((time.perf_counter() - self._t0) * 1000)
        self.spans.append({"name": name, "at_ms": at, "meta": meta or None})

    @contextmanager
    def span(self, name: str, **meta: Any) -> Iterator[None]:
        start = time.perf_counter()
        try:
            yield
        finally:
            ms = round((time.perf_counter() - start) * 1000)
            self.spans.append({"name": name, "ms": ms, "meta": meta or None})

    def set(self, *, domain: str | None = None, status: str | None = None,
            error: str | None = None) -> None:
        if domain is not None:
            self.domain = domain
        if status is not None:
            self.status = status
        if error is not None:
            self.error = error

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id, "actor": self.actor, "command": self.command,
            "domain": self.domain, "status": self.status, "error": self.error,
            "duration_ms": self.duration_ms, "spans": self.spans,
            "created_at": self.created_at,
        }


# --------------------------------------------------------------------------- #
def current() -> Optional[Trace]:
    """The trace active on this thread, if any."""
    return getattr(_local, "trace", None)


def event(name: str, **meta: Any) -> None:
    """Annotate the current turn (no-op if nothing is being traced)."""
    tr = current()
    if tr is not None:
        tr.event(name, **meta)


def set_actor(actor: str) -> None:
    tr = current()
    if tr is not None:
        tr.actor = actor


@contextmanager
def trace(actor: str = "user", command: str = "") -> Iterator[Trace]:
    tr = Trace(actor, command)
    _local.trace = tr
    try:
        yield tr
    except Exception as exc:           # capture failures as part of the trace
        tr.set(status="error", error=str(exc))
        raise
    finally:
        tr.duration_ms = round((time.perf_counter() - tr._t0) * 1000)
        _local.trace = None
        _finish(tr)


def _finish(tr: Trace) -> None:
    with _lock:
        _totals["turns"] += 1
        _totals["spans"] += len(tr.spans)
        if tr.status == "error":
            _totals["errors"] += 1
        _counters["by_actor"][tr.actor] += 1
        _counters["by_domain"][tr.domain or "unknown"] += 1
        _counters["by_status"][tr.status or "unknown"] += 1
        for sp in tr.spans:
            if sp["name"].startswith("gateway:"):
                _counters["by_decision"][sp["name"].split(":", 1)[1]] += 1
        _latency.append(tr.duration_ms)
        _recent.appendleft(tr.to_dict())
    _persist(tr)


def _persist(tr: Trace) -> None:
    """Best-effort history write — never let observability break a turn."""
    try:
        from core.db import get_conn

        with get_conn() as conn:
            conn.execute(
                """INSERT INTO trace
                   (id, actor, command, domain, status, duration_ms, spans, created_at)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (tr.id, tr.actor, tr.command, tr.domain, tr.status,
                 tr.duration_ms, json.dumps(tr.spans), tr.created_at),
            )
    except Exception:
        pass


# --------------------------------------------------------------------------- #
def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    k = max(0, min(len(s) - 1, round(pct / 100 * (len(s) - 1))))
    return round(s[k], 1)


def metrics() -> dict[str, Any]:
    with _lock:
        lat = list(_latency)
        return {
            "turns": _totals["turns"],
            "errors": _totals["errors"],
            "error_rate": round(_totals["errors"] / _totals["turns"], 3) if _totals["turns"] else 0.0,
            "spans": _totals["spans"],
            "latency_ms": {
                "avg": round(sum(lat) / len(lat), 1) if lat else 0.0,
                "p50": _percentile(lat, 50),
                "p95": _percentile(lat, 95),
                "max": round(max(lat), 1) if lat else 0.0,
            },
            "by_domain": dict(_counters["by_domain"]),
            "by_status": dict(_counters["by_status"]),
            "by_actor": dict(_counters["by_actor"]),
            "by_decision": dict(_counters["by_decision"]),
        }


def recent_traces(limit: int = 25) -> list[dict[str, Any]]:
    with _lock:
        return list(_recent)[:limit]


def summary(limit: int = 15) -> dict[str, Any]:
    """One call for the observability dashboard."""
    return {"metrics": metrics(), "recent": recent_traces(limit)}


def reset() -> None:
    """Clear in-memory state (tests)."""
    with _lock:
        _recent.clear()
        _latency.clear()
        for c in _counters.values():
            c.clear()
        for k in _totals:
            _totals[k] = 0
