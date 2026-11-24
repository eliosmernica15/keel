import {
  test,
  expect,
  mockBridge,
  fulfillJson,
  openApp,
  gotoDestination,
  settingsSection,
  capabilitiesTab,
  storageText,
} from "./fixtures";

test("permission mode persists and is applied to the composer, not just remembered", async ({
  page,
  consoleErrors,
}) => {
  void consoleErrors;
  const mock = await mockBridge(page);
  await openApp(page);
  await gotoDestination(page, "Settings");
  await settingsSection(page, "Permission mode");

  await page.getByRole("radio", { name: /Accept edits/ }).check();
  expect(await page.evaluate(() => localStorage.getItem("keel-mode"))).toBe("acceptEdits");
  await expect(page.getByText("Permission mode set to Accept edits.")).toBeVisible();

  await page.reload();
  await expect(page.locator(".keel-app")).toBeVisible();
  await gotoDestination(page, "Settings");
  await settingsSection(page, "Permission mode");
  await expect(page.getByRole("radio", { name: /Accept edits/ })).toBeChecked();

  // The preference must reach a real composer, otherwise the success is false.
  await gotoDestination(page, "Cowork");
  await expect(page.getByRole("combobox", { name: "Permission mode" })).toHaveValue("acceptEdits");
  expect(mock.calls.some((call) => call.path.includes("mode"))).toBe(false);
  expect(consoleErrors).toEqual([]);
});

test("workspace trust requires confirmation and calls the real project route", async ({
  page,
  consoleErrors,
}) => {
  void consoleErrors;
  let projects = [
    { id: "p1", name: "Root drive", path: "C:\\", trusted: false },
    { id: "p2", name: "Safe project", path: "C:\\Work\\safe", trusted: true },
  ];
  const mock = await mockBridge(page, {
    handlers: {
      projects: (route) => fulfillJson(route, { projects }),
      "projects/p1/trust": async (route, request) => {
        const body = JSON.parse(request.postData() ?? "{}") as { trusted: boolean };
        projects = projects.map((p) => p.id === "p1" ? { ...p, trusted: body.trusted } : p);
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({ project: projects[0] }),
        });
      },
    },
  });

  await openApp(page);
  await gotoDestination(page, "Settings");
  await settingsSection(page, "Workspace trust");

  const rootRow = page.locator("li").filter({ hasText: "Root drive" }).first();
  await expect(rootRow.getByText("Not trusted")).toBeVisible();
  await expect(rootRow.getByText(/root, home or system location/)).toBeVisible();

  await rootRow.getByRole("button", { name: "Trust this folder…" }).click();
  const dialog = page.getByRole("dialog", { name: "Trust this workspace?" });
  await expect(dialog).toContainText("C:\\");
  expect(mock.callsTo("projects/p1/trust"), "dialog alone must not grant trust").toHaveLength(0);
  await dialog.getByRole("button", { name: "Trust folder" }).click();
  await expect(page.getByText("Root drive trusted.")).toBeVisible();
  expect(mock.callsTo("projects/p1/trust")).toHaveLength(1);
  expect(mock.callsTo("projects/p1/trust")[0]?.body).toEqual({ trusted: true });
  await expect(rootRow.getByText("Trusted", { exact: true })).toBeVisible();

  const safeRow = page.locator("li").filter({ hasText: "Safe project" }).first();
  await safeRow.getByRole("button", { name: "Revoke trust…" }).click();
  await page.getByRole("dialog", { name: "Revoke workspace trust?" }).getByRole("button", { name: "Cancel" }).click();
  expect(mock.callsTo("projects/p2/trust"), "cancelling the dialog must not revoke trust").toHaveLength(0);
  expect(consoleErrors).toEqual([]);
});

test("settings search, breadcrumb and deep links work; egress state is honest", async ({
  page,
  consoleErrors,
}) => {
  void consoleErrors;
  await mockBridge(page);
  await openApp(page);
  await gotoDestination(page, "Settings");

  await page.getByRole("searchbox", { name: "Search settings" }).fill("credential");
  const nav = page.locator('aside[aria-label="Settings navigation"]');
  await expect(nav.getByRole("button", { name: "Credentials" })).toBeVisible();
  await expect(nav.getByRole("button", { name: "Permission mode" })).toHaveCount(0);
  await expect(page.locator("main h1")).toHaveText("Credentials");
  await expect(page.locator('nav[aria-label="Breadcrumb"]')).toContainText("Models & providers");
  await expect(page.locator('nav[aria-label="Breadcrumb"]')).toContainText("Credentials");

  await page.getByRole("searchbox", { name: "Search settings" }).fill("");
  await settingsSection(page, "Network & egress");
  await expect(page.getByText("No egress-rule API is exposed by this bridge build")).toBeVisible();
  await expect(page.getByRole("button", { name: /Dry run|Add domain/ })).toHaveCount(0);

  await page.goto("/#settings-privacy");
  await expect(page.locator("main h1")).toHaveText("Privacy & data");
  await expect(page.locator('nav[aria-label="Breadcrumb"]')).toContainText("Privacy & data");
  expect(consoleErrors).toEqual([]);
});

test("diagnostics probes the bridge; privacy, appearance and reset stay within real scope", async ({
  page,
  consoleErrors,
}) => {
  void consoleErrors;
  const mock = await mockBridge(page, {
    handlers: {
      usage: { usage: { input_tokens: 1234, output_tokens: 56 } },
      "mcp/health": { health: {} },
    },
  });
  await openApp(page);
  await gotoDestination(page, "Settings");

  await settingsSection(page, "System diagnostics");
  await expect(page.getByText("No probe run yet")).toBeVisible();
  await page.getByRole("button", { name: "Probe bridge" }).click();
  await expect(page.getByText("Bridge responded")).toBeVisible();
  expect(mock.callsTo("mcp/health")).toHaveLength(1);
  mock.set("mcp/health", { error: "probe refused by bridge" });
  await page.getByRole("button", { name: "Probe bridge" }).click();
  await expect(page.getByText("probe refused by bridge")).toBeVisible();
  await expect(page.getByText("Bridge responded")).toHaveCount(0);
  await expect(page.getByText("Redacted diagnostics bundle — no export route exists in this bridge client.")).toBeVisible();

  await settingsSection(page, "Privacy & data");
  await expect(page.getByText("1,234")).toBeVisible();
  await expect(page.getByText(/no routes for retention policy, transcript cleanup, export\/import/)).toBeVisible();

  await settingsSection(page, "Appearance");
  await expect(page.getByText(/Resolved:/)).toBeVisible();

  await settingsSection(page, "Accessibility");
  await expect(page.getByText("Not exposed by the shell")).toBeVisible();

  await settingsSection(page, "Reset to defaults");
  await page.getByRole("button", { name: "Preview reset…" }).click();
  const dialog = page.getByRole("dialog", { name: "Preview reset" });
  await expect(dialog.getByRole("columnheader", { name: "After reset" })).toBeVisible();
  await expect(dialog).toContainText("dark");
  await dialog.getByRole("button", { name: "Apply these defaults" }).click();
  await expect(page.getByText("Theme and panel layout reset to defaults.")).toBeVisible();
  // Reset is UI-owned; it must never call a bridge route.
  expect(mock.calls.filter((call) => call.method !== "GET" && call.path.includes("reset"))).toEqual([]);
  expect(consoleErrors).toEqual([]);
});

test("no console errors while visiting every capability tab and settings section", async ({
  page,
  consoleErrors,
}) => {
  void consoleErrors;
  await mockBridge(page);
  await openApp(page);

  await gotoDestination(page, "Capabilities");
  for (const tab of ["Skills", "MCP servers", "Connectors", "Tools", "Commands", "Workflows", "Extensions"]) {
    await capabilitiesTab(page, tab);
  }

  await gotoDestination(page, "Settings");
  for (const section of [
    "Providers & models", "Credentials", "Permission mode", "Workspace trust", "Network & egress",
    "Privacy & data", "System diagnostics", "Appearance", "Accessibility", "Reset to defaults",
  ]) {
    await settingsSection(page, section);
  }
  expect(await storageText(page)).not.toMatch(/sk-[A-Za-z0-9_-]{16,}/);
  expect(consoleErrors).toEqual([]);
});
