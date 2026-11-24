import { test, expect, mockBridge, openSession, BOT } from "./fixtures";

const askRow = (id: string, question: string, options: string[]) => ({
  seq: id === "ask_1" ? 2 : 3,
  bot_id: BOT.id,
  kind: "ask",
  body: { ask_id: id, question, options, status: "pending" },
  created_at: "2026-11-24T10:00:00Z",
});

test("asking a question sends the real answer payload and survives reload", async ({ page, consoleErrors }) => {
  const bridge = await mockBridge(page, {
    rows: [askRow("ask_1", "Which environment should I use?", ["Staging", "Production"])],
  });
  await openSession(page);

  const card = page.getByRole("region", { name: "Agent question" });
  await expect(card.getByText("Which environment should I use?")).toBeVisible();
  await card.getByRole("button", { name: "Staging" }).click();
  await expect(page.getByText("Answered")).toBeVisible();

  const answered = bridge.requests.find((r) => r.method === "POST" && /\/asks\/ask_1\/answer$/.test(r.path));
  expect(answered?.body).toEqual({ answer: "Staging" });

  // The bridge does not rewrite ask rows. The confirmed answer id is kept in
  // frontend storage, so a reload must not resurrect a stale question card.
  await page.reload();
  await expect(page.getByRole("region", { name: "Agent question" })).toHaveCount(0);
  await expect(page.getByText("Answered")).toBeVisible();
  await expect(page.getByText("Waiting for you")).toHaveCount(0);
  expect(consoleErrors).toEqual([]);
});

test("typed answers are sent unchanged as strings", async ({ page, consoleErrors }) => {
  const bridge = await mockBridge(page, { rows: [askRow("ask_2", "Name the file", [])] });
  await openSession(page);

  await page.getByPlaceholder("Type your answer…").fill("notes.md");
  await page.getByRole("button", { name: "Answer" }).click();
  const answered = bridge.requests.find((r) => r.method === "POST" && /\/asks\/ask_2\/answer$/.test(r.path));
  expect(answered?.body).toEqual({ answer: "notes.md" });
  expect(consoleErrors).toEqual([]);
});
