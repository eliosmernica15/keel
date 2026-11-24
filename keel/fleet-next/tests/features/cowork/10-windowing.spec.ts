import { test, expect, mockBridge, openSession, streamFrame, BOT } from "./fixtures";

function longTranscript(buriedAt?: number): Record<string, unknown>[] {
  const out: Record<string, unknown>[] = [{
    seq: 1, bot_id: BOT.id, kind: "message", role: "user",
    body: { content: buriedAt === 1 ? "buried-needle" : "first-message" },
    created_at: "2026-11-24T10:00:00Z",
  }];
  for (let i = 2; i <= 1199; i++) {
    out.push({
      seq: i, bot_id: BOT.id, kind: "message", role: "assistant",
      body: { content: buriedAt === i ? "buried-needle" : `filler ${i}` },
      created_at: "2026-11-24T10:01:00Z",
    });
  }
  out.push({
    seq: 1200, bot_id: BOT.id, kind: "message", role: "assistant",
    body: { content: "last-message" }, created_at: "2026-11-24T10:02:00Z",
  });
  return out;
}

test("1200 loaded rows are windowed: newest shown, older added a page at a time without losing scroll", async ({ page, consoleErrors }) => {
  await mockBridge(page, { rows: longTranscript() });
  await openSession(page);

  const bubbles = page.locator("article[data-cowork-seq]");
  await expect(page.getByText("last-message")).toBeVisible();
  await expect(page.getByText("first-message")).toHaveCount(0);
  await expect(bubbles).toHaveCount(150);
  const earlier = page.getByRole("button", { name: /Show earlier messages/ });
  await expect(earlier).toContainText("1050 hidden");

  const scroll = page.getByRole("log", { name: "Cowork conversation" });
  await scroll.evaluate((el) => { el.scrollTop = 0; });
  const before = await scroll.evaluate((el) => el.scrollHeight - el.scrollTop);

  await earlier.click();
  await expect(bubbles).toHaveCount(250);
  await expect(earlier).toContainText("950 hidden");
  // Older content was inserted above the viewport: distance from the top stays
  // put, so the user keeps reading the same message.
  // Tolerance covers sub-pixel/animation layout changes when the first group
  // (with its own heading) enters the window.
  await expect.poll(() => scroll.evaluate((el) => el.scrollHeight - el.scrollTop)).toBeGreaterThan(before - 50);
  await expect.poll(() => scroll.evaluate((el) => el.scrollHeight - el.scrollTop)).toBeLessThan(before + 50);

  await page.getByRole("button", { name: "Jump to latest" }).click();
  await expect(bubbles).toHaveCount(150);
  await expect(page.getByText("last-message")).toBeVisible();
  await expect.poll(() => scroll.evaluate((el) => el.scrollHeight - el.scrollTop - el.clientHeight)).toBeLessThan(12);
  expect(consoleErrors).toEqual([]);
});

test("streaming tokens do not re-render the windowed transcript", async ({ page, consoleErrors }) => {
  const bridge = await mockBridge(page, {
    rows: longTranscript(),
    holdSse: true,
    sse: Array.from({ length: 12 }, (_, i) => streamFrame(BOT.id, `token${i} `)).join(""),
  });
  await openSession(page);
  await expect(page.locator("[data-timeline-renders]")).toBeVisible();
  await expect(page.locator("article[data-cowork-seq]")).toHaveCount(150);
  const rendersBefore = Number(await page.locator("[data-timeline-renders]").getAttribute("data-timeline-renders"));

  bridge.releaseSse();
  await expect(page.locator("[data-cowork-live]")).toContainText("token10 token11 ");
  await expect(page.locator("[data-cowork-live]")).toContainText("streaming");
  await expect(page.locator("article[data-cowork-seq]")).toHaveCount(150);
  const rendersAfter = Number(await page.locator("[data-timeline-renders]").getAttribute("data-timeline-renders"));
  // Twelve tokens cause only the one-off "turn became live" prop change
  // (double-invoked in StrictMode), never a render per token. The text is
  // updated by the isolated bubble alone.
  expect(rendersAfter - rendersBefore).toBeLessThanOrEqual(3);
  expect(consoleErrors).toEqual([]);
});

test("search finds a message outside the window and expands to it", async ({ page, consoleErrors }) => {
  await mockBridge(page, { rows: longTranscript(7) });
  await openSession(page);
  await expect(page.getByText("buried-needle", { exact: true })).toHaveCount(0);

  await page.getByRole("button", { name: "Search conversation" }).click();
  await page.getByRole("textbox", { name: "Search conversation" }).fill("buried-needle");
  await expect(page.getByText("1 match", { exact: true })).toBeVisible();
  await page.getByRole("list", { name: "Search results" }).getByRole("button").click();

  await expect(page.getByText("buried-needle", { exact: true })).toBeVisible();
  await expect(page.locator('[data-match-active="true"]')).toContainText("buried-needle");
  await expect(page.getByRole("button", { name: /Show earlier messages/ })).toHaveCount(0);
  expect(consoleErrors).toEqual([]);
});
