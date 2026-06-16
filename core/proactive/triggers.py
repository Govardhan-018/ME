"""Trigger grammar for scheduled jobs — tiny on purpose (rule #3).

A trigger is a string:
  * "daily@HH:MM"  — fires once a day at local wall-clock HH:MM
  * "every@Nm"     — every N minutes  (also Ns seconds, Nh hours)
  * "manual"       — never auto-fires; only runs when explicitly triggered

`compute_next_run` is the only thing the scheduler needs: given a trigger and the
moment we're computing from, when does it next fire? Returning None means "never
on its own".
"""
from __future__ import annotations

import re
from datetime import datetime, time, timedelta
from typing import Optional

_DAILY = re.compile(r"^daily@(\d{1,2}):(\d{2})$", re.I)
_EVERY = re.compile(r"^every@(\d+)\s*([smh])$", re.I)
_UNIT = {"s": "seconds", "m": "minutes", "h": "hours"}


def validate(trigger: str) -> bool:
    t = (trigger or "").strip().lower()
    return t in ("manual", "") or bool(_DAILY.match(t) or _EVERY.match(t))


def compute_next_run(trigger: str, after: datetime) -> Optional[datetime]:
    t = (trigger or "").strip().lower()
    if not t or t == "manual":
        return None

    m = _DAILY.match(t)
    if m:
        hh, mm = int(m.group(1)), int(m.group(2))
        candidate = datetime.combine(after.date(), time(hour=hh % 24, minute=mm % 60))
        if candidate <= after:
            candidate += timedelta(days=1)
        return candidate

    m = _EVERY.match(t)
    if m:
        n, unit = int(m.group(1)), m.group(2)
        return after + timedelta(**{_UNIT[unit]: n})

    return None


def describe(trigger: str) -> str:
    t = (trigger or "").strip().lower()
    m = _DAILY.match(t)
    if m:
        return f"every day at {int(m.group(1)):02d}:{m.group(2)}"
    m = _EVERY.match(t)
    if m:
        return f"every {m.group(1)} {_UNIT[m.group(2).lower()]}"
    return "manually"
