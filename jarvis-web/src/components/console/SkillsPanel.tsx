"use client";

import { useCallback, useEffect, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { Sparkles, X } from "lucide-react";
import { getSkills, skillAction, skillDesc, skillName, type Faculty } from "@/lib/jarvis";

interface SkillsPanelProps {
  open: boolean;
  onClose: () => void;
  online: boolean;
}

export function SkillsPanel({ open, onClose, online }: SkillsPanelProps) {
  const [builtin, setBuiltin] = useState<Faculty[]>([]);
  const [active, setActive] = useState<unknown[]>([]);
  const [staged, setStaged] = useState<unknown[]>([]);
  const [error, setError] = useState(false);

  const load = useCallback(async () => {
    try {
      const data = await getSkills();
      setBuiltin(data.builtin ?? []);
      setActive(data.skills ?? []);
      setStaged(data.staged ?? []);
      setError(false);
    } catch {
      setError(true);
    }
  }, []);

  useEffect(() => {
    if (open) load();
  }, [open, load]);

  const act = async (action: "approve" | "discard", name: string) => {
    await skillAction(action, name);
    load();
  };

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
            className="lg-panel lg-refract fixed right-0 top-0 z-50 flex h-dvh w-full max-w-sm flex-col border-l border-line bg-void-2"
          >
            <header className="flex items-center justify-between border-b border-line px-6 py-5">
              <div>
                <h2 className="font-display text-lg">Capabilities</h2>
                <p className="text-xs text-muted">Built-in faculties + skills it wrote itself</p>
              </div>
              <button
                onClick={onClose}
                aria-label="Close skills"
                className="inline-flex h-9 w-9 items-center justify-center rounded-full text-muted hover:text-ink"
              >
                <X size={18} />
              </button>
            </header>

            <div className="flex-1 overflow-y-auto px-6 py-5">
              {error || !online ? (
                <p className="text-sm text-muted">
                  Connect the Core to read its capabilities.
                </p>
              ) : (
                <div className="space-y-6">
                  {builtin.length > 0 && (
                    <section>
                      <p className="text-eyebrow mb-3 text-[0.65rem]">Faculties · built-in</p>
                      <div className="space-y-2">
                        {builtin.map((f) => (
                          <div
                            key={f.name}
                            className="rounded-xl border border-line bg-void p-3.5"
                          >
                            <div className="flex items-center justify-between">
                              <p className="font-display text-sm">{f.label}</p>
                              <span className="rounded-full border border-line px-1.5 py-0.5 text-[0.55rem] uppercase text-faint">
                                {f.tier}
                              </span>
                            </div>
                            <p className="mt-1 text-[0.8rem] leading-relaxed text-muted">
                              {f.description}
                            </p>
                          </div>
                        ))}
                      </div>
                    </section>
                  )}

                  {staged.length > 0 && (
                    <section>
                      <p className="text-eyebrow mb-3 text-[0.65rem]">Awaiting approval</p>
                      <div className="space-y-3">
                        {staged.map((s) => {
                          const name = skillName(s);
                          return (
                            <div
                              key={name}
                              className="rounded-xl border border-accent/30 bg-accent/[0.04] p-4"
                            >
                              <p className="font-display">{name}</p>
                              {skillDesc(s) && (
                                <p className="mt-1.5 text-sm text-muted">{skillDesc(s)}</p>
                              )}
                              <div className="mt-3 flex gap-4 text-sm">
                                <button
                                  onClick={() => act("approve", name)}
                                  className="text-accent hover:underline"
                                >
                                  Approve
                                </button>
                                <button
                                  onClick={() => act("discard", name)}
                                  className="text-muted hover:text-ink"
                                >
                                  Discard
                                </button>
                              </div>
                            </div>
                          );
                        })}
                      </div>
                    </section>
                  )}

                  <section>
                    <p className="text-eyebrow mb-3 flex items-center gap-1.5 text-[0.65rem]">
                      <Sparkles size={11} /> Self-built skills
                    </p>
                    {active.length > 0 ? (
                      <div className="space-y-3">
                        {active.map((s) => {
                          const name = skillName(s);
                          return (
                            <div
                              key={name}
                              className="rounded-xl border border-line bg-void p-4"
                            >
                              <p className="font-display">{name}</p>
                              {skillDesc(s) && (
                                <p className="mt-1.5 text-sm text-muted">{skillDesc(s)}</p>
                              )}
                            </div>
                          );
                        })}
                      </div>
                    ) : (
                      <p className="text-[0.8rem] leading-relaxed text-faint">
                        None yet. Ask for a deterministic computation it lacks, and watch it
                        write one — then approve it here.
                      </p>
                    )}
                  </section>
                </div>
              )}
            </div>
          </motion.aside>
        </>
      )}
    </AnimatePresence>
  );
}
