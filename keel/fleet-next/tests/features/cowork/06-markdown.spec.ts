import { test, expect, mockBridge, openSession } from "./fixtures";

const message = (seq: number, role: string, content: string) => ({
  seq, bot_id: "bot-1", kind: "message", role, body: { content }, created_at: "2026-11-24T10:00:00Z",
});

test("Markdown renders tables, fenced code and ordered lists from real rows", async ({ page, consoleErrors }) => {
  const content = [
    "## Result",
    "",
    "| File | Status |",
    "| --- | --- |",
    "| `src/a.ts` | done |",
    "| `src/b.ts` | pending |",
    "",
    "```ts",
    "const answer = 42;",
    "```",
    "",
    "1. first step",
    "2. second step",
  ].join("\n");
  await mockBridge(page, { rows: [message(1, "assistant", content)] });
  await openSession(page);

  await expect(page.getByRole("heading", { name: "Result" })).toBeVisible();
  const table = page.locator("table");
  await expect(table).toBeVisible();
  await expect(table.locator("th")).toHaveText(["File", "Status"]);
  await expect(table.locator("tbody tr")).toHaveCount(2);
  await expect(page.locator("pre code").filter({ hasText: "const answer = 42;" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Copy code block" })).toBeVisible();
  await expect(page.locator("ol li")).toContainText(["first step", "second step"]);
  expect(consoleErrors).toEqual([]);
});

test("consecutive messages are grouped by role without losing individual actions", async ({ page, consoleErrors }) => {
  await mockBridge(page, {
    rows: [
      message(1, "user", "first question"),
      message(2, "user", "second question"),
      message(3, "assistant", "first answer"),
      message(4, "assistant", "second answer"),
    ],
  });
  await openSession(page);

  await expect(page.getByRole("group", { name: "2 messages from You" })).toBeVisible();
  await expect(page.getByRole("group", { name: "2 messages from Audit task" })).toBeVisible();
  await expect(page.getByText("first question")).toBeVisible();
  await expect(page.getByText("second answer")).toBeVisible();
  await expect(page.getByRole("button", { name: "Copy message" })).toHaveCount(4);
  expect(consoleErrors).toEqual([]);
});

test("deliverable rows link to real download and preview routes", async ({ page, consoleErrors }) => {
  await mockBridge(page, {
    rows: [{
      seq: 2, bot_id: "bot-1", kind: "deliverable", created_at: "2026-11-24T10:00:00Z",
      body: { files: [{ id: "lib-9", name: "report.png", type: "image/png" }] },
    }],
  });
  await openSession(page);

  await expect(page.getByRole("link", { name: /report\.png/ })).toHaveAttribute("href", "/api/bridge/library/lib-9/download");
  await expect(page.locator('img[alt="Preview of report.png"]')).toHaveAttribute("src", "/api/bridge/library/lib-9/preview");
  expect(consoleErrors).toEqual([]);
});
