import {
  test, expect, openWizard, wizard, advance,
} from "./fixtures";

function helpDialog(page: import("@playwright/test").Page) {
  return page.getByRole("dialog", { name: "Help & troubleshooting" });
}

async function openHelpFromWizard(page: import("@playwright/test").Page): Promise<void> {
  await wizard(page).getByRole("button", { name: "Help & troubleshooting" }).click();
  await expect(helpDialog(page)).toBeVisible();
}

test("help reads live bridge data, explains all three states and closes without closing setup", async ({
  page, bridge, consoleErrors, hydrationWarnings,
}) => {
  void consoleErrors; void hydrationWarnings;
  await openWizard(page);
  await openHelpFromWizard(page);
  const help = helpDialog(page);

  // The status lines are real reads, not cached badges.
  expect(bridge.callsMatching("GET", "providers").length).toBeGreaterThan(0);
  expect(bridge.callsMatching("GET", "projects").length).toBeGreaterThan(0);
  await expect(help).toContainText("Bridge answered");
  await expect(help).toContainText("Both setup reads reached the local bridge.");
  await expect(help).toContainText("0 of 2 providers report a configured key.");
  await expect(help).toContainText("No local projects are registered yet.");

  for (const title of [
    "Bridge is unavailable", "No provider is configured", "Workspace is not trusted",
  ]) {
    await expect(help.getByText(title, { exact: true })).toBeVisible();
  }
  await expect(help).toContainText("not a sandbox");
  await expect(help).toContainText("Every route above opens a real surface.");

  // Escape belongs to help only; the wizard underneath stays open.
  await page.keyboard.press("Escape");
  await expect(help).toHaveCount(0);
  await expect(wizard(page).getByRole("heading", { name: "Welcome to Keel" })).toBeVisible();
});

test("bridge-unavailable help reports 502 honestly, re-checks for real and recovers", async ({
  page, bridge, consoleErrors, hydrationWarnings,
}) => {
  void consoleErrors; void hydrationWarnings;
  bridge.setOptions({ bridgeUnavailable: true });
  await openWizard(page);
  await openHelpFromWizard(page);
  const help = helpDialog(page);

  await expect(help).toContainText("Bridge unavailable");
  await expect(help).toContainText("Bridge read failed: bridge_unavailable");
  await expect(help).toContainText("Provider state could not be read; do not assume a key is working.");
  await expect(help).toContainText("Workspace trust could not be read; nothing is trusted by this page.");
  await expect(help).toContainText("This page cannot start a bridge");
  await expect(help).not.toContainText("Bridge answered");
  await expect(help).not.toContainText("report a configured key");

  // Re-check really re-reads the bridge; a live recovery changes the copy.
  const before = bridge.callsMatching("GET", "providers").length;
  bridge.setOptions({ bridgeUnavailable: false });
  await help.getByRole("button", { name: /Re-check connection/ }).click();
  await expect.poll(() => bridge.callsMatching("GET", "providers").length).toBeGreaterThan(before);
  await expect(help).toContainText("Bridge answered");
  await expect(help).toContainText("0 of 2 providers report a configured key.");

  // The bridge action navigates to a real settings section, not a dead link.
  await help.getByRole("button", { name: /Open system diagnostics/ }).click();
  await expect(help).toHaveCount(0);
  await expect(page.locator(".keel-onboarding-layer")).toHaveCount(0);
  await expect(page.locator("section[aria-label='System diagnostics']")).toBeVisible();
  expect(await page.evaluate(() => window.location.hash)).toBe("#settings-diagnostics");
});

test("provider help navigates to provider settings and saved credentials", async ({
  page, consoleErrors, hydrationWarnings,
}) => {
  void consoleErrors; void hydrationWarnings;
  await openWizard(page);
  await openHelpFromWizard(page);

  await helpDialog(page).getByRole("button", { name: /Open provider settings/ }).click();
  await expect(helpDialog(page)).toHaveCount(0);
  await expect(page.locator("section[aria-label='Providers & models']")).toBeVisible();
  expect(await page.evaluate(() => window.location.hash)).toBe("#settings-providers");

  // The always-mounted sidebar checklist reopens help after setup is closed.
  const checklist = page.locator("section[aria-label='Setup checklist']");
  await checklist.getByRole("button", { name: "Help", exact: true }).click();
  await expect(helpDialog(page)).toBeVisible();
  await helpDialog(page).getByRole("button", { name: /Open saved credentials/ }).click();
  await expect(page.locator("section[aria-label='Credentials']")).toBeVisible();
  expect(await page.evaluate(() => window.location.hash)).toBe("#settings-credentials");
});

test("workspace-trust help reports the real untrusted count and routes to Code and trust settings", async ({
  page, bridge, consoleErrors, hydrationWarnings,
}) => {
  void consoleErrors; void hydrationWarnings;
  bridge.setOptions({
    projects: [{ id: "p1", name: "app", path: "C:\\Work\\app", trusted: false }],
  });
  await openWizard(page);
  await openHelpFromWizard(page);

  await expect(helpDialog(page)).toContainText("1 of 1 registered projects are still untrusted.");
  await helpDialog(page).getByRole("button", { name: /Open Code workspace/ }).click();
  await expect(page.locator(".keel-statusbar")).toContainText("Surface: code");

  // Help is also reachable from the command palette after setup has closed.
  await page.keyboard.press("Control+k");
  const palette = page.getByRole("dialog", { name: "Command palette" });
  await expect(palette).toBeVisible();
  await palette.getByLabel("Search commands").fill("Open help & troubleshooting");
  await palette.getByRole("button", { name: "Open help & troubleshooting", exact: true }).click();
  await expect(helpDialog(page)).toBeVisible();
  await helpDialog(page).getByRole("button", { name: /Open workspace trust/ }).click();
  await expect(page.locator("section[aria-label='Workspace trust']")).toBeVisible();
  expect(await page.evaluate(() => window.location.hash)).toBe("#settings-trust");
});

test("the how-Keel-works step introduces all four surfaces and the tour names a real first task", async ({
  page, consoleErrors, hydrationWarnings,
}) => {
  void consoleErrors; void hydrationWarnings;
  await openWizard(page);
  const d = wizard(page);
  await d.getByRole("button", { name: /Start with Cowork/ }).click();
  await expect(d.getByRole("heading", { name: "How Keel works" })).toBeVisible();
  await expect(d.getByText("Four work surfaces")).toBeVisible();
  for (const name of ["Cowork", "Code", "Duet", "Fleet"]) {
    await expect(d.getByRole("button", { name: new RegExp(`^${name}\\b`) })).toBeVisible();
  }
  await d.getByRole("button", { name: /^Duet\b/ }).click();
  await expect(page.locator(".keel-statusbar")).toContainText("Surface: duet");

  await advance(page); // provider
  for (let i = 0; i < 5; i++) await advance(page, "Skip for now");
  await expect(d.getByRole("heading", { name: "Take the tour" })).toBeVisible();
  await expect(d.getByRole("button", { name: /Create your first task/ })).toBeVisible();
  const before = page.locator(".keel-notices");
  await d.getByRole("button", { name: /Create your first task/ }).click();
  await expect(before).toContainText("New task in the sidebar creates a real task through the bridge");
});
