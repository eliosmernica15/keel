import { type Page } from "@playwright/test";
import { test as sharedTest, expect } from "../../e2e/fixtures";

// Reuse the shared strict console gate; every spec below consumes
// `consoleErrors`, so a single pageerror/console.error fails the test.
export { test, openApp, gotoTop, expectBridgeOnline } from "../../e2e/fixtures";
export { expect };

/**
 * Only for the two specs that deliberately make the bridge return a real
 * 409/502. Chromium logs those HTTP statuses as `console.error` resource
 * messages even though the UI handles them correctly. Everything else is
 * still gated to zero console errors / zero page errors.
 */
export const testWithExpectedHttpError = sharedTest.extend<{ consoleErrors: string[] }>({
  consoleErrors: async ({ page }, use) => {
    const errors: string[] = [];
    page.on("pageerror", (error) => errors.push(`pageerror: ${error.message}\n${error.stack ?? ""}`));
    page.on("console", (message) => {
      if (message.type() !== "error") return;
      const text = message.text();
      if (/Failed to load resource: the server responded with a status of (409|502) \(/.test(text)) return;
      const loc = message.location();
      errors.push(`console.error: ${text} @ ${loc.url}:${loc.lineNumber + 1}:${loc.columnNumber + 1}`);
    });
    await use(errors);
    expect(errors, `The browser reported unexpected errors:\n${errors.join("\n") || "(none)"}`).toEqual([]);
  },
});

/* ------------------------------------------------------------------ shapes */
/* Every object below mirrors the Python bridge's real response envelopes
   (keel/src/keel/fleet/routes.py + service.py), not invented UI state. */

export const BOTS = [
  {
    id: "b_alpha", name: "Alpha", role: "researcher", engine: "provider",
    provider: "auto", model: "", notes: "lead", avatar_hue: 210,
    last_activity: "2026-11-24T10:00:00Z",
  },
  {
    id: "b_beta", name: "Beta", role: "reviewer", engine: "echo",
    provider: "auto", model: "", notes: "", avatar_hue: 280,
    last_activity: "2026-11-24T10:05:00Z",
  },
  {
    id: "b_child", name: "Child", role: "helper", engine: "echo",
    provider: "auto", model: "", notes: "", avatar_hue: 120,
    last_activity: "2026-11-24T10:06:00Z",
  },
];

export const ROWS: Record<string, unknown[]> = {
  b_alpha: [
    {
      seq: 1, kind: "step", created_at: "2026-11-24T10:00:01Z",
      body: {
        name: "send_to_bot", status: "done", detail: "→ Child",
        delegated: { to: "Child", to_id: "b_child", reply: "done", ok: true, task_id: "t1" },
      },
    },
    {
      seq: 2, kind: "turn_end", created_at: "2026-11-24T10:00:09Z",
      body: { duration_ms: 9000, num_steps: 1, terminal_reason: "completed" },
    },
  ],
  b_beta: [],
  b_child: [
    {
      seq: 1, kind: "message", created_at: "2026-11-24T10:00:04Z",
      body: {
        role: "user", content: "Check the notes",
        delegated_from: { id: "b_alpha", name: "Alpha" }, task_id: "t1",
      },
    },
  ],
};

export const TASKS = [
  {
    id: "t1", title: "Draft brief", status: "pending", priority: "normal",
    progress: 0, assigned_bot_id: "b_alpha", created_by: "user",
    source: "user", created: "2026-11-24T09:00:00Z",
  },
  {
    id: "t2", title: "Review draft", status: "in_progress", priority: "high",
    progress: 25, assigned_bot_id: "b_beta", created_by: "user",
    source: "user", created: "2026-11-24T09:10:00Z",
  },
];

export const POLICIES = [
  { bot_id: "b_alpha", tool_name: "shell", decision: "always", created_at: "2026-11-23T10:00:00Z", updated_at: "2026-11-24T10:00:00Z" },
];

export const AUDIT = [
  { id: 1, bot_id: "b_alpha", tool_name: "shell", fingerprint: "fp1", event: "requested", decision: null, outcome: null, approval_id: "a1", created_at: "2026-11-24T10:00:00Z" },
  { id: 2, bot_id: "b_alpha", tool_name: "shell", fingerprint: "fp1", event: "decided", decision: "always", outcome: "granted", approval_id: "a1", created_at: "2026-11-24T10:00:02Z" },
  { id: 3, bot_id: "b_alpha", tool_name: "send_to_bot", fingerprint: "fp2", event: "outcome", decision: "delegate", outcome: "executed", created_at: "2026-11-24T10:00:04Z" },
  { id: 4, bot_id: "b_alpha", tool_name: "shell", fingerprint: "policy", event: "policy_revoked", decision: null, outcome: null, created_at: "2026-11-23T10:00:00Z" },
];

export const GROUPS = [
  {
    id: "g1", name: "Ops", bot_ids: ["b_alpha", "b_beta"],
    members: [
      { id: "b_alpha", name: "Alpha", role: "researcher", engine: "provider" },
      { id: "b_beta", name: "Beta", role: "reviewer", engine: "echo" },
    ],
    created_at: "2026-11-24T09:00:00Z", updated_at: "2026-11-24T10:00:00Z",
  },
];

export const INITIAL_GROUP_ROWS = [
  { seq: 1, group_id: "g1", author: "user", kind: "message", body: { role: "user", content: "Start" }, created_at: "2026-11-24T10:00:00Z" },
];

export const FINISHED_GROUP_ROWS = [
  ...INITIAL_GROUP_ROWS,
  { seq: 2, group_id: "g1", author: "system", kind: "member_status", body: { bot_id: "b_alpha", bot_name: "Alpha", status: "done" }, created_at: "2026-11-24T10:00:02Z" },
  { seq: 3, group_id: "g1", author: "system", kind: "member_status", body: { bot_id: "b_beta", bot_name: "Beta", status: "done" }, created_at: "2026-11-24T10:00:04Z" },
];

export const ROUTINES = [
  {
    id: "r1", name: "Morning sweep", bot_id: "b_alpha",
    prompt: "Summarise new work", cron_expr: "0 9 * * *", timezone: "UTC",
    enabled: true, paused: false, running: false, next_run_at: "2026-11-25T09:00:00Z",
    last_run_at: "2026-11-24T09:00:00Z", last_status: "completed",
  },
];

export const RUNS = [
  { id: 1, routine_id: "r1", task_id: null, scheduled_at: "2026-11-24T09:00:00Z", started_at: "2026-11-24T09:00:01Z", finished_at: "2026-11-24T09:00:09Z", status: "completed", summary: "ok" },
  { id: 2, routine_id: "r1", task_id: null, scheduled_at: "2026-11-23T09:00:00Z", started_at: null, finished_at: null, status: "skipped_missed", summary: "" },
];

export const FILES = [
  { id: "f1", name: "chart.png", type: "file", mime: "image/png", size: 1024, bot_id: "b_alpha", created: "2026-11-24T10:00:00Z" },
  { id: "f2", name: "blob.bin", type: "file", mime: "application/octet-stream", size: 512, bot_id: "b_beta", created: "2026-11-24T10:01:00Z" },
];

/* ------------------------------------------------------------------ router */

export interface CapturedCall {
  method: string;
  path: string;
  body: unknown;
}

export interface FleetBridgeFixture {
  calls: CapturedCall[];
  groupRows: unknown[];
  groupMessageMode: "ok" | "conflict";
  runMode: "ok" | "conflict";
}

function json(route: import("@playwright/test").Route, body: unknown, status = 200) {
  return route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
}

function parseBody(route: import("@playwright/test").Route): unknown {
  const raw = route.request().postData();
  if (!raw) return {};
  try { return JSON.parse(raw); } catch { return { raw }; }
}

/**
 * Routes every /api/bridge/* call the Fleet surface makes with real-shaped
 * envelopes. `events` receives a valid text/event-stream ping frame so the
 * EventSource stays quiet without depending on the bridge proxy's availability.
 */
export async function routeFleetBridge(page: Page, options: { groupMessageMode?: "ok" | "conflict"; runMode?: "ok" | "conflict"; botsUnavailable?: boolean; audit?: typeof AUDIT } = {}): Promise<FleetBridgeFixture> {
  const fixture: FleetBridgeFixture = {
    calls: [],
    groupRows: [...INITIAL_GROUP_ROWS],
    groupMessageMode: options.groupMessageMode ?? "ok",
    runMode: options.runMode ?? "ok",
  };
  await page.route((url) => url.pathname.startsWith("/api/bridge/"), async (route) => {
    const path = route.request().url().split("/api/bridge/")[1]?.split("?")[0] ?? "";
    const method = route.request().method();
    if (path === "events") {
      // A real-shaped SSE keep-alive. The bridge's raw proxy can return 504 on
      // a busy host; that would log a console.error unrelated to Fleet logic.
      return route.fulfill({
        status: 200,
        contentType: "text/event-stream; charset=utf-8",
        headers: { "Cache-Control": "no-cache", "X-Accel-Buffering": "no" },
        body: ": ping\n\n".repeat(4),
      });
    }

    if (method !== "GET") {
      const body = parseBody(route);
      fixture.calls.push({ method, path, body });
      if (path === "bots") return json(route, { bot: { id: "b_new", ...(body as object) } }, 201);
      if (/^bots\/[^/]+\/update$/.test(path)) return json(route, { bot: { id: path.split("/")[1] } });
      if (/^bots\/[^/]+\/policies\/revoke$/.test(path)) return json(route, { revoked: true });
      if (/^bots\/[^/]+\/(messages|cancel|approvals|asks)/.test(path)) return json(route, { queued: true, seq: 9 });
      if (path === "groups") return json(route, { group: { id: "g_new", name: "Ops", members: [] } }, 201);
      if (/^groups\/[^/]+\/messages$/.test(path)) {
        if (fixture.groupMessageMode === "conflict") {
          return json(route, { queued: false, busy: true, seq: 2 }, 409);
        }
        return json(route, { queued: true, seq: 4 }, 202);
      }
      if (/^groups\/[^/]+\/delete$/.test(path)) return json(route, { deleted: true });
      if (path === "tasks") return json(route, { task: { id: "t_new", ...(body as object) } }, 201);
      if (path === "tasks/reorder") return json(route, { tasks: TASKS });
      if (/^tasks\/[^/]+\/undo$/.test(path)) return json(route, { task: TASKS[1] });
      if (/^tasks\/[^/]+\/(update|assign|cancel|delete)$/.test(path)) {
        return json(route, path.endsWith("/delete") ? { deleted: true } : { task: TASKS[1] });
      }
      if (path === "routines") return json(route, { routine: { id: "r_new", ...(body as object) } }, 201);
      if (/^routines\/[^/]+\/run$/.test(path)) {
        return fixture.runMode === "conflict"
          ? json(route, { error: "routine is already running" }, 409)
          : json(route, { queued: true, routine_id: "r1" }, 202);
      }
      if (/^routines\/[^/]+\//.test(path)) return json(route, { routine: ROUTINES[0] });
      if (path === "library") return json(route, { file: { id: "f_new" } }, 201);
      if (/^library\/[^/]+\/delete$/.test(path)) return json(route, { deleted: true });
      return json(route, {});
    }

    if (path === "providers") return json(route, { providers: [], session_keys: [] });
    if (options.botsUnavailable && path === "bots") {
      return json(route, { error: "bridge_unavailable" }, 502);
    }
    if (path === "bots") return json(route, { bots: BOTS });
    const botRows = path.match(/^bots\/([^/]+)\/rows$/);
    if (botRows) return json(route, { bot_id: botRows[1], rows: ROWS[botRows[1]] ?? [] });
    const botPolicies = path.match(/^bots\/([^/]+)\/policies$/);
    if (botPolicies) return json(route, { bot_id: botPolicies[1], policies: POLICIES });
    const botAudit = path.match(/^bots\/([^/]+)\/audit$/);
    if (botAudit) return json(route, { bot_id: botAudit[1], audit: options.audit ?? AUDIT });
    if (path === "tasks") return json(route, { tasks: TASKS });
    const taskEvents = path.match(/^tasks\/([^/]+)\/events$/);
    if (taskEvents) return json(route, { task_id: taskEvents[1], events: [{ id: 1, task_id: taskEvents[1], event: "created", from_status: null, to_status: "pending", created_at: "2026-11-24T09:00:00Z" }] });
    const taskDetail = path.match(/^tasks\/([^/]+)$/);
    if (taskDetail) return json(route, { task: TASKS.find((t) => t.id === taskDetail[1]) ?? TASKS[0] });
    if (path === "groups") return json(route, { groups: GROUPS });
    const groupDetail = path.match(/^groups\/([^/]+)$/);
    if (groupDetail) return json(route, { group: GROUPS[0], rows: fixture.groupRows });
    if (path === "routines") return json(route, { routines: ROUTINES });
    const routineRuns = path.match(/^routines\/([^/]+)\/runs$/);
    if (routineRuns) return json(route, { routine_id: routineRuns[1], runs: RUNS });
    const routineDetail = path.match(/^routines\/([^/]+)$/);
    if (routineDetail) return json(route, { routine: ROUTINES[0], runs: RUNS });
    if (path === "library") return json(route, { files: FILES, usage_bytes: 1536 });
    return json(route, {});
  });
  return fixture;
}

export function callWithPath(calls: CapturedCall[], fragment: string): CapturedCall | undefined {
  const methodPrefix = fragment.match(/^(GET|POST|PUT|DELETE) /);
  if (methodPrefix) {
    return calls.find((c) => `${c.method} ${c.path}` === fragment);
  }
  return calls.find((c) => c.path.includes(fragment));
}
