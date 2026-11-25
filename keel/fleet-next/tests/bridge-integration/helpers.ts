import { execFileSync } from "child_process";
import os from "os";
import path from "path";
import type { APIRequestContext } from "@playwright/test";

/** Throwaway token. Never a provider key or production credential. */
export const TOKEN =
  process.env.KEEL_BRIDGE_INTEGRATION_TOKEN ?? "bridge-int-throwaway-4f8c2a91";

export const REAL_BASE = "http://127.0.0.1:3311";
export const MOCK_BASE = "http://127.0.0.1:3312";
export const UNCONFIGURED_BASE = "http://127.0.0.1:3313";
export const PY_BRIDGE_BASE = "http://127.0.0.1:8797";

export const STATE_DIR = path.join(os.tmpdir(), "keel-bridge-integration-state");
export const STATE_DB = path.join(STATE_DIR, "fleet.db");
export const WORKSPACE_DIR = path.join(os.tmpdir(), "keel-bridge-integration-workspace");
export const KEEL_ROOT = path.resolve(__dirname, "../../..");

export interface CallResult {
  status: number;
  body: any;
  text: string;
  headers: Record<string, string>;
}

/** Call the same-origin BFF. `path` is relative to /api/bridge/. */
export async function call(
  request: APIRequestContext,
  method: string,
  bridgePath: string,
  body?: unknown,
  headers: Record<string, string> = {},
  base: string = REAL_BASE,
): Promise<CallResult> {
  const response = await request.fetch(`${base}/api/bridge/${bridgePath}`, {
    method,
    headers: body !== undefined
      ? { "Content-Type": "application/json", ...headers }
      : headers,
    data: body !== undefined ? body : undefined,
    failOnStatusCode: false,
  });
  const text = await response.text();
  let parsed: any = null;
  try {
    parsed = text ? JSON.parse(text) : null;
  } catch {
    parsed = { raw: text };
  }
  return {
    status: response.status(),
    body: parsed,
    text,
    headers: response.headers(),
  };
}

export async function ok(
  request: APIRequestContext,
  method: string,
  bridgePath: string,
  body?: unknown,
  headers?: Record<string, string>,
  base?: string,
): Promise<any> {
  const result = await call(request, method, bridgePath, body, headers, base);
  if (result.status < 200 || result.status >= 300) {
    throw new Error(
      `${method} /api/bridge/${bridgePath} -> ${result.status}: ${result.text.slice(0, 400)}`,
    );
  }
  return result.body;
}

/** FIXTURE-SEEDED: create a pending approval in the real bridge's DB. */
export function seedApproval(botId: string, tool = "run_shell"): string {
  const script = path.join(__dirname, "seed_approval.py");
  const out = execFileSync(
    "python",
    [script, "--db", STATE_DB, "--bot", botId, "--tool", tool],
    { encoding: "utf-8" },
  );
  return out.trim();
}

let counter = 0;
export function unique(label: string): string {
  counter += 1;
  return `${label}-${Date.now().toString(36)}-${counter}`;
}
