"""Calendar persistence — CRUD over the `calendar_event` table (the SQLite spine).

Event times are stored as **naive local ISO8601** strings ("2026-06-16T15:00:00")
because a personal calendar is reasoned about in the user's own wall-clock time
("today", "9am meeting"). created_at/updated_at follow the same convention so a
single table reads consistently.

This is the seam: the proactive engine and the calendar agent both talk to these
functions, never to SQL directly.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, time, timedelta
from typing import Any, Optional

from core.db import get_conn, rows_to_dicts

# --------------------------------------------------------------------------- #
# datetime helpers — tolerant in, canonical out
# --------------------------------------------------------------------------- #
_FORMATS = (
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%dT%H:%M",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %H:%M",
    "%Y/%m/%d %H:%M",
    "%Y-%m-%d",
    "%Y/%m/%d",
)


def parse_dt(value: str | datetime | None) -> Optional[datetime]:
    """Parse the assorted shapes the LLM/UI might hand us into a naive datetime."""
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.replace(tzinfo=None)
    s = str(value).strip().replace("Z", "")
    # Drop a timezone offset if one slipped in; we keep everything naive-local.
    if len(s) >= 6 and (s[-6] in "+-") and s[-3] == ":":
        s = s[:-6]
    for fmt in _FORMATS:
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        return None


def iso(dt: datetime | None) -> Optional[str]:
    return dt.replace(microsecond=0).isoformat() if dt else None


def _now() -> datetime:
    return datetime.now().replace(microsecond=0)


def day_bounds(d: date) -> tuple[str, str]:
    """[start, end) ISO strings spanning a local calendar day."""
    start = datetime.combine(d, time.min)
    return iso(start), iso(start + timedelta(days=1))


# --------------------------------------------------------------------------- #
# CRUD
# --------------------------------------------------------------------------- #
def add_event(
    title: str,
    start: str | datetime,
    end: str | datetime | None = None,
    all_day: bool = False,
    location: str | None = None,
    notes: str | None = None,
    source: str = "local",
    external_id: str | None = None,
) -> dict[str, Any]:
    """Insert an event. `start`/`end` accept ISO strings or datetimes."""
    start_dt = parse_dt(start)
    if start_dt is None:
        raise ValueError(f"Could not parse start time: {start!r}")
    end_dt = parse_dt(end)
    if end_dt is None and not all_day:
        end_dt = start_dt + timedelta(hours=1)  # sensible default duration

    eid = uuid.uuid4().hex[:12]
    now = iso(_now())
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO calendar_event
               (id, title, start_ts, end_ts, all_day, location, notes,
                source, external_id, created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (eid, title.strip(), iso(start_dt), iso(end_dt), int(all_day),
             location, notes, source, external_id, now, now),
        )
    return get_event(eid)


def get_event(event_id: str) -> Optional[dict[str, Any]]:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM calendar_event WHERE id = ?", (event_id,)
        ).fetchone()
    return dict(row) if row else None


def list_events(
    start_from: str | datetime | None = None,
    start_to: str | datetime | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    """Events whose start falls in [start_from, start_to), ordered by start."""
    clauses, params = [], []
    if start_from is not None:
        clauses.append("start_ts >= ?")
        params.append(iso(parse_dt(start_from)))
    if start_to is not None:
        clauses.append("start_ts < ?")
        params.append(iso(parse_dt(start_to)))
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    with get_conn() as conn:
        rows = conn.execute(
            f"SELECT * FROM calendar_event {where} ORDER BY start_ts ASC LIMIT ?",
            (*params, limit),
        ).fetchall()
    return rows_to_dicts(rows)


def events_on(d: date) -> list[dict[str, Any]]:
    start, end = day_bounds(d)
    return list_events(start, end)


def today() -> list[dict[str, Any]]:
    return events_on(date.today())


def upcoming(within_hours: int | None = None, limit: int = 20) -> list[dict[str, Any]]:
    """Future events from now, optionally capped to a horizon."""
    now = _now()
    end = iso(now + timedelta(hours=within_hours)) if within_hours else None
    return list_events(iso(now), end, limit=limit)


def find_events(query: str, limit: int = 10) -> list[dict[str, Any]]:
    """Title substring search (for cancel/lookup)."""
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT * FROM calendar_event
               WHERE lower(title) LIKE ? ORDER BY start_ts ASC LIMIT ?""",
            (f"%{query.strip().lower()}%", limit),
        ).fetchall()
    return rows_to_dicts(rows)


def cancel_event(event_id: str) -> bool:
    with get_conn() as conn:
        cur = conn.execute("DELETE FROM calendar_event WHERE id = ?", (event_id,))
        return cur.rowcount > 0


def upsert_external(external_id: str, **fields) -> dict[str, Any]:
    """Insert-or-update by external (e.g. Google) id — used by the importer."""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT id FROM calendar_event WHERE external_id = ?", (external_id,)
        ).fetchone()
    if row:
        now = iso(_now())
        sets = ", ".join(f"{k} = ?" for k in fields)
        with get_conn() as conn:
            conn.execute(
                f"UPDATE calendar_event SET {sets}, updated_at = ? WHERE id = ?",
                (*[_coerce(v) for v in fields.values()], now, row["id"]),
            )
        return get_event(row["id"])
    return add_event(external_id=external_id, source="google", **fields)


def _coerce(v):
    if isinstance(v, datetime):
        return iso(v)
    if isinstance(v, bool):
        return int(v)
    return v


# --------------------------------------------------------------------------- #
# Scheduling intelligence — free/busy
# --------------------------------------------------------------------------- #
def free_slots(
    d: date,
    work_start: int = 9,
    work_end: int = 18,
    min_minutes: int = 30,
) -> list[dict[str, str]]:
    """Gaps in the working day not covered by a timed event (>= min_minutes)."""
    window_start = datetime.combine(d, time(hour=work_start))
    window_end = datetime.combine(d, time(hour=work_end))

    busy: list[tuple[datetime, datetime]] = []
    for ev in events_on(d):
        if ev.get("all_day"):
            return []  # an all-day event blocks the whole day
        s = parse_dt(ev["start_ts"])
        e = parse_dt(ev["end_ts"]) or (s + timedelta(hours=1))
        if e > window_start and s < window_end:
            busy.append((max(s, window_start), min(e, window_end)))
    busy.sort()

    slots, cursor = [], window_start
    for s, e in busy:
        if s - cursor >= timedelta(minutes=min_minutes):
            slots.append({"start": iso(cursor), "end": iso(s)})
        cursor = max(cursor, e)
    if window_end - cursor >= timedelta(minutes=min_minutes):
        slots.append({"start": iso(cursor), "end": iso(window_end)})
    return slots


def describe(ev: dict[str, Any]) -> str:
    """One-line human rendering of an event, e.g. '15:00–16:00  Standup @ Zoom'."""
    s = parse_dt(ev["start_ts"])
    e = parse_dt(ev.get("end_ts"))
    if ev.get("all_day"):
        when = "all day"
    elif e and e.date() == s.date():
        when = f"{s:%H:%M}–{e:%H:%M}"
    else:
        when = f"{s:%H:%M}"
    loc = f"  @ {ev['location']}" if ev.get("location") else ""
    return f"{when}  {ev['title']}{loc}"
