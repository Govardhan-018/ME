"use client";

import { Canvas } from "@react-three/fiber";
import { motion, useTransform, type MotionValue } from "framer-motion";
import { CoreScene } from "./CoreScene";
import { useDevicePerf, usePrefersReducedMotion } from "@/lib/perf";

interface AICoreProps {
  level: MotionValue<number>;
  flow: MotionValue<number>;
}

/**
 * The living JARVIS core. Default-exported for `dynamic(ssr:false)`.
 * Brightens as activity rises so the orb visibly responds to real work.
 */
export default function AICore({ level, flow }: AICoreProps) {
  const perf = useDevicePerf();
  const reduced = usePrefersReducedMotion();
  const opacity = useTransform(level, [0.6, 3.6], [0.45, 0.92]);

  return (
    <motion.div className="absolute inset-0" style={{ opacity }}>
      <Canvas
        gl={{ antialias: true, alpha: true, powerPreference: "high-performance" }}
        dpr={[1, perf.maxDpr]}
        camera={{ position: [0, 0, 6], fov: 48 }}
        style={{ background: "transparent" }}
        frameloop={reduced ? "demand" : "always"}
      >
        <CoreScene level={level} flow={flow} perf={perf} reduced={reduced} />
      </Canvas>
    </motion.div>
  );
}
