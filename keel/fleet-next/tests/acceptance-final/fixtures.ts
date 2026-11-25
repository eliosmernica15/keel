import { test as base, expect, type Page, type Route } from "@playwright/test";

// Agent G's independent acceptance fixtures. Every payload below is a labelled
// FIXTURE shaped like the real Python bridge envelope — it is test scaffolding,
// never presented as live bridge data. Assertions target the exact mutation
// bodies the UI sends to /api/bridge/*, not just visible text.
export { test, expect, openApp, gotoTop, gotoSidebar, expectSurface } from "../e2e/fixtures";

/** For tests that deliberately make a fixture return a real 409/502. Chromium
 * logs those statuses as resource console.errors; every other error still fails. */
export const testWithExpectedHttpError = base.extend<{ consoleErrors: string[] }>({
  consoleErrors: async ({ page }, use) => {
    const errors: string[] = [];
    page.on("pageerror", (error) => errors.push(`pageerror: ${error.message}`));
    page.on("console", (message) => {
      if (message.type() !== "error") return;
      const text = message.text();
      if (/Failed to load resource: the server responded with a status of (409|502) \(/.test(text)) return;
      errors.push(`console.error: ${text}`);
    });
    await use(errors);
    expect(errors, `Unexpected browser errors:\n${errors.join("\n") || "(none)"}`).toEqual([]);
  },
});

/* --------------------------------------------------------------- fixtures */

export const FIXTURE_BOTS = [
  {
    id: "b_alpha", name: "Alpha", role: "researcher", engine: "provider",
    provider: "auto", model: "", notes: "lead", avatar_hue: 210,
    last_activity: "2026-11-25T10:00:00Z",
  },
  {
    id: "b_beta", name: "Beta", role: "reviewer", engine: "echo",
    provider: "auto", model: "", notes: "", avatar_hue: 280,
    last_activity: "2026-11-25T10:05:00Z",
  },
];

/** FIXTURE rows: seq is the only stable history point the bridge exposes. */
export const FIXTURE_ROWS: Record<string, unknown[]> = {
  b_alpha: [
    { seq: 1, kind: "message", created_at: "2026-11-25T10:00:01Z", body: { role: "user", content: "Draft the brief" } },
    { seq: 2, kind: "step", created_at: "2026-11-25T10:00:03Z", body: { name: "read_file", status: "done", detail: "notes.md" } },
    { seq: 3, kind: "turn_end", created_at: "2026-11-25T10:00:09Z", body: { duration_ms: 9000, num_steps: 1, terminal_reason: "completed" } },
  ],
  b_beta: [],
};

/** FIXTURE deleted rows returned by POST bots/:id/rewind (routes.py:1400). */
export const FIXTURE_DELETED_ROWS = FIXTURE_ROWS.b_alpha.slice(1);

/** FIXTURE Markdown that the real export.md route would serve (routes.py:344). */
export const FIXTURE_MARKDOWN = [
  "# Alpha — transcript",
  "",
  "## seq 1 · message",
  "",
  "You: Draft the brief",
  "",
  "## seq 2 · step",
  "",
  "read_file — notes.md",
  "",
  "## seq 3 · turn_end",
  "",
  "Turn complete · 9000 ms · completed",
  "",
].join("\n");

/** FIXTURE tasks for the recoverable-delete/undo regression. */
export const FIXTURE_TASKS = [
  {
    id: "t1", title: "QA undo target", status: "pending", priority: "normal",
    progress: 0, assigned_bot_id: "b_alpha", created_by: "user", source: "user",
    created: "2026-11-25T09:00:00Z",
  },
];

export interface CapturedCall {
  method: string;
  path: string;
  body: unknown;
}

export interface AcceptanceBridgeFixture {
  calls: CapturedCall[];
  /** Flip to exercise the honest "export unavailable" branch. */
  exportMode: "markdown" | "invalid";
  /** Flip to exercise the honest "no deleted rows" branch. */
  rewindMode: "rows" | "empty";
}

function json(route: Route, body: unknown, status = 200) {
  return route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
}

function parseBody(route: Route): unknown {
  const raw = route.request().postData();
  if (!raw) return {};
  try { return JSON.parse(raw); } catch { return { raw }; }
}

/** Route every /api/bridge/* call the surfaces make with real-shaped envelopes. */
export async function routeAcceptanceBridge(page: Page, options: {
  exportMode?: "markdown" | "invalid";
  rewindMode?: "rows" | "empty";
  rows?: Record<string, unknown[]>;
  botsUnavailable?: boolean;
} = {}): Promise<AcceptanceBridgeFixture> {
  const fixture: AcceptanceBridgeFixture = {
    calls: [],
    exportMode: options.exportMode ?? "markdown",
    rewindMode: options.rewindMode ?? "rows",
  };
  await page.route((url) => url.pathname.startsWith("/api/bridge/"), async (route) => {
    const path = route.request().url().split("/api/bridge/")[1]?.split("?")[0] ?? "";
    const method = route.request().method();
    fixture.calls.push({ method, path, body: parseBody(route) });

    if (path === "events") {
      return route.fulfill({
        status: 200,
        contentType: "text/event-stream; charset=utf-8",
        headers: { "Cache-Control": "no-cache", "X-Accel-Buffering": "no" },
        body: ": ping\n\n".repeat(4),
      });
    }

    // Real export.md response: Markdown attachment, no-store, nosniff.
    const exportMatch = path.match(/^bots\/([^/]+)\/export\.md$/);
    if (exportMatch && method === "GET") {
      if (fixture.exportMode === "invalid") {
        return route.fulfill({ status: 200, contentType: "text/html", body: "<html>not an export</html>" });
      }
      return route.fulfill({
        status: 200,
        contentType: "text/markdown; charset=utf-8",
        headers: {
          "Content-Disposition": `attachment; filename="${exportMatch[1]}.md"`,
          "X-Content-Type-Options": "nosniff",
          "Cache-Control": "no-store",
        },
        body: FIXTURE_MARKDOWN,
      });
    }

    const rewindMatch = path.match(/^bots\/([^/]+)\/rewind$/);
    if (rewindMatch && method === "POST") {
      return fixture.rewindMode === "empty"
        ? json(route, { rows: [], deleted: 0 })
        : json(route, { rows: FIXTURE_DELETED_ROWS, deleted: FIXTURE_DELETED_ROWS.length });
    }
    const restoreMatch = path.match(/^bots\/([^/]+)\/restore$/);
    if (restoreMatch && method === "POST") return json(route, { restored: FIXTURE_DELETED_ROWS.length });

    if (method !== "GET") {
      if (/^tasks\/[^/]+\/undo$/.test(path)) return json(route, { task: FIXTURE_TASKS[0] });
      if (/^tasks\/[^/]+\/(delete|update|cancel|assign)$/.test(path)) {
        return json(route, path.endsWith("/delete") ? { deleted: true } : { task: FIXTURE_TASKS[0] });
      }
      if (path === "tasks") return json(route, { task: { id: "t_new" } }, 201);
      return json(route, { queued: true, seq: 9 });
    }

    if (path === "providers") return json(route, { providers: [], session_keys: [] });
    if (options.botsUnavailable && path === "bots") return json(route, { error: "bridge_unavailable" }, 502);
    if (path === "bots") return json(route, { bots: FIXTURE_BOTS });
    const botRows = path.match(/^bots\/([^/]+)\/rows$/);
    if (botRows) return json(route, { bot_id: botRows[1], rows: (options.rows ?? FIXTURE_ROWS)[botRows[1]] ?? [] });
    const botAudit = path.match(/^bots\/([^/]+)\/audit$/);
    if (botAudit) return json(route, { bot_id: botAudit[1], audit: [] });
    if (path === "tasks") return json(route, { tasks: FIXTURE_TASKS });
    if (path === "groups") return json(route, { groups: [] });
    if (path === "routines") return json(route, { routines: [] });
    if (path === "library") return json(route, { files: [], usage_bytes: 0 });
    if (path === "projects") return json(route, { projects: [] });
    if (path === "skills") return json(route, { skills: [] });
    if (path === "mcp/servers") return json(route, { servers: [] });
    if (path === "usage") return json(route, { tokens: 0 });
    return json(route, {});
  });
  return fixture;
}

export function callWithPath(calls: CapturedCall[], fragment: string): CapturedCall | undefined {
  const withMethod = fragment.match(/^(GET|POST|PUT|DELETE) /);
  if (withMethod) return calls.find((c) => `${c.method} ${c.path}` === fragment);
  return calls.find((c) => c.path.includes(fragment));
}

/* ------------------------------------------------- SpeechRecognition mock */

/**
 * Install a deterministic Web Speech mock BEFORE navigation. All calls and
 * instances are observable through window.__qaSpeech so the specs can assert
 * that start/stop were invoked and drive onstart/onresult/onerror/onend.
 * Nothing here touches a real microphone.
 */
export async function installSpeechRecognitionMock(page: Page): Promise<void> {
  await page.addInitScript(() => {
    const probe = {
      calls: [] as string[],
      instances: [] as Array<{
        emitResult(transcript: string): void;
        emitError(error: string): void;
        emitEnd(): void;
      }>,
    };
    (window as unknown as { __qaSpeech: typeof probe }).__qaSpeech = probe;

    class MockSpeechRecognition {
      onstart: (() => void) | null = null;
      onresult: ((event: unknown) => void) | null = null;
      onerror: ((event: unknown) => void) | null = null;
      onend: (() => void) | null = null;
      lang = "";
      continuous = false;
      interimResults = false;
      maxAlternatives = 1;
      constructor() {
        probe.instances.push({
          emitResult: (transcript: string) => {
            this.onresult?.({
              resultIndex: 0,
              results: [{ isFinal: true, 0: { transcript } }],
            });
          },
          emitError: (error: string) => { this.onerror?.({ error }); },
          emitEnd: () => { this.onend?.(); },
        });
      }
      start() { probe.calls.push("start"); this.onstart?.(); }
      stop() { probe.calls.push("stop"); }
      abort() { probe.calls.push("abort"); }
    }
    (window as unknown as { SpeechRecognition: unknown }).SpeechRecognition = MockSpeechRecognition;
  });
}

export interface SpeechProbeState { calls: string[]; count: number }

export async function speechState(page: Page): Promise<SpeechProbeState> {
  return page.evaluate(() => {
    const probe = (window as unknown as {
      __qaSpeech: { calls: string[]; instances: unknown[] };
    }).__qaSpeech;
    return { calls: [...probe.calls], count: probe.instances.length };
  });
}

export async function emitSpeechResult(page: Page, transcript: string): Promise<void> {
  await page.evaluate((text) => {
    const probe = (window as unknown as {
      __qaSpeech: { instances: Array<{ emitResult(t: string): void }> };
    }).__qaSpeech;
    probe.instances[probe.instances.length - 1].emitResult(text);
  }, transcript);
}

export async function emitSpeechError(page: Page, error: string): Promise<void> {
  await page.evaluate((code) => {
    const probe = (window as unknown as {
      __qaSpeech: { instances: Array<{ emitError(e: string): void }> };
    }).__qaSpeech;
    probe.instances[probe.instances.length - 1].emitError(code);
  }, error);
}

export async function emitSpeechEnd(page: Page): Promise<void> {
  await page.evaluate(() => {
    const probe = (window as unknown as {
      __qaSpeech: { instances: Array<{ emitEnd(): void }> };
    }).__qaSpeech;
    probe.instances[probe.instances.length - 1].emitEnd();
  });
}
