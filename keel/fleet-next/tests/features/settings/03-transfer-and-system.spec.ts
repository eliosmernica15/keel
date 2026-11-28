import { test, expect, mockBridge, fulfillJson, openApp, gotoSettings, gotoCapabilities, settingsSection } from "./fixtures";

test("export links, import upload, keep-awake, diagnostics and project open are real", async ({ page, consoleErrors }) => {
  void consoleErrors;
  let awake = false;
  const mock = await mockBridge(page, {
    secrets: ["sk-secret-value-1234567890"],
    handlers: {
      bots: { bots: [{ id: "b1", name: "Chat A" }] },
      library: { files: [{ id: "f1", name: "notes.md", size: 12 }] },
      projects: { projects: [{ id: "p1", name: "Repo", path: "C:\\Repo", trusted: true }] },
      "projects/p1/open": { ok: true },
      "keep-awake": async (route, request) => {
        if (request.method() === "POST") {
          const body = JSON.parse(request.postData() ?? "{}") as { on?: boolean };
          awake = body.on === true;
        }
        await fulfillJson(route, { supported: true, on: awake, handle: awake ? "shell-1" : undefined });
      },
      skills: { skills: [{ name: "s1", description: "A skill" }] },
      "skills/manage": { skills: [{ name: "s1", enabled: true }] },
      "mcp/servers": { servers: [{ name: "srv1", transport: "stdio" }] },
      "mcp/health": { health: { srv1: true } },
      connectors: { connectors: [{ name: "c1" }], presets: [] },
    },
  });

  await openApp(page);
  await gotoSettings(page);

  await settingsSection(page, "Import & export");
  await expect(page.locator('a[href="/api/bridge/bots/b1/export.md"]')).toBeVisible();
  await expect(page.locator('a[href="/api/bridge/library/f1/download"]')).toBeVisible();
  await page.getByLabel("Import into chat").selectOption("b1");
  await page.getByLabel("File to import").setInputFiles({
    name: "notes.md", mimeType: "text/markdown", buffer: Buffer.from("hello notes"),
  });
  await page.getByRole("button", { name: "Import file" }).click();
  const uploads = () => mock.callsTo("library").filter((call) => call.method === "POST");
  await expect.poll(() => uploads().length).toBe(1);
  const upload = uploads()[0];
  expect(upload?.method).toBe("POST");
  expect(upload?.body).toMatchObject({ bot_id: "b1", filename: "notes.md" });
  expect(typeof upload?.body?.content_base64).toBe("string");
  expect(upload?.sawSecret).toBe(false);
  await expect(page.getByText("notes.md imported into the library.")).toBeVisible();

  await settingsSection(page, "Keel Desktop");
  const awakeToggle = page.getByRole("checkbox", { name: "Keep this machine awake while Keel runs" });
  await expect(awakeToggle).toBeEnabled();
  await page.locator('label.keel-toggle:has(input[aria-label="Keep this machine awake while Keel runs"])').click();
  await expect.poll(() => mock.callsTo("keep-awake").filter((c) => c.method === "POST").length).toBe(1);
  expect(mock.callsTo("keep-awake").find((c) => c.method === "POST")?.body).toEqual({ on: true });
  await expect(awakeToggle).toBeChecked();

  await settingsSection(page, "Developer");
  await expect(page.getByText("Skills discovered")).toBeVisible();
  await expect(page.getByText("1", { exact: true }).first()).toBeVisible();
  await page.getByRole("button", { name: "Run health check" }).click();
  await expect.poll(() => mock.callsTo("mcp/health").filter((c) => c.method === "POST").length).toBeGreaterThan(0);

  await settingsSection(page, "Keel Code");
  await expect(page.getByRole("heading", { name: "Repo" })).toBeVisible();
  await page.getByRole("button", { name: "Open in Code" }).click();
  await expect.poll(() => mock.callsTo("projects/p1/open").length).toBe(1);
  await expect(page.getByRole("tabpanel", { name: "code" })).toBeVisible();

  expect(consoleErrors).toEqual([]);
});

test("the Extensions tab lists real skills and connectors and switches tabs", async ({ page, consoleErrors }) => {
  void consoleErrors;
  await mockBridge(page, {
    handlers: {
      skills: { skills: [{ name: "s1", description: "A skill" }] },
      "skills/manage": { skills: [{ name: "s1", enabled: true }] },
      "mcp/servers": { servers: [{ name: "srv1" }] },
      connectors: { connectors: [{ name: "c1" }], presets: [] },
    },
  });
  await openApp(page);

  await gotoCapabilities(page);
  await page.getByRole("tab", { name: "Extensions" }).click();
  await expect(page.getByText("Skills · 1")).toBeVisible();
  await expect(page.getByText("MCP servers · 1")).toBeVisible();
  await expect(page.getByText("Connectors · 1")).toBeVisible();
  await expect(page.getByText("not available in this build")).toHaveCount(0);

  await page.getByRole("button", { name: "Manage connectors" }).click();
  await expect(page.getByRole("tab", { name: "Connectors" })).toHaveAttribute("aria-selected", "true");
  await expect(page.getByRole("heading", { name: "c1" })).toBeVisible();
  expect(consoleErrors).toEqual([]);
});
