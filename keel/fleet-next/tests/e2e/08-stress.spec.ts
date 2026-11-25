import type { Page } from "@playwright/test";
import { test, expect, gotoDestination, openApp } from "./fixtures";

/**
 * Large-data stress tests. All bridge data is injected with page.route
 * fixtures: no bridge mutation, no provider credential, no network write.
 * A catch-all keeps unrelated endpoints deterministic so a busy shared local
 * bridge cannot turn into 504 console noise during a stress measurement.
 */

async function stubBridge(page: Page) {
  // Registered first: the specific routes below take precedence.
  await page.route("**/api/bridge/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path.endsWith("/events")) {
      await route.fulfill({ status: 200, contentType: "text/event-stream", body: "" });
      return;
    }
    await route.fulfill({ status: 200, contentType: "application/json", body: "{}" });
  });
}

async function measureIdle(page: Page, ms = 1500) {
  const cdp = await page.context().newCDPSession(page);
  await cdp.send("Performance.enable");
  const before = await cdp.send("Performance.getMetrics");
  const beforeScript = before.metrics.find((m) => m.name === "ScriptDuration")?.value ?? 0;

  const dom = await page.evaluate(async (duration) => {
    let mutations = 0;
    const observer = new MutationObserver((records) => { mutations += records.length; });
    observer.observe(document.body, { subtree: true, childList: true, attributes: true, characterData: true });
    const start = performance.now();
    let frames = 0;
    let running = true;
    const tick = () => { if (!running) return; frames++; requestAnimationFrame(tick); };
    requestAnimationFrame(tick);
    await new Promise((resolve) => setTimeout(resolve, duration));
    running = false;
    observer.disconnect();
    return { mutations, frames, elapsedMs: Math.round(performance.now() - start) };
  }, ms);

  const after = await cdp.send("Performance.getMetrics");
  const afterScript = after.metrics.find((m) => m.name === "ScriptDuration")?.value ?? 0;
  await cdp.detach();
  return {
    ...dom,
    scriptMs: Math.round((afterScript - beforeScript) * 1000),
    nodes: await page.evaluate(() => document.querySelectorAll("*").length),
  };
}

async function expectNoRunaway(page: Page, label: string) {
  const m = await measureIdle(page);
  console.log(`STRESS ${label}: ${JSON.stringify(m)}`);
  // A mounted shell with SSE/idle timers should not continuously re-render.
  expect(m.mutations, `${label}: excessive idle DOM mutations ${JSON.stringify(m)}`).toBeLessThan(1200);
  // rAF is heavily throttled in headless Chromium with a 12k-node DOM, so it
  // is reported but not used as a pass/fail gate. Mutations + script time are
  // the runaway-render signals; a real click below proves responsiveness.
  expect(m.scriptMs, `${label}: runaway script time ${JSON.stringify(m)}`).toBeLessThan(1500);
  return m;
}

test("1200-row transcript renders without runaway rerenders or console errors", async ({ page, consoleErrors }) => {
  void consoleErrors;
  await stubBridge(page);
  const rows = Array.from({ length: 1200 }, (_, i) => ({
    seq: i + 1,
    kind: "message",
    role: i % 2 ? "assistant" : "user",
    body: { text: `stress transcript row ${i + 1} with enough text to exercise wrapping in the timeline` },
    ts: "2026-11-24T00:00:00Z",
  }));
  await page.route("**/api/bridge/bots", (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ bots: [{ id: "stress-bot", name: "Stress bot" }] }) }));
  await page.route("**/api/bridge/bots/stress-bot/rows", (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ rows }) }));

  await page.addInitScript(() => {
    localStorage.setItem("keel-onboarding-done", "true");
    localStorage.setItem("keel-cowork-bot", "stress-bot");
  });
  await page.goto("/");
  await expect(page.locator(".keel-app")).toBeVisible();
  await expect(page.locator("main article").first()).toBeVisible({ timeout: 20_000 });
  const rendered = await page.locator("main article").count();
  expect(rendered, `expected a rendered transcript, got ${rendered}`).toBeGreaterThan(100);
  await expectNoRunaway(page, "1200-row transcript");
});

test("400-agent Fleet list renders without runaway rerenders or console errors", async ({ page, consoleErrors }) => {
  void consoleErrors;
  await stubBridge(page);
  const bots = Array.from({ length: 400 }, (_, i) => ({
    id: `stress-agent-${i}`, name: `Agent ${i}`, status: i % 3 ? "idle" : "active",
  }));
  const tasks = Array.from({ length: 60 }, (_, i) => ({ id: `task-${i}`, title: `Task ${i}`, status: "open" }));
  await page.route("**/api/bridge/bots", (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ bots }) }));
  await page.route("**/api/bridge/bots/*/rows", (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ rows: [] }) }));
  await page.route("**/api/bridge/tasks", (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ tasks }) }));

  await openApp(page);
  await gotoDestination(page, { id: "fleet", label: "Fleet" });
  await expect(page.getByRole("button", { name: "Select Agent 399" })).toBeVisible({ timeout: 20_000 });
  const cards = await page.getByRole("button", { name: /^Select Agent / }).count();
  expect(cards, `expected many agent cards, got ${cards}`).toBeGreaterThan(100);
  await expectNoRunaway(page, "400-agent Fleet");
});

test("1600-node file tree renders without runaway rerenders or console errors", async ({ page, consoleErrors }) => {
  void consoleErrors;
  await stubBridge(page);
  const tree = Array.from({ length: 200 }, (_, d) => ({
    name: `dir-${d}`, path: `/stress/dir-${d}`, type: "dir",
    children: Array.from({ length: 8 }, (_, f) => ({
      name: `file-${f}.txt`, path: `/stress/dir-${d}/file-${f}.txt`, type: "file", size: 1024,
    })),
  }));
  await page.route("**/api/bridge/projects", (route) =>
    route.fulfill({
      status: 200, contentType: "application/json",
      body: JSON.stringify({ projects: [{ id: "stress-project", name: "Stress project", path: "/stress", trusted: true }] }),
    }));
  await page.route("**/api/bridge/projects/stress-project/tree", (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ tree }) }));

  await page.addInitScript(() => {
    localStorage.setItem("keel-onboarding-done", "true");
    localStorage.setItem("keel-code:project", "stress-project");
  });
  await page.goto("/");
  await expect(page.locator(".keel-app")).toBeVisible();
  await gotoDestination(page, { id: "code", label: "Code" });
  await expect(page.getByRole("treeitem").first()).toBeVisible({ timeout: 20_000 });
  const rows = await page.getByRole("treeitem").count();
  expect(rows, `expected a large tree, got ${rows}`).toBeGreaterThan(500);
  await expectNoRunaway(page, "1600-node file tree");
});
