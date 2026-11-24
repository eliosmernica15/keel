import { test, expect, mockBridge, openSession, BOT } from "./fixtures";

const message = (seq: number, role: string, content: string) => ({
  seq, bot_id: BOT.id, kind: "message", role, body: { content },
  created_at: "2026-11-24T10:00:00Z",
});

const rows = [
  message(1, "user", "Please investigate the login bug"),
  message(2, "assistant", "I will look at auth.py and run the tests."),
  message(3, "assistant", "Found needle in the trace."),
  message(4, "user", "Can you fix it?"),
  message(5, "assistant", "Another needle appeared in the log."),
];

test("session search covers loaded history, is keyboard-driven and never calls the bridge", async ({ page, consoleErrors }) => {
  const bridge = await mockBridge(page, { rows });
  await openSession(page);
  await page.getByRole("button", { name: "Search conversation" }).click();

  const input = page.getByRole("textbox", { name: "Search conversation" });
  await expect(input).toBeFocused();
  await input.fill("needle");
  await expect(page.getByText("2 matches", { exact: true })).toBeVisible();

  const results = page.getByRole("list", { name: "Search results" }).getByRole("button");
  await expect(results).toHaveCount(2);
  await expect(results.first()).toContainText("Found needle in the trace.");

  await input.press("Enter");
  await expect(results.first()).toHaveAttribute("aria-current", "true");
  await expect(page.locator('[data-match-active="true"]')).toHaveCount(1);
  await expect(page.locator('[data-match-active="true"]')).toContainText("Found needle");

  await input.press("Enter");
  await expect(results.nth(1)).toHaveAttribute("aria-current", "true");
  await expect(page.locator('[data-match-active="true"]')).toContainText("Another needle");

  await input.press("Shift+Enter");
  await expect(results.first()).toHaveAttribute("aria-current", "true");
  await input.press("Escape");
  await expect(input).toHaveCount(0);

  // Search is client-side over already loaded rows: no extra transcript GET.
  expect(bridge.count("GET", /\/rows$/)).toBe(1);
  expect(consoleErrors).toEqual([]);
});

test("Ctrl+F opens and focuses search; no-match and close states are explicit", async ({ page, consoleErrors }) => {
  await mockBridge(page, { rows });
  await openSession(page);
  await page.keyboard.press("Control+f");
  const input = page.getByRole("textbox", { name: "Search conversation" });
  await expect(input).toBeVisible();
  await expect(input).toBeFocused();

  await input.fill("not-in-this-session");
  await expect(page.getByText("No matches", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Next match" })).toBeDisabled();
  await expect(page.getByRole("button", { name: "Previous match" })).toBeDisabled();

  await input.fill("NEEDLE");
  await expect(page.getByText("2 matches", { exact: true })).toBeVisible();
  await input.press("ArrowUp");
  await expect(page.getByRole("list", { name: "Search results" }).getByRole("button").nth(1)).toHaveAttribute("aria-current", "true");
  await input.press("ArrowDown");
  await expect(page.getByRole("list", { name: "Search results" }).getByRole("button").first()).toHaveAttribute("aria-current", "true");

  await page.getByRole("button", { name: "Close search" }).click();
  await expect(input).toHaveCount(0);
  expect(consoleErrors).toEqual([]);
});
