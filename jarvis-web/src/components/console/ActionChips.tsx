"use client";

import { useEffect, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import {
  ArrowUpRight,
  Code2,
  FileText,
  FolderOpen,
  Globe,
  Mail,
  MessageSquare,
  type LucideIcon,
} from "lucide-react";
import { cn } from "@/lib/utils";

/**
 * The quick-action chips above the command bar. Clicking a chip opens a small
 * "faculty card" — what it does, which agent it routes to, and a few example
 * prompts you can tap to drop straight into the command bar.
 */

interface Action {
  id: string;
  label: string;
  icon: LucideIcon;
  routedTo: string;
  desc: string;
  examples: string[];
}

const ACTIONS: Action[] = [
  {
    id: "ask", label: "Ask", icon: MessageSquare, routedTo: "general",
    desc: "Think out loud — questions, ideas, anything. JARVIS routes it to the right faculty.",
    examples: ["What's on my plate today?", "Explain how a Kalman filter works", "Give me three STM32 project ideas"],
  },
  {
    id: "code", label: "Code", icon: Code2, routedTo: "coder",
    desc: "Generate, edit, explain, or run code inside the workspace sandbox.",
    examples: ["Write a Python script to rename files by date", "Explain what this regex does", "Make fibonacci.py iterative and run it"],
  },
  {
    id: "research", label: "Research", icon: Globe, routedTo: "browser",
    desc: "Search the web, read the sources, and hand back a cited summary.",
    examples: ["Latest on video-frame interpolation", "Compare Qdrant vs pgvector for recall", "Summarise the new EU AI Act"],
  },
  {
    id: "notion", label: "Notion", icon: FileText, routedTo: "notion",
    desc: "Create and update pages in your Notion workspace.",
    examples: ["Create a 'Weekly Review' page", "Add my ML study plan as a checklist", "Start a reading-list page"],
  },
  {
    id: "email", label: "Email", icon: Mail, routedTo: "gmail",
    desc: "Draft email — and, once you approve, send it from your account.",
    examples: ["Draft a polite decline to the 3pm meeting", "Email myself today's to-do list", "Write a follow-up to the recruiter"],
  },
  {
    id: "files", label: "Files", icon: FolderOpen, routedTo: "files",
    desc: "Read, search, and reason over the files in your workspace.",
    examples: ["Find my STM32 notes", "Summarise the README in workspace", "Which files changed most recently?"],
  },
];

export function ActionChips({ onPrefill }: { onPrefill: (text: string) => void }) {
  const [openId, setOpenId] = useState<string | null>(null);
  const ref = useRef<HTMLDivElement>(null);

  // dismiss on outside click / Escape
  useEffect(() => {
    if (!openId) return;
    const onDown = (e: PointerEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpenId(null);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpenId(null);
    };
    document.addEventListener("pointerdown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("pointerdown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [openId]);

  const pick = (text: string) => {
    onPrefill(text);
    setOpenId(null);
  };

  return (
    <div ref={ref} className="mb-3 flex flex-wrap justify-center gap-2">
      {ACTIONS.map((a) => {
        const open = openId === a.id;
        const Icon = a.icon;
        return (
          <div key={a.id} className="relative">
            <button
              onClick={() => setOpenId(open ? null : a.id)}
              aria-expanded={open}
              aria-haspopup="dialog"
              className={cn(
                "lg lg-chip inline-flex items-center gap-2 rounded-full border border-line bg-white/[0.02] px-3.5 py-1.5 text-xs backdrop-blur-sm transition-colors",
                open
                  ? "border-white/25 text-ink"
                  : "text-ink-soft hover:border-white/20 hover:text-ink",
              )}
            >
              <Icon size={13} />
              {a.label}
            </button>

            <AnimatePresence>
              {open && (
                <motion.div
                  initial={{ opacity: 0, y: 8, scale: 0.96 }}
                  animate={{ opacity: 1, y: 0, scale: 1 }}
                  exit={{ opacity: 0, y: 6, scale: 0.97 }}
                  transition={{ type: "spring", damping: 26, stiffness: 360 }}
                  style={{ transformOrigin: "bottom center" }}
                  role="dialog"
                  aria-label={`${a.label} — examples`}
                  className="absolute bottom-full left-1/2 z-50 mb-2.5 w-64 max-w-[calc(100vw-2rem)] -translate-x-1/2 rounded-2xl border border-line-strong bg-void-2/90 p-3.5 shadow-[0_18px_50px_-16px_rgba(0,0,0,0.85)] backdrop-blur-xl"
                >
                  <div className="mb-1.5 flex items-center justify-between gap-2">
                    <span className="flex items-center gap-2 font-display text-sm text-ink">
                      <Icon size={14} className="text-accent" /> {a.label}
                    </span>
                    <span className="text-eyebrow text-[0.5rem] text-faint">→ {a.routedTo}</span>
                  </div>
                  <p className="mb-3 text-[0.78rem] leading-relaxed text-muted">{a.desc}</p>
                  <p className="text-eyebrow mb-1.5 text-[0.52rem]">Try</p>
                  <div className="space-y-0.5">
                    {a.examples.map((ex) => (
                      <button
                        key={ex}
                        onClick={() => pick(ex)}
                        className="group flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-left text-[0.8rem] text-ink-soft transition-colors hover:bg-white/[0.06] hover:text-ink"
                      >
                        <ArrowUpRight
                          size={12}
                          className="mt-0.5 shrink-0 text-faint transition-colors group-hover:text-accent"
                        />
                        <span className="leading-snug">{ex}</span>
                      </button>
                    ))}
                  </div>

                  {/* tail pointing down to the chip */}
                  <span className="absolute -bottom-1 left-1/2 h-2.5 w-2.5 -translate-x-1/2 rotate-45 border-b border-r border-line-strong bg-void-2/90" />
                </motion.div>
              )}
            </AnimatePresence>
          </div>
        );
      })}
    </div>
  );
}
