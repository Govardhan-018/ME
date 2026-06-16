"""Local-first calendar (§ Phase 7 — Calendar).

The user's calendar lives in SQLite as the source of truth, so scheduling and
proactive briefings work with zero external setup. Google Calendar is an
optional importer layered on top (core/calendar/google_sync.py), never a hard
dependency — consistent with the project's local-first, all-local posture.
"""
from core.calendar import store  # noqa: F401
