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
  await scroll.evaluate((el: Element) => { (el as HTMLElement).scrollTop = 0; });

  // Capture an actual row (not just geometry): its seq must survive paging and
  // keep the same viewport offset afterwards.
  const anchor = await scroll.evaluate((el: Element) => {
    const root = el as HTMLElement;
    const top = root.getBoundingClientRect().top;
    const node = Array.from(root.querySelectorAll<HTMLElement>("[data-cowork-seq]")).find((candidate) => {
      const rect = candidate.getBoundingClientRect();
      return rect.bottom > top + 1 && rect.top < top + root.clientHeight;
    });
    return node
      ? { seq: node.getAttribute("data-cowork-seq") ?? "", offset: node.getBoundingClientRect().top - top }
      : null;
  });
  expect(anchor, "a visible row anchor must exist before paging").not.toBeNull();
  if (!anchor) return;

  await earlier.click();
  await expect(bubbles).toHaveCount(250);
  await expect(earlier).toContainText("950 hidden");

  const anchoredOffset = await scroll.evaluate((el: Element, seq: string) => {
    const root = el as HTMLElement;
    const node = Array.from(root.querySelectorAll<HTMLElement>("[data-cowork-seq]"))
      .find((candidate) => candidate.getAttribute("data-cowork-seq") === seq);
    return node ? node.getBoundingClientRect().top - root.getBoundingClientRect().top : null;
  }, anchor.seq);
  expect(anchoredOffset, `anchor seq ${anchor.seq} must still be rendered`).not.toBeNull();
  expect(Math.abs((anchoredOffset ?? 0) - anchor.offset)).toBeLessThanOrEqual(10);

  // Collapsing the window bottom-aligns the newest row through the same anchor.
  await page.getByRole("button", { name: "Jump to latest" }).click();
  await expect(bubbles).toHaveCount(150);
  await expect(page.getByText("last-message")).toBeVisible();
  const gapToBottom = await scroll.evaluate((el: Element) => {
    const root = el as HTMLElement;
    const nodes = Array.from(root.querySelectorAll<HTMLElement>("[data-cowork-seq]"));
    const last = nodes[nodes.length - 1];
    return root.getBoundingClientRect().top + root.clientHeight - last.getBoundingClientRect().bottom;
  });
  expect(Math.abs(gapToBottom)).toBeLessThanOrEqual(10);
  await expect.poll(() => scroll.evaluate((el: Element) => {
    const root = el as HTMLElement;
    return root.scrollHeight - root.scrollTop - root.clientHeight;
  })).toBeLessThan(12);
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
