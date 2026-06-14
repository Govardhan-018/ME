# J.A.R.V.I.S — AI Operating System

A living AI workstation, not a chat app. A glowing **AI Core** sits at the center
and reacts to cognitive state; tools **orbit** it and ignite when used; a
Raycast-style **command palette**, a **memory galaxy**, an **agent execution
flow**, and a first-class **voice mode** complete the spatial OS.

> Design language: _"Dala discipline at rest, JARVIS light on activity."_ Pure
> void black, ultra-thin display type, one authority accent (electric cyan).
> Glow, glass and energy appear **only where the AI is alive** — light is information.

## Stack

Electron · React 18 · TypeScript · Vite (electron-vite) · Tailwind v4 ·
Framer Motion · Zustand · Lucide · class-variance-authority.

## Run

```bash
npm install
npm run dev        # hot-reloading dev OS
npm run build      # type-check + bundle main/preload/renderer → out/
npm run dist:win   # package a Windows installer → dist/
```

Global shortcut **Ctrl/Cmd+Space** summons/dismisses the whole OS.
In-app: **⌘/Ctrl-K** command palette · **⌘/Ctrl-J** voice · **Esc** dismiss.

## Architecture

```
src/
  main/index.ts          Electron main — hardened (contextIsolation + sandbox), frameless void window
  preload/index.ts       Minimal typed bridge (window controls only) via contextBridge
  renderer/src/
    App.tsx              Shell: ambient bg + titlebar + stage + overlays + boot
    styles/globals.css   Design tokens (Tailwind v4 @theme) + glass/glow utilities
    lib/
      motion.ts          The motion language: springs, curves, variants
      utils.ts           cn(), math helpers
      sim/conductor.ts   ★ The CONDUCTOR — choreographs every agent turn
    stores/              Zustand: core · tools · conversation · voice · memory · agent · command · ui
    hooks/               useMicAnalyser · useHotkeys · useMagnetic
    components/
      background/        AmbientBackground + canvas neural ParticleField
      core/              AICore (the living orb) + coreParams (state→visuals)
      orbital/           OrbitalSystem (tools that ignite & pull inward)
      chat/              ChatPanel · Message · Composer (streaming, reasoning, tool chips)
      voice/             VoiceOverlay (circular spectrum + waveform, live mic)
      memory/            MemoryGalaxy (knowledge graph + retrieval animation)
      agent/             AgentFlow (animated execution pipeline)
      command/           CommandPalette (Raycast-style navigator)
      shell/             TitleBar · Stage (view morphing)
      ui/                GlassPanel · Button (magnetic)
```

## Wiring the real backend

Today the OS is driven by `lib/sim/conductor.ts`, which **simulates** agent turns
(think → reason → tool use → stream) so the experience is fully alive with no
backend. To go live, replace the bodies of `submitPrompt` / `startAmbientLife`
with calls to the Python Agent Core (see `../JARVIS_DESIGN.md`) over IPC or
WebSocket, dispatching the same store actions. **The UI and stores never change** —
that decoupling is the whole point.

The state stores map 1:1 to backend concepts: `coreStore` = agent cognitive
state, `toolsStore` = MCP tool activity, `conversationStore` = streamed messages,
`agentStore` = the plan/execution graph, `memoryStore` = the memory layer.
