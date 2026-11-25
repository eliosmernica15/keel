import { test as base, expect, type APIRequestContext, type Page } from "@playwright/test";

/**
 * Shared helpers for the packaged-context compatibility suite.
 *
 * All bridge data is FIXTURE data served by tests/packaged-compat/fixture-bridge.mjs
 * through the real same-origin BFF. The browser never sees a token or a
 * bridge URL; assertions about them are made from the Node side.
 */

export const BRIDGE_PORT = Number(process.env.KEEL_COMPAT_BRIDGE_PORT ?? 3472);
export const APP_PORT = Number(process.env.KEEL_COMPAT_APP_PORT ?? 3471);
export const TOKEN = "local-packaged-compat-token";
export const DOWNLOAD_URL = "https://keel-desktop.vercel.app/download";
export const FIXTURE_MARKDOWN = "# Compat task\n\nfixture transcript bytes\n";
export const FIXTURE_ROWS = [
  { id: "r1", bot_id: "bot-1", seq: 1, kind: "user", role: "user", body: { text: "fixture one" }, created_at: "2026-11-25T09:00:00Z" },
  { id: "r2", bot_id: "bot-1", seq: 2, kind: "agent", role: "agent", body: { text: "fixture two" }, created_at: "2026-11-25T09:01:00Z" },
  { id: "r3", bot_id: "bot-1", seq: 3, kind: "user", role: "user", body: { text: "fixture three" }, created_at: "2026-11-25T09:02:00Z" },
];

/** Fail on any page error or console error, including a CSP violation. */
export const test = base.extend<{ consoleErrors: string[] }>({
  consoleErrors: async ({ page }, use) => {
    const errors: string[] = [];
    page.on("pageerror", (error) => errors.push(`pageerror: ${error.message}\n${error.stack ?? ""}`));
    page.on("console", (message) => {
      if (message.type() === "error") {
        const loc = message.location();
        errors.push(`console.error: ${message.text()} @ ${loc.url}:${loc.lineNumber + 1}`);
      }
    });
    await use(errors);
    expect(errors, `The browser reported errors:\n${errors.join("\n") || "(none)"}`).toEqual([]);
  },
});

export { expect };

/** Open the shell with first-run onboarding complete by default. */
export async function openApp(
  page: Page,
  options: { onboardingDone?: boolean; theme?: "dark" | "light" | "system" } = {},
): Promise<void> {
  await page.addInitScript((opts: { done: boolean; theme?: string }) => {
    try {
      // One-shot seeding: a reload must observe the value PERSISTED by the
      // app, not a value re-injected by the test fixture.
      if (!sessionStorage.getItem("keel-compat-init")) {
        localStorage.setItem("keel-onboarding-done", opts.done ? "true" : "false");
        if (opts.theme) localStorage.setItem("keel-theme-v2", JSON.stringify(opts.theme));
        sessionStorage.setItem("keel-compat-init", "1");
      }
    } catch { /* storage disabled */ }
  }, { done: options.onboardingDone !== false, theme: options.theme });
  await page.goto("/", { waitUntil: "domcontentloaded" });
  await expect(page.locator(".keel-app")).toBeVisible();
  // AppProvider sets this after hydration; without it a forced click can be
  // dropped and produce a false negative in surface navigation tests.
  await page.locator("html[data-reduced-motion]").waitFor({ state: "attached" });
}

export async function gotoTop(page: Page, label: string): Promise<void> {
  await page.getByRole("tab", { name: label, exact: true }).first().click({ force: true });
}

export async function gotoSidebar(page: Page, label: string): Promise<void> {
  const nav = page.locator('aside[aria-label="Main navigation"]');
  await nav.getByRole("button", { name: label, exact: true }).click({ force: true });
}

export async function expectSurface(page: Page, id: string): Promise<void> {
  await expect(page.locator(".keel-statusbar")).toContainText(`Surface: ${id}`);
}

interface BridgeCall {
  method: string;
  path: string;
  body: unknown;
  tokenSeen: boolean;
}

interface Observations {
  calls: BridgeCall[];
  tokenSeen: number;
  tokenMatchesExpected: number;
  tokenHeaderNames: string[];
}

/** Read the FIXTURE bridge's observations from Node, never from the browser. */
export async function observations(request: APIRequestContext): Promise<Observations> {
  const response = await request.get(`http://127.0.0.1:${BRIDGE_PORT}/__fixture/observations`);
  expect(response.ok()).toBeTruthy();
  return (await response.json()) as Observations;
}

export async function resetObservations(request: APIRequestContext): Promise<void> {
  const response = await request.post(`http://127.0.0.1:${BRIDGE_PORT}/__fixture/reset`);
  expect(response.ok()).toBeTruthy();
}

export async function findCall(
  request: APIRequestContext,
  method: string,
  path: string,
): Promise<BridgeCall | undefined> {
  const all = (await observations(request)).calls;
  return all.find((c) => c.method === method && c.path.replace(/\?.*$/, "") === path);
}
