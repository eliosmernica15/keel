import {
  test,
  expect,
  mockBridge,
  openApp,
  gotoDestination,
  capabilitiesTab,
} from "./fixtures";

test("command catalogue is real, execution reports real results and real errors", async ({
  page,
  consoleErrors,
}) => {
  void consoleErrors;
  const mock = await mockBridge(page, {
    handlers: {
      commands: {
        commands: [
          { name: "review", description: "Review current changes", source: "bundled", argument_hint: "--all" },
        ],
      },
      "commands/execute": {
        ok: true,
        name: "review",
        result: "reviewed 3 files, 0 problems",
      },
    },
  });

  await openApp(page);
  await gotoDestination(page, "Capabilities");
  await capabilitiesTab(page, "Commands");

  await expect(page.getByRole("heading", { name: "/review" })).toBeVisible();
  await expect(page.getByText("Review current changes")).toBeVisible();
  await expect(page.getByText("bundled", { exact: true })).toBeVisible();

  // Client-only slash commands are reference material, not runnable bridge commands.
  const clientRow = page.locator("li").filter({ hasText: "/context" }).first();
  await expect(clientRow).toBeVisible();
  await expect(clientRow.getByRole("button", { name: "Run…" })).toHaveCount(0);
  await expect(clientRow).toContainText("not runnable via bridge");

  const row = page.locator("li").filter({ hasText: "/review" }).first();
  await row.getByRole("button", { name: "Run…" }).click();
  const dialog = page.getByRole("dialog", { name: "Run /review" });
  await dialog.getByLabel("Arguments").fill("src");
  await dialog.getByRole("button", { name: "Run command" }).click();
  await expect(page.getByText("Command review completed")).toBeVisible();
  await expect(page.getByText("reviewed 3 files, 0 problems")).toBeVisible();
  expect(mock.callsTo("commands/execute").at(-1)?.body).toEqual({
    name: "review",
    args: "src",
  });

  await page.getByRole("dialog", { name: "Run /review" }).getByRole("button", { name: "Cancel" }).click();

  // A backend refusal must not be rendered as a success. A 200 envelope with
  // {error} keeps the browser's own network-error noise out of this UI gate.
  mock.set("commands/execute", { error: "command not found" });
  await row.getByRole("button", { name: "Run…" }).click();
  await page.getByRole("dialog", { name: "Run /review" }).getByRole("button", { name: "Run command" }).click();
  await expect(page.getByText("Execution failed: command not found")).toBeVisible();
  await expect(page.getByText("Command review completed")).toHaveCount(0);
  expect(consoleErrors).toEqual([]);
});

test("workflows run through the guarded runner and show real per-step outcomes", async ({
  page,
  consoleErrors,
}) => {
  void consoleErrors;
  const mock = await mockBridge(page, {
    handlers: {
      workflows: {
        workflows: [{ name: "check-changes", description: "Check the tree", source: "user", steps: 2 }],
      },
      "workflows/execute": {
        ok: false,
        name: "check-changes",
        results: [
          { ok: true, detail: "git status read" },
          { ok: false, error: "write_file denied by Tier-1 gate" },
        ],
      },
    },
  });

  await openApp(page);
  await gotoDestination(page, "Capabilities");
  await capabilitiesTab(page, "Workflows");

  await expect(page.getByText("A runner, not a builder: the bridge exposes discovery and guarded execution, but no node-schema, versioning or dry-run API for a visual editor.")).toBeVisible();
  await expect(page.getByRole("heading", { name: "check-changes" })).toBeVisible();
  await expect(page.getByText("2 steps")).toBeVisible();
  await expect(page.getByRole("button", { name: /Add step|Save workflow/ })).toHaveCount(0);

  await page.getByRole("button", { name: "Run…" }).click();
  await page.getByRole("dialog", { name: "Run workflow: check-changes" }).getByLabel("Project root (optional)").fill("C:\\fixtures\\project");
  await page.getByRole("dialog", { name: "Run workflow: check-changes" }).getByRole("button", { name: "Run workflow" }).click();

  await expect(page.getByText("check-changes: at least one step failed")).toBeVisible();
  await expect(page.getByText("git status read")).toBeVisible();
  await expect(page.getByText("write_file denied by Tier-1 gate")).toBeVisible();
  await expect(page.getByText("OK", { exact: true })).toBeVisible();
  await expect(page.getByText("Failed", { exact: true })).toBeVisible();
  expect(mock.callsTo("workflows/execute").at(-1)?.body).toEqual({
    name: "check-changes",
    project_root: "C:\\fixtures\\project",
  });

  mock.set("workflows/execute", { error: "workflow not found" });
  await page.getByRole("button", { name: "Run…" }).click();
  await page.getByRole("dialog", { name: "Run workflow: check-changes" }).getByRole("button", { name: "Run workflow" }).click();
  await expect(page.getByText("Run failed: workflow not found")).toBeVisible();
  expect(consoleErrors).toEqual([]);
});

test("tools view lists only names observed in real session rows", async ({
  page,
  consoleErrors,
}) => {
  void consoleErrors;
  await mockBridge(page, {
    handlers: {
      bots: { bots: [{ id: "b1", name: "Observed bot" }] },
      "bots/b1/rows": {
        rows: [
          { seq: 1, kind: "step", body: { tool_name: "read_file" } },
          { seq: 2, kind: "step", body: { tool_name: "read_file" } },
          { seq: 3, kind: "user", body: { content: "hello" } },
        ],
      },
    },
  });

  await openApp(page);
  await gotoDestination(page, "Capabilities");
  await capabilitiesTab(page, "Tools");

  await expect(page.getByText("No tool catalogue endpoint in this bridge build")).toBeVisible();
  await expect(page.getByText("read_file", { exact: true })).toBeVisible();
  await expect(page.getByText("2 observed rows")).toBeVisible();
  await expect(page.getByText("No tool calls in recent rows")).toHaveCount(0);
  // The client's real slash-command list is labelled as client-side.
  await expect(page.getByText("Command catalogue in this client")).toBeVisible();
  expect(consoleErrors).toEqual([]);
});
