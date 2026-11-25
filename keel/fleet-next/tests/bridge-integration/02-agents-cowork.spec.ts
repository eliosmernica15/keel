import { expect, test, type APIRequestContext } from "@playwright/test";
import {
  call,
  ok,
  REAL_BASE,
  seedApproval,
  unique,
} from "./helpers";

async function makeBot(request: APIRequestContext, name: string) {
  const created = await ok(request, "POST", "bots", { name, engine: "echo" });
  return created.bot.id as string;
}

test.describe("B — agents, conversations, approvals, asks and groups (REAL bridge)", () => {
  test("bots: create/list/rows/latest_seq/messages/update/fork/rewind/restore/export/delete", async ({ request }) => {
    const id = await makeBot(request, unique("agent-flow"));

    const listed = await ok(request, "GET", "bots");
    expect(listed.bots.some((b: any) => b.id === id)).toBe(true);

    const sent = await call(request, "POST", `bots/${id}/messages`, {
      content: "bridge integration ping",
      mode: "build",
    });
    expect(sent.status).toBe(202);
    expect(sent.body.queued).toBe(true);
    expect(typeof sent.body.seq).toBe("number");

    // Wait for the scripted echo turn to finish before mutating its rows;
    // otherwise a daemon turn can write into a deleted bot (FK error).
    await expect.poll(async () => {
      const rows = await ok(request, "GET", `bots/${id}/rows?after=0&limit=50`);
      return rows.rows.some((r: any) => r.kind === "turn_end");
    }, { timeout: 10_000 }).toBe(true);

    const rowsBefore = await ok(request, "GET", `bots/${id}/rows`);
    expect(rowsBefore.bot_id).toBe(id);
    const latest = await ok(request, "GET", `bots/${id}/latest_seq`);
    expect(latest.seq).toBeGreaterThanOrEqual(sent.body.seq);

    const updated = await ok(request, "POST", `bots/${id}/update`, { notes: "verified" });
    expect(updated.bot.notes).toBe("verified");

    const forked = await call(request, "POST", `bots/${id}/fork`, { name: "forked-copy" });
    expect(forked.status).toBe(201);
    expect(forked.body.bot.name).toBe("forked-copy");

    const rewound = await ok(request, "POST", `bots/${id}/rewind`, { from_seq: 1 });
    expect(rewound.deleted).toBeGreaterThan(0);
    const restored = await ok(request, "POST", `bots/${id}/restore`, { rows: rowsBefore.rows });
    expect(restored.restored).toBe(rowsBefore.rows.length);

    const cancelled = await ok(request, "POST", `bots/${id}/cancel`);
    expect("cancelled" in cancelled).toBe(true);

    const exported = await call(request, "GET", `bots/${id}/export.md`);
    expect(exported.status).toBe(200);
    expect(exported.headers["content-type"]).toContain("text/markdown");

    const deleted = await ok(request, "POST", `bots/${id}/delete`);
    expect(deleted.deleted).toBe(true);
  });

  test("policies and audit: real envelopes and revoke flow", async ({ request }) => {
    const id = await makeBot(request, unique("policy-bot"));
    const policies = await ok(request, "GET", `bots/${id}/policies`);
    expect(policies.bot_id).toBe(id);
    expect(Array.isArray(policies.policies)).toBe(true);
    const audit = await ok(request, "GET", `bots/${id}/audit?limit=10`);
    expect(Array.isArray(audit.audit)).toBe(true);

    const revoked = await ok(request, "POST", `bots/${id}/policies/revoke`, { tool_name: "run_shell" });
    expect(revoked.tool_name).toBe("run_shell");
    expect(typeof revoked.revoked).toBe("boolean");
    const missingTool = await call(request, "POST", `bots/${id}/policies/revoke`, { tool_name: "" });
    expect(missingTool.status).toBe(400);
  });

  test("approvals: real decide contract (FIXTURE-SEEDED pending card), validation and outcome", async ({ request }) => {
    const id = await makeBot(request, unique("approval-bot"));

    // FIXTURE-SEEDED: a pending card is inserted deterministically into the
    // real bridge DB; the HTTP decide itself is a genuine bridge round-trip.
    const onceId = seedApproval(id, "run_shell");
    const once = await call(request, "POST", `bots/${id}/approvals/${onceId}/decide`, { decision: "once" });
    expect(once.status).toBe(200);
    expect(once.body.outcome).toBe("granted");
    expect(once.body.approval.status).toBe("approved");

    const neverId = seedApproval(id, "write_file");
    const never = await call(request, "POST", `bots/${id}/approvals/${neverId}/decide`, { decision: "never" });
    expect(never.status).toBe(200);
    expect(never.body.outcome).toBe("refused");
    const after = await ok(request, "GET", `bots/${id}/policies`);
    expect(after.policies.some((p: any) => p.tool_name === "write_file" && p.decision === "never")).toBe(true);

    const invalid = await call(request, "POST", `bots/${id}/approvals/${onceId}/decide`, { decision: "maybe" });
    expect(invalid.status).toBe(400);
    expect(invalid.body.error).toMatch(/decision/);
    const missing = await call(request, "POST", `bots/${id}/approvals/ap_missing_123/decide`, { decision: "once" });
    expect(missing.status).toBe(404);
    expect(missing.body.error).toBe("approval_not_found");
  });

  test("asks: genuine validation/404 envelopes (no live provider question is available)", async ({ request }) => {
    const id = await makeBot(request, unique("ask-bot"));
    const missing = await call(request, "POST", `bots/${id}/asks/ask_missing_123/answer`, { answer: "yes" });
    expect(missing.status).toBe(404);
    expect(missing.body.error).toBe("ask_not_found_or_expired");
    const empty = await call(request, "POST", `bots/${id}/asks/ask_missing_123/answer`, { answer: "" });
    expect(empty.status).toBe(400);
    // A successful answer needs a real provider turn with an ask_user tool;
    // no provider credentials are available in this verification environment.
  });

  test("groups: create/list/detail/rows/message/delete", async ({ request }) => {
    // The bridge requires 2–3 distinct agents per group (service.py:894).
    const botA = await makeBot(request, unique("group-member-a"));
    const botB = await makeBot(request, unique("group-member-b"));
    const created = await call(request, "POST", "groups", {
      name: unique("integration-group"),
      bot_ids: [botA, botB],
    });
    expect(created.status).toBe(201);
    const gid = created.body.group.id;

    const groups = await ok(request, "GET", "groups");
    expect(groups.groups.some((g: any) => g.id === gid)).toBe(true);
    const detail = await ok(request, "GET", `groups/${gid}`);
    expect(detail.group.id).toBe(gid);
    expect(Array.isArray(detail.rows)).toBe(true);
    const rows = await ok(request, "GET", `groups/${gid}/rows?after=0`);
    expect(rows.group_id).toBe(gid);

    const message = await call(request, "POST", `groups/${gid}/messages`, { content: "hello group" });
    expect([202, 409]).toContain(message.status);
    if (message.status === 202) expect(message.body.queued).toBe(true);
    else expect(message.body.busy).toBe(true);

    const deleted = await ok(request, "POST", `groups/${gid}/delete`);
    expect(deleted.deleted).toBe(true);
  });

  test("SSE: browser EventSource receives the named row events (api.ts listener path)", async ({ page, request }) => {
    // subscribeEvents() in lib/api.ts registers both an "row" listener and a
    // generic onmessage handler; named frames must reach the named listener.
    await page.goto(`${REAL_BASE}/`, { waitUntil: "domcontentloaded" });
    const received = page.evaluate(() => new Promise<string>((resolve) => {
      const es = new EventSource("/api/bridge/events");
      const done = (event: MessageEvent) => {
        es.close();
        resolve(String(event.data));
      };
      // Only the NAMED listener is registered here; generic onmessage would
      // never see these frames, so any data proves the named-frame path.
      es.addEventListener("row", done as EventListener);
      setTimeout(() => { es.close(); resolve("timeout"); }, 10_000);
    }));

    const id = await makeBot(request, unique("browser-sse-bot"));
    await ok(request, "POST", `bots/${id}/messages`, { content: "browser stream", mode: "build" });

    const data = await received;
    expect(data).not.toBe("timeout");
    const frame = JSON.parse(data);
    expect(frame.type).toBe("row");
    expect(typeof frame.seq).toBe("number");
  });

  test("SSE: real bridge emits named event: row frames through the BFF proxy", async ({ request }) => {
    const controller = new AbortController();
    let text = "";
    try {
      const response = await fetch(`${REAL_BASE}/api/bridge/events`, {
        signal: controller.signal,
      });
      expect(response.status).toBe(200);
      expect(response.headers.get("content-type")).toContain("text/event-stream");

      const id = await makeBot(request, unique("sse-bot"));
      await ok(request, "POST", `bots/${id}/messages`, { content: "stream me", mode: "build" });

      const reader = response.body!.getReader();
      const deadline = Date.now() + 12_000;
      while (Date.now() < deadline && !/event: row\ndata: \{/.test(text)) {
        const piece = await Promise.race([
          reader.read(),
          new Promise<{ value: undefined; done: boolean }>((resolve) =>
            setTimeout(() => resolve({ value: undefined, done: false }), 400)),
        ]);
        if (piece.value) text += Buffer.from(piece.value).toString("utf8");
      }
    } finally {
      controller.abort();
    }

    expect(text).toMatch(/event: row\ndata: \{/);
    const match = text.match(/data: (\{[^\n]*\})/);
    expect(match).not.toBeNull();
    const event = JSON.parse(match![1]);
    expect(event.type).toBe("row");
    expect(typeof event.seq).toBe("number");
    expect(event.bot_id).toBeTruthy();
  });
});
