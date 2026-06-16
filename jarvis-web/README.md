# JARVIS — Web Console

A single-screen personal HUD for the JARVIS core — the living neural orb plus a
command bar to actually do work. Next.js 15 · React 19 · React Three Fiber ·
Framer Motion · GSAP · Tailwind v4. It is **not** a marketing page — it's a
standalone client that talks to the Python brain over HTTP.

## Run

Two pieces: the **core** (the brain) and the **web console**.

```powershell
# 1. Start the core (the brain) from the "ME AI" root.
#    Voice is on by default — add JARVIS_NO_VOICE=1 to skip.
python -m uvicorn core.app.main:app --port 8000

# 2. Start the web console
npm --prefix jarvis-web run dev        # -> http://localhost:4173
```

The status dot, top-right, turns **cyan ("Core online")** when it reaches the
brain. If the core is down the page still loads and the console explains how to
start it.

## What it does

| Control | Wired to |
|---|---|
| Command bar (Enter to send) | `POST /api/chat` — answer rendered with its routed domain |
| Quick-action chips (Ask / Code / Research / Notion / Email / Files) | prefill common requests |
| Mic button | `POST /api/voice/transcribe` -> sends the transcript |
| Status dot | `GET /api/health` (polled) |
| Voice chip ("Hey Jarvis") | `GET /api/voice/state` (mirrors the always-on loop) |
| Skills panel | `GET /api/skills`, `POST /api/skills/{approve,discard}` |

The neural **Core** reacts to real agent state: idle -> listening -> thinking ->
responding (brightness, scale, and inbound/outbound data-flow all shift).

## Configure

- `NEXT_PUBLIC_JARVIS_API` — override the core URL (default `http://127.0.0.1:8000`).

## Build

```powershell
npm --prefix jarvis-web run build
npm --prefix jarvis-web start
```

## Notes

- Particle budget adapts to the device (phone -> workstation); `prefers-reduced-motion`
  freezes the Core and disables streaming.
- Fonts: Inter Tight (display), Inter (body), JetBrains Mono (labels).
- Personal use -> the page is `noindex`.
