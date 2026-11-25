import {
  test,
  expect,
  openApp,
  expectBridgeOnline,
  gotoTop,
  captureTrustRequests,
} from "./fixtures";

test("Cowork home shows an empty state and real composer controls", async ({
  page,
  consoleErrors,
}) => {
  void consoleErrors;
  await openApp(page);
  await expectBridgeOnline(page);

  await expect(page.getByRole("heading", { name: /A calm place to/ })).toBeVisible();
  await expect(
    page.getByText("Describe a task and Keel will work in your local workspace"),
  ).toBeVisible();

  const composer = page.getByRole("textbox", { name: "Message Keel" });
  const send = page.getByRole("button", { name: "Send message" });
  await expect(composer).toBeVisible();
  await expect(send).toBeDisabled();
  await expect(page.getByRole("button", { name: "Attach files" })).toBeVisible();
  await expect(page.getByRole("combobox", { name: "Permission mode" })).toHaveValue("build");
  await expect(page.getByText("Quick starts")).toBeVisible();
  await expect(page.getByRole("button", { name: /Summarize the key points/ })).toBeVisible();

  await composer.fill("A real test draft, not sent");
  await expect(send).toBeEnabled();
  await page.getByRole("button", { name: /Summarize the key points/ }).click();
  await expect(composer).toHaveValue(/Summarize the key points/);
  // Draft is local only; no agent run was started by these UI checks.
  await expect(page.getByRole("heading", { name: /A calm place to/ })).toBeVisible();
});

test("Fleet renders agents and tasks reported by the real bridge", async ({
  page,
  consoleErrors,
}) => {
  void consoleErrors;
  await openApp(page);
  await expectBridgeOnline(page);

  const botsResponse = await page.request.get("/api/bridge/bots");
  expect(botsResponse.ok()).toBeTruthy();
  const bots = ((await botsResponse.json()) as { bots?: Array<{ id: string; name?: string }> })
    .bots ?? [];
  expect(bots.length).toBeGreaterThan(0);

  const tasksResponse = await page.request.get("/api/bridge/tasks");
  expect(tasksResponse.ok()).toBeTruthy();
  const tasks = ((await tasksResponse.json()) as {
    tasks?: Array<{ id: string; title?: string }>;
  }).tasks ?? [];
  expect(tasks.length).toBeGreaterThan(0);

  await gotoTop(page, "Fleet");
  await expect(page.getByRole("heading", { name: "Fleet", exact: true })).toBeVisible();

  const agentsTab = page.getByRole("tab", { name: /Agents/ });
  await expect(agentsTab).toContainText(String(bots.length));
  for (const bot of bots.slice(0, 3)) {
    const name = bot.name || bot.id;
    await expect(page.getByRole("button", { name: `Select ${name}` }).first()).toBeVisible();
  }

  const tasksTab = page.getByRole("tab", { name: /Tasks/ });
  await tasksTab.click();
  await expect(tasksTab).toContainText(String(tasks.length));
  for (const task of tasks.slice(0, 2)) {
    const title = task.title || task.id;
    await expect(page.getByRole("button", { name: `Open task ${title}` })).toBeVisible();
  }
});

test("Code and Duet show empty states without granting trust", async ({
  page,
  consoleErrors,
}) => {
  void consoleErrors;
  const projectsResponse = await page.request.get("/api/bridge/projects");
  expect(projectsResponse.ok()).toBeTruthy();
  const projects =
    ((await projectsResponse.json()) as { projects?: Array<{ id: string; trusted?: boolean }> })
      .projects ?? [];

  const trustCalls = captureTrustRequests(page);
  await openApp(page);
  await expectBridgeOnline(page);

  await gotoTop(page, "Code");
  await expect(page.locator('main[aria-label="Code workspace"]')).toBeVisible();
  if (projects.length === 0) {
    await expect(page.getByText("No project selected")).toBeVisible();
    await expect(page.getByRole("button", { name: "Add project" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Trust this local folder?" })).toHaveCount(0);
  }

  await gotoTop(page, "Duet");
  await expect(page.locator('main[aria-label="Duet active workspace"]')).toBeVisible();
  if (projects.length === 0) {
    await expect(page.getByText("No project selected")).toBeVisible();
    await expect(page.getByRole("button", { name: "Add project" })).toBeVisible();
    await expect(
      page.getByRole("heading", { name: "Trust this folder before using Duet" }),
    ).toHaveCount(0);
  }

  // No loader may silently call the trust endpoint, and the bridge's persisted
  // trust flags must be byte-for-byte unchanged after visiting both surfaces.
  expect(trustCalls, "no automatic project trust request was made").toEqual([]);
  const afterResponse = await page.request.get("/api/bridge/projects");
  expect(await afterResponse.json()).toEqual(await projectsResponse.json());
});

test("an untrusted project shows explicit trust gates in Code and Duet", async ({
  page,
  consoleErrors,
}) => {
  void consoleErrors;
  // A read-only UI fixture: never mutates the real bridge's project registry.
  await page.route(
    (url) => url.pathname === "/api/bridge/projects",
    async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          projects: [
            {
              id: "e2e-untrusted-fixture",
              name: "E2E fixture",
              path: "C:\\e2e\\fixture",
              trusted: false,
            },
          ],
        }),
      });
    },
  );

  const trustCalls = captureTrustRequests(page);
  await openApp(page);

  await gotoTop(page, "Code");
  // Wait for the bridge project list to finish loading before checking the gate.
  await expect(page.getByRole("combobox", { name: "Active project" })).toHaveValue(
    "e2e-untrusted-fixture",
  );
  const codeGate = page.getByRole("heading", { name: "Trust this local folder?" });
  await expect(codeGate).toBeVisible();
  await expect(page.getByText(/Keel never trusts a folder automatically/)).toBeVisible();
  await expect(page.getByRole("button", { name: /Trust this folder/ })).toBeVisible();
  await expect(page.getByRole("button", { name: "Reject" })).toBeVisible();
  await expect(page.getByText("Not trusted")).toBeVisible();
  expect(trustCalls).toEqual([]);

  await gotoTop(page, "Duet");
  await expect(
    page.getByRole("heading", { name: "Trust this folder before using Duet" }),
  ).toBeVisible();
  await expect(page.getByText(/There is no automatic trust/)).toBeVisible();
  await expect(page.getByRole("button", { name: "Trust", exact: true })).toBeVisible();
  expect(trustCalls, "viewing the gate never grants trust").toEqual([]);
});
