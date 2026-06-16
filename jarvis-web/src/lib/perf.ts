"use client";

import { useEffect, useState } from "react";

export type PerfTier = "low" | "mid" | "high";

export interface PerfProfile {
  /** neural node count */
  nodes: number;
  /** flowing data-stream particle count */
  streams: number;
  /** max neighbour connections per node */
  links: number;
  /** device-pixel-ratio ceiling for the renderer */
  maxDpr: number;
  tier: PerfTier;
}

const TABLE: Record<PerfTier, Omit<PerfProfile, "tier">> = {
  low: { nodes: 360, streams: 260, links: 2, maxDpr: 1.4 },
  mid: { nodes: 820, streams: 600, links: 2, maxDpr: 1.6 },
  high: { nodes: 1500, streams: 1100, links: 3, maxDpr: 1.85 },
};

/**
 * Picks a particle budget from the device's width, core count and memory so the
 * AI Core holds 60fps on a phone and still looks dense on a workstation.
 * SSR-safe: starts at "mid" and refines after mount.
 */
export function useDevicePerf(): PerfProfile {
  const [profile, setProfile] = useState<PerfProfile>({ ...TABLE.mid, tier: "mid" });

  useEffect(() => {
    const nav = navigator as Navigator & { deviceMemory?: number };
    const width = window.innerWidth;
    const cores = nav.hardwareConcurrency ?? 4;
    const mem = nav.deviceMemory ?? 4;

    let tier: PerfTier = "high";
    if (width < 768 || cores <= 4 || mem <= 4) tier = "low";
    else if (width < 1200 || cores <= 8) tier = "mid";

    setProfile({ ...TABLE[tier], tier });
  }, []);

  return profile;
}

/** Reactive `prefers-reduced-motion` flag. */
export function usePrefersReducedMotion(): boolean {
  const [reduced, setReduced] = useState(false);

  useEffect(() => {
    const mq = window.matchMedia("(prefers-reduced-motion: reduce)");
    const update = () => setReduced(mq.matches);
    update();
    mq.addEventListener("change", update);
    return () => mq.removeEventListener("change", update);
  }, []);

  return reduced;
}
