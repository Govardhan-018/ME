"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import dynamic from "next/dynamic";
import { AnimatePresence, motion, useMotionValue } from "framer-motion";
import {
  Brain,
  LayoutDashboard,
  Mic,
  Send,
  Sparkles,
  Square,
  X,
} from "lucide-react";
import { Logo } from "@/components/layout/Logo";
import { ActionChips } from "./ActionChips";
import { SkillsPanel } from "./SkillsPanel";
import { SystemPanel } from "./SystemPanel";
import { MemoryPanel } from "./MemoryPanel";
import { chat, health, systemSnapshot, transcribe, tts, voiceState, type VoiceState } from "@/lib/jarvis";
import { usePrefersReducedMotion } from "@/lib/perf";
import { cn } from "@/lib/utils";

const AICore = dynamic(() => import("@/components/core/AICore"), {
  ssr: false,
  loading: () => null,
});

type Role = "user" | "jarvis";
interface Msg {
  id: string;
  role: Role;
  text: string;
  domain?: string;
}
type Status = "connecting" | "online" | "offline";

const wait = (ms: number) => new Promise((r) => setTimeout(r, ms));

function renderBody(text: string) {
  if (!text) return <ThinkingDots />;
  return text.split(/```/).map((part, i) =>
    i % 2 === 1 ? (
      <pre
        key={i}
        className="my-2 overflow-x-auto rounded-lg border border-line bg-black/40 p-3 text-[0.8rem] leading-relaxed text-ink-soft"
      >
        <code>{part.replace(/^[a-zA-Z0-9+-]*\n/, "")}</code>
      </pre>
    ) : (
      <span key={i} className="whitespace-pre-wrap">
        {part}
      </span>
    ),
  );
}

function ThinkingDots() {
  return (
    <span className="inline-flex items-center gap-1.5 py-1" aria-label="Thinking">
      {[0, 1, 2].map((i) => (
        <span
          key={i}
          className="h-1.5 w-1.5 animate-pulse rounded-full bg-accent"
          style={{ animationDelay: `${i * 0.18}s` }}
        />
      ))}
    </span>
  );
}

export function Jarvis() {
  const reduced = usePrefersReducedMotion();
  const level = useMotionValue(1.15);
  const flow = useMotionValue(0);

  const [messages, setMessages] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState<Status>("connecting");
  const [voice, setVoice] = useState<VoiceState | null>(null);
  const [skillsOpen, setSkillsOpen] = useState(false);
  const [systemOpen, setSystemOpen] = useState(false);
  const [memoryOpen, setMemoryOpen] = useState(false);
  const [unread, setUnread] = useState(0);
  const [recording, setRecording] = useState(false);
  const [greeting, setGreeting] = useState("Hello");

  const lockRef = useRef(false);
  const lastTurn = useRef<number | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const recorderRef = useRef<MediaRecorder | null>(null);

  const setActivity = useCallback(
    (s: "idle" | "listening" | "thinking" | "responding") => {
      const map = {
        idle: [1.15, 0],
        listening: [1.6, -0.5],
        thinking: [2.6, -1],
        responding: [3.6, 1],
      } as const;
      level.set(map[s][0]);
      flow.set(map[s][1]);
    },
    [level, flow],
  );

  const addMsg = useCallback((role: Role, text: string, domain?: string) => {
    const id = typeof crypto !== 'undefined' && crypto.randomUUID ? crypto.randomUUID() : Math.random().toString(36).substring(2);
    setMessages((m) => [...m, { id, role, text, domain }]);
    return id;
  }, []);

  const updateMsg = useCallback((id: string, text: string) => {
    setMessages((m) => m.map((x) => (x.id === id ? { ...x, text } : x)));
  }, []);

  const stream = useCallback(
    async (id: string, full: string) => {
      if (reduced) {
        updateMsg(id, full);
        return;
      }
      const words = full.split(" ");
      let acc = "";
      for (let i = 0; i < words.length; i++) {
        acc += (i ? " " : "") + words[i];
        updateMsg(id, acc);
        await wait(12 + Math.random() * 22);
      }
    },
    [reduced, updateMsg],
  );

  const send = useCallback(
    async (raw: string) => {
      const text = raw.trim();
      if (!text || lockRef.current) return;
      lockRef.current = true;
      setBusy(true);
      addMsg("user", text);
      setInput("");
      if (textareaRef.current) textareaRef.current.style.height = "auto";
      setActivity("thinking");
      const replyId = addMsg("jarvis", "");
      try {
        const res = await chat(text);
        setActivity("responding");
        setMessages((m) => m.map((x) => (x.id === replyId ? { ...x, domain: res.domain } : x)));
        tts(res.answer);
        await stream(replyId, res.answer);
      } catch (e) {
        updateMsg(
          replyId,
          `I couldn't reach the Core (${(e as Error).message}).\n\nStart the brain on port 8000 — \`python -m uvicorn core.app.main:app --port 8000\` — then try again.`,
        );
      } finally {
        setActivity("idle");
        setBusy(false);
        lockRef.current = false;
      }
    },
    [addMsg, updateMsg, stream, setActivity],
  );

  const clearChat = useCallback(() => {
    setMessages([]);
    setActivity("idle");
  }, [setActivity]);

  /* time-based greeting (after mount → no hydration mismatch) */
  useEffect(() => {
    const h = new Date().getHours();
    setGreeting(h < 12 ? "Good morning" : h < 18 ? "Good afternoon" : "Good evening");
  }, []);

  /* core connection */
  useEffect(() => {
    let alive = true;
    const ping = async () => {
      const ok = await health();
      if (alive) setStatus(ok ? "online" : "offline");
    };
    ping();
    const iv = setInterval(ping, 4000);
    return () => {
      alive = false;
      clearInterval(iv);
    };
  }, []);

  /* always-on voice mirror */
  useEffect(() => {
    if (status !== "online") return;
    let alive = true;
    const tick = async () => {
      const v = await voiceState();
      if (!alive || !v) return;
      setVoice(v);
      if (typeof v.answer_turn === "number") {
        if (lastTurn.current === null) lastTurn.current = v.answer_turn;
        else if (v.answer_turn > lastTurn.current && v.answer_text) {
          lastTurn.current = v.answer_turn;
          if (v.user_text) addMsg("user", v.user_text);
          addMsg("jarvis", v.answer_text, v.answer_domain);
        }
      }
      if (!lockRef.current) {
        const s = v.state;
        if (s === "listening") setActivity("listening");
        else if (s === "thinking" || s === "processing") setActivity("thinking");
        else if (s === "speaking") setActivity("responding");
        else setActivity("idle");
      }
    };
    tick();
    const iv = setInterval(tick, 1700);
    return () => {
      alive = false;
      clearInterval(iv);
    };
  }, [status, setActivity, addMsg]);

  /* proactive feed unread badge */
  useEffect(() => {
    if (status !== "online") return;
    let alive = true;
    const tick = async () => {
      const s = await systemSnapshot();
      if (alive && s) setUnread(s.feed.unread);
    };
    tick();
    const iv = setInterval(tick, 8000);
    return () => {
      alive = false;
      clearInterval(iv);
    };
  }, [status]);

  /* keep the transcript pinned to the latest */
  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages]);

  const onPickAction = (prompt: string) => {
    setInput(prompt);
    const ta = textareaRef.current;
    if (ta) {
      ta.focus();
      ta.setSelectionRange(prompt.length, prompt.length);
    }
  };

  const onInput = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setInput(e.target.value);
    e.target.style.height = "auto";
    e.target.style.height = Math.min(e.target.scrollHeight, 160) + "px";
  };

  const onKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      send(input);
    }
  };

  const toggleMic = async () => {
    if (recording) {
      recorderRef.current?.stop();
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const recorder = new MediaRecorder(stream);
      const chunks: Blob[] = [];
      recorder.ondataavailable = (e) => {
        if (e.data.size) chunks.push(e.data);
      };
      recorder.onstop = async () => {
        stream.getTracks().forEach((t) => t.stop());
        setRecording(false);
        const blob = new Blob(chunks, { type: recorder.mimeType || "audio/webm" });
        const text = await transcribe(blob);
        if (text.trim()) send(text);
      };
      recorderRef.current = recorder;
      recorder.start();
      setRecording(true);
      setActivity("listening");
    } catch {
      addMsg("jarvis", "I couldn't access the microphone. Check the browser's permissions.");
    }
  };

  const wake = voice?.wake_phrase ?? "Hey Jarvis";
  const voiceLabel =
    voice?.state === "listening"
      ? "Listening"
      : voice?.state === "thinking" || voice?.state === "processing"
        ? "Thinking"
        : voice?.state === "speaking"
          ? "Speaking"
          : `“${wake}”`;
  const voiceActive =
    voice?.state === "listening" ||
    voice?.state === "thinking" ||
    voice?.state === "processing" ||
    voice?.state === "speaking";

  const hasChat = messages.length > 0;
  const PANEL = "lg:w-[460px] sm:w-[400px] w-full";

  return (
    <div className="relative h-dvh overflow-hidden bg-void">
      {/* living core — stays centered */}
      <div className="pointer-events-none fixed inset-0 z-0" aria-hidden="true">
        <div
          className={cn(
            "absolute inset-0 transition-transform duration-[900ms] ease-[cubic-bezier(0.16,1,0.3,1)] will-change-transform",
            hasChat && "sm:-translate-x-[200px] lg:-translate-x-[230px]",
          )}
        >
          <div
            className="absolute left-1/2 top-1/2 h-[70vmin] w-[70vmin] -translate-x-1/2 -translate-y-1/2 rounded-full"
            style={{
              background:
                "radial-gradient(circle, rgba(56,232,255,0.10) 0%, rgba(56,232,255,0.03) 38%, transparent 70%)",
            }}
          />
          <AICore level={level} flow={flow} />
        </div>
        <div className="vignette absolute inset-0" />
      </div>

      {/* header */}
      <header className="fixed inset-x-0 top-0 z-30 flex h-14 items-center justify-between px-5 sm:px-8">
        <Logo className="text-ink" />
        <div className="flex items-center gap-3 sm:gap-5">
          {status === "online" && voice !== null && voice.state !== "offline" && (
            <span className="hidden items-center gap-2 text-xs text-muted sm:flex">
              <span
                className={cn(
                  "h-1.5 w-1.5 rounded-full",
                  voiceActive ? "animate-pulse bg-accent" : "bg-faint",
                )}
              />
              {voiceLabel}
            </span>
          )}
          <span className="flex items-center gap-2 text-xs text-muted">
            <span
              className={cn(
                "h-1.5 w-1.5 rounded-full",
                status === "online"
                  ? "bg-accent shadow-[0_0_8px_var(--color-accent-glow)]"
                  : status === "offline"
                    ? "bg-red-500"
                    : "bg-amber-400",
              )}
            />
            <span className="hidden sm:inline">
              {status === "online" ? "Core online" : status === "offline" ? "Core offline" : "Connecting"}
            </span>
          </span>
          <button
            onClick={() => setSystemOpen(true)}
            className="lg lg-chip relative inline-flex items-center gap-1.5 rounded-full border border-line px-3 py-1.5 text-xs text-ink-soft transition-colors hover:border-white/20 hover:text-ink"
          >
            <LayoutDashboard size={14} />
            <span className="hidden sm:inline">System</span>
            {unread > 0 && (
              <span className="absolute -right-1 -top-1 flex h-4 min-w-4 items-center justify-center rounded-full bg-accent px-1 text-[0.6rem] font-medium text-void">
                {unread}
              </span>
            )}
          </button>
          <button
            onClick={() => setMemoryOpen(true)}
            className="lg lg-chip inline-flex items-center gap-1.5 rounded-full border border-line px-3 py-1.5 text-xs text-ink-soft transition-colors hover:border-white/20 hover:text-ink"
          >
            <Brain size={14} />
            <span className="hidden sm:inline">Memory</span>
          </button>
          <button
            onClick={() => setSkillsOpen(true)}
            className="lg lg-chip inline-flex items-center gap-1.5 rounded-full border border-line px-3 py-1.5 text-xs text-ink-soft transition-colors hover:border-white/20 hover:text-ink"
          >
            <Sparkles size={14} />
            <span className="hidden sm:inline">Skills</span>
          </button>
        </div>
      </header>

      {/* greeting — shown over the centered core when idle */}
      {!hasChat && (
        <div className="relative z-10 flex h-dvh flex-col items-center justify-center px-6 text-center">
          <p className="text-eyebrow mb-4">
            {status === "online" ? "At your service" : "Awaiting the core"}
          </p>
          <h1 className="font-display text-4xl tracking-tight sm:text-5xl">{greeting}.</h1>
          <p className="lede mt-3 max-w-md">What would you like to do?</p>
        </div>
      )}

      {/* conversation — right-hand panel, never covers the core */}
      <AnimatePresence>
        {hasChat && (
          <motion.aside
            initial={{ opacity: 0, x: 48 }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0, x: 48 }}
            transition={{ type: "spring", damping: 32, stiffness: 280 }}
            className={cn(
              "lg-panel lg-refract lg-clear fixed right-0 top-14 bottom-0 z-10 flex flex-col border-l border-line bg-void/80",
              PANEL,
            )}
          >
            <div className="flex items-center justify-between border-b border-line px-5 py-3">
              <span className="text-eyebrow text-[0.62rem]">Transcript</span>
              <button
                onClick={clearChat}
                className="inline-flex items-center gap-1.5 text-xs text-muted transition-colors hover:text-ink"
              >
                <X size={13} /> Clear
              </button>
            </div>
            <div ref={scrollRef} className="flex-1 space-y-6 overflow-y-auto px-5 py-6 pb-44">
              {messages.map((m) =>
                m.role === "user" ? (
                  <div key={m.id} className="flex justify-end">
                    <div className="lg lg-bubble max-w-[88%] rounded-2xl rounded-br-md bg-white/[0.06] px-3.5 py-2 text-[0.9rem] text-ink">
                      {m.text}
                    </div>
                  </div>
                ) : (
                  <div key={m.id}>
                    {m.domain && (
                      <p className="text-eyebrow mb-1.5 text-[0.58rem]">Routed · {m.domain}</p>
                    )}
                    <div className="text-[0.9rem] leading-relaxed text-ink-soft">
                      {renderBody(m.text)}
                    </div>
                  </div>
                ),
              )}
            </div>
          </motion.aside>
        )}
      </AnimatePresence>

      {/* command bar — fixed bottom, kept clear of the panel on desktop */}
      <div className="fixed inset-x-0 bottom-0 z-30 sm:right-[400px] lg:right-[460px]">
        <div className="mx-auto w-full max-w-2xl px-4 pb-5 pt-3 sm:px-6">
          <ActionChips onPrefill={onPickAction} />

          <form
            onSubmit={(e) => {
              e.preventDefault();
              send(input);
            }}
            className="lg-bar lg-refract flex items-end gap-2 rounded-2xl border border-line bg-void/70 p-2 pl-4 backdrop-blur-sm transition-colors focus-within:border-white/25"
          >
            <textarea
              ref={textareaRef}
              value={input}
              onChange={onInput}
              onKeyDown={onKeyDown}
              rows={1}
              placeholder="Tell JARVIS what to do…"
              aria-label="Command for JARVIS"
              className="max-h-40 flex-1 resize-none bg-transparent py-2 text-[0.95rem] text-ink outline-none placeholder:text-faint"
            />
            <button
              type="button"
              onClick={toggleMic}
              aria-label={recording ? "Stop recording" : "Speak to JARVIS"}
              className={cn(
                "lg-icon inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-xl transition-colors",
                recording
                  ? "bg-accent/15 text-accent"
                  : "text-muted hover:bg-white/5 hover:text-ink",
              )}
            >
              {recording ? <Square size={16} /> : <Mic size={18} />}
            </button>
            <button
              type="submit"
              disabled={busy || !input.trim()}
              aria-label="Send"
              className="lg-accent inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-accent text-void transition-all hover:brightness-110 disabled:bg-white/10 disabled:text-faint"
            >
              <Send size={17} />
            </button>
          </form>
          <p className="mt-2 text-center text-[0.7rem] text-faint">
            JARVIS routes each request to the right faculty · Enter to send
          </p>
        </div>
      </div>

      <SkillsPanel
        open={skillsOpen}
        onClose={() => setSkillsOpen(false)}
        online={status === "online"}
      />

      <SystemPanel
        open={systemOpen}
        onClose={() => setSystemOpen(false)}
        online={status === "online"}
      />

      <MemoryPanel
        open={memoryOpen}
        onClose={() => setMemoryOpen(false)}
        online={status === "online"}
      />
    </div>
  );
}
