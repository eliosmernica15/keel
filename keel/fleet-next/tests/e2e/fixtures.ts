import { test as base, expect, type Page } from "@playwright/test";

/**
 * Every spec uses this fixture. It fails the test on ANY pageerror or
 * console.error observed while the page is open — no silent browser noise.
 */
export const test = base.extend<{ consoleErrors: string[] }>({
  consoleErrors: async ({ page }, use) => {
    // D-E2E-002 is fixed in next.config.mjs ('unsafe-eval' is now added only
    // for development), so no CSP header workaround is needed any more.
    // No `networkidle` wait is used anywhere: all navigation waits are explicit
    // locator assertions, so the long-lived /api/bridge/events EventSource does
    // not need to be aborted (aborting it produces console.error ERR_FAILED and
    // would trip the strict console gate).

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
    expect(
      errors,
      `The browser reported errors:\n${errors.join("\n") || "(none)"}`,
    ).toEqual([]);
  },
});

export { expect };

export const DESTINATIONS = [
  { id: "cowork", label: "Cowork" },
  { id: "code", label: "Code" },
  { id: "duet", label: "Duet" },
  { id: "fleet", label: "Fleet" },
  { id: "capabilities", label: "Capabilities" },
  { id: "settings", label: "Settings" },
] as const;

export type DestinationId = (typeof DESTINATIONS)[number]["id"];

/** Open the shell with first-run onboarding already marked complete (default). */
export async function openApp(
  page: Page,
  options: { onboardingDone?: boolean } = {},
): Promise<void> {
  const done = options.onboardingDone !== false;
  await page.addInitScript((value: boolean) => {
    try {
      localStorage.setItem("keel-onboarding-done", value ? "true" : "false");
    } catch {
      /* storage disabled */
    }
  }, done);
  await page.goto("/");
  await expect(page.locator(".keel-app")).toBeVisible();
}

/** The BFF must actually reach the local Python bridge before we trust UI data. */
export async function expectBridgeOnline(page: Page): Promise<void> {
  await expect(page.locator(".keel-statusbar")).toContainText("Bridge online");
}

/** Click a destination in the global top bar. */
export async function gotoTop(page: Page, label: string): Promise<void> {
  // `force` avoids actionability flakiness when React re-renders the top bar
  // continuously (see D-E2E-001 in docs/UI-E2E-GUIDE.md).
  await page.getByRole("tab", { name: label, exact: true }).first().click({ force: true });
}

/** Click a destination in the left sidebar. */
export async function gotoSidebar(page: Page, label: string): Promise<void> {
  const sidebar = page.locator("aside.keel-sidebar");
  if (await page.evaluate(() => window.innerWidth <= 1100)) {
    if (!(await sidebar.evaluate((el) => el.classList.contains("is-open")))) {
      await page.getByRole("button", { name: "Toggle sidebar" }).click();
      await expect(sidebar).toHaveClass(/is-open/);
    }
  }
  await page
    .locator('aside[aria-label="Main navigation"]')
    .getByRole("button", { name: label, exact: true })
    .click({ force: true });
}

export async function expectSurface(page: Page, id: string): Promise<void> {
  await expect(page.locator(".keel-statusbar")).toContainText(`Surface: ${id}`);
}

/**
 * The top bar exposes the four work surfaces; Capabilities and Settings live
 * in the sidebar (and the command palette), not as top-bar tabs.
 */
export async function gotoDestination(
  page: Page,
  dest: { id: string; label: string },
): Promise<void> {
  if (["cowork", "code", "duet", "fleet"].includes(dest.id)) await gotoTop(page, dest.label);
  else await gotoSidebar(page, dest.label);
}

/** Record any attempt to grant project trust through the BFF. */
export function captureTrustRequests(page: Page): string[] {
  const calls: string[] = [];
  page.on("request", (request) => {
    if (/\/api\/bridge\/projects\/[^/?]+\/trust(?:\?|$)/.test(request.url())) {
      calls.push(`${request.method()} ${request.url()}`);
    }
  });
  return calls;
}
