/**
 * Client for the JARVIS Agent Core (the Python brain).
 * Mirrors the contract used by the Electron HUD's conductor.ts.
 *   POST /api/chat {command}      -> {status,domain,result,answer,error}
 *   GET  /api/health
 *   GET  /api/voice/state
 *   GET  /api/skills              + POST /api/skills/{approve,discard}
 *   POST /api/voice/transcribe    (raw audio body) -> {text}
 * CORS on the core is "*", so this site talks to it cross-origin.
 */
const BASE = (process.env.NEXT_PUBLIC_JARVIS_API ?? "http://127.0.0.1:8000").replace(
  /\/$/,
  "",
);

export interface ChatResult {
  answer: string;
  domain: string;
  error: string | null;
}

interface RawChat {
  status?: string;
  domain?: string;
  result?: Record<string, unknown> | null;
  answer?: string | null;
  error?: string | null;
}

export async function chat(command: string): Promise<ChatResult> {
  const res = await fetch(`${BASE}/api/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ command }),
  });
  if (!res.ok) throw new Error(`Core returned ${res.status}`);
  const data: RawChat = await res.json();

  let answer = data.answer ?? "";
  if (!answer && data.result) {
    const synthesis = (data.result as { synthesis?: { answer?: string } }).synthesis;
    answer =
      synthesis?.answer ??
      "I executed the command. Raw result:\n" + JSON.stringify(data.result, null, 2);
  }
  if (data.error) answer = `Error: ${data.error}`;

  return { answer: answer || "Done.", domain: data.domain ?? "general", error: data.error ?? null };
}

export async function health(): Promise<boolean> {
  try {
    const ctrl = new AbortController();
    const t = setTimeout(() => ctrl.abort(), 2500);
    const res = await fetch(`${BASE}/api/health`, { signal: ctrl.signal });
    clearTimeout(t);
    return res.ok;
  } catch {
    return false;
  }
}

export interface VoiceState {
  state: string;
  running?: boolean;
  enabled?: boolean;
  wake_phrase?: string;
  user_text?: string;
  answer_text?: string;
  answer_domain?: string;
  answer_turn?: number;
}

export async function voiceState(): Promise<VoiceState | null> {
  try {
    const res = await fetch(`${BASE}/api/voice/state`);
    if (!res.ok) return null;
    return (await res.json()) as VoiceState;
  } catch {
    return null;
  }
}

export interface Faculty {
  name: string;
  label: string;
  tier: string;
  description: string;
}

export interface SkillsData {
  builtin?: Faculty[];
  skills: unknown[];
  staged: unknown[];
}

export async function getSkills(): Promise<SkillsData> {
  const res = await fetch(`${BASE}/api/skills`);
  if (!res.ok) throw new Error("skills unavailable");
  return (await res.json()) as SkillsData;
}

export interface MemoryFact {
  id?: number;
  subject?: string | null;
  fact: string;
  confidence?: number;
  source?: string | null;
  created_at?: string;
  last_seen?: string;
}

export interface MemoryData {
  facts: MemoryFact[];
  recent: { role: string; content: string; domain?: string }[];
}

export async function getMemory(): Promise<MemoryData> {
  const res = await fetch(`${BASE}/api/memory`);
  if (!res.ok) throw new Error("memory unavailable");
  const d = (await res.json()) as Partial<MemoryData>;
  return { facts: d.facts ?? [], recent: d.recent ?? [] };
}

export async function skillAction(action: "approve" | "discard", name: string): Promise<void> {
  await fetch(`${BASE}/api/skills/${action}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name }),
  });
}

export async function transcribe(blob: Blob): Promise<string> {
  try {
    const res = await fetch(`${BASE}/api/voice/transcribe`, { method: "POST", body: blob });
    if (!res.ok) return "";
    const data = (await res.json()) as { text?: string, error?: string };
    if (data.error) console.error("Transcribe error:", data.error);
    return data.text ?? "";
  } catch (e) {
    console.error("Transcribe fetch error:", e);
    return "";
  }
}

export async function tts(text: string): Promise<void> {
  try {
    const res = await fetch(`${BASE}/api/voice/tts`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text }),
    });
    if (!res.ok) {
      console.error("TTS failed with status", res.status);
      return;
    }
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const audio = new Audio(url);
    audio.play().catch(e => console.error("Audio playback blocked/failed:", e));
  } catch (e) {
    console.error("TTS fetch error:", e);
  }
}

// --------------------------------------------------------------------------- //
// Integrated OS — calendar, proactive feed, schedules, autonomy, observability
// --------------------------------------------------------------------------- //
export interface CalEvent {
  id: string;
  title: string;
  start_ts: string;
  end_ts: string | null;
  all_day?: number;
  location?: string | null;
}

export interface FeedItem {
  id: string;
  kind: string;
  title: string;
  body: string;
  status: string;
  confirmation_id: string | null;
  created_at: string;
}

export interface Schedule {
  id: string;
  name: string;
  kind: string;
  trigger: string;
  enabled: number;
  next_run: string | null;
  last_status: string | null;
}

export interface Pending {
  confirmation_id: string;
  tool: string;
  action: string;
  risk_tier: string;
  summary: string;
}

export interface SystemSnapshot {
  mode: string;
  pending: Pending[];
  calendar: { today: CalEvent[]; free_today: { start: string; end: string }[] };
  feed: { items: FeedItem[]; unread: number };
  schedules: Schedule[];
  plans: { id: string; goal: string; status: string }[];
  observability: {
    turns: number;
    errors: number;
    error_rate: number;
    by_domain: Record<string, number>;
    by_actor: Record<string, number>;
    latency_ms: { avg: number; p50: number; p95: number; max: number };
  };
}

export async function systemSnapshot(): Promise<SystemSnapshot | null> {
  try {
    const res = await fetch(`${BASE}/api/system`);
    if (!res.ok) return null;
    return (await res.json()) as SystemSnapshot;
  } catch {
    return null;
  }
}

async function post(path: string, body?: unknown): Promise<void> {
  await fetch(`${BASE}${path}`, {
    method: "POST",
    headers: body ? { "Content-Type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
}

export const setMode = (mode: string) => post("/api/gateway/mode", { mode });
export const gatewayApprove = (id: string) =>
  post("/api/gateway/approve", { confirmation_id: id });
export const gatewayDeny = (id: string) =>
  post("/api/gateway/deny", { confirmation_id: id });
export const runBrief = () => post("/api/proactive/brief");
export const runSchedule = (sid: string) =>
  post(`/api/proactive/schedules/${sid}/run`);
export const toggleSchedule = (sid: string, enabled: boolean) =>
  post(`/api/proactive/schedules/${sid}/toggle?enabled=${enabled}`);
export const markFeedRead = (id: string) =>
  post(`/api/proactive/feed/${id}/read`);

export function fmtTime(iso: string | null): string {
  if (!iso) return "";
  const d = new Date(iso.length <= 16 ? iso : iso);
  if (Number.isNaN(d.getTime())) return iso.slice(11, 16);
  return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

export function describeTrigger(t: string): string {
  const daily = /^daily@(\d{1,2}):(\d{2})$/i.exec(t);
  if (daily) return `daily ${daily[1].padStart(2, "0")}:${daily[2]}`;
  const every = /^every@(\d+)\s*([smh])$/i.exec(t);
  if (every) {
    const u = { s: "sec", m: "min", h: "hr" }[every[2].toLowerCase()] ?? every[2];
    return `every ${every[1]} ${u}`;
  }
  return "manual";
}

export function skillName(s: unknown): string {
  if (typeof s === "string") return s;
  const o = s as { name?: string; skill?: string; id?: string };
  return o?.name ?? o?.skill ?? o?.id ?? "unnamed";
}

export function skillDesc(s: unknown): string {
  if (typeof s === "string") return "";
  const o = s as { description?: string; doc?: string; summary?: string };
  return o?.description ?? o?.doc ?? o?.summary ?? "";
}
