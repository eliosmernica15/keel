import { test, expect, openApp, gotoTop } from "./fixtures";
import type { Page } from "@playwright/test";

/**
 * Independent-QA coverage for the NEW completion-round requirements that were
 * not part of the original 131-test suite:
 *   - Fleet: kanban board, org/delegation map, live wall, cost honest states
 *   - Cowork: session search, export, bounded history
 *   - Onboarding: contextual help / troubleshooting
 *   - Duet: builder/reviewer identity and reviewer comment-only mode
 *
 * Every assertion is against user-visible behaviour of the real app. No app
 * source is modified by this spec.
 */

/* ------------------------------------------------------------------ helpers */

async function mockCowork(page: Page, rows: Record<string, unknown>[]): Promise<void> {
  const bot = {
    id: "qa-bot", name: "QA task", role: "Assistant", engine: "echo",
    provider: "auto", model: "", state: "idle",
  };
  let eventsCalls = 0;
  await page.route("**/api/bridge/**", async (route) => {
    const url = new URL(route.request().url());
    const path = url.pathname.replace(/^\/api\/bridge\//, "");
    const json = (body: unknown) =>
      route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(body) });
    if (path === "bots") return json({ bots: [bot] });
    if (path === "bots/qa-bot/rows") return json({ bot_id: bot.id, rows });
    if (path === "events") {
      eventsCalls += 1;
      if (eventsCalls > 1) await new Promise<void>(() => {}); // hold reconnect open
      return route.fulfill({ status: 200, contentType: "text/event-stream", body: ": ping\n\n" });
    }
    if (path === "providers") return json({ providers: [] });
    if (path === "projects") return json({ projects: [] });
    if (path === "library") return json({ files: [] });
    if (path === "usage") return json({ tokens: 0, requests: 0 });
    if (path === "providers/catalog") return json({ models: [] });
    return json({});
  });
}

const messageRow = (seq: number, role: string, content: string) => ({
  seq, bot_id: "qa-bot", kind: "message", role,
  body: { content }, created_at: "2026-11-24T10:00:0" + (seq % 10) + "Z",
});

async function openSession(page: Page, rows: Record<string, unknown>[]): Promise<void> {
  await mockCowork(page, rows);
  await openApp(page);
  await page.getByLabel("Open an existing task").selectOption("qa-bot");
  await expect(page.getByRole("log", { name: "Cowork conversation" })).toBeVisible();
}

/* --------------------------------------------------------------- Fleet views */

test("Fleet kanban, delegation map, live wall and cost tabs render real panels, not dead controls", async ({ page, consoleErrors }) => {
  void consoleErrors;
  await openApp(page);
  await gotoTop(page, "Fleet");

  const views: Array<[string, string]> = [
    ["Board", "Task board"],
    ["Delegation map", "Agent organization"],
    ["Live wall", "Live agent wall"],
    ["Cost", "Cost per agent"],
  ];
  for (const [tab, heading] of views) {
    await page.getByRole("tab", { name: new RegExp(`^${tab}`) }).click();
    await expect(page.getByRole("heading", { name: heading })).toBeVisible();
  }

  // Honest states: nothing invented where the bridge has no data.
  await page.getByRole("tab", { name: /^Delegation map/ }).click();
  await expect(page.getByText("Organization hierarchy is unavailable from the bridge.")).toBeVisible();
  await expect(page.getByText(/A nested org chart would be fabricated/)).toBeVisible();

  await page.getByRole("tab", { name: /^Cost/ }).click();
  await expect(page.getByText("Cost per agent")).toBeVisible();
  await expect(page.getByText(/Token counts are not a cost estimate/)).toBeVisible();
  // Either honest state is acceptable: bridge-reported cost, or an explicit
  // "not reported" state. No inferred/estimated dollar value may be shown.
  await expect(page.getByText(/Not reported by bridge|Reported cost by agent/).first()).toBeVisible();

  await page.getByRole("tab", { name: /^Live wall/ }).click();
  await expect(page.getByText(/An agent with no reported activity stays/)).toBeVisible();
});

test("Fleet board columns are the bridge's real task statuses", async ({ page, consoleErrors }) => {
  void consoleErrors;
  await openApp(page);
  await gotoTop(page, "Fleet");
  await page.getByRole("tab", { name: /^Board/ }).click();
  await expect(page.getByRole("heading", { name: "Task board" })).toBeVisible();
  for (const column of ["Pending", "In progress", "Completed", "Failed", "Cancelled"]) {
    await expect(page.getByRole("region", { name: `${column} column` })).toBeVisible();
  }
  await expect(page.getByRole("group", { name: "Filter by reported priority" })).toBeVisible();
});

/* ------------------------------------------------------------- Cowork search */

test("Cowork conversation search opens with Ctrl+F, counts matches, steps and closes with Escape", async ({ page, consoleErrors }) => {
  void consoleErrors;
  await openSession(page, [
    messageRow(1, "user", "needle alpha one"),
    messageRow(2, "assistant", "unrelated reply"),
    messageRow(3, "user", "needle beta two"),
  ]);

  await page.keyboard.press("Control+f");
  const panel = page.getByRole("region", { name: "Conversation search" });
  await expect(panel).toBeVisible();
  const input = page.getByRole("textbox", { name: "Search conversation" });
  await expect(input).toBeFocused();
  await input.fill("needle");
  await expect(panel.getByRole("status")).toContainText("2 matches");

  await page.getByRole("button", { name: "Next match" }).click();
  await expect(panel.locator('[aria-current="true"]').first()).toBeVisible();
  // Escape is handled by the search input; refocus it before closing here.
  await input.focus();
  await page.keyboard.press("Escape");
  await expect(panel).toHaveCount(0);
});

test("Cowork search Escape also closes after using the match navigation buttons", async ({ page, consoleErrors }) => {
  void consoleErrors;
  await openSession(page, [messageRow(1, "user", "needle alpha"), messageRow(2, "user", "needle beta")]);
  await page.keyboard.press("Control+f");
  const panel = page.getByRole("region", { name: "Conversation search" });
  await page.getByRole("textbox", { name: "Search conversation" }).fill("needle");
  await page.getByRole("button", { name: "Next match" }).click();
  await expect(panel).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(panel).toHaveCount(0);
});

test("Cowork export link targets the real bridge export route and import is honestly unavailable", async ({ page, consoleErrors }) => {
  void consoleErrors;
  await openSession(page, [messageRow(1, "user", "hello export")]);
  const link = page.locator('a[title="Export this conversation as Markdown"]');
  await expect(link).toBeVisible();
  await expect(link).toHaveAttribute("href", "/api/bridge/bots/qa-bot/export.md");
  await expect(link).toHaveAttribute("download", "");
  await expect(page.getByRole("note")).toContainText("Import unavailable");
});

test("Cowork long history is windowed and search reaches rows outside the window", async ({ page, consoleErrors }) => {
  void consoleErrors;
  const rows = Array.from({ length: 400 }, (_, i) =>
    messageRow(i + 1, i % 2 ? "assistant" : "user", i === 10 ? "needle hidden early" : `message ${i + 1}`));
  await openSession(page, rows);
  const log = page.getByRole("log", { name: "Cowork conversation" });
  // Only the newest 150 rows are in the DOM, not all 400.
  await expect(log.locator("[data-cowork-seq]")).toHaveCount(150);
  const earlier = page.getByRole("button", { name: /Show earlier messages/ });
  await expect(earlier).toContainText("250 hidden");
  await earlier.click();
  await expect(log.locator("[data-cowork-seq]")).toHaveCount(250);

  // Search indexes every loaded row, including one far outside the window.
  await page.keyboard.press("Control+f");
  const panel = page.getByRole("region", { name: "Conversation search" });
  await page.getByRole("textbox", { name: "Search conversation" }).fill("needle hidden early");
  await expect(panel.getByRole("status")).toContainText("1 match");
  await page.getByRole("button", { name: "Next match" }).click();
  await expect(page.locator('[data-cowork-seq="11"][data-match-active="true"]')).toBeVisible();
});

/* --------------------------------------------------------- Onboarding help */

test("Onboarding Help & troubleshooting reads the bridge and navigates to real surfaces", async ({ page, consoleErrors }) => {
  void consoleErrors;
  await openApp(page, { onboardingDone: false });
  await expect(page.locator('[role="dialog"][aria-labelledby="onboarding-title"]')).toBeVisible();

  await page.getByRole("button", { name: "Help & troubleshooting" }).click();
  const help = page.getByRole("dialog", { name: "Help & troubleshooting" });
  await expect(help).toBeVisible();
  // Probe result is a real read, not a cached badge.
  await expect(help.getByRole("status").first()).toBeVisible();
  for (const card of ["Bridge is unavailable", "No provider is configured", "Workspace is not trusted"]) {
    await expect(help.locator("section").filter({ has: page.getByRole("heading", { name: card }) })).toBeVisible();
  }

  await page.keyboard.press("Escape");
  await expect(help).toHaveCount(0);

  await page.getByRole("button", { name: "Help & troubleshooting" }).click();
  await page.getByRole("button", { name: "Open Code workspace" }).click();
  await expect(page.locator(".keel-statusbar")).toContainText("Surface: code");
});

/* ------------------------------------------------------------- Duet identity */

async function openReviewPair(page: Page): Promise<ReturnType<typeof page.locator>> {
  await openApp(page);
  await gotoTop(page, "Duet");
  await page.getByRole("button", { name: "Open review pair (builder and reviewer)" }).click();
  const pair = page.locator('[data-pair-root="true"]');
  await expect(pair).toBeVisible();
  await expect(pair.getByRole("heading", { name: "Review pair" })).toBeVisible();
  return pair;
}

test("Duet review pair shows builder/reviewer identity and an honest state with the real bridge", async ({ page, consoleErrors }) => {
  void consoleErrors;
  const pair = await openReviewPair(page);
  await expect(pair.getByRole("heading", { name: "Builder", exact: true })).toBeVisible();
  await expect(pair.getByRole("heading", { name: "Independent reviewer", exact: true })).toBeVisible();
  await expect(pair).toContainText(/not configured by this bridge|Comment-only/);
  // The reviewer is comment-only: this pane never exposes an edit/write/run control.
  await expect(pair.getByRole("button", { name: /save file|write file|run command|execute|apply|trust/i })).toHaveCount(0);
});

test("Duet reviewer findings are comment-only rows, never editable state", async ({ page, consoleErrors }) => {
  void consoleErrors;
  let eventsCalls = 0;
  await page.route("**/api/bridge/**", async (route) => {
    const path = new URL(route.request().url()).pathname.replace(/^\/api\/bridge\//, "");
    const json = (body: unknown) =>
      route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(body) });
    if (path === "bots") return json({ bots: [
      { id: "builder-1", name: "Build agent", role: "builder", engine: "echo", provider: "auto" },
      { id: "reviewer-1", name: "Review agent", role: "independent reviewer", engine: "echo", provider: "auto" },
    ] });
    if (path === "bots/builder-1/rows") return json({ rows: [
      { seq: 1, kind: "message", role: "user", body: { content: "Please review this diff" }, created_at: "2026-11-24T10:00:00Z" },
    ] });
    if (path === "bots/reviewer-1/rows") return json({ rows: [
      { seq: 2, kind: "message", role: "assistant", body: { content: "Finding: handle the null case" }, created_at: "2026-11-24T10:01:00Z" },
    ] });
    if (path === "events") {
      eventsCalls += 1;
      if (eventsCalls > 1) await new Promise<void>(() => {});
      return route.fulfill({ status: 200, contentType: "text/event-stream", body: ": ping\n\n" });
    }
    if (path === "projects") return json({ projects: [] });
    if (path === "providers") return json({ providers: [] });
    return json({});
  });

  const pair = await openReviewPair(page);
  await expect(pair.getByText("Comment-only", { exact: true }).first()).toBeVisible();
  await expect(pair.getByText("Please review this diff")).toBeVisible();
  await expect(pair.getByText("Finding: handle the null case")).toBeVisible();
  await expect(pair.getByText(/Inferred from the reviewer's last real message row/)).toHaveCount(0);
  await expect(pair.getByText(/The bridge has no review-status field/)).toBeVisible();
  await expect(pair.getByRole("button", { name: /save|write|execute|apply/i })).toHaveCount(0);
});
