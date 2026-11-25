import { expect, test } from "./fixtures";

// FIXTURE-BASED audit tests for Code actions whose requests were not covered
// by the owner suite: project chat and project removal. Both must use the real
// bridge routes and must never touch files on disk.

test("Open project chat uses the real chat route and reports the returned bot", async ({ harness }) => {
  const { goto, requests } = harness;
  await goto("code");
  const gate = harness.page.locator("section[aria-labelledby='trust-title']");
  await expect(gate).toBeVisible();
  await gate.getByRole("button", { name: /Trust this folder/ }).click();
  await expect(gate).toHaveCount(0);

  await harness.page.getByRole("button", { name: "Open project chat" }).click();

  const posts = requests.filter((r) => r.method === "POST" && r.path === "/api/bridge/projects/p1/chat");
  expect(posts).toHaveLength(1);
  expect(posts[0].body).toEqual({});
  await expect(harness.page.getByRole("status").filter({ hasText: "Alpha chat" })).toBeVisible();
});

test("Removing a project posts the real remove route and leaves disk files untouched", async ({ harness }) => {
  const { goto, requests, state } = harness;
  const original = { ...state.files };
  await goto("code");
  const gate = harness.page.locator("section[aria-labelledby='trust-title']");
  await expect(gate).toBeVisible();
  await gate.getByRole("button", { name: /Trust this folder/ }).click();
  await expect(gate).toHaveCount(0);

  harness.page.once("dialog", (d) => void d.accept());
  await harness.page.getByRole("button", { name: "Remove project from Keel" }).click();

  const posts = requests.filter((r) => r.method === "POST" && r.path === "/api/bridge/projects/p1/remove");
  expect(posts).toHaveLength(1);
  await expect(harness.page.getByRole("combobox", { name: "Active project" })).toHaveValue("p2");
  expect(state.files).toEqual(original);
  expect(requests.filter((r) => r.method === "POST" && r.path.endsWith("/file/write"))).toEqual([]);
});
