import {
  test,
  expect,
  mockBridge,
  openApp,
  gotoDestination,
  settingsSection,
  storageText,
} from "./fixtures";

// The bridge never returns a full provider key; these fixtures deliberately
// include leaky `key`/`api_key`/`secret` fields to prove the UI ignores them.
const SESSION_SECRET = "sk-ant-SESSION-do-not-leak-9f3a7c2e";
const SAVED_SECRET = "sk-ant-SAVED-do-not-leak-7b21fe04";
const PROVIDERS = [
  {
    name: "anthropic",
    configured: true,
    key_source: "settings.json",
    key_hint: "abcd",
    default_model: "claude-sonnet-4-5",
    notes: "Opt-in provider",
    opt_in: true,
    session: false,
    key: SESSION_SECRET,
    api_key: SESSION_SECRET,
    secret: SESSION_SECRET,
  },
];

test("credential fields are password-masked, never prefilled, never stored and never echoed", async ({
  page,
  consoleErrors,
}) => {
  void consoleErrors;
  const mock = await mockBridge(page, {
    handlers: { providers: { providers: PROVIDERS, session_keys: [] } },
    secrets: [SESSION_SECRET],
  });
  mock.set("providers/credential", {
    ok: true,
    provider: "anthropic",
    models: ["claude-test-1"],
    model_count: 1,
    models_meta: [],
    key_source: "session",
    note: "held for this process only; nothing was written to disk",
  });

  await openApp(page);
  await gotoDestination(page, "Settings");
  await settingsSection(page, "Credentials");

  const input = page.getByLabel("API key for anthropic");
  await expect(input).toBeVisible();
  await expect(input).toHaveAttribute("type", "password");
  await expect(input).toHaveAttribute("autocomplete", "off");
  await expect(input).toHaveAttribute("spellcheck", "false");
  await expect(input).toHaveValue("");
  await expect(page.locator("body")).not.toContainText(SESSION_SECRET);

  await input.fill(SESSION_SECRET);
  await page.getByRole("button", { name: "Verify for this session" }).click();

  await expect(page.getByText(/Accepted for this bridge process only \(1 models verified\)/)).toBeVisible();
  await expect(input).toHaveValue("");
  await expect(page.locator("body")).not.toContainText(SESSION_SECRET);
  expect(await storageText(page)).not.toContain(SESSION_SECRET);

  const calls = mock.callsTo("providers/credential");
  expect(calls).toHaveLength(1);
  expect(calls[0]?.method).toBe("POST");
  expect(calls[0]?.body).toMatchObject({ name: "anthropic", key: "[redacted]" });
  expect(calls[0]?.sawSecret).toBe(true);
  expect(mock.calls.filter((call) => call.sawSecret).map((call) => call.path))
    .toEqual(["providers/credential"]);
  expect(consoleErrors).toEqual([]);
});

test("saved-key flow shows only the four-character hint; save/remove are real calls", async ({
  page,
  consoleErrors,
}) => {
  void consoleErrors;
  const mock = await mockBridge(page, {
    handlers: { providers: { providers: PROVIDERS, session_keys: [] } },
    secrets: [SAVED_SECRET],
  });
  mock.set("providers/save", {
    ok: true,
    provider: "anthropic",
    models: ["claude-a", "claude-b"],
    model_count: 2,
    models_meta: [],
    hint: "fe04",
    note: "saved to ~/.keel/settings.json on this machine only",
  });
  mock.set("providers/remove", { ok: true, provider: "anthropic" });
  mock.set("providers/credential/clear", { ok: true, provider: "anthropic" });

  await openApp(page);
  await gotoDestination(page, "Settings");
  await settingsSection(page, "Credentials");

  const input = page.getByLabel("API key for anthropic");
  await input.fill(SAVED_SECRET);
  await page.getByRole("button", { name: "Save on this machine" }).click();

  await expect(page.getByText(/Saved to this machine \(2 models verified\)/)).toBeVisible();
  await expect(page.getByText("Saved ••••fe04")).toBeVisible();
  await expect(input).toHaveValue("");
  await expect(page.locator("body")).not.toContainText(SAVED_SECRET);
  expect(await storageText(page)).not.toContain(SAVED_SECRET);
  expect(mock.callsTo("providers/save")).toHaveLength(1);
  expect(mock.callsTo("providers/save")[0]?.body).toMatchObject({
    name: "anthropic",
    key: "[redacted]",
  });

  // Removing the saved key is a separate, confirmed backend operation.
  await page.getByRole("button", { name: "Remove saved key" }).click();
  await expect(page.getByRole("dialog", { name: "Remove saved key?" })).toBeVisible();
  await page.getByRole("button", { name: "Confirm removal" }).click();
  await expect(page.getByText("Saved key removed from Keel settings.", { exact: true })).toBeVisible();
  await expect(page.getByText("Saved ••••fe04")).toHaveCount(0);
  expect(mock.callsTo("providers/remove")).toHaveLength(1);
  expect(mock.callsTo("providers/remove")[0]?.body).toEqual({ name: "anthropic" });

  // Clearing a session key is likewise explicit and reported by the bridge.
  await page.getByRole("button", { name: "Forget session key" }).click();
  await expect(page.getByRole("dialog", { name: "Forget session key?" })).toBeVisible();
  await page.getByRole("button", { name: "Confirm removal" }).click();
  await expect(page.getByText("Session key cleared.", { exact: true })).toBeVisible();
  expect(mock.callsTo("providers/credential/clear")[0]?.body).toEqual({ name: "anthropic" });

  expect(consoleErrors).toEqual([]);
});

test("provider catalogue shows real bridge models and honest errors, never a fabricated list", async ({
  page,
  consoleErrors,
}) => {
  void consoleErrors;
  const mock = await mockBridge(page, {
    handlers: {
      providers: { providers: PROVIDERS, session_keys: [] },
      // First attempt: the bridge has no key, so it refuses the live catalogue.
      "providers/catalog": {
        ok: false,
        error: "not_configured",
        detail: "anthropic: no key in env or session",
      },
    },
  });

  await openApp(page);
  await gotoDestination(page, "Settings");
  await settingsSection(page, "Providers & models");
  await page.getByRole("button", { name: "Load models" }).click();

  await expect(page.getByText("anthropic: no key in env or session")).toBeVisible();
  await expect(page.getByText("claude-a", { exact: true })).toHaveCount(0);
  const offline = page.getByRole("button", { name: "Browse offline catalogue" });
  await expect(offline).toBeVisible();

  mock.set("providers/catalog", {
    ok: true,
    provider: "anthropic",
    source: "offline",
    catalog_version: "2026-11",
    models: ["claude-a", "claude-b"],
    model_count: 2,
    models_meta: [{ id: "claude-a", context_length: 200000, supported_parameters: ["tools"] }],
  });
  await offline.click();

  await expect(page.getByText("offline catalogue", { exact: true })).toBeVisible();
  await expect(page.getByText("catalog v2026-11")).toBeVisible();
  await expect(page.getByText("claude-a", { exact: true })).toBeVisible();
  await expect(page.getByText("200,000 ctx")).toBeVisible();
  expect(mock.callsTo("providers/catalog").at(-1)?.body).toEqual({
    name: "anthropic",
    source: "offline",
  });

  await page.getByRole("searchbox", { name: "Search models" }).fill("claude-b");
  await expect(page.getByText("claude-a", { exact: true })).toHaveCount(0);
  await expect(page.getByText("claude-b", { exact: true })).toBeVisible();

  // No global default-model control is fabricated where the bridge has no route.
  await expect(page.getByText(/There is no bridge route for a global default-model setting/)).toBeVisible();
  expect(consoleErrors).toEqual([]);
});
