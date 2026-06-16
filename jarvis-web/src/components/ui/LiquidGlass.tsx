"use client";

/* =============================================================================
   LIQUID GLASS — experimental control surface
   -----------------------------------------------------------------------------
   Self-contained: renders (1) the hidden SVG filter that powers the refraction
   and (2) a discreet floating toggle to switch the effect on/off live (persisted
   to localStorage). The gate attribute html[data-lg] is what every CSS rule in
   liquid-glass.css keys off of.

   To remove the whole experiment: delete this file and its <LiquidGlass /> mount
   + import in app/layout.tsx (see that file's header note).
   ========================================================================== */

import { useEffect, useState } from "react";
import { cn } from "@/lib/utils";

export function LiquidGlass() {
  const [on, setOn] = useState(true);

  // adopt the persisted choice on mount (default = on)
  useEffect(() => {
    const saved = localStorage.getItem("lg");
    const initial = saved === null ? true : saved === "on";
    setOn(initial);
    document.documentElement.dataset.lg = initial ? "on" : "off";
  }, []);

  const toggle = () => {
    setOn((prev) => {
      const next = !prev;
      document.documentElement.dataset.lg = next ? "on" : "off";
      try {
        localStorage.setItem("lg", next ? "on" : "off");
      } catch {
        /* ignore private-mode storage errors */
      }
      return next;
    });
  };

  return (
    <>
      {/* refraction filter — referenced by `backdrop-filter: url(#lg-refraction)`.
          A gentle fractal-noise displacement of the backdrop = the liquid wobble. */}
      <svg aria-hidden="true" width="0" height="0" className="pointer-events-none absolute">
        <defs>
          <filter
            id="lg-refraction"
            x="-35%"
            y="-35%"
            width="170%"
            height="170%"
            colorInterpolationFilters="sRGB"
          >
            {/* two-octave fractal noise → a richer "twist" in the bent backdrop */}
            <feTurbulence
              type="fractalNoise"
              baseFrequency="0.006 0.012"
              numOctaves={2}
              seed={11}
              result="noise"
            />
            <feGaussianBlur in="noise" stdDeviation="1.4" result="softNoise" />
            {/* displace the backdrop by the noise — the background bends & twists */}
            <feDisplacementMap
              in="SourceGraphic"
              in2="softNoise"
              scale={17}
              xChannelSelector="R"
              yChannelSelector="G"
            />
          </filter>
        </defs>
      </svg>

      <button
        type="button"
        onClick={toggle}
        aria-pressed={on}
        title="Toggle Liquid Glass (experimental)"
        className="lg lg-chip fixed bottom-4 right-4 z-30 inline-flex items-center gap-2 rounded-full border border-line bg-void/60 px-3 py-1.5 text-[0.7rem] text-muted opacity-50 backdrop-blur-sm transition-opacity duration-300 hover:text-ink hover:opacity-100 focus-visible:opacity-100"
      >
        <span
          className={cn(
            "h-1.5 w-1.5 rounded-full transition-colors",
            on ? "bg-accent shadow-[0_0_8px_var(--color-accent-glow)]" : "bg-faint",
          )}
        />
        Liquid Glass
        <span className="text-faint">{on ? "On" : "Off"}</span>
      </button>
    </>
  );
}
