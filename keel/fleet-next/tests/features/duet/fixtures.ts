import { test as base, expect, type Page } from "@playwright/test";

// Duet bridge fixture. Every response mirrors real envelopes in
// keel/src/keel/fleet/routes.py. Unknown routes are answered honestly rather
// than turned into fake data that could make a dead control appear to work.

export interface CapturedRequest {
  method: string;
  path: string;
  body: unknown;
}

export interface BridgeState {
  bots: Record<string, unknown>[];
  botRows: Record<string, Record<string, unknown>[]>;
  policies: Record<string, Record<string, unknown>[]>;
  tasks: Record<string, unknown>[];
  chatBot: Record<string, unknown>;
  nextBotId: string;
  nextTaskId: number;
  nextSeq: number;
  cancelable: boolean;
}

export interface Harness {
  page: Page;
  state: BridgeState;
  requests: CapturedRequest[];
  consoleErrors: string[];
  gotoDuet: () => Promise<void>;
  openPair: () => Promise<void>;
}

const REVIEW = {
  is_git: true,
  status: " M src/app.ts\n?? notes.md\n",
  log: "9abc123 initial commit\n",
  diff_stat: " src/app.ts | 2 +-\n 1 file changed, 1 insertion(+), 1 deletion(-)\n",
};

export const test = base.extend<{ harness: Harness }>({
  harness: async ({ page, context }, use) => {
    const state: BridgeState = {
      bots: [],
      botRows: {},
      policies: {},
      tasks: [],
      chatBot: { id: "chat-b", name: "Project chat", role: "Builder for this project", engine: "provider" },
      nextBotId: "reviewer-r",
      nextTaskId: 1,
      nextSeq: 100,
      cancelable: true,
    };
    const requests: CapturedRequest[] = [];
    const consoleErrors: string[] = [];

    page.on("console", (msg) => {
      if (msg.type() !== "error") return;
      // A dropped Next dev/HMR resource load is browser transport noise, not
      // an application defect or an invented bridge response.
      if (/Failed to load resource: net::ERR_NO_BUFFER_SPACE/.test(msg.text())) return;
      consoleErrors.push(msg.text());
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

      if (method === "GET" && path === "events") {
        return route.fulfill({ status: 200, contentType: "text/event-stream", body: ": ping\n\n" });
      }
      if (method === "GET" && path === "bots") return json({ bots: state.bots });
      if (method === "POST" && path === "bots") {
        const payload = (body ?? {}) as Record<string, unknown>;
        const id = state.nextBotId;
        const bot = {
          id,
          name: String(payload.name ?? id),
          role: String(payload.role ?? ""),
          engine: String(payload.engine ?? "provider"),
          notes: String(payload.notes ?? ""),
          provider: "auto",
          model: "",
        };
        state.bots.push(bot);
        state.botRows[id] = [];
        return json({ bot }, 201);
      }
      if (segments[0] === "bots" && segments[2] === "policies" && method === "GET") {
        return json({ bot_id: segments[1], policies: state.policies[segments[1]] ?? [] });
      }
      if (segments[0] === "bots" && segments[2] === "policies" && segments[3] === "revoke" && method === "POST") {
        const tool = String((body as { tool_name?: unknown })?.tool_name ?? "");
        state.policies[segments[1]] = (state.policies[segments[1]] ?? [])
          .filter((p) => p.tool_name !== tool);
        return json({ bot_id: segments[1], tool_name: tool, revoked: true });
      }
      if (segments[0] === "bots" && segments[2] === "rows" && method === "GET") {
        return json({ bot_id: segments[1], rows: state.botRows[segments[1]] ?? [] });
      }
      if (segments[0] === "bots" && segments[2] === "messages" && method === "POST") {
        const seq = ++state.nextSeq;
        (state.botRows[segments[1]] ??= []).push({
          seq, kind: "message", created_at: "2026-11-28T10:00:00Z",
          body: { role: "user", content: String((body as { content?: unknown })?.content ?? "") },
        });
        return json({ queued: true, seq }, 202);
      }
      if (segments[0] === "bots" && segments[2] === "cancel" && method === "POST") {
        return json({ cancelled: state.cancelable });
      }
      if (method === "GET" && path === "tasks") return json({ tasks: state.tasks });
      if (method === "POST" && path === "tasks") {
        const payload = (body ?? {}) as Record<string, unknown>;
        const id = `t_${state.nextTaskId++}`;
        const task = {
          id,
          title: String(payload.title ?? ""),
          description: String(payload.description ?? ""),
          priority: String(payload.priority ?? "normal"),
          assigned_bot_id: String(payload.assigned_bot_id ?? ""),
          status: "pending",
          created_by: "user",
          source: "user",
        };
        state.tasks.push(task);
        return json({ task }, 201);
      }
      if (method === "GET" && path === "projects") {
        return json({ projects: [{ id: "p1", name: "Alpha", path: "C:\\work\\alpha", trusted: true }] });
      }
      if (segments[0] === "projects" && segments[2] === "review" && method === "GET") return json(REVIEW);
      if (segments[0] === "projects" && segments[2] === "tree" && method === "GET") {
        return json({ entries: [{ path: "src/app.ts", type: "file" }] });
      }
      if (segments[0] === "projects" && segments[2] === "chat" && method === "POST") {
        if (!state.bots.some((b) => b.id === state.chatBot.id)) state.bots.push(state.chatBot);
        state.botRows[state.chatBot.id as string] ??= [];
        return json({ bot: state.chatBot });
      }
      if (method === "GET" && path === "providers") {
        return json({ providers: [{ name: "fixture-provider", configured: true }], session_keys: [] });
      }
      if (method === "GET" && path === "usage") return json({ usage: { input_tokens: 1, output_tokens: 1 } });
      if (method === "GET" && path === "shells") return json({ shells: [] });
      if (method === "GET" && path === "shells/clear/finished") return json({ cleared: 0 });

      return json({ error: "fixture_unhandled", path });
    });

    const gotoDuet = async () => {
      await page.addInitScript(() => {
        localStorage.setItem("keel-onboarding-done", "true");
        localStorage.setItem("keel-surface", JSON.stringify("duet"));
      });
      await page.goto("/");
      await expect(page.getByRole("tabpanel", { name: "duet", exact: true })).toBeVisible();
    };
    const openPair = async () => {
      await page.getByRole("button", { name: "Open review pair (builder and reviewer)" }).click();
      await expect(page.getByRole("tab", { name: "Review pair" })).toHaveAttribute("aria-selected", "true");
    };

    await use({ page, state, requests, consoleErrors, gotoDuet, openPair });

    expect(consoleErrors, `browser console errors: ${consoleErrors.join(" | ")}`).toEqual([]);
  },
});

export { expect };
