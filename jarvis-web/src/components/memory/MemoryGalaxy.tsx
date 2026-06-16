"use client";

import { useEffect, useMemo, useState } from "react";
import { Canvas } from "@react-three/fiber";
import { OrbitControls } from "@react-three/drei";
import * as THREE from "three";
import { usePrefersReducedMotion } from "@/lib/perf";
import type { MemoryFact } from "@/lib/jarvis";

/**
 * A quiet, explorable web of JARVIS's long-term memory.
 *   hub ("You") → subject clusters → individual facts
 * Default-exported for `dynamic(ssr:false)` (R3F context can't cross the Canvas
 * boundary, so `onHover` is passed as a plain prop, not via context).
 *
 * Deliberately restrained: a warm palette (cadmium-orange hub, gold topics,
 * mahogany facts), lit pearl-like nodes, soft NON-additive halos, thin neutral
 * edges, and depth fog — a precise data graph, not a neon galaxy.
 */

const HUB = "#ED872D"; // cadmium orange — the single authority accent
const SUBJECT = "#E6BE8A"; // gold (Crayola) — warm secondary
const FACT = "#C04000"; // mahogany — deep, quiet
const EDGE = "#6b574a"; // warm neutral taupe

export interface MemoryNode {
  id: string;
  kind: "hub" | "subject" | "fact";
  label: string;
  pos: [number, number, number];
  color: string;
  halo: number;
  haloOpacity: number;
  coreR: number;
  hitR: number;
  fact?: string;
  subject?: string;
  source?: string;
}

interface Graph {
  nodes: MemoryNode[];
  edges: [string, string][];
}

/** A point on a Fibonacci sphere of radius r — deterministic, evenly spread. */
function fib(i: number, n: number, r: number): [number, number, number] {
  const golden = Math.PI * (3 - Math.sqrt(5));
  const y = n <= 1 ? 0 : 1 - (i / (n - 1)) * 2;
  const rad = Math.sqrt(Math.max(0, 1 - y * y));
  const theta = golden * i;
  return [Math.cos(theta) * rad * r, y * r, Math.sin(theta) * rad * r];
}

function buildGraph(facts: MemoryFact[]): Graph {
  const nodes: MemoryNode[] = [];
  const edges: [string, string][] = [];

  nodes.push({
    id: "hub", kind: "hub", label: "You", pos: [0, 0, 0], color: HUB,
    halo: 1.7, haloOpacity: 0.4, coreR: 0.17, hitR: 0.5,
  });

  const groups = new Map<string, MemoryFact[]>();
  for (const f of facts) {
    const key = (f.subject || "").trim() || "__none__";
    (groups.get(key) ?? groups.set(key, []).get(key)!).push(f);
  }

  const subjects = [...groups.keys()].filter((k) => k !== "__none__");
  subjects.forEach((key, si) => {
    const p = fib(si, subjects.length, 4.2);
    const sid = `s${si}`;
    nodes.push({
      id: sid, kind: "subject", label: key, pos: p, color: SUBJECT,
      halo: 1.0, haloOpacity: 0.3, coreR: 0.1, hitR: 0.32, subject: key,
    });
    edges.push(["hub", sid]);

    const fl = groups.get(key)!;
    fl.forEach((f, fi) => {
      const o = fib(fi, Math.max(fl.length, 2), 1.45);
      nodes.push({
        id: `${sid}f${fi}`, kind: "fact",
        label: f.fact, pos: [p[0] + o[0], p[1] + o[1], p[2] + o[2]],
        color: FACT, halo: 0.5, haloOpacity: 0.22, coreR: 0.055, hitR: 0.22,
        fact: f.fact, subject: key, source: f.source ?? undefined,
      });
      edges.push([sid, `${sid}f${fi}`]);
    });
  });

  const loose = groups.get("__none__") ?? [];
  loose.forEach((f, i) => {
    nodes.push({
      id: `n${i}`, kind: "fact", label: f.fact, pos: fib(i, Math.max(loose.length, 3), 2.9),
      color: FACT, halo: 0.5, haloOpacity: 0.22, coreR: 0.055, hitR: 0.22,
      fact: f.fact, source: f.source ?? undefined,
    });
    edges.push(["hub", `n${i}`]);
  });

  return { nodes, edges };
}

/** A soft, gentle radial falloff — used as a subtle aura, NOT an additive bloom. */
function makeGlow(): THREE.Texture {
  const size = 128;
  const c = document.createElement("canvas");
  c.width = c.height = size;
  const ctx = c.getContext("2d")!;
  const g = ctx.createRadialGradient(size / 2, size / 2, 0, size / 2, size / 2, size / 2);
  g.addColorStop(0, "rgba(255,255,255,0.85)");
  g.addColorStop(0.35, "rgba(255,255,255,0.22)");
  g.addColorStop(1, "rgba(255,255,255,0)");
  ctx.fillStyle = g;
  ctx.fillRect(0, 0, size, size);
  const tex = new THREE.CanvasTexture(c);
  tex.needsUpdate = true;
  return tex;
}

const EMISSIVE: Record<MemoryNode["kind"], number> = { hub: 0.9, subject: 0.55, fact: 0.55 };

function Node({ node, glow, onHover }: {
  node: MemoryNode;
  glow: THREE.Texture;
  onHover: (n: MemoryNode | null) => void;
}) {
  const [hot, setHot] = useState(false);
  return (
    <group position={node.pos}>
      {/* soft aura — normal blending keeps it a quiet halo, not a neon flare */}
      <sprite scale={node.halo * (hot ? 1.22 : 1)}>
        <spriteMaterial
          map={glow} color={node.color} transparent
          opacity={node.haloOpacity * (hot ? 1.5 : 1)}
          depthWrite={false} toneMapped={false}
        />
      </sprite>
      {/* lit core — gentle dimensional shading reads as precise, not flat */}
      <mesh scale={hot ? 1.3 : 1}>
        <sphereGeometry args={[node.coreR, 32, 32]} />
        <meshStandardMaterial
          color={node.color} emissive={node.color}
          emissiveIntensity={EMISSIVE[node.kind] * (hot ? 1.6 : 1)}
          roughness={0.5} metalness={0} toneMapped={false}
        />
      </mesh>
      {/* invisible, larger hit target for easy hover */}
      <mesh
        onPointerOver={(e) => {
          e.stopPropagation();
          setHot(true);
          onHover(node);
          document.body.style.cursor = "pointer";
        }}
        onPointerOut={() => {
          setHot(false);
          onHover(null);
          document.body.style.cursor = "auto";
        }}
      >
        <sphereGeometry args={[node.hitR, 8, 8]} />
        <meshBasicMaterial transparent opacity={0} depthWrite={false} />
      </mesh>
    </group>
  );
}

function Scene({ facts, onHover, reduced }: {
  facts: MemoryFact[];
  onHover: (n: MemoryNode | null) => void;
  reduced: boolean;
}) {
  const glow = useMemo(makeGlow, []);
  useEffect(() => () => glow.dispose(), [glow]);

  const graph = useMemo(() => buildGraph(facts), [facts]);
  const edgePos = useMemo(() => {
    const map = new Map(graph.nodes.map((n) => [n.id, n.pos]));
    const arr = new Float32Array(graph.edges.length * 6);
    graph.edges.forEach(([a, b], i) => {
      const pa = map.get(a), pb = map.get(b);
      if (pa && pb) arr.set([...pa, ...pb], i * 6);
    });
    return arr;
  }, [graph]);

  return (
    <>
      {/* subtle depth — distant nodes recede into the void */}
      <fog attach="fog" args={["#050507", 11, 26]} />
      <ambientLight intensity={0.7} />
      <directionalLight position={[4, 6, 5]} intensity={0.7} />
      <directionalLight position={[-5, -2, -3]} intensity={0.35} color="#e3c9a8" />

      <OrbitControls
        enablePan={false}
        autoRotate={!reduced}
        autoRotateSpeed={0.16}
        enableDamping
        dampingFactor={0.08}
        rotateSpeed={0.6}
        minDistance={5}
        maxDistance={22}
      />

      {edgePos.length > 0 && (
        <lineSegments key={edgePos.length}>
          <bufferGeometry>
            <bufferAttribute attach="attributes-position" args={[edgePos, 3]} />
          </bufferGeometry>
          <lineBasicMaterial color={EDGE} transparent opacity={0.22} depthWrite={false} toneMapped={false} />
        </lineSegments>
      )}

      {graph.nodes.map((n) => (
        <Node key={n.id} node={n} glow={glow} onHover={onHover} />
      ))}
    </>
  );
}

export default function MemoryGalaxy({ facts, onHover }: {
  facts: MemoryFact[];
  onHover: (n: MemoryNode | null) => void;
}) {
  const reduced = usePrefersReducedMotion();
  return (
    <Canvas
      gl={{ antialias: true, alpha: true, powerPreference: "high-performance" }}
      dpr={[1, 1.8]}
      camera={{ position: [0, 1.2, 12.5], fov: 46 }}
      style={{ background: "transparent" }}
    >
      <Scene facts={facts} onHover={onHover} reduced={reduced} />
    </Canvas>
  );
}
