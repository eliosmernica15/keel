import { test as base, expect, type Page, type Route, type Request } from "@playwright/test";

/**
 * Settings E2E fixtures. Each spec mocks `/api/bridge/**` in the browser, so
 * tests never touch real Keel state. The fixture fails on any page error or
 * application console.error seen while the page is open.
 */
export const test = base.extend<{ consoleErrors: string[] }>({
  consoleErrors: async ({ page }, use) => {
    const errors: string[] = [];
    page.on("pageerror", (error) => errors.push(`pageerror: ${error.message}\n${error.stack ?? ""}`));
    page.on("console", (message) => {
      if (message.type() !== "error") return;
      const loc = message.location();
      if (message.text().startsWith("Failed to load resource:") && loc.url.includes("/api/bridge/")) return;
      errors.push(`console.error: ${message.text()} @ ${loc.url}:${loc.lineNumber + 1}:${loc.columnNumber + 1}`);
    });
    await use(errors);
    expect(errors, `The browser reported errors:\n${errors.join("\n") || "(none)"}`).toEqual([]);
  },
});

export { expect };

export function fulfillJson(route: Route, body: unknown): Promise<void> {
  return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(body ?? {}) });
}

export type Handler = (route: Route, request: Request) => void | Promise<void>;
export type Payload = Record<string, unknown> | unknown[];
export type StatusBody = { __status: number; body?: unknown };
export type MockValue = Payload | Handler | StatusBody;

export interface CapturedCall {
  method: string;
  path: string;
  body: Record<string, unknown> | null;
  sawSecret: boolean;
}

export interface BridgeMock {
  calls: CapturedCall[];
  set: (path: string, value: MockValue) => void;
  callsTo: (path: string) => CapturedCall[];
}

function isStatusBody(value: MockValue): value is StatusBody {
  return typeof value === "object" && value !== null && !Array.isArray(value) && "__status" in value;
}

function defaultPayload(path: string): unknown {
  if (path === "skills" || path === "skills/manage") return { skills: [] };
  if (path === "commands") return { commands: [] };
  if (path === "workflows") return { workflows: [] };
  if (path === "mcp/servers") return { servers: [] };
  if (path === "mcp/health") return { health: {} };
  if (path === "connectors") return { connectors: [], presets: [] };
  if (path === "projects") return { projects: [] };
  if (path === "keep-awake") return { supported: true, on: false };
  if (path === "bots") return { bots: [] };
  if (path === "library") return { files: [] };
  if (path === "usage") return { usage: {} };
  return {};
}

/** Catch-all bridge mock, keyed by bridge-relative path. */
export async function mockBridge(
  page: Page,
  options: { handlers?: Record<string, MockValue>; secrets?: string[] } = {},
): Promise<BridgeMock> {
  const calls: CapturedCall[] = [];
  const handlers: Record<string, MockValue> = { ...(options.handlers ?? {}) };
  const secrets = (options.secrets ?? []).filter(Boolean);

  await page.route("**/api/bridge/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = decodeURIComponent(url.pathname.replace(/^\/api\/bridge\//, "")).replace(/\/$/, "");
    const raw = request.postData() ?? "";
    const sawSecret = secrets.some((secret) => raw.includes(secret));
    let parsed: unknown = null;
    if (raw) {
      try { parsed = JSON.parse(raw); } catch { parsed = { raw: "[unparsed body]" }; }
    }
    calls.push({
      method: request.method(), path,
      body: parsed && typeof parsed === "object" && !Array.isArray(parsed)
        ? parsed as Record<string, unknown> : null,
      sawSecret,
    });

    const value = handlers[path];
    if (typeof value === "function") { await value(route, request); return; }
    if (isStatusBody(value)) {
      await route.fulfill({
        status: value.__status,
        contentType: "application/json",
        body: JSON.stringify(value.body ?? {}),
      });
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(value !== undefined ? value : defaultPayload(path) ?? {}),
    });
  });

  return {
    calls,
    set(path, value) { handlers[path] = value; },
    callsTo(path) { return calls.filter((call) => call.path === path); },
  };
}

/** Boot with onboarding complete and the long-lived SSE stream stubbed out. */
export async function openApp(page: Page): Promise<void> {
  await page.addInitScript(() => {
    try { localStorage.setItem("keel-onboarding-done", "true"); } catch { /* storage disabled */ }
    class FakeEventSource {
      readyState = 1;
      url = "";
      withCredentials = false;
      onopen: ((e: Event) => void) | null = null;
      onmessage: ((e: MessageEvent) => void) | null = null;
      onerror: ((e: Event) => void) | null = null;
      addEventListener(): void { /* no-op */ }
      removeEventListener(): void { /* no-op */ }
      dispatchEvent(): boolean { return true; }
      close(): void { this.readyState = 2; }
    }
    (window as unknown as { EventSource: unknown }).EventSource = FakeEventSource;
  });
  await page.goto("/");
  await expect(page.locator(".keel-app")).toBeVisible();
}

export async function gotoSettings(page: Page): Promise<void> {
  const sidebar = page.locator("aside.keel-sidebar");
  if (await page.evaluate(() => window.innerWidth <= 1100)) {
    if (!(await sidebar.evaluate((el) => el.classList.contains("is-open")))) {
      await page.getByRole("button", { name: "Toggle sidebar" }).click();
      await expect(sidebar).toHaveClass(/is-open/);
    }
  }
  const arrived = page.locator('aside[aria-label="Settings navigation"]');
  for (let attempt = 0; attempt < 3; attempt += 1) {
    await page.locator('aside[aria-label="Main navigation"]').getByRole("button", { name: "Settings", exact: true }).click({ force: true });
    try {
      await expect(arrived).toBeVisible({ timeout: 4_000 });
      return;
    } catch { /* click may have landed before hydration; retry */ }
  }
  await expect(arrived, "Could not open Settings").toBeVisible();
}

export async function gotoCapabilities(page: Page): Promise<void> {
  const sidebar = page.locator("aside.keel-sidebar");
  if (await page.evaluate(() => window.innerWidth <= 1100)) {
    if (!(await sidebar.evaluate((el) => el.classList.contains("is-open")))) {
      await page.getByRole("button", { name: "Toggle sidebar" }).click();
      await expect(sidebar).toHaveClass(/is-open/);
    }
  }
  const arrived = page.getByRole("heading", { name: "Capabilities", exact: true });
  for (let attempt = 0; attempt < 3; attempt += 1) {
    await sidebar.getByRole("button", { name: "Capabilities", exact: true }).click({ force: true });
    try {
      await expect(arrived).toBeVisible({ timeout: 4_000 });
      return;
    } catch { /* click may have landed before hydration; retry */ }
  }
  await expect(arrived, "Could not open Capabilities").toBeVisible();
}

export async function settingsSection(page: Page, title: string): Promise<void> {
  const nav = page.locator('aside[aria-label="Settings navigation"]');
  await expect(nav).toBeVisible();
  await nav.getByRole("button", { name: title, exact: true }).click();
}
