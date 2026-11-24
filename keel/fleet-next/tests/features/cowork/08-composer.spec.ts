import { test, expect, mockBridge, openSession, ignoreExpectedHttpError } from "./fixtures";

test("send uses the selected permission mode and the real queued payload", async ({ page, consoleErrors }) => {
  const bridge = await mockBridge(page, { rows: [] });
  await openSession(page);
  await page.getByLabel("Permission mode").selectOption("plan");
  const textarea = page.getByRole("textbox", { name: "Message Keel" });
  await textarea.fill("inspect the repo");
  await textarea.press("Enter");

  await expect.poll(() => bridge.count("POST", /\/messages$/)).toBe(1);
  const sent = bridge.requests.find((r) => r.method === "POST" && /\/messages$/.test(r.path));
  expect(sent?.body).toEqual({ content: "inspect the repo", mode: "plan" });
  await expect(textarea).toHaveValue("");
  expect(consoleErrors).toEqual([]);
});

test("a failed send keeps the attempt and Retry resends the same payload", async ({ page, consoleErrors }) => {
  const bridge = await mockBridge(page, {
    rows: [],
    messagesError: { status: 500, body: { error: "provider_not_configured", detail: "Provider not configured" } },
  });
  ignoreExpectedHttpError(page, /\/api\/bridge\/bots\/bot-1\/messages$/);
  await openSession(page);
  const textarea = page.getByRole("textbox", { name: "Message Keel" });
  await textarea.fill("retry me");
  await textarea.press("Enter");

  await expect(page.getByRole("alert").filter({ hasText: "Message failed: Provider not configured" }).first()).toBeVisible();
  bridge.messagesError = undefined;
  await page.getByRole("button", { name: "Retry" }).last().click();
  await expect.poll(() => bridge.count("POST", /\/messages$/)).toBe(2);
  const sends = bridge.requests.filter((r) => r.method === "POST" && /\/messages$/.test(r.path));
  expect(sends[1].body).toEqual(sends[0].body);
  expect(consoleErrors).toEqual([]);
});

test("Stop calls the bridge cancel route while a turn is in flight", async ({ page, consoleErrors }) => {
  const bridge = await mockBridge(page, { rows: [], messagesDelayMs: 1200 });
  await openSession(page);
  await page.getByRole("textbox", { name: "Message Keel" }).fill("long running task");
  await page.getByRole("button", { name: "Send message" }).click();

  await expect(page.getByRole("button", { name: "Stop the current turn" })).toBeVisible();
  await page.getByRole("button", { name: "Stop the current turn" }).click();
  await expect.poll(() => bridge.count("POST", /\/cancel$/)).toBe(1);
  expect(consoleErrors).toEqual([]);
});

test("model selector persists a real model change through the bot update route", async ({ page, consoleErrors }) => {
  const bridge = await mockBridge(page, { rows: [], models: ["claude-sonnet-4-5", "gpt-4o"] });
  await openSession(page);
  await page.getByLabel("Model for this task").selectOption("gpt-4o");
  await expect.poll(() => bridge.count("POST", /\/update$/)).toBe(1);
  const update = bridge.requests.find((r) => r.method === "POST" && /\/update$/.test(r.path));
  expect(update?.body).toEqual({ model: "gpt-4o" });
  await expect(page.getByLabel("Model for this task")).toHaveValue("gpt-4o");
  expect(consoleErrors).toEqual([]);
});
