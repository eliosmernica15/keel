"use client";

// Duet pair support: honest normalisers for review comments and the real
// endpoints (or exact missing endpoints) used by Live Pair / Review Pair.
// Nothing here invents a bridge field or a completion.

import { unwrap, wrapped } from "@/features/fleet/support";
import type { Bot } from "@/lib/types";

/** Real Fleet tool names whose standing approvals are revoked for a reviewer. */
export const REVIEW_TOOLS = ["write_file", "edit_file", "run_shell"] as const;

/** Exact endpoints the current bridge does not expose. They are named in the
 *  UI instead of being called with invented payloads. */
export const MISSING_COMPLETION_ENDPOINT = "POST /api/bridge/completions";
export const MISSING_COMMENT_ENDPOINT =
  "POST /api/bridge/projects/:id/review/comments";
export const MISSING_RESOLVE_ENDPOINT =
  "POST /api/bridge/reviews/:id/comments/:commentId/resolve";

export interface PairPolicy {
  bot_id?: string;
  tool_name?: string;
  decision?: string;
  created_at?: string;
  updated_at?: string;
  [key: string]: unknown;
}

export interface PairRowLike {
  seq: number;
  kind: string;
  role: string;
  content: string;
  createdAt?: string;
}

export interface ReviewComment {
  key: string;
  seq: number | null;
  file?: string;
  line?: number | null;
  severity?: string;
  message: string;
  suggestion?: string;
  createdAt?: string;
  /** True when parsed from a structured object in a real message row. */
  structured: boolean;
}

/** Unwrap the mutation envelopes the bridge actually returns. */
export function unwrapBot(value: unknown): Bot {
  return unwrap<Bot>(value, "bot");
}
export function unwrapTask(value: unknown): { id?: string; [key: string]: unknown } {
  return unwrap<{ id?: string; [key: string]: unknown }>(value, "task");
}
export function policiesOf(value: unknown): PairPolicy[] {
  return wrapped<PairPolicy>(value as Record<string, unknown>, "policies");
}

function str(value: unknown): string | undefined {
  if (typeof value === "string" && value.trim()) return value.trim();
  return undefined;
}

function num(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string" && /^\d+$/.test(value.trim())) return Number(value.trim());
  return null;
}

/** Extract every balanced JSON object from a message, ignoring braces inside
 *  strings. Reviewer prose may surround the structured block. */
function jsonObjects(text: string): unknown[] {
  const out: unknown[] = [];
  for (let start = 0; start < text.length; start += 1) {
    if (text[start] !== "{") continue;
    let depth = 0;
    let inString = false;
    let escaped = false;
    for (let i = start; i < text.length; i += 1) {
      const ch = text[i];
      if (inString) {
        if (escaped) escaped = false;
        else if (ch === "\\") escaped = true;
        else if (ch === '"') inString = false;
        continue;
      }
      if (ch === '"') { inString = true; continue; }
      if (ch === "{") depth += 1;
      else if (ch === "}") {
        depth -= 1;
        if (depth === 0) {
          try { out.push(JSON.parse(text.slice(start, i + 1))); } catch { /* prose, not JSON */ }
          break;
        }
      }
    }
  }
  return out;
}

function record(value: unknown): Record<string, unknown> | null {
  return value && typeof value === "object" && !Array.isArray(value)
    ? value as Record<string, unknown>
    : null;
}

function normalizeStructured(
  raw: unknown,
  row: PairRowLike,
  index: number,
): ReviewComment | null {
  const o = record(raw);
  if (!o) return null;
  const message = str(o.message) ?? str(o.text) ?? str(o.comment)
    ?? str(o.body) ?? str(o.content) ?? str(o.description);
  const suggestion = str(o.suggestion) ?? str(o.fix) ?? str(o.replacement);
  if (!message && !suggestion) return null;
  return {
    key: `${row.seq}:${index}`,
    seq: row.seq,
    file: str(o.file) ?? str(o.path) ?? str(o.filename),
    line: num(o.line) ?? num(o.line_number),
    severity: str(o.severity) ?? str(o.level),
    message: message ?? suggestion ?? "",
    suggestion,
    createdAt: row.createdAt,
    structured: true,
  };
}

/**
 * Comments come only from real reviewer message rows. The bridge has no
 * structured comment field (see MISSING_COMMENT_ENDPOINT), so a JSON block
 * authored by the reviewer is parsed explicitly; plain messages stay plain.
 */
export function parseReviewComments(rows: PairRowLike[]): ReviewComment[] {
  const comments: ReviewComment[] = [];
  for (const row of rows) {
    if (row.kind !== "message" || row.role === "user" || !row.content.trim()) continue;
    let found = false;
    for (const candidate of jsonObjects(row.content)) {
      const o = record(candidate);
      const list = o && Array.isArray(o.comments) ? o.comments : null;
      if (list) {
        list.forEach((entry, index) => {
          const comment = normalizeStructured(entry, row, index);
          if (comment) comments.push(comment);
        });
        found = true;
        break;
      }
      const single = normalizeStructured(candidate, row, 0);
      if (single && (single.file || single.severity || single.suggestion)) {
        comments.push(single);
        found = true;
        break;
      }
    }
    if (!found) {
      comments.push({
        key: String(row.seq),
        seq: row.seq,
        message: row.content.trim(),
        createdAt: row.createdAt,
        structured: false,
      });
    }
  }
  return comments;
}

/** Parse real `git status --porcelain` text into the file paths it reports. */
export function reviewPaths(value: unknown): string[] {
  if (Array.isArray(value)) {
    return value
      .map((v) => str(record(v)?.path))
      .filter((p): p is string => Boolean(p));
  }
  if (typeof value !== "string") return [];
  const out: string[] = [];
  for (const line of value.split("\n")) {
    if (line.length < 4) continue;
    const path = line.slice(3).trim();
    if (path && !out.includes(path)) out.push(path);
  }
  return out;
}
