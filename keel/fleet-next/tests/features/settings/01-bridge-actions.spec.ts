import { test, expect, mockBridge, openApp, gotoSettings, settingsSection } from "./fixtures";

test("skills, commands, workflows, MCP and connectors call their real routes", async ({ page, consoleErrors }) => {
  void consoleErrors;
  let connectors = [{ name: "github", command: "npx" }];
  const mock = await mockBridge(page, {
    handlers: {
      skills: { skills: [{ name: "code-review", description: "Review changes", scope: "user" }] },
      "skills/manage": { skills: [{ name: "code-review", enabled: true }] },
      "skills/enable": { ok: true, name: "code-review", enabled: false },
      commands: { commands: [{ name: "context", description: "Show workspace context", source: "bundled", argument_hint: "/context" }] },
      "commands/execute": { ok: true, name: "context", result: "workspace context" },
      workflows: { workflows: [{ name: "nightly", description: "Nightly checks", source: "user", steps: 2 }] },
      "workflows/execute": { ok: true, name: "nightly", results: [{ ok: true }] },
      "mcp/servers": { servers: [{ name: "filesystem", transport: "stdio", scope: "user", command: "npx" }] },
      "mcp/health": { health: { filesystem: true } },
      "connectors/test": { ok: true, name: "github", tool_count: 3 },
      "connectors/remove": { ok: true },
    },
  });
  // A stateful handler keeps the connector list in sync with add/remove calls.
  mock.set("connectors", async (route) => {
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ connectors, presets: [] }) });
  });

  await openApp(page);
  await gotoSettings(page);

  await settingsSection(page, "Skills");
  await expect(page.getByRole("heading", { name: "code-review" })).toBeVisible();
  const skillToggle = page.getByRole("checkbox", { name: "Enable code-review" });
  await expect(skillToggle).toBeEnabled();
  // The shared Toggle renders a visually hidden checkbox; click its label.
  await page.locator('label.keel-toggle:has(input[aria-label="Enable code-review"])').click();
  await expect.poll(() => mock.callsTo("skills/enable").length).toBe(1);
  expect(mock.callsTo("skills/enable")[0]?.body).toEqual({ name: "code-review", enabled: false });

  await settingsSection(page, "Commands");
  await expect(page.getByRole("heading", { name: /\/context/ })).toBeVisible();
  await page.getByRole("button", { name: "Run…" }).click();
  const commandDialog = page.getByRole("dialog", { name: "Run /context" });
  await commandDialog.getByPlaceholder("Optional arguments").fill("workspace");
  await commandDialog.getByRole("button", { name: "Run command" }).click();
  await expect.poll(() => mock.callsTo("commands/execute").length).toBe(1);
  expect(mock.callsTo("commands/execute")[0]?.body).toEqual({ name: "context", args: "workspace" });
  await expect(page.getByText("Command completed")).toBeVisible();

  await settingsSection(page, "Workflows");
  await expect(page.getByRole("heading", { name: "nightly" })).toBeVisible();
  await page.getByRole("button", { name: "Run…" }).click();
  await page.getByRole("dialog", { name: "Run workflow: nightly" }).getByRole("button", { name: "Run workflow" }).click();
  await expect.poll(() => mock.callsTo("workflows/execute").length).toBe(1);
  expect(mock.callsTo("workflows/execute")[0]?.body).toEqual({ name: "nightly" });
  await expect(page.getByText("nightly: 1 step completed")).toBeVisible();

  await settingsSection(page, "MCP Servers");
  await expect(page.getByRole("heading", { name: "filesystem" })).toBeVisible();
  await page.getByRole("button", { name: "Run health check" }).click();
  await expect.poll(() => mock.callsTo("mcp/health").filter((c) => c.method === "POST").length).toBeGreaterThan(0);
  await expect(page.getByText("Healthy", { exact: true })).toBeVisible();

  await settingsSection(page, "Plugins");
  await expect(page.getByRole("heading", { name: "github" })).toBeVisible();
  await page.getByRole("button", { name: "Test" }).click();
  await expect(page.getByText("Handshake succeeded (3 tools).")).toBeVisible();
  expect(mock.callsTo("connectors/test")[0]?.body).toEqual({ name: "github" });

  await page.getByRole("button", { name: "Remove…" }).click();
  const removeDialog = page.getByRole("dialog", { name: "Remove github?" });
  await removeDialog.getByRole("button", { name: "Cancel" }).click();
  expect(mock.callsTo("connectors/remove")).toHaveLength(0);
  await page.getByRole("button", { name: "Remove…" }).click();
  await page.getByRole("dialog", { name: "Remove github?" }).getByRole("button", { name: "Remove connector" }).click();
  await expect.poll(() => mock.callsTo("connectors/remove").length).toBe(1);
  expect(mock.callsTo("connectors/remove")[0]?.body).toEqual({ name: "github" });
  connectors = [];
  await expect(page.getByRole("heading", { name: "No connectors configured" })).toBeVisible();

  await page.getByRole("button", { name: "Add connector" }).first().click();
  const addDialog = page.getByRole("dialog", { name: "Add connector" });
  await addDialog.getByPlaceholder("Connector name").fill("new-connect");
  await addDialog.getByPlaceholder("Executable for the MCP server").fill("npx");
  await addDialog.getByRole("button", { name: "Add connector" }).click();
  await expect.poll(() => mock.callsTo("connectors/add").length).toBe(1);
  expect(mock.callsTo("connectors/add")[0]?.body).toMatchObject({ name: "new-connect", command: "npx" });
  expect(consoleErrors).toEqual([]);
});
