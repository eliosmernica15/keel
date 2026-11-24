import {
  test,
  expect,
  mockBridge,
  openApp,
  gotoDestination,
  settingsSection,
  storageText,
} from "./fixtures";

// Real-shaped bot rows: the bridge stores `model` as a non-null TEXT that is
// empty when no per-agent choice has been made, and `engine` distinguishes the
// scripted Echo harness from a provider-backed agent.
const AGENTS = [
  {
    id: "b1", name: "Research", role: "researcher", engine: "provider",
    provider: "anthropic", model: "claude-sonnet-4-5",
  },
  {
    id: "b2", name: "Drafter", engine: "provider", provider: "anthropic", model: "",
  },
  { id: "b3", name: "Echo test", engine: "echo", model: "" },
];

const PROVIDERS = [
  {
    name: "anthropic", configured: true, key_source: "settings.json",
    key_hint: "abcd", default_model: "claude-sonnet-4-5", session: false,
  },
];

test("per-agent model save uses the real bots/:id/update route and reports honest state", async ({
  page,
  consoleErrors,
}) => {
  void consoleErrors;
  const agents = AGENTS.map((agent) => ({ ...agent }));
  const mock = await mockBridge(page, {
    handlers: {
      bots: (route) => route.fulfill({
        status: 200, contentType: "application/json",
        body: JSON.stringify({ bots: agents }),
      }),
      "bots/b1/update": async (route, request) => {
        const patch = JSON.parse(request.postData() ?? "{}") as { model: string };
        const updated = { ...agents[0], model: patch.model };
        agents[0] = updated;
        await route.fulfill({
          status: 200, contentType: "application/json",
          body: JSON.stringify({ bot: updated }),
        });
      },
      "bots/b2/update": async (route, request) => {
        const patch = JSON.parse(request.postData() ?? "{}") as { model: string };
        const updated = { ...agents[1], model: patch.model };
        agents[1] = updated;
        await route.fulfill({
          status: 200, contentType: "application/json",
          body: JSON.stringify({ bot: updated }),
        });
      },
      "providers/catalog": {
        ok: true, provider: "anthropic", source: "offline", catalog_version: "2026-11",
        models: ["claude-sonnet-4-5", "claude-opus-4-1"], model_count: 2,
      },
    },
  });

  await openApp(page);
  await gotoDestination(page, "Settings");
  await settingsSection(page, "Agent models");

  await expect(page.locator("main h1")).toHaveText("Agent models");
  await expect(page.locator('nav[aria-label="Breadcrumb"]')).toContainText("Models & providers");
  await expect(page.getByText("Model: claude-sonnet-4-5")).toBeVisible();
  await expect(page.getByText("Provider default", { exact: true })).toBeVisible();
  await expect(page.getByText(/No per-agent model is set/)).toBeVisible();
  await expect(page.getByText(/no bridge route for a global default-model/)).toBeVisible();

  // A scripted Echo agent never calls a model: no dead model control is shown.
  const echoRow = page.locator("li").filter({ hasText: "Echo test" }).first();
  await expect(echoRow.getByText("Scripted Echo agent")).toBeVisible();
  await expect(echoRow.getByRole("textbox")).toHaveCount(0);
  await expect(echoRow.getByRole("button", { name: /Save model for Echo test/ })).toHaveCount(0);

  // Catalogue selection is real: models appear only after a bridge response.
  const researchRow = page.locator("li").filter({ hasText: "Research" }).first();
  await researchRow.getByRole("button", { name: "Browse offline catalogue" }).click();
  const picker = researchRow.getByRole("combobox", { name: /Pick a model from the offline catalogue/ });
  await expect(picker).toBeVisible();
  await expect(picker.locator("option")).toHaveCount(3); // provider default + 2 models
  await picker.selectOption("claude-opus-4-1");
  await expect(researchRow.getByRole("textbox", { name: "Model for Research" })).toHaveValue("claude-opus-4-1");
  await researchRow.getByRole("button", { name: "Save model for Research" }).click();

  await expect(page.getByText("Model saved for Research: claude-opus-4-1.")).toBeVisible();
  await expect(researchRow.getByText("Model: claude-opus-4-1")).toBeVisible();
  const saveCalls = mock.callsTo("bots/b1/update");
  expect(saveCalls).toHaveLength(1);
  expect(saveCalls[0]?.method).toBe("POST");
  expect(saveCalls[0]?.body).toEqual({ model: "claude-opus-4-1" });

  // A refused update is an inline error, never a false success.
  mock.set("bots/b1/update", {
    __status: 400, body: { error: "model not allowed for this provider" },
  });
  await researchRow.getByRole("textbox", { name: "Model for Research" }).fill("not-a-real-model");
  await researchRow.getByRole("button", { name: "Save model for Research" }).click();
  await expect(researchRow.getByRole("alert").filter({ hasText: "model not allowed for this provider" })).toBeVisible();
  await expect(page.getByText("Model saved for Research: not-a-real-model.")).toHaveCount(0);

  // A successful envelope without the confirmed bot is also not a success.
  mock.set("bots/b1/update", { ok: false, error: "update was not applied" });
  await researchRow.getByRole("button", { name: "Save model for Research" }).click();
  await expect(researchRow.getByRole("alert").filter({ hasText: "The bridge did not confirm the agent update." })).toBeVisible();

  // Clearing writes an empty model through the same real route and reports the
  // honest fallback to the provider default.
  mock.set("bots/b1/update", async (route, request) => {
    const patch = JSON.parse(request.postData() ?? "{}") as { model: string };
    const updated = { ...agents[0], model: patch.model };
    agents[0] = updated;
    await route.fulfill({
      status: 200, contentType: "application/json",
      body: JSON.stringify({ bot: updated }),
    });
  });
  await researchRow.getByRole("button", { name: "Clear model for Research" }).click();
  await expect(page.getByText("Per-agent model cleared for Research; the provider default applies.")).toBeVisible();
  expect(mock.callsTo("bots/b1/update").at(-1)?.body).toEqual({ model: "" });
  await expect(researchRow.getByText("Provider default", { exact: true })).toBeVisible();
  expect(consoleErrors).toEqual([]);
});

test("provider verification and save failures are honest, masked and never stored", async ({
  page,
  consoleErrors,
}) => {
  void consoleErrors;
  const BAD_KEY = "sk-ant-INVALID-do-not-leak-51ac9d30";
  const mock = await mockBridge(page, {
    handlers: {
      providers: { providers: PROVIDERS, session_keys: [] },
      "providers/credential": {
        ok: false, error: "invalid_key", detail: "provider rejected the key (HTTP 401)",
      },
      "providers/save": {
        ok: false, error: "bad_key", detail: "key must be 1-512 characters",
      },
      "providers/remove": {
        ok: false, error: "not_saved", detail: "anthropic: no stored key",
      },
    },
    secrets: [BAD_KEY],
  });

  await openApp(page);
  await gotoDestination(page, "Settings");
  await settingsSection(page, "Credentials");

  const input = page.getByLabel("API key for anthropic");
  await input.fill(BAD_KEY);
  await page.getByRole("button", { name: "Verify for this session" }).click();
  await expect(page.getByText("provider rejected the key (HTTP 401)")).toBeVisible();
  await expect(page.getByText(/Accepted for this bridge process only/)).toHaveCount(0);
  await expect(input).toHaveValue("");
  await expect(page.locator("body")).not.toContainText(BAD_KEY);
  expect(await storageText(page)).not.toContain(BAD_KEY);

  await input.fill(BAD_KEY);
  await page.getByRole("button", { name: "Save on this machine" }).click();
  await expect(page.getByText("key must be 1-512 characters")).toBeVisible();
  await expect(page.getByText(/Saved to this machine/)).toHaveCount(0);
  await expect(page.getByText("Saved ••••")).toHaveCount(0);
  await expect(page.locator("body")).not.toContainText(BAD_KEY);
  expect(await storageText(page)).not.toContain(BAD_KEY);
  expect(mock.callsTo("providers/credential")).toHaveLength(1);
  expect(mock.callsTo("providers/save")).toHaveLength(1);

  // A refused removal keeps the dialog open and never claims success.
  await page.getByRole("button", { name: "Remove saved key" }).click();
  await page.getByRole("dialog", { name: "Remove saved key?" }).getByRole("button", { name: "Confirm removal" }).click();
  await expect(page.getByText("anthropic: no stored key")).toBeVisible();
  await expect(page.getByText("Saved key removed from Keel settings.")).toHaveCount(0);
  await expect(page.getByRole("dialog", { name: "Remove saved key?" })).toBeVisible();
  expect(mock.callsTo("providers/remove")).toHaveLength(1);
  expect(consoleErrors).toEqual([]);
});

test("bridge-unavailable and catalogue error states are shown honestly with a retry", async ({
  page,
  consoleErrors,
}) => {
  void consoleErrors;
  const mock = await mockBridge(page, {
    handlers: {
      providers: { __status: 502, body: { error: "bridge_unavailable" } },
    },
  });

  await openApp(page);
  await gotoDestination(page, "Settings");
  await settingsSection(page, "Providers & models");

  await expect(page.getByText("The local bridge is unavailable")).toBeVisible();
  await expect(page.getByText("bridge_unavailable")).toBeVisible();
  await expect(page.getByRole("button", { name: "Load models" })).toHaveCount(0);

  mock.set("providers", { providers: PROVIDERS, session_keys: [] });
  await page.getByRole("button", { name: "Retry" }).click();
  await expect(page.getByRole("heading", { name: "anthropic" })).toBeVisible();

  // Live catalogue refusal uses the real error category, with an offline route
  // still available; a second refusal is shown as-is.
  mock.set("providers/catalog", {
    ok: false, error: "http_error", detail: "provider returned HTTP 500",
  });
  await page.getByRole("button", { name: "Load models" }).click();
  await expect(page.getByText("provider returned HTTP 500")).toBeVisible();
  await expect(page.getByRole("button", { name: "Browse offline catalogue" })).toBeVisible();
  expect(mock.callsTo("providers/catalog")).toHaveLength(1);
  expect(consoleErrors).toEqual([]);
});
