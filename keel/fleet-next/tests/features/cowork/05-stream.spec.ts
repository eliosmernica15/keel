import { test, expect, mockBridge, openSession, rowFrame, streamFrame, BOT } from "./fixtures";

const userRow = { seq: 1, bot_id: BOT.id, kind: "message", role: "user", body: { content: "start" }, created_at: "2026-11-24T10:00:00Z" };
const assistantRow = (seq = 2) => ({
  seq, bot_id: BOT.id, kind: "message", role: "assistant",
  body: { content: "A streamed answer" }, created_at: "2026-11-24T10:01:00Z",
});

test("named row frames are deduped by seq while deltas are batched into one bubble", async ({ page, consoleErrors }) => {
  const bridge = await mockBridge(page, {
    rows: [userRow],
    holdSse: true,
    sse: [
      rowFrame(assistantRow()),
      rowFrame(assistantRow()), // replayed cursor — must not cause a second reload
      streamFrame(BOT.id, "Hello "),
      streamFrame(BOT.id, "from stream"),
    ].join(""),
  });
  await openSession(page);
  const before = bridge.count("GET", /\/rows$/);

  bridge.releaseSse();
  await expect(page.getByText("Hello from stream")).toBeVisible();
  await expect(page.getByText("streaming")).toBeVisible();
  await expect.poll(() => bridge.count("GET", /\/rows$/)).toBe(before + 1);
  expect(consoleErrors).toEqual([]);
});

test("turn_end produces a real finish-of-turn summary from row bodies", async ({ page, consoleErrors }) => {
  const step = {
    seq: 2, bot_id: BOT.id, kind: "step", created_at: "2026-11-24T10:01:00Z",
    body: { name: "write_file", path: "src/app.ts", status: "done" },
  };
  const end = {
    seq: 3, bot_id: BOT.id, kind: "turn_end", created_at: "2026-11-24T10:02:00Z",
    body: {
      terminal_reason: "completed", duration_ms: 4200,
      usage: { input_tokens: 1234, output_tokens: 56 },
    },
  };
  const bridge = await mockBridge(page, {
    rows: [],
    holdSse: true,
    sse: [rowFrame(step), rowFrame(end)].join(""),
  });
  await openSession(page);
  await expect(page.getByText("No messages yet")).toBeVisible();
  // The bridge persists these rows; after the SSE turn_end the UI refetches
  // them instead of inventing a summary from the stream itself.
  bridge.setRows([step, end]);
  bridge.releaseSse();

  await expect(page.getByRole("region", { name: "Turn summary" })).toBeVisible();
  await expect(page.getByText("src/app.ts")).toBeVisible();
  await expect(page.getByText("1,234 in · 56 out tokens")).toBeVisible();
  await expect(page.getByRole("region", { name: "Turn summary" }).getByText("4s", { exact: true })).toBeVisible();
  await expect(page.getByRole("region", { name: "Turn summary" }).getByText("Turn complete", { exact: true })).toBeVisible();
  expect(consoleErrors).toEqual([]);
});
