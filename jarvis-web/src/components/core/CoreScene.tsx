"use client";

import { useEffect, useMemo, useRef } from "react";
import { useFrame } from "@react-three/fiber";
import * as THREE from "three";
import type { MotionValue } from "framer-motion";
import { buildCoreGeometry, buildStreams } from "./coreConfig";
import type { PerfProfile } from "@/lib/perf";
import { lerp } from "@/lib/utils";

/* ── shaders ──────────────────────────────────────────────────────────── */
const NODE_VERT = /* glsl */ `
  attribute float aSeed;
  attribute float aScale;
  attribute float aRadius;
  uniform float uTime;
  uniform float uLevel;     // 0..4 activity
  uniform vec2  uPointer;
  uniform float uPixelRatio;
  varying float vBright;

  void main() {
    vec3 pos = position;
    pos += 0.04 * vec3(
      sin(uTime * 0.5 + aSeed * 6.2831),
      cos(uTime * 0.4 + aSeed * 5.0),
      sin(uTime * 0.6 + aSeed * 4.0)
    );

    vec4 mv = modelViewMatrix * vec4(pos, 1.0);
    gl_Position = projectionMatrix * mv;

    float sn = uLevel / 4.0;
    float activate = smoothstep(aRadius - 0.15, aRadius + 0.25, sn + 0.15);
    float twinkle = 0.5 + 0.5 * sin(uTime * (1.0 + aSeed * 2.0) + aSeed * 30.0);
    float base = mix(0.2, 0.5, sn);
    float bright = base + activate * (0.35 + 0.65 * twinkle);

    vec2 ndc = gl_Position.xy / max(gl_Position.w, 0.001);
    bright += smoothstep(0.4, 0.0, distance(ndc, uPointer)) * 0.5;

    vBright = bright;

    float size = aScale * (0.42 + 0.62 * sn) * (1.0 + activate * 0.5);
    gl_PointSize = size * uPixelRatio * (74.0 / max(-mv.z, 0.1));
  }
`;

const NODE_FRAG = /* glsl */ `
  uniform vec3 uColorBase;
  uniform vec3 uColorAccent;
  uniform float uLevel;
  varying float vBright;

  void main() {
    float d = length(gl_PointCoord - 0.5);
    float a = smoothstep(0.5, 0.0, d);
    a = pow(a, 1.5);
    if (a < 0.01) discard;
    float sn = uLevel / 4.0;
    float mixv = clamp(vBright - 0.4, 0.0, 1.0) * (0.4 + 0.6 * sn);
    vec3 col = mix(uColorBase, uColorAccent, mixv);
    gl_FragColor = vec4(col * (0.6 + vBright), a * clamp(vBright, 0.12, 1.4));
  }
`;

const STREAM_VERT = /* glsl */ `
  attribute float aSeed;
  attribute float aSpeed;
  uniform float uTime;
  uniform float uRin;
  uniform float uRout;
  uniform float uFlowDir;
  uniform float uFlowAmt;
  uniform float uPixelRatio;
  varying float vA;

  void main() {
    float phase = fract(aSeed + uTime * aSpeed * 0.13);
    float rIn = mix(uRout, uRin, phase);
    float rOut = mix(uRin, uRout, phase);
    float r = mix(rIn, rOut, step(0.0, uFlowDir));
    vec3 pos = normalize(position) * r;

    vec4 mv = modelViewMatrix * vec4(pos, 1.0);
    gl_Position = projectionMatrix * mv;

    float edge = sin(phase * 3.14159);
    vA = edge * uFlowAmt;
    gl_PointSize = (1.1 + aSpeed) * uPixelRatio * (84.0 / max(-mv.z, 0.1)) * step(0.001, vA);
  }
`;

const STREAM_FRAG = /* glsl */ `
  uniform vec3 uColor;
  varying float vA;

  void main() {
    float d = length(gl_PointCoord - 0.5);
    float a = smoothstep(0.5, 0.0, d);
    if (a * vA < 0.01) discard;
    gl_FragColor = vec4(uColor, a * vA * 0.9);
  }
`;

interface CoreSceneProps {
  /** 0..4 activity level (idle→responding) */
  level: MotionValue<number>;
  /** -1 inbound … +1 outbound data flow; magnitude = amount */
  flow: MotionValue<number>;
  perf: PerfProfile;
  reduced: boolean;
}

export function CoreScene({ level, flow, perf, reduced }: CoreSceneProps) {
  const built = useMemo(() => {
    const geo = buildCoreGeometry(perf.nodes, perf.links);
    const str = buildStreams(perf.streams);

    const nodeGeom = new THREE.BufferGeometry();
    nodeGeom.setAttribute("position", new THREE.BufferAttribute(geo.positions, 3));
    nodeGeom.setAttribute("aSeed", new THREE.BufferAttribute(geo.seeds, 1));
    nodeGeom.setAttribute("aScale", new THREE.BufferAttribute(geo.scales, 1));
    nodeGeom.setAttribute("aRadius", new THREE.BufferAttribute(geo.radii, 1));

    const nodeMat = new THREE.ShaderMaterial({
      vertexShader: NODE_VERT,
      fragmentShader: NODE_FRAG,
      transparent: true,
      depthWrite: false,
      blending: THREE.AdditiveBlending,
      uniforms: {
        uTime: { value: 0 },
        uLevel: { value: 1.15 },
        uPointer: { value: new THREE.Vector2(0, 0) },
        uPixelRatio: { value: 1.5 },
        uColorBase: { value: new THREE.Color("#8093a6") },
        uColorAccent: { value: new THREE.Color("#38e8ff") },
      },
    });
    const nodes = new THREE.Points(nodeGeom, nodeMat);

    const lineGeom = new THREE.BufferGeometry();
    lineGeom.setAttribute("position", new THREE.BufferAttribute(geo.lines, 3));
    const lineMat = new THREE.LineBasicMaterial({
      color: new THREE.Color("#5a6f82"),
      transparent: true,
      opacity: 0.07,
      depthWrite: false,
      blending: THREE.AdditiveBlending,
    });
    const lines = new THREE.LineSegments(lineGeom, lineMat);

    const streamGeom = new THREE.BufferGeometry();
    streamGeom.setAttribute("position", new THREE.BufferAttribute(str.dirs, 3));
    streamGeom.setAttribute("aSeed", new THREE.BufferAttribute(str.seeds, 1));
    streamGeom.setAttribute("aSpeed", new THREE.BufferAttribute(str.speeds, 1));
    const streamMat = new THREE.ShaderMaterial({
      vertexShader: STREAM_VERT,
      fragmentShader: STREAM_FRAG,
      transparent: true,
      depthWrite: false,
      blending: THREE.AdditiveBlending,
      uniforms: {
        uTime: { value: 0 },
        uRin: { value: 0.2 },
        uRout: { value: 3.4 },
        uFlowDir: { value: -1 },
        uFlowAmt: { value: 0 },
        uPixelRatio: { value: 1.5 },
        uColor: { value: new THREE.Color("#38e8ff") },
      },
    });
    const streams = new THREE.Points(streamGeom, streamMat);

    const group = new THREE.Group();
    group.add(lines, nodes, streams);
    group.scale.setScalar(0.7);

    return { group, nodeMat, lineMat, streamMat, nodeGeom, lineGeom, streamGeom };
  }, [perf.nodes, perf.streams, perf.links]);

  useEffect(() => {
    const b = built;
    return () => {
      b.nodeGeom.dispose();
      b.lineGeom.dispose();
      b.streamGeom.dispose();
      b.nodeMat.dispose();
      b.lineMat.dispose();
      b.streamMat.dispose();
    };
  }, [built]);

  const pointerTarget = useRef({ x: 0, y: 0 });
  const pointer = useRef({ x: 0, y: 0 });
  useEffect(() => {
    const onMove = (e: PointerEvent) => {
      pointerTarget.current.x = (e.clientX / window.innerWidth) * 2 - 1;
      pointerTarget.current.y = -((e.clientY / window.innerHeight) * 2 - 1);
    };
    window.addEventListener("pointermove", onMove, { passive: true });
    return () => window.removeEventListener("pointermove", onMove);
  }, []);

  const time = useRef(0);
  const shownLevel = useRef(1.15);
  const shownFlow = useRef(0);
  const spin = useRef(0);

  useFrame((state, delta) => {
    const d = Math.min(delta, 0.05);
    const ease = 1 - Math.pow(0.0015, d);
    const dpr = state.gl.getPixelRatio();
    const { group, nodeMat, lineMat, streamMat } = built;

    time.current += reduced ? 0 : d;
    shownLevel.current = lerp(shownLevel.current, level.get(), reduced ? 1 : ease);
    shownFlow.current = lerp(shownFlow.current, flow.get(), reduced ? 1 : ease);
    const lv = shownLevel.current;
    const sn = lv / 4;

    pointer.current.x = lerp(pointer.current.x, pointerTarget.current.x, ease);
    pointer.current.y = lerp(pointer.current.y, pointerTarget.current.y, ease);

    nodeMat.uniforms.uTime.value = time.current;
    nodeMat.uniforms.uLevel.value = lv;
    nodeMat.uniforms.uPixelRatio.value = dpr;
    (nodeMat.uniforms.uPointer.value as THREE.Vector2).set(pointer.current.x, pointer.current.y);

    streamMat.uniforms.uTime.value = time.current;
    streamMat.uniforms.uPixelRatio.value = dpr;
    streamMat.uniforms.uFlowDir.value = shownFlow.current >= 0 ? 1 : -1;
    streamMat.uniforms.uFlowAmt.value = Math.min(1, Math.abs(shownFlow.current));

    lineMat.opacity = 0.08 + sn * 0.16;

    spin.current += reduced ? 0 : d * 0.05;
    group.rotation.y = spin.current + pointer.current.x * 0.3;
    group.rotation.x = lerp(group.rotation.x, -pointer.current.y * 0.2, ease);
    const targetScale = 0.62 + sn * 0.26;
    group.scale.setScalar(lerp(group.scale.x, targetScale, ease));
  });

  return <primitive object={built.group} />;
}
