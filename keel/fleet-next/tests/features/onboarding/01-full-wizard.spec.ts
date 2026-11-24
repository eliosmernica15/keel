import {
  test, expect, openWizard, wizard, advance, readChecklist,
  TEST_KEY, TEST_PATH, TEST_PROVIDER,
} from "./fixtures";

test("full wizard verifies a key for real, saves a masked hint, trusts explicitly and finishes", async ({
  page, bridge, consoleErrors, hydrationWarnings,
}) => {
  void consoleErrors; void hydrationWarnings;
  await openWizard(page);
  const d = wizard(page);

  // First launch: three real entry choices, no fourth fake one.
  await expect(d.getByText("Step 1 of 8")).toBeVisible();
  await expect(d.getByRole("button", { name: /Start with Cowork/ })).toBeVisible();
  await expect(d.getByRole("button", { name: /Start with Code/ })).toBeVisible();
  await expect(d.getByRole("button", { name: /Set up Fleet/ })).toBeVisible();
  await expect(d.getByText(/three places to begin/)).toBeVisible();
  await d.getByRole("button", { name: /Start with Code/ }).click();
  await expect(d.getByRole("heading", { name: "How Keel works" })).toBeVisible();
  await expect(page.locator(".keel-statusbar")).toContainText("Surface: code");
  await advance(page);

  // Provider: the offline catalogue is browsing only, verification is a real call.
  await expect(d.getByRole("heading", { name: "Connect a provider" })).toBeVisible();
  await d.getByRole("radio", { name: /anthropic/i }).click();
  await expect(d.getByText(/Offline catalogue: 3 models.*browsing only, not a connection test/)).toBeVisible();
  await d.getByLabel("Provider API key").fill(TEST_KEY);
  await d.getByRole("button", { name: /Verify & use for this session/ }).click();
  await expect(d.getByText(/Verified with the live provider — 3 models available/)).toBeVisible();
  const credentialCalls = bridge.callsMatching("POST", "providers/credential");
  expect(credentialCalls).toHaveLength(1);
  expect(credentialCalls[0].body).toEqual({ name: TEST_PROVIDER, key: TEST_KEY });

  await d.getByRole("button", { name: "Save on this device" }).click();
  await expect(d.getByText(/Saved on this device only \(hint: …a1b2\)/)).toBeVisible();
  const saveCalls = bridge.callsMatching("POST", "providers/save");
  expect(saveCalls).toHaveLength(1);
  expect(saveCalls[0].body).toEqual({ name: TEST_PROVIDER, key: TEST_KEY });
  // The full key is never rendered back to the user.
  await expect(d).not.toContainText(TEST_KEY);
  await advance(page);

  // Workspace: adding is NOT trusting; the trust call happens only on decision.
  await expect(d.getByRole("heading", { name: "Choose a workspace" })).toBeVisible();
  await d.getByLabel("Absolute folder path").fill(TEST_PATH);
  await d.getByRole("button", { name: "Add folder" }).click();
  await expect(d.getByText(/NOT trusted yet — make an explicit decision below/)).toBeVisible();
  expect(bridge.callsMatching("POST", "projects")).toHaveLength(1);
  expect(bridge.callsMatching("POST", "projects/p1/trust")).toHaveLength(0);
  await d.getByRole("button", { name: "Trust this folder" }).click();
  await expect(d.getByText(/Trusted\. Keel can now work in this folder/)).toBeVisible();
  const trustCalls = bridge.callsMatching("POST", "projects/p1/trust");
  expect(trustCalls).toHaveLength(1);
  expect(trustCalls[0].body).toEqual({ trusted: true });
  await advance(page);

  // Permission: exactly the four modes the bridge accepts.
  await expect(d.getByRole("heading", { name: "Permission mode" })).toBeVisible();
  for (const name of ["Plan", "Build", "Accept edits", "Autopilot"]) {
    await expect(d.getByRole("radio", { name: new RegExp(`\\b${name}\\b`, "i") })).toBeVisible();
  }
  await d.getByRole("radio", { name: /Accept edits/i }).click();
  await expect(page.locator(".keel-notices")).toContainText("Permission mode saved: Accept edits");
  expect(await page.evaluate(() => localStorage.getItem("keel-mode"))).toBe("acceptEdits");
  await advance(page);

  // Capabilities: provenance copy, real lists, nothing installed here.
  await expect(d.getByRole("heading", { name: "Capabilities (optional)" })).toBeVisible();
  await expect(d.getByText("keel-bundled-review")).toBeVisible();
  await expect(d.getByText("github", { exact: true })).toBeVisible();
  await expect(d.getByText(/Third-party MCP servers/i)).toBeVisible();
  await expect(d.getByText(/Review their source and permissions before using them/)).toBeVisible();
  await advance(page);

  // Channels are honestly absent.
  await expect(d.getByRole("heading", { name: "Voice & channels (optional)" })).toBeVisible();
  await expect(d.getByText(/External channels are not configured/)).toBeVisible();
  await advance(page);

  // Tour narrates only: clicking a row opens a surface and sends guidance,
  // but never starts an agent turn, approval or file change.
  await expect(d.getByRole("heading", { name: "Take the tour" })).toBeVisible();
  const before = bridge.calls.length;
  await d.getByRole("button", { name: /Send a first prompt/ }).click();
  await expect(page.locator(".keel-notices")).toContainText("Cowork is open. Send a prompt from the composer");
  expect(bridge.calls.slice(before).filter((c) => c.method === "POST" && c.path.includes("/messages"))).toHaveLength(0);
  expect(bridge.calls.filter((c) => c.method === "POST" && c.path.includes("/approvals/"))).toHaveLength(0);

  await d.getByRole("button", { name: "Finish setup" }).click();
  await expect(page.locator(".keel-onboarding-layer")).toHaveCount(0);
  await expect.poll(() => page.evaluate(() => localStorage.getItem("keel-onboarding-done"))).toBe("true");
  const checklist = await readChecklist(page);
  expect(checklist).toMatchObject({
    surface: "done", provider: "done", workspace: "done",
    permission: "done", tour: "done",
  });
});

test("provider verification failure is reported honestly and never marked done", async ({
  page, bridge, consoleErrors, hydrationWarnings,
}) => {
  void consoleErrors; void hydrationWarnings;
  bridge.setOptions({ credential: "failure" });
  await openWizard(page);
  const d = wizard(page);

  await d.getByRole("button", { name: /Start with Cowork/ }).click();
  await advance(page);
  await d.getByRole("radio", { name: /anthropic/i }).click();
  await d.getByLabel("Provider API key").fill(TEST_KEY);
  await d.getByRole("button", { name: /Verify & use for this session/ }).click();

  await expect(d.getByRole("alert")).toContainText(
    "Verification failed: Key rejected by provider: invalid x-api-key",
  );
  await expect(d.getByRole("button", { name: "Save on this device" })).toHaveCount(0);
  const checklist = await readChecklist(page);
  expect(checklist.provider).not.toBe("done");

  // Local use is still possible; the user can add a key later in Settings.
  await advance(page);
  await expect(d.getByRole("heading", { name: "Choose a workspace" })).toBeVisible();
});
