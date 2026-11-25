import { test as base, expect, type Page } from "@playwright/test";

/** Chromium logs a browser-level "Failed to load resource" console.error for
 *  any deliberate 4xx/5xx mock response. Tests must opt in per endpoint; every
 *  other console.error and every pageerror still fails the test. */
const expectedHttpErrors = new WeakMap<Page, RegExp[]>();

export function ignoreExpectedHttpError(page: Page, urlPattern: RegExp): void {
  const list = expectedHttpErrors.get(page) ?? [];
  list.push(urlPattern);
  expectedHttpErrors.set(page, list);
}

/**
 * Cowork tests feed REAL bridge envelope shapes through page.route:
 *   { bots }, { bot_id, rows }, { queued:true, seq }, and named `event: row`
 * SSE frames. Nothing here starts a fake backend; the UI must do the work.
 * Every test fails on any pageerror/console.error, including SSE noise.
 */
export const test = base.extend<{ consoleErrors: string[] }>({
  consoleErrors: async ({ page }, use) => {
    const errors: string[] = [];
    page.on("pageerror", (error) => errors.push(`pageerror: ${error.message}`));
    page.on("console", (message) => {
      if (message.type() === "error") {
        const loc = message.location();
        const allowed = expectedHttpErrors.get(page) ?? [];
        if (/^Failed to load resource:/.test(message.text())
          && allowed.some((pattern) => pattern.test(loc.url))) return;
        errors.push(`console.error: ${message.text()} @ ${loc.url}:${loc.lineNumber + 1}`);
      }
    });
    await use(errors);
    expect(errors, `browser errors:\n${errors.join("\n") || "(none)"}`).toEqual([]);
  },
});

export { expect };

export interface RecordedRequest { method: string; path: string; body: unknown; }

export const BOT = {
  id: "bot-1",
  name: "Audit task",
  role: "General assistant",
  engine: "provider",
  provider: "anthropic",
  model: "claude-sonnet-4-5",
  state: "idle",
};

export interface BridgeOptions {
  bots?: Record<string, unknown>[];
  rows?: Record<string, unknown>[];
  library?: Record<string, unknown>[];
  providers?: Record<string, unknown>[];
  projects?: Record<string, unknown>[];
  models?: string[];
  sse?: string;
  /** Delay SSE until the test calls releaseSse(); useful for event ordering. */
  holdSse?: boolean;
  /** Upstream SSE failure, used to exercise the honest reconnect banner. */
  sseError?: boolean;
  /** Delay the rows GET so the loading skeleton can be observed. */
  rowsDelayMs?: number;
  /** Body served by the real bots/:id/export.md route. */
  exportMarkdown?: string;
  /** Rows GET returns this status/body, e.g. an expired session. */
  rowsError?: { status: number; body: Record<string, unknown> };
  /** Number of initial library POSTs that fail before uploads succeed. */
  libraryFailures?: number;
  /** Hold the library POST open long enough to observe real upload progress. */
  libraryDelayMs?: number;
  /** Hold the messages POST open so Stop can be exercised. */
  messagesDelayMs?: number;
  /** Messages POST returns this status/body. */
  messagesError?: { status: number; body: Record<string, unknown> };
}

export interface BridgeController {
  requests: RecordedRequest[];
  rows: Record<string, unknown>[];
  bots: Record<string, unknown>[];
  sseFrames: string;
  sseError: boolean;
  rowsDelayMs: number;
  exportMarkdown: string;
  libraryFailures: number;
  libraryDelayMs: number;
  messagesDelayMs: number;
  rowsError?: { status: number; body: Record<string, unknown> };
  messagesError?: { status: number; body: Record<string, unknown> };
  setRows: (rows: Record<string, unknown>[]) => void;
  releaseSse: () => void;
  count: (method: string, pattern: RegExp) => number;
}

export async function mockBridge(page: Page, options: BridgeOptions = {}): Promise<BridgeController> {
  let release: (() => void) | null = null;
  let eventsCalls = 0;
  const gate = options.holdSse
    ? new Promise<void>((resolve) => { release = resolve; })
    : Promise.resolve();

  const controller: BridgeController = {
    requests: [],
    rows: options.rows ? structuredClone(options.rows) : [],
    bots: options.bots ? structuredClone(options.bots) : [structuredClone(BOT)],
    sseFrames: options.sse ?? ": ping\n\n",
    sseError: options.sseError ?? false,
    rowsDelayMs: options.rowsDelayMs ?? 0,
    exportMarkdown: options.exportMarkdown ?? "",
    libraryFailures: options.libraryFailures ?? 0,
    libraryDelayMs: options.libraryDelayMs ?? 0,
    messagesDelayMs: options.messagesDelayMs ?? 0,
    rowsError: options.rowsError,
    messagesError: options.messagesError,
    setRows(rows) { controller.rows = structuredClone(rows); },
    releaseSse: () => release?.(),
    count(method, pattern) {
      return controller.requests.filter((r) => r.method === method && pattern.test(r.path)).length;
    },
  };

  await page.route("**/api/bridge/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname.replace(/^\/api\/bridge\//, "");
    let body: unknown = null;
    try { body = request.postData() ? JSON.parse(request.postData() ?? "null") : null; } catch { /* unchanged */ }
    controller.requests.push({ method: request.method(), path, body });

    const fulfill = (status: number, json: unknown) =>
      route.fulfill({ status, contentType: "application/json", body: JSON.stringify(json) });

    if (path === "events") {
      await gate;
      eventsCalls++;
      if (controller.sseError && eventsCalls === 1) {
        return route.fulfill({ status: 503, contentType: "text/plain", body: "bridge unavailable" });
      }
      // Only the first connection carries the scripted frames. A real bridge
      // keeps its SSE connection open; leaving the reconnect pending avoids a
      // reconnect storm (and replayed deltas) during parallel test runs.
      if (eventsCalls > 1) return;
      await route.fulfill({
        status: 200,
        headers: { "content-type": "text/event-stream; charset=utf-8", "cache-control": "no-cache" },
        body: controller.sseFrames,
      });
      return;
    }
    if (request.method() === "GET" && path === "bots") return fulfill(200, { bots: controller.bots });
    if (request.method() === "POST" && path === "bots") return fulfill(201, { bot: controller.bots[0] });
    const rowsMatch = /^bots\/([^/]+)\/rows$/.exec(path);
    if (rowsMatch && request.method() === "GET") {
      if (controller.rowsDelayMs) await new Promise((r) => setTimeout(r, controller.rowsDelayMs));
      if (controller.rowsError) return fulfill(controller.rowsError.status, controller.rowsError.body);
      return fulfill(200, { bot_id: rowsMatch[1], rows: controller.rows });
    }
    const exportMatch = /^bots\/([^/]+)\/export\.md$/.exec(path);
    if (exportMatch && request.method() === "GET") {
      const markdown = controller.exportMarkdown
        || `# ${controller.bots[0]?.name ?? "Audit task"}\n\n**You**\n\nhello\n`;
      return route.fulfill({
        status: 200,
        contentType: "text/markdown; charset=utf-8",
        headers: { "content-disposition": `attachment; filename="Audit-task.md"`, "cache-control": "no-store" },
        body: markdown,
      });
    }
    if (path === "providers" && request.method() === "GET") return fulfill(200, { providers: options.providers ?? [], session_keys: [] });
    if (path === "projects" && request.method() === "GET") return fulfill(200, { projects: options.projects ?? [] });
    if (path === "library" && request.method() === "GET") return fulfill(200, { files: options.library ?? [], usage_bytes: 0 });
    if (path === "library" && request.method() === "POST") {
      if (controller.libraryDelayMs) await new Promise((r) => setTimeout(r, controller.libraryDelayMs));
      if (controller.libraryFailures > 0) {
        controller.libraryFailures--;
        return fulfill(500, { error: "library_write_failed", detail: "Quota exceeded" });
      }
      const sent = (body ?? {}) as Record<string, unknown>;
      return fulfill(200, { file: { id: "lib-1", name: sent.filename ?? "upload.txt", size: 4 } });
    }
    if (path === "usage" && request.method() === "GET") return fulfill(200, { usage: {} });
    if (path === "providers/catalog" && request.method() === "POST") {
      return fulfill(200, { ok: true, source: "offline", models: options.models ?? ["claude-sonnet-4-5", "gpt-4o"] });
    }
    const messageMatch = /^bots\/([^/]+)\/messages$/.exec(path);
    if (messageMatch && request.method() === "POST") {
      if (controller.messagesDelayMs) await new Promise((r) => setTimeout(r, controller.messagesDelayMs));
      if (controller.messagesError) return fulfill(controller.messagesError.status, controller.messagesError.body);
      return fulfill(202, { queued: true, seq: 900 });
    }
    if (/^bots\/[^/]+\/approvals\/[^/]+\/decide$/.test(path) && request.method() === "POST") {
      const decision = (body as Record<string, unknown> | null)?.decision;
      return fulfill(200, { approval: { status: "approved" }, outcome: decision });
    }
    if (/^bots\/[^/]+\/asks\/[^/]+\/answer$/.test(path) && request.method() === "POST") return fulfill(200, { ok: true });
    if (/^bots\/[^/]+\/cancel$/.test(path) && request.method() === "POST") return fulfill(200, { cancelled: true });
    if (/^bots\/[^/]+\/update$/.test(path) && request.method() === "POST") {
      return fulfill(200, { bot: { ...controller.bots[0], ...((body ?? {}) as object) } });
    }
    if (/^bots\/[^/]+\/(fork|rewind|restore)$/.test(path) && request.method() === "POST") return fulfill(200, { bot: controller.bots[0] });
    if (/^library\/[^/]+\/(download|preview)$/.test(path) && request.method() === "GET") {
      return fulfill(200, { ok: true });
    }
    // Unexpected bridge call: return an honest error rather than hanging.
    return fulfill(404, { error: "unmocked_bridge_route", path });
  });
  return controller;
}

export async function openApp(page: Page): Promise<void> {
  await page.addInitScript(() => {
    try {
      localStorage.setItem("keel-onboarding-done", "true");
      // Reset once per fresh browser context, never on reload — the tests
      // explicitly assert that drafts, active task and ask answers survive it.
      if (!sessionStorage.getItem("keel-cowork-test-init")) {
        localStorage.removeItem("keel-cowork-bot");
        localStorage.removeItem("keel-mode");
        Object.keys(localStorage)
          .filter((k) => k.startsWith("keel-draft:") || k.startsWith("keel-ask-answered:"))
          .forEach((k) => localStorage.removeItem(k));
        sessionStorage.setItem("keel-cowork-test-init", "1");
      }
    } catch { /* storage disabled */ }
  });
  await page.goto("/");
  await expect(page.locator(".keel-app")).toBeVisible();
}

export async function openSession(page: Page, botId = BOT.id as string): Promise<void> {
  await openApp(page);
  await page.locator('select[aria-label="Open an existing task"]').selectOption(botId);
  await expect(page.getByRole("button", { name: "Back to Cowork home" })).toBeVisible();
}

/** Named SSE frames exactly as the Python bridge emits them. */
export function rowFrame(row: Record<string, unknown>): string {
  return `event: row\ndata: ${JSON.stringify(row)}\n\n`;
}

export function streamFrame(botId: string, delta: string): string {
  return `data: ${JSON.stringify({ type: "stream", bot_id: botId, delta })}\n\n`;
}
