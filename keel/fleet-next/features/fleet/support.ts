"use client";

// Fleet feature-local support: real response shapes, honest derivations and
// small hooks. Everything here is derived from data returned by the bridge;
// nothing is invented. Evidence for the shapes is in keel/src/keel/fleet/
// (db.py schema, service.py projections, routes.py dispatch) and the classic
// reference UI at keel/desktop/fleet/fleet.js.

import React, { useCallback, useEffect, useRef, useState } from "react";
import { subscribeEvents, isBridgeUnavailable } from "@/lib/api";
import type { Bot, BotRow, FleetEvent, FleetTask, LibraryItem, Routine } from "@/lib/types";

/* ------------------------------------------------------------------ types */

export interface GroupMember {
  id: string;
  name?: string;
  role?: string;
  engine?: string;
  provider?: string;
  model?: string;
  avatar_hue?: number;
  [key: string]: unknown;
}
export interface FleetGroup {
  id: string;
  name?: string;
  members?: GroupMember[];
  created_at?: string;
  updated_at?: string;
  [key: string]: unknown;
}
export interface GroupRow {
  seq?: number;
  group_id?: string;
  author?: string;
  kind?: string;
  body?: Record<string, unknown>;
  created_at?: string;
  [key: string]: unknown;
}
export interface Policy {
  bot_id?: string;
  tool_name?: string;
  decision?: string;
  created_at?: string;
  updated_at?: string;
  [key: string]: unknown;
}
export interface AuditEntry {
  id?: number;
  bot_id?: string;
  tool_name?: string;
  fingerprint?: string;
  event?: string;
  decision?: string | null;
  outcome?: string | null;
  approval_id?: string;
  created_at?: string;
  [key: string]: unknown;
}
export interface RoutineRun {
  id?: number;
  routine_id?: string;
  task_id?: string | null;
  scheduled_at?: string;
  started_at?: string | null;
  finished_at?: string | null;
  status?: string;
  summary?: string;
  error?: string;
  created_at?: string;
  [key: string]: unknown;
}
export interface TaskEvent {
  id?: number;
  task_id?: string;
  actor?: string;
  event?: string;
  from_status?: string | null;
  to_status?: string | null;
  note?: string;
  created_at?: string;
  [key: string]: unknown;
}

/* ------------------------------------------------------------- normalisers */

/** Fleet list endpoints return wrapped objects ({bots}, {tasks}, ...). */
export function wrapped<T>(value: T[] | Record<string, unknown> | null | undefined, key: string): T[] {
  if (Array.isArray(value)) return value;
  if (value && Array.isArray(value[key])) return value[key] as T[];
  return [];
}
/** Mutation routes return `{bot|task|group|routine|file: ...}`; tolerate that shape. */
export function unwrap<T>(value: unknown, key: string): T {
  if (value && typeof value === "object" && (value as Record<string, unknown>)[key] != null) {
    return (value as Record<string, unknown>)[key] as T;
  }
  return value as T;
}
export function text(value: unknown, fallback = ""): string {
  return typeof value === "string" ? value : value == null ? fallback : String(value);
}
export function number(value: unknown, fallback = 0): number {
  const n = typeof value === "number" ? value : Number(value);
  return Number.isFinite(n) ? n : fallback;
}

export function fmtDate(value?: string | number | null): string {
  if (value === undefined || value === null || value === "") return "—";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleString(undefined, {
    year: "numeric", month: "short", day: "numeric",
    hour: "2-digit", minute: "2-digit",
  });
}
export function fmtElapsed(ms: number): string {
  const sec = Math.max(0, Math.floor(ms / 1000));
  if (sec < 60) return `${sec}s`;
  const min = Math.floor(sec / 60);
  if (min < 60) return `${min}m ${sec % 60}s`;
  return `${Math.floor(min / 60)}h ${min % 60}m`;
}
export function since(value?: string | number | null, now = Date.now()): number | null {
  if (value === undefined || value === null || value === "") return null;
  const t = typeof value === "number" ? value : new Date(value).getTime();
  return Number.isFinite(t) ? Math.max(0, now - t) : null;
}
export function fmtBytes(n: number): string {
  if (!Number.isFinite(n) || n <= 0) return "0 B";
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / (1024 * 1024)).toFixed(1)} MB`;
}

/** Audit rows and approval summaries must never surface credential-looking text. */
export function redact(value: unknown): string {
  let s = text(value);
  s = s.replace(/sk-[A-Za-z0-9_-]{8,}/g, "sk-••••");
  s = s.replace(/Bearer\s+[A-Za-z0-9._-]{8,}/gi, "Bearer ••••");
  s = s.replace(/(api[_-]?key|token|secret|password|authorization)\s*[:=]\s*\S+/gi, "$1=••••");
  return s;
}

export type Tone = "neutral" | "success" | "warning" | "danger" | "info" | "accent";
export function statusTone(status?: string): Tone {
  const s = text(status).toLowerCase();
  if (["completed", "done", "approved", "success", "granted", "executed", "enabled"].includes(s)) return "success";
  if (["pending", "waiting", "awaiting_approval", "running", "in_progress", "queued", "requested"].includes(s)) return "warning";
  if (["failed", "error", "denied", "refused", "cancelled", "timeout", "never"].includes(s)) return "danger";
  if (["paused", "expired", "skipped_missed", "disabled", "stale"].includes(s)) return "neutral";
  return "neutral";
}

/* ---------------------------------------------------------- live activity  */

export interface ActivityView {
  state: "working" | "waiting" | "idle" | "failed" | "unknown";
  phrase: string;
  detail?: string;
  elapsedMs: number | null;
  openSteps: number;
  pendingApproval?: { id: string; tool: string; scope?: string; detail?: string };
  pendingAsk?: { id: string; question: string };
  lastTurn?: { endedAt?: string; durationMs?: number; steps?: number; reason?: string };
  lastAt?: string;
}

/**
 * Derive one honest activity line from persisted rows + live SSE events.
 * The bridge has no bots.state column: "working" exists only while a real
 * `step` row with status=running is open, and "waiting for you" only when a
 * real pending approval/ask row is present.
 */
export function deriveActivity(
  rows: BotRow[],
  events: FleetEvent[],
  now: number,
  engine?: string,
): ActivityView {
  const all = [
    ...rows.map((r) => ({ kind: text(r.kind), body: r.body ?? {}, ts: r.ts, created: (r as Record<string, unknown>).created_at })),
    ...events.map((e) => ({ kind: text(e.kind ?? e.type), body: e.body ?? {}, ts: e.ts, created: (e as Record<string, unknown>).created_at })),
  ].filter((r) => ["step", "approval", "ask", "turn_end", "message", "notice", "stream"].includes(r.kind));

  let openSteps = 0;
  let lastRunning: { name?: string; detail?: string; ts?: string | number } | undefined;
  let lastError: string | undefined;
  let approval: ActivityView["pendingApproval"];
  let ask: ActivityView["pendingAsk"];
  let lastTurn: ActivityView["lastTurn"];
  let lastAt: string | undefined;
  let lastMessage: string | undefined;
  let lastNotice: string | undefined;

  for (const r of all) {
    const b = r.body as Record<string, unknown>;
    const at = text(r.created ?? r.ts);
    if (at) lastAt = at;
    if (r.kind === "step") {
      const st = text(b.status);
      if (st === "running") {
        openSteps += 1;
        lastRunning = { name: text(b.name) || "tool call", detail: text(b.detail).slice(0, 160), ts: text(r.created ?? r.ts) || undefined };
      } else if (st === "error" || st === "failed") {
        lastError = text(b.detail || b.name || "a tool call failed");
      }
    } else if (r.kind === "approval") {
      if (text(b.status) === "pending") {
        approval = {
          id: text(b.approval_id),
          tool: text(b.tool_name || b.tool || "tool"),
          scope: text(b.scope) || undefined,
          detail: redact(b.args_summary || b.explanation),
        };
      }
    } else if (r.kind === "ask") {
      if (text(b.status) === "pending" || b.answer === undefined) {
        ask = { id: text(b.ask_id ?? b.id), question: text(b.question || b.text).slice(0, 200) };
      }
    } else if (r.kind === "turn_end") {
      lastTurn = {
        endedAt: at || undefined,
        durationMs: number(b.duration_ms, 0),
        steps: number(b.num_steps, 0),
        reason: text(b.terminal_reason) || undefined,
      };
      openSteps = 0;
    } else if (r.kind === "message" && text(b.role) === "assistant") {
      lastMessage = text(b.content).slice(0, 140);
    } else if (r.kind === "notice") {
      lastNotice = text(b.text).slice(0, 140);
    }
  }

  const scripted = text(engine).toLowerCase() === "echo";
  const prefix = scripted ? "Scripted (Echo) · " : "";
  if (approval) {
    return {
      state: "waiting",
      phrase: `${prefix}Waiting for your decision on ${approval.tool}`,
      detail: approval.detail || "Approval requested by this agent",
      elapsedMs: lastAt ? since(lastAt, now) : null,
      openSteps, pendingApproval: approval, lastTurn, lastAt,
    };
  }
  if (ask) {
    return {
      state: "waiting",
      phrase: `${prefix}Waiting for your answer`,
      detail: ask.question,
      elapsedMs: lastAt ? since(lastAt, now) : null,
      openSteps, pendingAsk: ask, lastTurn, lastAt,
    };
  }
  if (openSteps > 0) {
    return {
      state: "working",
      phrase: `${prefix}${lastRunning?.name || "Working"}`,
      detail: lastRunning?.detail,
      elapsedMs: lastRunning ? since(lastRunning.ts, now) : null,
      openSteps, lastTurn, lastAt,
    };
  }
  if (lastError) {
    return { state: "failed", phrase: `${prefix}A tool call failed`, detail: lastError, elapsedMs: null, openSteps, lastTurn, lastAt };
  }
  if (lastTurn) {
    return {
      state: "idle",
      phrase: `${prefix}Turn complete${lastTurn.steps ? ` · ${lastTurn.steps} steps` : ""}`,
      detail: lastTurn.reason || (lastMessage ? redact(lastMessage) : lastNotice),
      elapsedMs: lastTurn.endedAt ? since(lastTurn.endedAt, now) : null,
      openSteps, lastTurn, lastAt,
    };
  }
  return {
    state: "unknown",
    phrase: scripted ? "Scripted (Echo) agent — no run reported" : "No activity reported by bridge",
    detail: undefined, elapsedMs: null, openSteps, lastAt,
  };
}

export function activityTone(state: ActivityView["state"]): Tone {
  if (state === "working") return "info";
  if (state === "waiting") return "warning";
  if (state === "failed") return "danger";
  if (state === "idle") return "success";
  return "neutral";
}

/** Delegation links are real row fields (`delegated_to` / `delegated_from`). */
export interface DelegationLink {
  from: string;
  to: string;
  toId?: string;
  ok: boolean;
  detail?: string;
  ts?: string;
}
export function delegations(rows: BotRow[], bots: Bot[]): DelegationLink[] {
  const out: DelegationLink[] = [];
  for (const r of rows) {
    const b = (r.body ?? {}) as Record<string, unknown>;
    if (text(b.name) !== "send_to_bot") continue;
    const d = (b.delegated ?? b.delegation ?? {}) as Record<string, unknown>;
    if (!d || !Object.keys(d).length) continue;
    const to = text(d.to ?? d.to_id);
    if (!to) continue;
    const target = bots.find((x) => x.id === d.to_id || x.name === d.to);
    out.push({
      from: text(d.from ?? d.from_id) || "this agent",
      to: target?.name || to,
      toId: target?.id,
      ok: d.ok !== false,
      detail: redact(d.detail || d.reply),
      ts: text((r as Record<string, unknown>).created_at ?? r.ts) || undefined,
    });
  }
  return out;
}

/* ------------------------------------------------------------------ hooks */

/** Ticking clock for elapsed labels; pauses while the document is hidden. */
export function useNow(intervalMs = 1000): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const id = window.setInterval(() => {
      if (!document.hidden) setNow(Date.now());
    }, intervalMs);
    return () => window.clearInterval(id);
  }, [intervalMs]);
  return now;
}

export interface Resource<T> {
  data: T | null;
  error: unknown;
  loading: boolean;
  unavailable: boolean;
  reload: () => void;
  setData: React.Dispatch<React.SetStateAction<T | null>>;
}

/** Load one bridge resource with loading/error/unavailable states + retry. */
export function useBridgeResource<T>(load: () => Promise<T>, deps: React.DependencyList): Resource<T> {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [loading, setLoading] = useState(true);
  const [nonce, setNonce] = useState(0);
  const loadRef = useRef(load);
  loadRef.current = load;
  const depsRef = useRef(deps);
  depsRef.current = deps;
  const key = JSON.stringify(deps);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    setError(null);
    loadRef.current()
      .then((v) => { if (alive) setData(v); })
      .catch((e) => { if (alive) setError(e); })
      .finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, nonce]);

  return {
    data, error, loading,
    unavailable: error ? isBridgeUnavailable(error) : false,
    reload: useCallback(() => setNonce((n) => n + 1), []),
    setData,
  };
}

/**
 * SSE subscription. `subscribeEvents` handles unnamed frames; the bridge also
 * emits named `event: row` frames (routes.py:1748), so a second listener is
 * registered for those. Both are cleaned up. A failed stream is reported so
 * callers can show an honest stale/offline state and retry.
 */
export function useFleetEvents(onEvent: (e: MessageEvent) => void): { streamError: boolean; retry: () => void } {
  const [streamError, setStreamError] = useState(false);
  const [nonce, setNonce] = useState(0);
  const handler = useRef(onEvent);
  handler.current = onEvent;

  useEffect(() => {
    let alive = true;
    const fire = (e: MessageEvent) => { if (alive) handler.current(e); };
    const onErr = () => { if (alive) setStreamError(true); };
    const unsub = subscribeEvents(fire, onErr);
    const es = new EventSource("/api/bridge/events");
    const rowHandler = (e: Event) => { fire(e as MessageEvent); };
    es.addEventListener("row", rowHandler);
    es.onerror = onErr;
    es.onopen = () => { if (alive) setStreamError(false); };
    return () => {
      alive = false;
      unsub();
      es.removeEventListener("row", rowHandler);
      es.close();
    };
  }, [nonce]);

  return { streamError, retry: useCallback(() => setNonce((n) => n + 1), []) };
}

/** Shared move-up/move-down reorder helper using the real reorder endpoint. */
export function reorderByIds(items: Array<{ id: string }>, from: string, to: string): string[] {
  const ids = items.map((i) => i.id);
  const a = ids.indexOf(from);
  const b = ids.indexOf(to);
  if (a < 0 || b < 0 || a === b) return ids;
  const next = [...ids];
  next.splice(a, 1);
  next.splice(b, 0, from);
  return next;
}

export type { Bot, BotRow, FleetEvent, FleetTask, LibraryItem, Routine };
