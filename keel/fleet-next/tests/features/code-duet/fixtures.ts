import { test as base, expect, type Page } from "@playwright/test";

// Real-shaped bridge fixtures. No new dependencies: everything is supplied by
// page.route() and mirrors the envelopes documented in
// keel/docs/UI-BACKEND-CONTRACT.md and verified in src/keel/fleet/routes.py.

export type Surface = "code" | "duet";

export interface CapturedRequest {
  method: string;
  /** pathname + search, e.g. /api/bridge/projects/p1/file/read?path=src%2Fapp.ts */
  path: string;
  body: unknown;
}

export interface BridgeState {
  trusted: Record<string, boolean>;
  files: Record<string, string>;
  shellPolls: number;
  shellKilled: boolean;
  shellHandle: string | null;
}

export interface Harness {
  page: Page;
  state: BridgeState;
  requests: CapturedRequest[];
  consoleErrors: string[];
  goto: (surface: Surface) => Promise<void>;
}

const REVIEW = {
  is_git: true,
  status: " M src/app.ts\n?? notes.md\nM  README.md\n",
  log: "9abc123 initial commit\n7def456 add app\n",
  diff_stat:
    " README.md  | 2 +-\n src/app.ts | 4 ++--\n 2 files changed, 3 insertions(+), 3 deletions(-)\n",
};

const TREE: Record<string, Array<{ path: string; type: string; size?: number }>> = {
  p1: [
    { path: "src", type: "dir" },
    { path: "src/app.ts", type: "file", size: 68 },
    { path: "notes.md", type: "file", size: 19 },
    { path: "README.md", type: "file", size: 42 },
  ],
  p2: [{ path: "beta.ts", type: "file", size: 20 }],
};

export const test = base.extend<{ harness: Harness }>({
  harness: async ({ page, context }, use) => {
    const state: BridgeState = {
      trusted: { p1: false, p2: false },
      files: {
        "p1:src/app.ts": 'const greeting = "hello";\n// a comment\nconsole.log(greeting);\n',
        "p1:notes.md": "# Notes\n\nDraft text.\n",
        "p1:README.md": "# Project Alpha\n",
        "p2:beta.ts": "export const beta = 2;\n",
      },
      shellPolls: 0,
      shellKilled: false,
      shellHandle: null,
    };
    const requests: CapturedRequest[] = [];
    const consoleErrors: string[] = [];
    let shellCount = 0;

    page.on("console", (msg) => {
      if (msg.type() === "error") consoleErrors.push(msg.text());
    });
    page.on("pageerror", (err) => consoleErrors.push(`pageerror: ${err.message}`));

    await context.route("**/api/bridge/**", async (route) => {
      const request = route.request();
      const url = new URL(request.url());
      const path = url.pathname.replace(/^\/api\/bridge\/?/, "");
      const segments = path.split("/").filter(Boolean);
      const method = request.method();

      let body: unknown = null;
      const raw = request.postData();
      if (raw && method !== "GET") {
        try { body = JSON.parse(raw); } catch { body = raw; }
      }
      requests.push({ method, path: url.pathname + url.search, body });

      const json = (value: unknown, status = 200) =>
        route.fulfill({ status, contentType: "application/json", body: JSON.stringify(value) });
      // The shell initially mounts Cowork before hydration switches to the
      // requested surface. Cowork opens an EventSource; a JSON MIME type here
      // would produce a real browser console error. Serve a valid SSE frame.
      if (method === "GET" && path === "events") {
        return route.fulfill({ status: 200, contentType: "text/event-stream", body: ": ping\n\n" });
      }
      const projectList = () => [
        { id: "p1", name: "Alpha", path: "C:\\work\\alpha", trusted: state.trusted.p1 === true },
        { id: "p2", name: "Beta", path: "C:\\work\\beta", trusted: state.trusted.p2 === true },
      ];

      if (method === "GET" && path === "providers") {
        return json({ providers: [{ name: "fixture-provider", configured: true }], session_keys: [] });
      }
      if (method === "GET" && path === "usage") {
        return json({ usage: { input_tokens: 128, output_tokens: 64 } });
      }
      if (method === "GET" && path === "projects") return json({ projects: projectList() });
      if (method === "POST" && path === "projects") {
        return json({ project: { id: "p3", name: "Gamma", path: "/tmp/gamma", trusted: false } }, 201);
      }

      if (segments[0] === "projects" && segments[2] === "trust" && method === "POST") {
        const trusted = Boolean((body as { trusted?: unknown })?.trusted);
        state.trusted[segments[1]] = trusted;
        return json({ project: { id: segments[1], trusted } });
      }
      if (segments[0] === "projects" && segments[2] === "tree" && method === "GET") {
        return json({ entries: TREE[segments[1]] ?? [] });
      }
      if (segments[0] === "projects" && segments[2] === "review" && method === "GET") {
        return json(REVIEW);
      }
      if (segments[0] === "projects" && segments[2] === "file" && segments[3] === "read" && method === "GET") {
        const rel = url.searchParams.get("path") ?? "";
        const content = state.files[`${segments[1]}:${rel}`] ?? "";
        return json({ path: rel, content, size: content.length, encoding: "utf-8", binary: false, truncated: false });
      }
      if (segments[0] === "projects" && segments[2] === "file" && segments[3] === "write" && method === "POST") {
        const rel = String((body as { path?: unknown })?.path ?? "");
        const content = String((body as { content?: unknown })?.content ?? "");
        state.files[`${segments[1]}:${rel}`] = content;
        return json({ ok: true, path: rel, bytes: content.length });
      }
      if (segments[0] === "projects" && segments[2] === "terminal" && segments[3] === "exec" && method === "POST") {
        const handle = `sh-${++shellCount}`;
        state.shellHandle = handle;
        state.shellPolls = 0;
        state.shellKilled = false;
        return json({
          handle, pid: 4242, running: true,
          command: (body as { command?: string })?.command ?? "",
          shell: "posix", cwd: "C:\\work\\alpha",
        }, 202);
      }
      if (segments[0] === "projects" && ["open", "chat", "model"].includes(segments[2]) && method === "POST") {
        return json({ project: projectList().find((p) => p.id === segments[1]) ?? null });
      }

      if (method === "GET" && path === "shells") return json({ shells: [], running: 0 });
      if (method === "GET" && path === "shells/clear/finished") return json({ cleared: 1 });
      if (segments[0] === "shells" && segments[2] === "output" && method === "GET") {
        state.shellPolls += 1;
        const running = !state.shellKilled && state.shellPolls < 3;
        return json({
          handle: segments[1],
          running,
          exit_code: running ? null : 0,
          output: running ? "hello " : "hello world\n",
          truncated: false,
        });
      }
      if (segments[0] === "shells" && segments[2] === "kill" && method === "POST") {
        state.shellKilled = true;
        return json({ ok: true, pid: 4242 });
      }

      // Unexpected calls are recorded and answered honestly; they are never
      // silently turned into fake data that could make a dead control pass.
      return json({ error: "fixture_unhandled", path });
    });

    const goto = async (surface: Surface) => {
      await page.addInitScript((value: Surface) => {
        localStorage.setItem("keel-onboarding-done", "true");
        localStorage.setItem("keel-surface", JSON.stringify(value));
      }, surface);
      await page.goto("/");
      await expect(page.getByRole("tabpanel", { name: surface, exact: true })).toBeVisible();
    };

    await use({ page, state, requests, consoleErrors, goto });

    expect(consoleErrors, `browser console errors: ${consoleErrors.join(" | ")}`).toEqual([]);
  },
});

export { expect };
