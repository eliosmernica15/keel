import { test, expect, mockBridge, openApp, gotoSettings, settingsSection } from "./fixtures";

const EMPTY_SECTIONS = [
  { title: "Skills", heading: "No skills found", action: "Refresh skills" },
  { title: "Commands", heading: "No commands found", action: "Refresh commands" },
  { title: "Workflows", heading: "No workflows found", action: "Refresh workflows" },
  { title: "MCP Servers", heading: "No MCP servers configured", action: "Refresh servers" },
  { title: "Plugins", heading: "No connectors configured", action: "Add connector" },
  { title: "Keel Code", heading: "No projects added", action: "Open Code" },
  { title: "Import & export", heading: "Nothing to export yet", action: "Open Cowork" },
];

test("empty states offer a real primary action and no internal bridge language", async ({ page, consoleErrors }) => {
  void consoleErrors;
  await mockBridge(page);
  await openApp(page);
  await gotoSettings(page);

  for (const section of EMPTY_SECTIONS) {
    await settingsSection(page, section.title);
    await expect(page.getByRole("heading", { name: section.heading })).toBeVisible();
    await expect(page.getByRole("button", { name: section.action }).first()).toBeVisible();
    await expect(page.locator("main").last()).not.toContainText(
      /not reported by bridge|bridge returned no data|not available in this build|not exposed by this bridge/i,
    );
  }

  await settingsSection(page, "Keel Desktop");
  await expect(page.locator('label.keel-toggle:has(input[aria-label="Keep this machine awake while Keel runs"])')).toBeVisible();
  await settingsSection(page, "Developer");
  await expect(page.getByText("Skills discovered")).toBeVisible();
  await expect(page.getByRole("button", { name: "Run health check" })).toBeVisible();
  expect(consoleErrors).toEqual([]);
});

test("a bridge error is shown with Retry and recovers into real rows", async ({ page, consoleErrors }) => {
  void consoleErrors;
  const mock = await mockBridge(page);
  await openApp(page);
  await gotoSettings(page);

  await settingsSection(page, "General");
  mock.set("skills", { __status: 502, body: { error: "bridge_unavailable", detail: "Bridge is offline" } });
  await settingsSection(page, "Skills");

  // Next's route announcer also has role=alert; target the settings error box.
  const alert = page.locator('div[role="alert"]').filter({ hasText: "Bridge is offline" });
  await expect(alert).toBeVisible();
  await expect(alert).toContainText("Bridge is offline");
  await expect(alert.getByRole("button", { name: "Retry" })).toBeVisible();

  mock.set("skills", { skills: [{ name: "recovered-skill", description: "Back online" }] });
  await alert.getByRole("button", { name: "Retry" }).click();
  await expect(page.getByRole("heading", { name: "recovered-skill" })).toBeVisible();
  expect(mock.callsTo("skills").length).toBeGreaterThan(1);
  expect(consoleErrors).toEqual([]);
});
