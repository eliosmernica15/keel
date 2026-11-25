import { expect, test as base, type CDPSession, type Page } from "@playwright/test";

/** The six destinations asserted by the frontend matrix. */
export const DESTINATIONS = [
  { id: "cowork", label: "Cowork" },
  { id: "code", label: "Code" },
  { id: "duet", label: "Duet" },
  { id: "fleet", label: "Fleet" },
  { id: "capabilities", label: "Capabilities" },
  { id: "settings", label: "Settings" },
] as const;

export type Theme = "dark" | "light";
export type Destination = (typeof DESTINATIONS)[number];

/**
 * Test fixture with the same strict "no browser console errors / pageerrors"
 * gate as the main E2E suite. The bridge is mocked deterministically because
 * this host has no Python bridge listener; no provider credentials are used.
 */
export const test = base.extend<{ consoleErrors: string[] }>({
  consoleErrors: async ({ page }, use) => {
    const errors: string[] = [];
    page.on("pageerror", (error) => errors.push(`pageerror: ${error.message}`));
    page.on("console", (message) => {
      if (message.type() === "error") {
        const loc = message.location();
        errors.push(
          `console.error: ${message.text()} @ ${loc.url}:${loc.lineNumber + 1}:${loc.columnNumber + 1}`,
        );
      }
    });
    await use(errors);
    expect(errors, `browser errors:\n${errors.join("\n") || "(none)"}`).toEqual([]);
  },
});

export { expect };

/**
 * Deterministic bridge stub: honest empty data, no invented provider content.
 * `failPaths` lets a test force a real BFF error (e.g. providers -> HTTP 500)
 * so error live-region announcements can be observed without credentials.
 */
export interface BridgeMock {
  /** Deliver a held SSE body (used to stream deltas after a session is open). */
  releaseEvents?: () => void;
}

export async function mockBridge(
  page: Page,
  options: {
    failPaths?: Record<string, { status: number; body: unknown }>;
    bots?: unknown[];
    rows?: Record<string, unknown>[];
    holdEvents?: boolean;
    eventsBody?: string;
  } = {},
): Promise<BridgeMock> {
  let resolveHold: (() => void) | undefined;
  const held = options.holdEvents
    ? new Promise<void>((resolve) => {
        resolveHold = resolve;
      })
    : null;
  await page.route("**/api/bridge/**", async (route) => {
    const path = new URL(route.request().url()).pathname.replace(/^\/api\/bridge\//, "");
    const json = (body: unknown, status = 200) =>
      route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
    if (options.failPaths?.[path]) {
      const failure = options.failPaths[path];
      return json(failure.body, failure.status);
    }
    if (path === "events") {
      if (held) await held;
      return route.fulfill({
        status: 200,
        contentType: "text/event-stream",
        body: options.eventsBody ?? ": ping\n\n",
      });
    }
    if (path === "bots") return json({ bots: options.bots ?? [] });
    if (/^bots\/[^/]+\/rows$/.test(path)) {
      return json({ bot_id: path.split("/")[1], rows: options.rows ?? [] });
    }
    if (path === "providers") return json({ providers: [] });
    if (path === "projects") return json({ projects: [] });
    if (path === "library") return json({ files: [] });
    if (path === "usage") return json({ tokens: 0, requests: 0 });
    if (path === "providers/catalog") return json({ models: [] });
    return json({});
  });
  return { releaseEvents: () => resolveHold?.() };
}

/** Open the shell with onboarding complete and a deterministic theme. */
export async function openAppThemed(
  page: Page,
  theme: Theme = "dark",
  bridgeOptions: Parameters<typeof mockBridge>[1] = {},
): Promise<BridgeMock> {
  const bridge = await mockBridge(page, bridgeOptions);
  await page.addInitScript((value: Theme) => {
    try {
      localStorage.setItem("keel-onboarding-done", "true");
      localStorage.setItem("keel-theme-v2", JSON.stringify(value));
    } catch {
      /* storage disabled */
    }
  }, theme);
  await page.goto("/", { waitUntil: "domcontentloaded" });
  await page.locator(".keel-app").waitFor({ state: "visible" });
  await page.locator(`html[data-theme="${theme}"]`).waitFor({ state: "attached" });
  await page.locator("html[data-reduced-motion]").waitFor({ state: "attached" });
  return bridge;
}

async function gotoSidebar(page: Page, label: string): Promise<void> {
  const sidebar = page.locator("aside.keel-sidebar");
  const narrow = await page.evaluate(() => window.innerWidth <= 1100);
  if (narrow && !(await sidebar.evaluate((el) => el.classList.contains("is-open")))) {
    await page.getByRole("button", { name: "Toggle sidebar" }).click();
    await expect(sidebar).toHaveClass(/is-open/);
    await page.waitForTimeout(250);
  }
  await page
    .locator('aside[aria-label="Main navigation"]')
    .getByRole("button", { name: label, exact: true })
    .click({ force: true });
}

/** Navigate to a destination through the real UI (top bar or sidebar). */
export async function gotoDestination(page: Page, dest: Destination): Promise<void> {
  if (["cowork", "code", "duet", "fleet"].includes(dest.id)) {
    await page.getByRole("tab", { name: dest.label, exact: true }).first().click({ force: true });
  } else {
    await gotoSidebar(page, dest.label);
  }
  await expect(page.locator(".keel-statusbar")).toContainText(`Surface: ${dest.id}`);
}

export interface ZoomMetrics {
  innerWidth: number;
  innerHeight: number;
  dpr: number;
  vvScale: number;
  vvWidth: number;
  vvHeight: number;
  scrollWidth: number;
  bodyScrollWidth: number;
  clientWidth: number;
}

/** Snapshot layout + visual-viewport metrics from the live document. */
export async function zoomMetrics(page: Page): Promise<ZoomMetrics> {
  return page.evaluate(() => ({
    innerWidth: window.innerWidth,
    innerHeight: window.innerHeight,
    dpr: window.devicePixelRatio,
    vvScale: window.visualViewport?.scale ?? 1,
    vvWidth: window.visualViewport?.width ?? window.innerWidth,
    vvHeight: window.visualViewport?.height ?? window.innerHeight,
    scrollWidth: document.documentElement.scrollWidth,
    bodyScrollWidth: document.body.scrollWidth,
    clientWidth: document.documentElement.clientWidth,
  }));
}

/** Apply the Chromium CDP visual zoom used by pinch-zoom / browser zoom UI. */
export async function applyPageScaleFactor(page: Page, factor = 2): Promise<CDPSession> {
  const cdp = await page.context().newCDPSession(page);
  await cdp.send("Emulation.setPageScaleFactor", { pageScaleFactor: factor });
  await page.waitForTimeout(80);
  return cdp;
}

export interface AXNodeSummary {
  id: string;
  childIds: string[];
  role: string;
  name: string;
  live?: string;
}

/** Read Chromium's accessibility tree (the same tree NVDA/VoiceOver query). */
export async function accessibilityTree(page: Page): Promise<AXNodeSummary[]> {
  const cdp = await page.context().newCDPSession(page);
  try {
    const { nodes } = await cdp.send("Accessibility.getFullAXTree");
    return nodes.map((node) => {
      const prop = (name: string) => {
        const found = node.properties?.find((p) => p.name === name);
        return found?.value?.value;
      };
      return {
        id: String(node.nodeId ?? ""),
        childIds: (node.childIds ?? []).map(String),
        role: String(node.role?.value ?? "unknown"),
        name: String(node.name?.value ?? ""),
        ...(prop("live") !== undefined ? { live: String(prop("live")) } : {}),
      };
    });
  } finally {
    await cdp.detach();
  }
}

/** Flatten an AX node and its descendants into one searchable string. */
export function axSubtreeText(tree: AXNodeSummary[], nodeId: string): string {
  const byId = new Map(tree.map((node) => [node.id, node]));
  const out: string[] = [];
  const visit = (id: string, depth: number) => {
    if (depth > 12) return;
    const node = byId.get(id);
    if (!node) return;
    if (node.name) out.push(node.name);
    for (const child of node.childIds) visit(child, depth + 1);
  };
  visit(nodeId, 0);
  return out.join(" | ");
}

/** Focus descriptor used to prove keyboard focus is visible and well named. */
export async function focusDescriptor(page: Page) {
  return page.evaluate(() => {
    const el = document.activeElement as HTMLElement | null;
    if (!el || el === document.body) {
      return { tag: "body", label: "", text: "", tabindex: null as number | null, visible: false, ring: "" };
    }
    const s = getComputedStyle(el);
    const ring =
      s.outlineStyle !== "none" && parseFloat(s.outlineWidth) > 0
        ? `${s.outlineStyle} ${s.outlineWidth} ${s.outlineColor}`
        : "";
    return {
      tag: el.tagName.toLowerCase(),
      label: el.getAttribute("aria-label") ?? "",
      text: (el.textContent ?? "").trim().slice(0, 60),
      tabindex: el.hasAttribute("tabindex") ? Number(el.getAttribute("tabindex")) : null,
      visible: el.getClientRects().length > 0,
      ring,
    };
  });
}

/** Compare focus restoration by target identity, not by the transient
 * :focus-visible ring (programmatic focus before/after a dialog differs). */
export function focusIdentity(
  descriptor: Awaited<ReturnType<typeof focusDescriptor>>,
): string {
  return `${descriptor.tag}:${descriptor.label || descriptor.text}`;
}

/** Structural landmark / heading / live-region / accessible-name audit. */
export async function semanticAudit(page: Page) {
  return page.evaluate(() => {
    const visible = (el: Element) =>
      !el.closest("[aria-hidden='true'], script, style, .sr-only") &&
      el.getClientRects().length > 0 &&
      getComputedStyle(el).visibility !== "hidden" &&
      getComputedStyle(el).display !== "none";
    const controls = Array.from(
      document.querySelectorAll<HTMLElement>(
        "button, input:not([type=hidden]), select, textarea, [role='button'], [role='tab'], [role='dialog'], a[href]",
      ),
    ).filter(visible);
    const unnamed = controls.filter((el) => {
      const aria = (el.getAttribute("aria-label") ?? "").trim();
      const labelledby = (el.getAttribute("aria-labelledby") ?? "").trim();
      const title = (el.getAttribute("title") ?? "").trim();
      const text = (el.textContent ?? "").trim();
      const nativeLabel =
        el instanceof HTMLInputElement ||
        el instanceof HTMLTextAreaElement ||
        el instanceof HTMLSelectElement
          ? !!document.querySelector(`label[for="${CSS.escape(el.id)}"]`) || !!el.closest("label")
          : false;
      return !aria && !labelledby && !title && !text && !nativeLabel;
    });
    const live = Array.from(document.querySelectorAll<HTMLElement>("[aria-live], [role='status'], [role='alert'], [role='log']"))
      .filter(visible)
      .map((el) => ({
        tag: el.tagName.toLowerCase(),
        role: el.getAttribute("role") ?? "",
        live: el.getAttribute("aria-live") ?? "",
        atomic: el.getAttribute("aria-atomic") ?? "",
        text: (el.textContent ?? "").trim().slice(0, 100),
      }));
    return {
      landmarks: {
        header: document.querySelectorAll("header.keel-topbar").length,
        main: document.querySelectorAll("main#main").length,
        footer: document.querySelectorAll("footer.keel-statusbar").length,
        nav: document.querySelectorAll("nav[aria-label='Surfaces']").length,
      },
      headings: Array.from(document.querySelectorAll("main h1, main h2, main h3, main [role='heading']"))
        .filter(visible)
        .map((el) => `${el.tagName.toLowerCase()}:${(el.textContent ?? "").trim().slice(0, 60)}`),
      live,
      controls: controls.length,
      unnamed: unnamed.map((el) => el.outerHTML.slice(0, 160)),
    };
  });
}
