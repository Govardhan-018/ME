"use client";

import { useCallback, useEffect, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { Bell, CalendarDays, Check, Clock, Play, X, Zap } from "lucide-react";
import {
  describeTrigger,
  fmtTime,
  gatewayApprove,
  gatewayDeny,
  markFeedRead,
  runBrief,
  runSchedule,
  setMode,
  systemSnapshot,
  toggleSchedule,
  type CalEvent,
  type FeedItem,
  type Pending,
  type Schedule,
  type SystemSnapshot,
} from "@/lib/jarvis";
import { cn } from "@/lib/utils";

interface SystemPanelProps {
  open: boolean;
  onClose: () => void;
  online: boolean;
}

const MODES = ["observe", "copilot", "autopilot"] as const;

export function SystemPanel({ open, onClose, online }: SystemPanelProps) {
  const [snap, setSnap] = useState<SystemSnapshot | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    const s = await systemSnapshot();
    if (s) setSnap(s);
  }, []);

  useEffect(() => {
    if (!open || !online) return;
    load();
    const iv = setInterval(load, 5000);
    return () => clearInterval(iv);
  }, [open, online, load]);

  const run = useCallback(
    async (fn: () => Promise<unknown>) => {
      setBusy(true);
      try {
        await fn();
        await load();
      } finally {
        setBusy(false);
      }
    },
    [load],
  );

  return (
    <AnimatePresence>
      {open && (
        <>
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={onClose}
            className="fixed inset-0 z-40 bg-black/50"
          />
          <motion.aside
            initial={{ x: "100%" }}
            animate={{ x: 0 }}
            exit={{ x: "100%" }}
            transition={{ type: "spring", damping: 32, stiffness: 280 }}
            className="lg-panel lg-refract fixed right-0 top-0 z-50 flex h-dvh w-full max-w-md flex-col border-l border-line bg-void-2"
          >
            <header className="flex items-center justify-between border-b border-line px-6 py-5">
              <div>
                <h2 className="font-display text-lg">System</h2>
                <p className="text-xs text-muted">Your AI operating system, live</p>
              </div>
              <button
                onClick={onClose}
                aria-label="Close system"
                className="inline-flex h-9 w-9 items-center justify-center rounded-full text-muted hover:text-ink"
              >
                <X size={18} />
              </button>
            </header>

            <div className="flex-1 space-y-7 overflow-y-auto px-6 py-6">
              {!online || !snap ? (
                <p className="text-sm text-muted">
                  Connect the Core to see your calendar, briefings, and live metrics.
                </p>
              ) : (
                <>
                  <AutonomySection mode={snap.mode} busy={busy}
                    onSet={(m) => run(() => setMode(m))} />

                  <MetricsStrip snap={snap} />

                  {snap.pending.length > 0 && (
                    <Section label="Awaiting your approval" icon={<Bell size={12} />}>
                      <div className="space-y-2.5">
                        {snap.pending.map((p) => (
                          <PendingCard key={p.confirmation_id} p={p} busy={busy}
                            onApprove={() => run(() => gatewayApprove(p.confirmation_id))}
                            onDeny={() => run(() => gatewayDeny(p.confirmation_id))} />
                        ))}
                      </div>
                    </Section>
                  )}

                  <Section
                    label="Today"
                    icon={<CalendarDays size={12} />}
                    action={
                      <button
                        disabled={busy}
                        onClick={() => run(runBrief)}
                        className="text-xs text-accent hover:underline disabled:opacity-50"
                      >
                        Brief me
                      </button>
                    }
                  >
                    <Agenda events={snap.calendar.today} />
                  </Section>

                  <Section label="Proactive feed" icon={<Zap size={12} />}>
                    <Feed items={snap.feed.items} busy={busy}
                      onApprove={(id) => run(() => gatewayApprove(id))}
                      onDeny={(id) => run(() => gatewayDeny(id))}
                      onRead={(id) => run(() => markFeedRead(id))} />
                  </Section>

                  <Section label="Schedules" icon={<Clock size={12} />}>
                    <Schedules rows={snap.schedules} busy={busy}
                      onRun={(id) => run(() => runSchedule(id))}
                      onToggle={(id, en) => run(() => toggleSchedule(id, en))} />
                  </Section>
                </>
              )}
            </div>
          </motion.aside>
        </>
      )}
    </AnimatePresence>
  );
}

/* ---- sections ---------------------------------------------------------- */
function Section({ label, icon, action, children }: {
  label: string; icon?: React.ReactNode; action?: React.ReactNode; children: React.ReactNode;
}) {
  return (
    <section>
      <div className="mb-3 flex items-center justify-between">
        <p className="text-eyebrow flex items-center gap-1.5 text-[0.65rem] text-muted">
          {icon} {label}
        </p>
        {action}
      </div>
      {children}
    </section>
  );
}

function AutonomySection({ mode, busy, onSet }: {
  mode: string; busy: boolean; onSet: (m: string) => void;
}) {
  return (
    <Section label="Autonomy">
      <div className="grid grid-cols-3 gap-1 rounded-xl border border-line bg-void p-1">
        {MODES.map((m) => (
          <button
            key={m}
            disabled={busy}
            onClick={() => onSet(m)}
            className={cn(
              "rounded-lg py-1.5 text-xs capitalize transition-colors disabled:opacity-60",
              mode === m
                ? "bg-accent/15 text-accent shadow-[0_0_12px_var(--color-accent-glow)]"
                : "text-muted hover:text-ink",
            )}
          >
            {m}
          </button>
        ))}
      </div>
      <p className="mt-2 text-[0.7rem] leading-relaxed text-faint">
        {mode === "observe"
          ? "Reads only — proposes actions but executes nothing."
          : mode === "autopilot"
            ? "Acts autonomously through irreversible steps — still confirms anything outward or costly."
            : "Auto read + in-scope writes; confirms irreversible, outward, or costly actions."}
      </p>
    </Section>
  );
}

function MetricsStrip({ snap }: { snap: SystemSnapshot }) {
  const o = snap.observability;
  const stats = [
    { k: "Turns", v: String(o.turns) },
    { k: "p50", v: `${Math.round(o.latency_ms.p50)}ms` },
    { k: "Errors", v: `${Math.round(o.error_rate * 100)}%` },
    { k: "Unread", v: String(snap.feed.unread) },
  ];
  return (
    <div className="grid grid-cols-4 gap-2">
      {stats.map((s) => (
        <div key={s.k} className="rounded-xl border border-line bg-void px-2 py-2.5 text-center">
          <p className="font-display text-base text-ink">{s.v}</p>
          <p className="text-eyebrow mt-0.5 text-[0.55rem] text-faint">{s.k}</p>
        </div>
      ))}
    </div>
  );
}

function Agenda({ events }: { events: CalEvent[] }) {
  if (!events.length)
    return <p className="text-sm text-muted">Nothing on the calendar today.</p>;
  return (
    <div className="space-y-2">
      {events.map((e) => (
        <div key={e.id} className="flex items-baseline gap-3 rounded-lg border border-line bg-void px-3 py-2">
          <span className="font-display text-xs text-accent tabular-nums">
            {e.all_day ? "all day" : fmtTime(e.start_ts)}
          </span>
          <span className="flex-1 text-sm text-ink-soft">{e.title}</span>
          {e.location && <span className="text-[0.7rem] text-faint">{e.location}</span>}
        </div>
      ))}
    </div>
  );
}

const KIND_TINT: Record<string, string> = {
  suggestion: "border-accent/30 bg-accent/[0.04]",
  alert: "border-red-500/30 bg-red-500/[0.04]",
  briefing: "border-line bg-void",
  result: "border-line bg-void",
};

function Feed({ items, busy, onApprove, onDeny, onRead }: {
  items: FeedItem[]; busy: boolean;
  onApprove: (id: string) => void; onDeny: (id: string) => void; onRead: (id: string) => void;
}) {
  if (!items.length)
    return <p className="text-sm text-muted">Quiet for now. Briefings and suggestions land here.</p>;
  return (
    <div className="space-y-2.5">
      {items.map((it) => (
        <div key={it.id} className={cn("rounded-xl border p-3.5", KIND_TINT[it.kind] ?? "border-line bg-void")}>
          <div className="flex items-center justify-between gap-2">
            <p className="text-xs font-medium text-ink">{it.title}</p>
            <span className="text-eyebrow text-[0.55rem] text-faint">{it.kind}</span>
          </div>
          {it.body && (
            <p className="mt-1.5 whitespace-pre-wrap text-[0.78rem] leading-relaxed text-muted line-clamp-6">
              {it.body}
            </p>
          )}
          {it.confirmation_id ? (
            <div className="mt-3 flex gap-4 text-xs">
              <button disabled={busy} onClick={() => onApprove(it.confirmation_id!)}
                className="inline-flex items-center gap-1 text-accent hover:underline disabled:opacity-50">
                <Check size={12} /> Approve
              </button>
              <button disabled={busy} onClick={() => onDeny(it.confirmation_id!)}
                className="text-muted hover:text-ink disabled:opacity-50">
                Dismiss
              </button>
            </div>
          ) : it.status === "unread" ? (
            <button disabled={busy} onClick={() => onRead(it.id)}
              className="mt-2.5 text-[0.7rem] text-faint hover:text-ink disabled:opacity-50">
              Mark read
            </button>
          ) : null}
        </div>
      ))}
    </div>
  );
}

function PendingCard({ p, busy, onApprove, onDeny }: {
  p: Pending; busy: boolean; onApprove: () => void; onDeny: () => void;
}) {
  return (
    <div className="rounded-xl border border-accent/30 bg-accent/[0.04] p-3.5">
      <div className="flex items-center justify-between gap-2">
        <p className="text-xs text-ink">{p.summary}</p>
        <span className="rounded-full border border-line px-1.5 py-0.5 text-[0.55rem] uppercase text-faint">
          {p.risk_tier}
        </span>
      </div>
      <div className="mt-3 flex gap-4 text-xs">
        <button disabled={busy} onClick={onApprove}
          className="inline-flex items-center gap-1 text-accent hover:underline disabled:opacity-50">
          <Check size={12} /> Approve
        </button>
        <button disabled={busy} onClick={onDeny}
          className="text-muted hover:text-ink disabled:opacity-50">
          Deny
        </button>
      </div>
    </div>
  );
}

function Schedules({ rows, busy, onRun, onToggle }: {
  rows: Schedule[]; busy: boolean;
  onRun: (id: string) => void; onToggle: (id: string, enabled: boolean) => void;
}) {
  if (!rows.length) return <p className="text-sm text-muted">No schedules yet.</p>;
  return (
    <div className="space-y-2">
      {rows.map((s) => (
        <div key={s.id} className="flex items-center gap-3 rounded-lg border border-line bg-void px-3 py-2">
          <div className="min-w-0 flex-1">
            <p className="truncate text-sm text-ink-soft">{s.name}</p>
            <p className="text-[0.68rem] text-faint">
              {s.kind} · {describeTrigger(s.trigger)}
              {s.next_run && s.enabled ? ` · next ${fmtTime(s.next_run)}` : ""}
            </p>
          </div>
          <button disabled={busy} onClick={() => onRun(s.id)} aria-label={`Run ${s.name}`}
            className="inline-flex h-7 w-7 items-center justify-center rounded-md text-muted hover:bg-white/5 hover:text-accent disabled:opacity-50">
            <Play size={13} />
          </button>
          <button disabled={busy} onClick={() => onToggle(s.id, !s.enabled)} aria-label="Toggle"
            className={cn(
              "relative h-4 w-7 shrink-0 rounded-full transition-colors",
              s.enabled ? "bg-accent/60" : "bg-white/10",
            )}>
            <span className={cn(
              "absolute top-0.5 h-3 w-3 rounded-full bg-ink transition-all",
              s.enabled ? "left-3.5" : "left-0.5",
            )} />
          </button>
        </div>
      ))}
    </div>
  );
}
