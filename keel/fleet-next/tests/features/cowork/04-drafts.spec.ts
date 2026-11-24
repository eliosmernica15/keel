import { test, expect, mockBridge, openSession, BOT } from "./fixtures";

const BOT2 = { ...BOT, id: "bot-2", name: "Second task", provider: "openai", model: "gpt-4o" };

test("composer drafts are scoped per session and survive reload", async ({ page, consoleErrors }) => {
  await mockBridge(page, { bots: [BOT, BOT2] });
  await openSession(page, BOT.id);
  const textarea = page.getByRole("textbox", { name: "Message Keel" });

  await textarea.fill("draft for first task");
  await page.getByRole("button", { name: "Back to Cowork home" }).click();
  await page.locator('select[aria-label="Open an existing task"]').selectOption(BOT2.id);
  await page.getByRole("textbox", { name: "Message Keel" }).fill("draft for second task");

  await page.getByRole("button", { name: "Back to Cowork home" }).click();
  await page.locator('select[aria-label="Open an existing task"]').selectOption(BOT.id);
  await expect(page.getByRole("textbox", { name: "Message Keel" })).toHaveValue("draft for first task");

  await page.reload();
  await expect(page.getByRole("textbox", { name: "Message Keel" })).toHaveValue("draft for first task");
  const stored = await page.evaluate(() => localStorage.getItem("keel-draft:bot-1"));
  expect(stored).toBe("draft for first task");
  expect(consoleErrors).toEqual([]);
});
