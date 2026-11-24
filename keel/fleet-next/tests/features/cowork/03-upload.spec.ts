import { test, expect, mockBridge, openSession, ignoreExpectedHttpError } from "./fixtures";

const userRow = { seq: 1, bot_id: "bot-1", kind: "message", role: "user", body: { content: "hello" }, created_at: "2026-11-24T10:00:00Z" };

test("failed library upload is never claimed as sent; retry uploads for real", async ({ page, consoleErrors }) => {
  const bridge = await mockBridge(page, { rows: [userRow], libraryFailures: 1, libraryDelayMs: 350 });
  ignoreExpectedHttpError(page, /\/api\/bridge\/library$/);
  await openSession(page);

  await page.locator('input[type="file"]').setInputFiles({
    name: "notes.txt", mimeType: "text/plain", buffer: Buffer.from("hello world"),
  });
  await expect(page.getByText("notes.txt")).toBeVisible();
  await page.getByRole("textbox", { name: "Message Keel" }).fill("first attempt");
  await page.getByRole("button", { name: "Send message" }).click();

  // Real XHR progress is observable while the body is in flight.
  await expect(page.getByRole("progressbar", { name: "Uploading notes.txt" })).toBeVisible();
  await expect(page.getByText("Quota exceeded")).toBeVisible();
  await expect(page.getByText("Failed", { exact: true })).toBeVisible();

  const firstSend = bridge.requests.find((r) => r.method === "POST" && /\/messages$/.test(r.path));
  expect((firstSend?.body as { content: string }).content).not.toContain("notes.txt");

  await page.locator('[aria-label="Files for this message"]').getByRole("button", { name: "Retry" }).click();
  await expect(page.getByText("In library")).toBeVisible();

  await page.getByRole("textbox", { name: "Message Keel" }).fill("second attempt");
  await page.getByRole("button", { name: "Send message" }).click();
  const sends = bridge.requests.filter((r) => r.method === "POST" && /\/messages$/.test(r.path));
  expect(sends).toHaveLength(2);
  expect((sends[1].body as { content: string }).content).toContain("notes.txt");
  expect(bridge.count("POST", /^library$/)).toBe(2);
  expect(consoleErrors).toEqual([]);
});
