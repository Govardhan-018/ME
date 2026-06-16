/**
 * Geometry for the AI Core — a neural cloud, not a sphere.
 * Nodes are distributed on a noisy shell plus an interior volume, then linked
 * to their nearest neighbours to form data pathways. All pure math so it can be
 * memoised once and handed to the GPU.
 */

export interface CoreGeometryData {
  positions: Float32Array; // node xyz
  seeds: Float32Array; // per-node randomness
  scales: Float32Array; // per-node base size
  radii: Float32Array; // normalized radius 0(inner)→1(outer) for staged activation
  lines: Float32Array; // neighbour segment endpoints (pairs of xyz)
  nodeCount: number;
  lineCount: number;
}

export interface StreamData {
  dirs: Float32Array; // unit directions (used as position; shader scales by radius)
  seeds: Float32Array;
  speeds: Float32Array;
  count: number;
}

const CORE_RADIUS = 1.7;

export function buildCoreGeometry(nodeCount: number, links: number): CoreGeometryData {
  const positions = new Float32Array(nodeCount * 3);
  const seeds = new Float32Array(nodeCount);
  const scales = new Float32Array(nodeCount);
  const radii = new Float32Array(nodeCount);

  const golden = Math.PI * (3 - Math.sqrt(5));

  for (let i = 0; i < nodeCount; i++) {
    let x: number, y: number, z: number, r: number;

    if (i % 10 < 7) {
      // shell — fibonacci sphere with organic noise
      const t = i / nodeCount;
      const inc = Math.acos(1 - 2 * t);
      const az = golden * i;
      r = CORE_RADIUS * (1 + (Math.random() - 0.5) * 0.34);
      x = Math.sin(inc) * Math.cos(az) * r;
      y = Math.sin(inc) * Math.sin(az) * r;
      z = Math.cos(inc) * r;
    } else {
      // interior volume
      r = CORE_RADIUS * Math.cbrt(Math.random()) * 0.9;
      const theta = Math.random() * Math.PI * 2;
      const phi = Math.acos(2 * Math.random() - 1);
      x = Math.sin(phi) * Math.cos(theta) * r;
      y = Math.sin(phi) * Math.sin(theta) * r;
      z = Math.cos(phi) * r;
    }

    positions[i * 3] = x;
    positions[i * 3 + 1] = y;
    positions[i * 3 + 2] = z;
    seeds[i] = Math.random();
    scales[i] = 0.5 + Math.random() * Math.random() * 2.6; // mostly small, a few large
    radii[i] = Math.min(1, r / CORE_RADIUS);
  }

  // nearest-neighbour links → neural pathways
  const seen = new Set<number>();
  const linePts: number[] = [];

  for (let i = 0; i < nodeCount; i++) {
    const ax = positions[i * 3];
    const ay = positions[i * 3 + 1];
    const az = positions[i * 3 + 2];
    const best: Array<{ j: number; d: number }> = [];

    for (let j = 0; j < nodeCount; j++) {
      if (j === i) continue;
      const dx = ax - positions[j * 3];
      const dy = ay - positions[j * 3 + 1];
      const dz = az - positions[j * 3 + 2];
      const d = dx * dx + dy * dy + dz * dz;
      if (best.length < links) {
        best.push({ j, d });
        best.sort((p, q) => p.d - q.d);
      } else if (d < best[best.length - 1].d) {
        best[best.length - 1] = { j, d };
        best.sort((p, q) => p.d - q.d);
      }
    }

    for (const b of best) {
      const key = i < b.j ? i * nodeCount + b.j : b.j * nodeCount + i;
      if (seen.has(key)) continue;
      seen.add(key);
      linePts.push(ax, ay, az, positions[b.j * 3], positions[b.j * 3 + 1], positions[b.j * 3 + 2]);
    }
  }

  return {
    positions,
    seeds,
    scales,
    radii,
    lines: new Float32Array(linePts),
    nodeCount,
    lineCount: linePts.length / 6,
  };
}

export function buildStreams(count: number): StreamData {
  const dirs = new Float32Array(count * 3);
  const seeds = new Float32Array(count);
  const speeds = new Float32Array(count);

  for (let i = 0; i < count; i++) {
    const theta = Math.random() * Math.PI * 2;
    const phi = Math.acos(2 * Math.random() - 1);
    dirs[i * 3] = Math.sin(phi) * Math.cos(theta);
    dirs[i * 3 + 1] = Math.sin(phi) * Math.sin(theta);
    dirs[i * 3 + 2] = Math.cos(phi);
    seeds[i] = Math.random();
    speeds[i] = 0.6 + Math.random() * 0.9;
  }

  return { dirs, seeds, speeds, count };
}

/** The five narrative stages the Core moves through on scroll. */
export const STAGES = [
  { id: "awareness", label: "Awareness" },
  { id: "memory", label: "Memory" },
  { id: "reasoning", label: "Reasoning" },
  { id: "action", label: "Action" },
  { id: "autonomy", label: "Autonomy" },
] as const;
