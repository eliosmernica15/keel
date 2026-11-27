import {
  test,
  expect,
  mockBridge,
  fulfillJson,
  openApp,
  gotoDestination,
  capabilitiesTab,
} from "./fixtures";

interface ManagedSkill {
  name: string;
  enabled: boolean;
  scope: string;
  path?: string;
  sha256?: string;
}

test("skills enable, install and remove call real bridge routes and show real outcomes", async ({
  page,
  consoleErrors,
}) => {
  void consoleErrors;
  let managed: ManagedSkill[] = [
    { name: "code-review", enabled: true, scope: "user", path: "~/.keel/skills/code-review", sha256: "abc123" },
  ];
  const mock = await mockBridge(page, {
    handlers: {
      skills: {
        skills: [
          { name: "code-review", description: "Reviews code", scope: "user", trusted: true, injection_suspects: 0 },
          { name: "bundled-skill", description: "Ships with Keel", scope: "bundled", trusted: true, injection_suspects: 0 },
        ],
      },
      "skills/manage": (route) => fulfillJson(route, { skills: managed }),
      "skills/enable": async (route, request) => {
        const body = JSON.parse(request.postData() ?? "{}") as { name: string; enabled: boolean };
        managed = managed.map((skill) => skill.name === body.name ? { ...skill, enabled: body.enabled } : skill);
        await fulfillJson(route, { ok: true, name: body.name, enabled: body.enabled });
      },
      "skills/install": async (route, request) => {
        const body = JSON.parse(request.postData() ?? "{}") as { name?: string; scope: string };
        const name = body.name ?? "installed-skill";
        managed = [...managed, { name, enabled: true, scope: body.scope }];
        await fulfillJson(route, { ok: true, name, scope: body.scope, path: `~/.keel/skills/${name}` });
      },
      "skills/remove": async (route, request) => {
        const body = JSON.parse(request.postData() ?? "{}") as { name: string };
        managed = managed.filter((skill) => skill.name !== body.name);
        await fulfillJson(route, { ok: true, removed: true });
      },
    },
  });

  await openApp(page);
  await gotoDestination(page, "Capabilities");
  await capabilitiesTab(page, "Skills");

  const toggle = page.getByRole("checkbox", { name: "Enable code-review" });
  // The shared Toggle visually hides its <input>; users click the label.
  const toggleLabel = page.locator("label.keel-toggle").filter({ hasText: "Enable code-review" });
  await expect(toggle).toBeChecked();
  await expect(page.getByText("abc123")).toHaveCount(0); // hash is only in details
  await toggleLabel.click();
  await expect(page.getByText("code-review disabled.")).toBeVisible();
  await expect(toggle).not.toBeChecked();
  expect(mock.callsTo("skills/enable").at(-1)?.body).toEqual({ name: "code-review", enabled: false });
  await toggleLabel.click();
  await expect(page.getByText("code-review enabled.")).toBeVisible();
  expect(mock.callsTo("skills/enable").at(-1)?.body).toEqual({ name: "code-review", enabled: true });

  // Bundled skills cannot be removed by the bridge; the control is withheld.
  const bundledRow = page.locator("li").filter({ hasText: "bundled-skill" }).first();
  await expect(bundledRow.getByRole("button", { name: "Remove bundled-skill" })).toHaveCount(0);

  await page.getByRole("button", { name: "Install skill" }).click();
  const installDialog = page.getByRole("dialog", { name: "Install a skill" });
  await installDialog.getByLabel("Source (path or URL)").fill("C:\\fixtures\\new-skill");
  await installDialog.getByLabel("Name (optional)").fill("new-skill");
  await installDialog.getByRole("button", { name: "Install" }).click();
  await expect(page.getByText("new-skill installed (user scope).")).toBeVisible();
  await expect(page.getByRole("heading", { name: "new-skill" })).toBeVisible();
  expect(mock.callsTo("skills/install").at(-1)?.body).toEqual({
    source: "C:\\fixtures\\new-skill",
    scope: "user",
    name: "new-skill",
  });

  await page.getByRole("button", { name: "Remove new-skill" }).click();
  const removeDialog = page.getByRole("dialog", { name: "Remove skill?" });
  await expect(removeDialog).toContainText("new-skill");
  await removeDialog.getByRole("button", { name: "Remove skill" }).click();
  await expect(page.getByText("new-skill removed.")).toBeVisible();
  await expect(page.getByRole("heading", { name: "new-skill" })).toHaveCount(0);
  expect(mock.callsTo("skills/remove").at(-1)?.body).toEqual({ name: "new-skill", scope: "user" });

  // A refused change is reported inline — never as a false success.
  mock.set("skills/enable", { ok: false, error: "disabled list is read-only" });
  await toggleLabel.click();
  await expect(page.getByRole("alert").filter({ hasText: "disabled list is read-only" })).toBeVisible();
  await expect(page.getByText("code-review disabled.")).toHaveCount(0);
  expect(consoleErrors).toEqual([]);
});

test("MCP health is only shown after a real bridge probe, including failures", async ({
  page,
  consoleErrors,
}) => {
  void consoleErrors;
  const mock = await mockBridge(page, {
    handlers: {
      "mcp/servers": {
        servers: [
          { name: "local-tools", transport: "stdio", scope: "user", command: "node" },
          { name: "remote", transport: "http", scope: "user", url: "http://127.0.0.1:9999/mcp" },
        ],
      },
      "mcp/health": { error: "bridge refused the health probe" },
    },
  });

  await openApp(page);
  await gotoDestination(page, "Capabilities");
  await capabilitiesTab(page, "MCP servers");
  await expect(page.getByRole("heading", { name: "local-tools" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "remote" })).toBeVisible();
  await expect(page.getByText("Not checked")).toHaveCount(2);

  await page.getByRole("button", { name: "Run health check" }).click();
  await expect(page.getByText("Health check failed: bridge refused the health probe")).toBeVisible();
  await expect(page.getByText("Not checked")).toHaveCount(2);
  expect(mock.callsTo("mcp/health")).toHaveLength(1);

  mock.set("mcp/health", { health: { "local-tools": true, remote: false } });
  await page.getByRole("button", { name: "Run health check" }).click();
  await expect(page.getByText("Healthy", { exact: true })).toBeVisible();
  await expect(page.getByText("Unhealthy", { exact: true })).toBeVisible();
  await expect(page.getByText("Not checked")).toHaveCount(0);
  expect(mock.callsTo("mcp/health")).toHaveLength(2);
  expect(mock.callsTo("mcp/health")[1]?.method).toBe("POST");
  expect(consoleErrors).toEqual([]);
});

test("connectors add, test and remove surface real handshake results and errors", async ({
  page,
  consoleErrors,
}) => {
  void consoleErrors;
  interface Connector {
    name: string;
    command: string;
    args: string[];
    arg_count?: number;
    env_keys?: string[];
  }
  const argumentSecret = "opaque-user-supplied-secret-value";
  let configured: Connector[] = [
    {
      name: "filesystem",
      command: "npx",
      args: ["--token", argumentSecret],
      arg_count: 2,
      env_keys: ["FS_ROOT"],
    },
  ];
  const mock = await mockBridge(page, {
    handlers: {
      connectors: (route) => fulfillJson(route, {
        connectors: configured,
        presets: [{ name: "github", label: "GitHub", description: "GitHub tools", command: "npx" }],
      }),
      "connectors/add": async (route, request) => {
        const body = JSON.parse(request.postData() ?? "{}") as { name: string };
        configured = [...configured, { name: body.name, command: "npx", args: ["-y", "@mcp/github"] }];
        await fulfillJson(route, { ok: true, name: body.name, command: "npx" });
      },
      "connectors/remove": async (route, request) => {
        const body = JSON.parse(request.postData() ?? "{}") as { name: string };
        configured = configured.filter((connector) => connector.name !== body.name);
        await fulfillJson(route, { ok: true, name: body.name, removed: true });
      },
      "connectors/test": async (route, request) => {
        const body = JSON.parse(request.postData() ?? "{}") as { name: string };
        if (body.name === "github") {
          await fulfillJson(route, { ok: true, name: "github", tool_count: 1, tools: [{ name: "create_issue", description: "Create an issue" }] });
        } else {
          await fulfillJson(route, { ok: true, name: "filesystem", tool_count: 2, tools: [{ name: "read_file", description: "Read a file" }] });
        }
      },
    },
  });

  await openApp(page);
  await gotoDestination(page, "Capabilities");
  await capabilitiesTab(page, "Connectors");
  await expect(page.getByRole("heading", { name: "filesystem" })).toBeVisible();

  const fsRow = page.locator("li").filter({ hasText: "filesystem" }).first();
  await expect(fsRow.getByText("2 argument values hidden")).toBeVisible();
  await expect(fsRow.getByText(argumentSecret)).toHaveCount(0);
  await fsRow.getByRole("button", { name: "Test" }).click();
  await expect(page.getByText("Verified", { exact: true })).toBeVisible();
  await expect(page.getByText("read_file", { exact: true })).toBeVisible();
  expect(mock.callsTo("connectors/test").at(-1)?.body).toEqual({ name: "filesystem" });

  mock.set("connectors/test", {
    ok: false,
    name: "filesystem",
    error: "handshake failed: timeout",
  });
  await fsRow.getByRole("button", { name: "Test" }).click();
  await expect(page.getByText("Test failed", { exact: true })).toBeVisible();
  await expect(page.getByText("Test error: handshake failed: timeout")).toBeVisible();

  // Restore a truthful successful handshake for the newly added connector.
  mock.set("connectors/test", async (route, request) => {
    const body = JSON.parse(request.postData() ?? "{}") as { name: string };
    await fulfillJson(route, {
      ok: true,
      name: body.name,
      tool_count: 1,
      tools: [{ name: "create_issue", description: "Create an issue" }],
    });
  });
  await page.getByRole("button", { name: "Add", exact: true }).click();
  const addDialog = page.getByRole("dialog", { name: "Add github preset" });
  await addDialog.getByRole("button", { name: "Add connector" }).click();
  await expect(page.getByText("github added.")).toBeVisible();
  expect(mock.callsTo("connectors/add").at(-1)?.body).toMatchObject({ name: "github", preset: "github" });
  await expect(page.getByRole("heading", { name: "github" })).toBeVisible();
  // Adding a connector triggers a real handshake test, not an assumed success.
  await expect(page.getByText("create_issue", { exact: true })).toBeVisible();

  await page.getByRole("button", { name: "Remove github" }).click();
  const removeDialog = page.getByRole("dialog", { name: "Remove connector?" });
  await expect(removeDialog).toContainText("github");
  await removeDialog.getByRole("button", { name: "Remove", exact: true }).click();
  await expect(page.getByText("github removed.")).toBeVisible();
  await expect(page.getByRole("heading", { name: "github" })).toHaveCount(0);
  expect(mock.callsTo("connectors/remove").at(-1)?.body).toEqual({ name: "github" });
  expect(consoleErrors).toEqual([]);
});
