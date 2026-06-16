"use client";

import { useCallback, useEffect, useState } from "react";
import dynamic from "next/dynamic";
import { AnimatePresence, motion } from "framer-motion";
import { Brain, X } from "lucide-react";
import { getMemory, type MemoryData } from "@/lib/jarvis";
import type { MemoryNode } from "@/components/memory/MemoryGalaxy";

const MemoryGalaxy = dynamic(() => import("@/components/memory/MemoryGalaxy"), {
  ssr: false,
  loading: () => null,
});

interface MemoryPanelProps {
  open: boolean;
  onClose: () => void;
  online: boolean;
}

const LEGEND = [
  { c: "#ED872D", label: "You" },
  { c: "#E6BE8A", label: "Topics" },
  { c: "#C04000", label: "Facts" },
];

export function MemoryPanel({ open, onClose, online }: MemoryPanelProps) {
  const [data, setData] = useState<MemoryData | null>(null);
  const [hovered, setHovered] = useState<MemoryNode | null>(null);
  const onHover = useCallback((n: MemoryNode | null) => setHovered(n), []);

  useEffect(() => {
    if (!open || !online) return;
    getMemory()
      .then(setData)
      .catch(() => setData({ facts: [], recent: [] }));
  }, [open, online]);

  const facts = data?.facts ?? [];

  return (
    <AnimatePresence>
      {open && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          className="fixed inset-0 z-50 overflow-hidden bg-void"
        >
          <div
            className="pointer-events-none absolute inset-0"
            style={{
              background:
                "radial-gradient(circle at 50% 42%, rgba(237,135,45,0.06), transparent 55%)",
            }}
          />
          {/* vignette — darkens the edges to focus attention on the graph */}
          <div
            className="pointer-events-none absolute inset-0"
            style={{
              background:
                "radial-gradient(120% 100% at 50% 50%, transparent 52%, rgba(5,5,7,0.72) 100%)",
            }}
          />

          {/* the hologram */}
          <div className="absolute inset-0">
            {online && <MemoryGalaxy facts={facts} onHover={onHover} />}
          </div>

          {/* header */}
          <div className="pointer-events-none absolute inset-x-0 top-0 flex items-start justify-between px-6 py-5 sm:px-8">
            <div>
              <h2 className="flex items-center gap-2 font-display text-lg">
                <Brain size={18} style={{ color: "#E6BE8A" }} /> Memory
              </h2>
              <p className="text-xs text-muted">
                {facts.length} durable {facts.length === 1 ? "memory" : "memories"}
                {online ? " · drag to orbit, scroll to zoom" : ""}
              </p>
            </div>
            <button
              onClick={onClose}
              aria-label="Close memory"
              className="pointer-events-auto inline-flex h-9 w-9 items-center justify-center rounded-full border border-line text-muted transition-colors hover:text-ink"
            >
              <X size={18} />
            </button>
          </div>

          {/* legend */}
          <div className="pointer-events-none absolute bottom-5 left-6 flex gap-4 sm:left-8">
            {LEGEND.map((l) => (
              <span key={l.label} className="flex items-center gap-1.5 text-[0.7rem] text-muted">
                <span className="h-1.5 w-1.5 rounded-full" style={{ background: l.c }} />
                {l.label}
              </span>
            ))}
          </div>

          {/* hover detail */}
          <AnimatePresence>
            {hovered && hovered.kind !== "hub" && (
              <motion.div
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: 10 }}
                className="pointer-events-none absolute bottom-5 right-6 max-w-xs rounded-xl border border-line bg-void-2/90 p-4 backdrop-blur-sm sm:right-8"
              >
                <p className="text-eyebrow mb-1.5 text-[0.58rem]" style={{ color: hovered.kind === "subject" ? "#E6BE8A" : "#e0905f" }}>
                  {hovered.kind === "subject" ? "Topic" : "Memory"}
                  {hovered.source ? ` · ${hovered.source}` : ""}
                </p>
                <p className="text-sm leading-relaxed text-ink-soft">
                  {hovered.kind === "subject" ? hovered.label : hovered.fact}
                </p>
              </motion.div>
            )}
          </AnimatePresence>

          {/* empty / offline states */}
          {online && data && facts.length === 0 && (
            <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center px-6 text-center">
              <p className="font-display text-xl text-ink-soft">Memory is empty</p>
              <p className="lede mt-2 max-w-sm">
                As you talk to JARVIS, the nightly reflection distils durable facts —
                they&apos;ll appear here as a growing web.
              </p>
            </div>
          )}
          {!online && (
            <div className="pointer-events-none absolute inset-0 flex items-center justify-center px-6 text-center">
              <p className="lede max-w-sm">Connect the Core to visualize its memory.</p>
            </div>
          )}
        </motion.div>
      )}
    </AnimatePresence>
  );
}
