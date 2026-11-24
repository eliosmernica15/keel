import { test as base, expect, type Page, type Route, type Request } from "@playwright/test";

/**
 * Capabilities & Settings E2E fixtures.
 *
 * Every spec in this folder mocks the bridge at the browser boundary with
 * `page.route`, so no test mutates real Keel state and every success/error is
 * driven by a known response. The fixture fails on ANY pageerror or
 * console.error observed while the page is open.
 */
export const test = base.extend<{ consoleErrors: string[] }>({
  consoleErrors: async ({ page }, use) => {
    const errors: string[] = [];
    page.on("pageerror", (error) =>
      errors.push(`pageerror: ${error.message}\n${error.stack ?? ""}`),
    );
    page.on("console", (message) => {
      if (message.type() === "error") {
        const loc = message.location();
        errors.push(
          `console.error: ${message.text()} @ ${loc.url}:${loc.lineNumber + 1}:${loc.columnNumber + 1}`,
        );
      }
    });
    await use(errors);
    expect(errors, `The browser reported errors:\n${errors.join("\n") || "(none)"}`).toEqual([]);
  },
});

export { expect };

/** Fulfil a mocked bridge call with a JSON body and a real HTTP 200. */
export function fulfillJson(route: Route, body: unknown): Promise<void> {
  return route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify(body ?? {}),
  });
}

export type Handler = (route: Route, request: Request) => void | Promise<void>;
export type Payload = Record<string, unknown> | unknown[];
export type StatusBody = { __status: number; body?: unknown; __contentType?: string };
export type MockValue = Payload | Handler | StatusBody;

export interface CapturedCall {
  method: string;
  path: string;
  /** JSON body with sensitive values replaced by "[redacted]". */
  body: Record<string, unknown> | null;
  /** True when the raw POST body contained one of the watched secret strings. */
  sawSecret: boolean;
}

export interface BridgeMock {
  calls: CapturedCall[];
  set: (path: string, value: MockValue) => void;
  callsTo: (path: string) => CapturedCall[];
}

const SENSITIVE_KEY = /key|secret|token|password|credential/i;

function redact(value: unknown): Record<string, unknown> | null {
  if (!value || typeof value !== "object" || Array.isArray(value)) return null;
  const out: Record<string, unknown> = {};
  for (const [k, v] of Object.entries(value as Record<string, unknown>)) {
    out[k] = SENSITIVE_KEY.test(k) ? "[redacted]" : v;
  }
  return out;
}

function isStatusBody(value: MockValue): value is StatusBody {
  return typeof value === "object" && value !== null && !Array.isArray(value) &&
    "__status" in (value as Record<string, unknown>);
}

function defaultPayload(path: string): unknown {
  if (path === "providers") return { providers: [], session_keys: [] };
  if (path === "bots") return { bots: [] };
  if (/^bots\/[^/]+\/rows$/.test(path)) return { rows: [] };
  if (path === "usage") return { usage: {} };
  if (path === "projects") return { projects: [] };
  if (path === "library") return { files: [] };
  if (path === "skills" || path === "skills/manage") return { skills: [] };
  if (path === "commands") return { commands: [] };
  if (path === "workflows") return { workflows: [] };
  if (path === "mcp/servers") return { servers: [] };
  if (path === "mcp/health") return { health: {} };
  if (path === "connectors") return { connectors: [], presets: [] };
  if (path === "providers/catalog") {
    return { ok: false, error: "not_configured", detail: "no key on this host" };
  }
  return {};
}

/**
 * Install a single catch-all bridge route. Handler entries are keyed by the
 * bridge-relative path (e.g. "providers/save"). A function handler receives the
 * raw Route so specs can exercise real HTTP error statuses.
 */
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
    calls.push({ method: request.method(), path, body: redact(parsed), sawSecret });

    const value = handlers[path];
    if (typeof value === "function") {
      await value(route, request);
      return;
    }
    if (isStatusBody(value)) {
      await route.fulfill({
        status: value.__status,
        contentType: value.__contentType ?? "application/json",
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

/** Open the shell with onboarding complete and the long-lived SSE stream stubbed. */
export async function openApp(page: Page): Promise<void> {
  await page.addInitScript(() => {
    try { localStorage.setItem("keel-onboarding-done", "true"); } catch { /* storage disabled */ }
    // The bridge emits named SSE frames; these tests never exercise streaming,
    // so a no-op EventSource keeps the long-lived connection out of the console gate.
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

export async function gotoDestination(
  page: Page,
  label: "Capabilities" | "Settings" | "Cowork" | "Code" | "Duet" | "Fleet",
): Promise<void> {
  if (label === "Capabilities" || label === "Settings") {
    const sidebar = page.locator("aside.keel-sidebar");
    if (await page.evaluate(() => window.innerWidth <= 1100)) {
      if (!(await sidebar.evaluate((el) => el.classList.contains("is-open")))) {
        await page.getByRole("button", { name: "Toggle sidebar" }).click();
        await expect(sidebar).toHaveClass(/is-open/);
      }
    }
    await page.locator('aside[aria-label="Main navigation"]')
      .getByRole("button", { name: label, exact: true }).click({ force: true });
  } else {
    await page.getByRole("tab", { name: label, exact: true }).first().click({ force: true });
  }
}

export async function capabilitiesTab(page: Page, label: string): Promise<void> {
  await expect(page.getByRole("heading", { name: "Capabilities", exact: true })).toBeVisible();
  await page.getByRole("tab", { name: label, exact: true }).click();
}

export async function settingsSection(page: Page, title: string): Promise<void> {
  // The Settings surface has no "Settings" heading — its own nav is the anchor.
  const nav = page.locator('aside[aria-label="Settings navigation"]');
  await expect(nav).toBeVisible();
  await nav.getByRole("button", { name: title, exact: true }).click();
}

export async function storageText(page: Page): Promise<string> {
  return page.evaluate(() => {
    const parts: string[] = [];
    for (let i = 0; i < localStorage.length; i += 1) {
      const key = localStorage.key(i);
      parts.push(`${key}=${key ? localStorage.getItem(key) : ""}`);
    }
    for (let i = 0; i < sessionStorage.length; i += 1) {
      const key = sessionStorage.key(i);
      parts.push(`${key}=${key ? sessionStorage.getItem(key) : ""}`);
    }
    return parts.join("\n");
  });
}
