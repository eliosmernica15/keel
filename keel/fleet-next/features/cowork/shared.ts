// Cowork-local view helpers. These only reshape data that the bridge actually
// returned; nothing here invents rows, files, steps or status.

import type { Bot, Usage } from "@/lib/types";

export interface RowView {
  key: string;
  seq: number | string;
  kind: string;
  role?: string;
  body: Record<string, unknown>;
  ts?: string | number;
  botId?: string;
}

export interface LibraryView {
  id: string;
  name?: string;
  type?: string;
  size?: number;
  created?: string;
}

export interface ProjectView {
  id: string;
  name?: string;
  path?: string;
  trusted?: boolean;
}

export type WorkState =
  | "running" | "queued" | "paused" | "waiting-for-user"
  | "failed" | "cancelled" | "completed" | "idle";

function asRecord(v: unknown): Record<string, unknown> {
  return v && typeof v === "object" && !Array.isArray(v) ? (v as Record<string, unknown>) : {};
}

export function toBots(input: unknown): Bot[] {
  const list = Array.isArray(input) ? input : asRecord(input).bots;
  return Array.isArray(list) ? (list as Bot[]).filter((b): b is Bot => !!b && typeof b.id === "string") : [];
}

export function toRows(input: unknown): RowView[] {
  const list = Array.isArray(input) ? input : asRecord(input).rows;
  if (!Array.isArray(list)) return [];
  const seen = new Set<string>();
  const out: RowView[] = [];
  for (let i = 0; i < list.length; i++) {
    const r = asRecord(list[i]);
    const seq = r.seq ?? r.id ?? i;
    const key = String(seq ?? i);
    if (seen.has(key)) continue; // SSE cursor replays must not duplicate rows
    seen.add(key);
    out.push({
      key,
      seq: (typeof seq === "number" || typeof seq === "string" ? seq : i),
      kind: typeof r.kind === "string" ? r.kind : typeof r.type === "string" ? r.type : "unknown",
      role: typeof r.role === "string" ? r.role : undefined,
      body: asRecord(r.body),
      ts: (typeof r.ts === "string" || typeof r.ts === "number") ? r.ts
        : (typeof r.created_at === "string" ? r.created_at : undefined),
      botId: typeof r.bot_id === "string" ? r.bot_id : undefined,
    });
  }
  return out;
}

export function toLibrary(input: unknown): LibraryView[] {
  const list = Array.isArray(input) ? input : (asRecord(input).files ?? asRecord(input).items);
  if (!Array.isArray(list)) return [];
  return list.map((raw, i) => {
    const r = asRecord(raw);
    return {
      id: String(r.id ?? i),
      name: typeof r.name === "string" ? r.name : undefined,
      type: typeof r.type === "string" ? r.type : undefined,
      size: typeof r.size === "number" ? r.size : undefined,
      created: typeof r.created_at === "string" ? r.created_at : undefined,
    };
  });
}

export function toProjects(input: unknown): ProjectView[] {
  const list = Array.isArray(input) ? input : asRecord(input).projects;
  if (!Array.isArray(list)) return [];
  return list.map((raw, i) => {
    const r = asRecord(raw);
    return {
      id: String(r.id ?? i),
      name: typeof r.name === "string" ? r.name : undefined,
      path: typeof r.path === "string" ? r.path : undefined,
      trusted: r.trusted === true || r.trusted === 1,
    };
  });
}

export function textOf(v: unknown): string {
  return typeof v === "string" ? v : v == null ? "" : String(v);
}

export function formatTime(ts?: string | number): string {
  if (ts == null || ts === "") return "";
  const d = typeof ts === "number" ? new Date(ts < 1e12 ? ts * 1000 : ts) : new Date(ts);
  if (Number.isNaN(d.getTime())) return "";
  return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

export function formatRelative(ts?: string | number): string {
  if (ts == null || ts === "") return "";
  const d = typeof ts === "number" ? new Date(ts < 1e12 ? ts * 1000 : ts) : new Date(ts);
  if (Number.isNaN(d.getTime())) return "";
  const secs = Math.max(0, Math.round((Date.now() - d.getTime()) / 1000));
  if (secs < 60) return `${secs}s ago`;
  if (secs < 3600) return `${Math.floor(secs / 60)}m ago`;
  if (secs < 86400) return `${Math.floor(secs / 3600)}h ago`;
  return `${Math.floor(secs / 86400)}d ago`;
}

export function formatDuration(ms: number): string {
  if (!Number.isFinite(ms) || ms < 0) return "0s";
  const s = Math.floor(ms / 1000);
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m ${s % 60}s`;
  return `${Math.floor(m / 60)}h ${m % 60}m`;
}

export function safeJson(v: unknown): string {
  try { return JSON.stringify(v, null, 2) ?? String(v); } catch { return String(v); }
}

const TOOL_VERBS: Record<string, string> = {
  read_file: "Read", read: "Read", write_file: "Wrote", edit_file: "Edited",
  save_file: "Saved", run_shell: "Ran", shell: "Ran", glob: "Searched", grep: "Searched",
  list_tasks: "Listed tasks", create_task: "Created task", update_task: "Updated task",
  send_to_bot: "Delegated to", ask_user: "Asked you", browser: "Browsed",
};

export function toolVerb(name?: string): string {
  if (!name) return "Used tool";
  return TOOL_VERBS[name] ?? name.replace(/_/g, " ");
}

/** Human summary derived from real step bodies — e.g. "Read 3 files". */
export function humanSummary(rows: RowView[]): string {
  const counts: Record<string, number> = {};
  const targets: Record<string, number> = {};
  for (const row of rows) {
    const b = row.body;
    const name = textOf(b.name ?? b.tool ?? "tool") || "tool";
    counts[name] = (counts[name] ?? 0) + 1;
    const detail = textOf(b.detail ?? b.path ?? b.command ?? b.query ?? "");
    if (detail) targets[name] = (targets[name] ?? 0) + 1;
  }
  const parts = Object.entries(counts).map(([name, count]) => {
    const verb = toolVerb(name);
    const n = targets[name];
    if (n && n > 1) return `${verb} ${n} targets`;
    if (count > 1) return `${verb} ${count}×`;
    return verb;
  });
  if (!parts.length) return "Agent activity";
  return parts.length <= 3 ? parts.join(" · ") : `${parts.slice(0, 2).join(" · ")} · +${parts.length - 2} more`;
}

/** File paths only when a real row body exposes them. */
export function changedFiles(rows: RowView[]): string[] {
  const files: string[] = [];
  const push = (v: unknown) => {
    const s = textOf(v).trim();
    if (s && !files.includes(s)) files.push(s);
  };
  for (const row of rows) {
    const b = row.body;
    const name = textOf(b.name ?? b.tool ?? "");
    if (/write|edit|save/i.test(name)) push(b.path ?? b.file ?? b.detail);
    if (Array.isArray(b.files)) b.files.forEach(push);
    if (Array.isArray(b.changed_files)) b.changed_files.forEach(push);
  }
  return files;
}

const RESOLVED_STATUSES = new Set([
  "answered", "resolved", "approved", "denied", "never", "refused", "rejected",
  "decided", "expired", "timeout", "timed_out", "cancelled", "canceled",
]);

/** A request whose advertised deadline has passed is stale, not pending.
 *  The bridge rejects decisions on expired approvals; the UI must not keep
 *  presenting them as actionable. */
export function isExpired(row: RowView): boolean {
  if (textOf(row.body.status).toLowerCase() === "expired") return true;
  const raw = textOf(row.body.expires_at);
  if (!raw) return false;
  const ms = Date.parse(raw);
  return Number.isFinite(ms) && Date.now() > ms;
}

export function isUnanswered(row: RowView): boolean {
  if (row.kind !== "ask" && row.kind !== "approval") return false;
  if (isExpired(row)) return false;
  const status = textOf(row.body.status ?? row.body.decision).toLowerCase();
  return !RESOLVED_STATUSES.has(status);
}

const requestId = (row: RowView): string =>
  textOf(row.body.approval_id ?? row.body.ask_id ?? row.body.id);

/** The bridge appends a *second* approval row with the decision. Previous
 *  pending rows must not keep the session in "waiting for you" forever, and
 *  an answered ask (whose row is not rewritten by the bridge) is handled by
 *  caller-supplied answered ids. */
export function outstandingRequest(rows: RowView[], answeredAskIds: Set<string> = new Set()): RowView | null {
  const latest = new Map<string, RowView>();
  for (const row of rows) {
    if (row.kind !== "ask" && row.kind !== "approval") continue;
    const id = requestId(row);
    if (!id || (row.kind === "ask" && answeredAskIds.has(id))) continue;
    latest.set(id, row);
  }
  let found: RowView | null = null;
  for (const row of latest.values()) if (isUnanswered(row)) found = row;
  return found;
}

export interface StepProgress { done: number; failed: number; running: number; total: number; }

/** Progress comes only from step rows with a real status. The bridge emits a
 *  `running` row and later a `done` row for the same tool; count the newest
 *  state per tool so progress never double-counts or invents steps. */
export function stepProgress(rows: RowView[]): StepProgress | null {
  const latest = new Map<string, string>();
  let reported = false;
  for (const row of rows) {
    if (row.kind !== "step") continue;
    const status = textOf(row.body.status).toLowerCase();
    if (!status) continue;
    reported = true;
    const id = textOf(row.body.id ?? row.body.tool_use_id)
      || `${textOf(row.body.name ?? row.body.tool)}|${textOf(row.body.detail ?? row.body.path ?? row.body.command ?? "")}`;
    latest.set(id, status);
  }
  if (!reported || latest.size === 0) return null;
  const result: StepProgress = { done: 0, failed: 0, running: 0, total: latest.size };
  for (const status of latest.values()) {
    if (/done|complete|success|ok/.test(status)) result.done++;
    else if (/fail|error|denied|cancel/.test(status)) result.failed++;
    else if (/running|progress|active/.test(status)) result.running++;
  }
  return result;
}

/** Token/cost facts from the real turn_end body (not from global metadata). */
export function turnUsageFacts(row: RowView): string[] {
  const usage = (row.body.usage && typeof row.body.usage === "object" ? row.body.usage : {}) as Record<string, unknown>;
  const out: string[] = [];
  const inTokens = usage.input_tokens;
  const outTokens = usage.output_tokens;
  if (typeof inTokens === "number" || typeof outTokens === "number") {
    const ins = typeof inTokens === "number" ? inTokens.toLocaleString() : "?";
    const outs = typeof outTokens === "number" ? outTokens.toLocaleString() : "?";
    out.push(`${ins} in · ${outs} out tokens`);
  }
  if (typeof usage.cost === "number") out.push(`$${usage.cost.toFixed(4)}`);
  return out;
}

export interface StatusInfo { state: WorkState; label: string; reason?: string; }

/** Every state below is derived from real bot fields, rows or turn metadata. */
export function deriveStatus(bot: Bot | null, rows: RowView[], busy: boolean, answeredAskIds: Set<string> = new Set()): StatusInfo {
  const raw = `${textOf(bot?.state)} ${textOf(bot?.status)}`.trim().toLowerCase();
  const waiting = outstandingRequest(rows, answeredAskIds);
  if (waiting) {
    const reason = textOf(waiting.body.question ?? waiting.body.description ?? waiting.body.operation ?? waiting.body.tool_name);
    return { state: "waiting-for-user", label: "Waiting for you", reason: reason || undefined };
  }
  // A persisted `running` step from an already-ended turn is not live work.
  const lastEndSeq = [...rows].reverse().find((r) => r.kind === "turn_end")?.seq;
  const liveStep = rows.some((r) => r.kind === "step"
    && textOf(r.body.status).toLowerCase() === "running"
    && (lastEndSeq == null || (typeof r.seq === "number" && typeof lastEndSeq === "number" && r.seq > lastEndSeq)));
  if (busy || liveStep) {
    return { state: "running", label: "Running" };
  }
  if (/fail|error/.test(raw)) return { state: "failed", label: "Failed", reason: textOf(bot?.state ?? bot?.status) || undefined };
  if (/cancel|abort|interrupt/.test(raw)) return { state: "cancelled", label: "Cancelled", reason: textOf(bot?.state ?? bot?.status) || undefined };
  if (/queue/.test(raw)) return { state: "queued", label: "Queued", reason: textOf(bot?.state ?? bot?.status) || undefined };
  if (/pause/.test(raw)) return { state: "paused", label: "Paused", reason: textOf(bot?.state ?? bot?.status) || undefined };
  const lastEnd = [...rows].reverse().find((r) => r.kind === "turn_end");
  if (lastEnd) {
    const why = textOf(lastEnd.body.terminal_reason).toLowerCase();
    if (/fail|error/.test(why)) return { state: "failed", label: "Failed", reason: textOf(lastEnd.body.terminal_reason) || undefined };
    if (/cancel|abort|interrupt/.test(why)) return { state: "cancelled", label: "Cancelled", reason: textOf(lastEnd.body.terminal_reason) || undefined };
    const dur = typeof lastEnd.body.duration_ms === "number" ? ` · ${formatDuration(lastEnd.body.duration_ms)}` : "";
    return { state: "completed", label: "Completed", reason: `${textOf(lastEnd.body.terminal_reason) || "turn ended"}${dur}` };
  }
  return { state: "idle", label: "Ready" };
}

export function usageFacts(usage: Usage | null): string[] {
  if (!usage) return [];
  const out: string[] = [];
  if (typeof usage.tokens === "number") out.push(`${usage.tokens.toLocaleString()} tokens`);
  if (typeof usage.cost === "number") out.push(`$${usage.cost.toFixed(4)}`);
  if (typeof usage.requests === "number") out.push(`${usage.requests} requests`);
  return out;
}
