import { cn } from "@/lib/utils";

/** The JARVIS mark — a minimal core glyph + wordmark. */
export function Logo({ className }: { className?: string }) {
  return (
    <span className={cn("inline-flex items-center gap-2.5", className)}>
      <svg width="22" height="22" viewBox="0 0 22 22" fill="none" aria-hidden="true">
        <circle cx="11" cy="11" r="9.2" stroke="currentColor" strokeOpacity="0.28" />
        <circle cx="11" cy="11" r="5" stroke="var(--color-accent)" strokeOpacity="0.7" />
        <circle cx="11" cy="11" r="1.9" fill="var(--color-accent)" />
        <circle cx="11" cy="1.8" r="1" fill="currentColor" fillOpacity="0.5" />
        <circle cx="20.2" cy="11" r="1" fill="currentColor" fillOpacity="0.5" />
      </svg>
      <span className="font-display text-[1.05rem] font-semibold tracking-tight">
        JARVIS
      </span>
    </span>
  );
}
