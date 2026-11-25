import { expect, test } from "./fixtures";

async function trust(page: import("@playwright/test").Page) {
  await expect(page.getByRole("combobox", { name: "Active project" })).toHaveValue("p1");
  await expect(page.locator("section[aria-labelledby='trust-title'], [data-tree-row]").first()).toBeVisible();
  const gate = page.locator("section[aria-labelledby='trust-title']");
  if (await gate.count()) await gate.getByRole("button", { name: /Trust this folder/ }).click();
  await expect(gate).toHaveCount(0);
}

test("Git review renders only real {is_git,status,log,diff_stat} strings", async ({ harness }) => {
  const { goto, requests } = harness;
  await goto("code");
  await trust(harness.page);

  await expect(harness.page.getByRole("heading", { name: "Review" })).toBeVisible();
  await expect(harness.page.getByText("Read-only", { exact: true })).toBeVisible();
  await expect(harness.page.locator("pre").filter({ hasText: "9abc123 initial commit" })).toBeVisible();
  await expect(harness.page.locator("pre").filter({ hasText: "2 files changed" })).toBeVisible();

  // Porcelain XY codes include a leading space for worktree-only changes.
  const codes = await harness.page.locator('[class*="statusCode"]').allTextContents();
  expect(codes.map((c) => c.trim())).toEqual(["M", "??", "M"]);
  await expect(harness.page.locator('[class*="statusRow"]')).toHaveCount(3);

  await expect(
    harness.page.getByText(/File-level diffs are not reported by this bridge endpoint/),
  ).toBeVisible();
  await expect(harness.page.getByText(/Apply \/ revert actions are intentionally not offered/)).toBeVisible();
  expect(requests.filter((r) => r.path.endsWith("/api/bridge/projects/p1/review")).length).toBeGreaterThan(0);
});

test("Terminal polls output only while running and stop uses the real kill route", async ({ harness }) => {
  const { goto, requests, state } = harness;
  await goto("code");
  await trust(harness.page);
  await harness.page.getByRole("tablist", { name: "Context panels" }).getByRole("tab", { name: "Terminal" }).click();

  const polls = () => requests.filter((r) => r.method === "GET" && /\/shells\/sh-1\/output/.test(r.path));
  expect(polls()).toHaveLength(0);

  await harness.page.getByLabel("Shell command").fill("echo hello");
  await harness.page.getByRole("button", { name: /Run/ }).click();

  const exec = requests.filter((r) => r.method === "POST" && r.path.endsWith("/terminal/exec"));
  expect(exec).toHaveLength(1);
  expect(exec[0].body).toEqual({ command: "echo hello" });
  expect(state.shellHandle).toBe("sh-1");

  await expect(harness.page.getByRole("button", { name: "Stop" })).toBeVisible();
  await expect.poll(() => polls().length).toBeGreaterThanOrEqual(1);
  await expect(harness.page.locator("pre").filter({ hasText: "hello" })).toBeVisible();

  await harness.page.getByRole("button", { name: "Stop" }).click();
  const kills = requests.filter((r) => r.method === "POST" && r.path.endsWith("/api/bridge/shells/sh-1/kill"));
  expect(kills).toHaveLength(1);
  expect(kills[0].body).toEqual({});

  await expect(harness.page.getByRole("button", { name: "Stop" })).toHaveCount(0);
  await expect(harness.page.locator("pre").filter({ hasText: "hello world" })).toBeVisible();

  // Give any in-flight poll time to settle, then prove polling really stopped.
  await harness.page.waitForTimeout(300);
  const settled = polls().length;
  await harness.page.waitForTimeout(2600);
  expect(polls().length).toBe(settled);
});

test("Context and environment panels report bridge facts and name missing ones", async ({ harness }) => {
  const { goto } = harness;
  await goto("code");
  await trust(harness.page);

  const panels = harness.page.getByRole("tablist", { name: "Context panels" });
  await panels.getByRole("tab", { name: "Context" }).click();
  await expect(harness.page.getByText("fixture-provider")).toBeVisible();
  await expect(harness.page.getByText("128 in / 64 out")).toBeVisible();
  await expect(harness.page.getByText("not reported by this bridge endpoint")).toBeVisible();

  await panels.getByRole("tab", { name: "Environment" }).click();
  await expect(harness.page.getByText("/api/fleet/shells")).toBeVisible();
  await expect(harness.page.getByText(/No project preview URL endpoint/)).toBeVisible();
  await expect(harness.page.getByText(/No permission-mode or token-limit field/)).toBeVisible();
});
