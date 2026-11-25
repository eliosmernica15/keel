import { test, expect, mockBridge, openSession, ignoreExpectedHttpError, BOT } from "./fixtures";

const step = (seq: number, path: string) => ({
  seq, bot_id: BOT.id, kind: "step", created_at: "2026-11-24T10:01:00Z",
  body: { name: "read_file", detail: path, status: "done", input: { path } },
});

const end = {
  seq: 6, bot_id: BOT.id, kind: "turn_end", created_at: "2026-11-24T10:02:00Z",
  body: { terminal_reason: "completed", duration_ms: 3200 },
};

test("work log groups real steps and exposes raw input only on demand", async ({ page, consoleErrors }) => {
  await mockBridge(page, {
    rows: [step(2, "src/a.ts"), step(3, "src/b.ts"), step(4, "src/c.ts"), step(5, "src/d.ts"), end],
  });
  await openSession(page);

  const workLog = page.getByRole("region", { name: "Work log" });
  await expect(workLog.getByText("Read 4 targets")).toBeVisible();
  const progress = page.getByRole("progressbar", { name: "Reported tool steps completed" });
  await expect(progress).toHaveAttribute("aria-valuenow", "4");

  const raw = page.locator("details").filter({ hasText: "Raw tool calls (4)" });
  await expect(raw).toBeVisible();
  await expect(raw.getByText("src/a.ts").first()).toBeHidden();
  await raw.locator("summary").click();
  await expect(raw.getByText("src/a.ts").first()).toBeVisible();
  await expect(raw).toContainText("input");
  expect(consoleErrors).toEqual([]);
});

test("a reported plan survives reload and its approval uses the once/always/never route", async ({ page, consoleErrors }) => {
  const plan = {
    seq: 2, bot_id: BOT.id, kind: "approval", created_at: "2026-11-24T10:01:00Z",
    body: {
      approval_id: "ap-plan", operation: "Apply the reported plan", status: "pending",
      steps: [{ title: "Inspect files", status: "done" }, { title: "Patch the handler", status: "active" }],
    },
  };
  const bridge = await mockBridge(page, { rows: [plan] });
  await openSession(page);

  const card = page.getByRole("region", { name: "Plan from the agent" });
  await expect(card).toBeVisible();
  await expect(card).toContainText("Inspect files");
  await expect(card).toContainText("Patch the handler");
  await page.reload();
  await expect(page.getByRole("region", { name: "Plan from the agent" })).toBeVisible();

  await card.getByRole("button", { name: "Approve once" }).click();
  await expect(card).toContainText("Decision recorded: Allowed once.");
  const decision = bridge.requests.find((r) => r.method === "POST" && /\/approvals\/ap-plan\/decide$/.test(r.path));
  expect(decision?.body).toEqual({ decision: "once" });
  expect(consoleErrors).toEqual([]);
});

test("an interrupted event stream offers an explicit reconnect", async ({ page, consoleErrors }) => {
  const bridge = await mockBridge(page, { rows: [], sseError: true, holdSse: true });
  ignoreExpectedHttpError(page, /\/api\/bridge\/events$/);
  await openSession(page);
  // Fail after the session is selected, so selecting it does not clear the
  // interruption banner that the stream reports.
  bridge.releaseSse();

  await expect(page.getByText(/event stream was interrupted/)).toBeVisible();
  const before = bridge.count("GET", /^events$/);
  await page.getByRole("button", { name: "Reconnect" }).click();
  await expect.poll(() => bridge.count("GET", /^events$/)).toBeGreaterThan(before);
  await expect(page.getByText(/event stream was interrupted/)).toHaveCount(0);
  expect(consoleErrors).toEqual([]);
});

test("a delayed transcript load shows a real loading state before the empty state", async ({ page, consoleErrors }) => {
  await mockBridge(page, { rows: [], rowsDelayMs: 700 });
  await openSession(page);
  await expect(page.getByLabel("Loading conversation")).toBeVisible();
  await expect(page.getByText("No messages yet")).toBeVisible();
  await expect(page.getByLabel("Loading conversation")).toHaveCount(0);
  expect(consoleErrors).toEqual([]);
});
