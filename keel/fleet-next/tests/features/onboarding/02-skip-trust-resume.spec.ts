import {
  test, expect, openWizard, wizard, advance, readChecklist,
  TEST_PATH,
} from "./fixtures";

test("skipping records deferred items and the wizard resumes after reload", async ({
  page, bridge, consoleErrors, hydrationWarnings,
}) => {
  void consoleErrors; void hydrationWarnings;
  await openWizard(page);
  const d = wizard(page);

  await d.getByRole("button", { name: /Start with Cowork/ }).click();
  await advance(page); // local explanation has no checklist item
  await advance(page, "Skip for now"); // provider
  await advance(page, "Skip for now"); // workspace
  await advance(page, "Skip for now"); // permission
  await expect(d.getByRole("heading", { name: "Capabilities (optional)" })).toBeVisible();
  await advance(page, "Skip for now");
  await expect(d.getByRole("heading", { name: "Voice & channels (optional)" })).toBeVisible();
  await d.getByRole("button", { name: "Skip for now", exact: true }).click();
  await expect(d.getByRole("heading", { name: "Take the tour" })).toBeVisible();

  const deferred = await readChecklist(page);
  expect(deferred).toMatchObject({
    provider: "deferred", workspace: "deferred", permission: "deferred",
    capabilities: "deferred", channels: "deferred",
  });
  expect(await page.evaluate(() => localStorage.getItem("keel-onboarding:step"))).toBe('"tour"');

  // Reload mid-wizard: the step and every deferral survive without a mismatch.
  await page.reload();
  await expect(wizard(page).getByRole("heading", { name: "Take the tour" })).toBeVisible();
  expect(await readChecklist(page)).toMatchObject(deferred);

  // "Finish later" closes without claiming the tour was taken.
  await wizard(page).getByRole("button", { name: "Finish later" }).click();
  await expect(page.locator(".keel-onboarding-layer")).toHaveCount(0);
  const after = await readChecklist(page);
  expect(after.tour).toBe("pending");
  expect(await page.evaluate(() => localStorage.getItem("keel-onboarding-done"))).toBe("true");
});

test("workspace trust is explicit: untrusted stays untrusted until the user opts in", async ({
  page, bridge, consoleErrors, hydrationWarnings,
}) => {
  void consoleErrors; void hydrationWarnings;
  await openWizard(page);
  const d = wizard(page);

  await d.getByRole("button", { name: /Set up Fleet/ }).click();
  await advance(page);
  await advance(page, "Skip for now"); // provider
  await expect(d.getByRole("heading", { name: "Choose a workspace" })).toBeVisible();

  await d.getByLabel("Absolute folder path").fill(TEST_PATH);
  await d.getByRole("button", { name: "Add folder" }).click();
  await expect(d.getByText(/Keel does not trust anything automatically/)).toBeVisible();
  await d.getByRole("button", { name: "Keep it untrusted" }).click();
  await expect(d.getByText(/Kept untrusted\. The folder stays registered/)).toBeVisible();
  const firstTrust = bridge.callsMatching("POST", "projects/p1/trust");
  expect(firstTrust).toHaveLength(1);
  expect(firstTrust[0].body).toEqual({ trusted: false });
  expect((await readChecklist(page)).workspace).toBe("deferred");

  // Selecting the registered-but-untrusted project re-offers the decision.
  await d.locator("button").filter({ hasText: TEST_PATH }).first().click();
  await expect(d.getByText("Explicit trust decision")).toBeVisible();
  await d.getByRole("button", { name: "Trust this folder" }).click();
  await expect(d.getByText(/Trusted\. Keel can now work in this folder/)).toBeVisible();
  const secondTrust = bridge.callsMatching("POST", "projects/p1/trust");
  expect(secondTrust).toHaveLength(2);
  expect(secondTrust[1].body).toEqual({ trusted: true });
  expect((await readChecklist(page)).workspace).toBe("done");
});

test("a relative path is rejected before any bridge call", async ({
  page, bridge, consoleErrors, hydrationWarnings,
}) => {
  void consoleErrors; void hydrationWarnings;
  await openWizard(page);
  const d = wizard(page);
  await d.getByRole("button", { name: /Start with Code/ }).click();
  await advance(page);
  await advance(page, "Skip for now");
  await expect(d.getByRole("heading", { name: "Choose a workspace" })).toBeVisible();
  await d.getByLabel("Absolute folder path").fill("relative/only");
  await d.getByRole("button", { name: "Add folder" }).click();
  await expect(d.getByText(/Enter an absolute path/)).toBeVisible();
  expect(bridge.callsMatching("POST", "projects")).toHaveLength(0);
});
