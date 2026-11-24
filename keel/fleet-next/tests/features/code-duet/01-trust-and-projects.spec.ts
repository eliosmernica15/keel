import { expect, test } from "./fixtures";

test("Code trust dialog is explicit: no auto-trust, no tree read before consent", async ({ harness }) => {
  const { goto, requests, state } = harness;
  await goto("code");

  const gate = harness.page.locator("section[aria-labelledby='trust-title']");
  await expect(gate).toBeVisible();
  await expect(gate.locator("strong")).toHaveText("C:\\work\\alpha");
  await expect(gate.getByText(/List files, view text files/)).toBeVisible();
  await expect(gate.getByText(/Save edits to files inside this folder/)).toBeVisible();
  await expect(gate.getByRole("button", { name: /Trust this folder/ })).toBeVisible();

  expect(requests.filter((r) => r.method === "POST" && r.path.includes("/trust"))).toEqual([]);
  expect(requests.filter((r) => r.path.includes("/tree"))).toEqual([]);

  await gate.getByRole("button", { name: /Trust this folder/ }).click();
  await expect(gate).toHaveCount(0);

  const trustPosts = requests.filter((r) => r.method === "POST" && r.path.endsWith("/api/bridge/projects/p1/trust"));
  expect(trustPosts).toHaveLength(1);
  expect(trustPosts[0].body).toEqual({ trusted: true });
  expect(state.trusted.p1).toBe(true);
  await expect.poll(() => requests.filter((r) => r.path.includes("/projects/p1/tree")).length).toBeGreaterThan(0);
});

test("Rejecting trust sends trusted:false and still reads nothing", async ({ harness }) => {
  const { goto, requests, state } = harness;
  await goto("code");
  const gate = harness.page.locator("section[aria-labelledby='trust-title']");
  await gate.getByRole("button", { name: "Reject" }).click();

  const posts = requests.filter((r) => r.method === "POST" && r.path.endsWith("/api/bridge/projects/p1/trust"));
  expect(posts).toHaveLength(1);
  expect(posts[0].body).toEqual({ trusted: false });
  expect(state.trusted.p1).toBe(false);
  expect(requests.filter((r) => r.path.includes("/tree"))).toEqual([]);
  await expect(harness.page.getByText(/You rejected trust\. No files were read/)).toBeVisible();
});

test("Project selection switches workspaces and trust is scoped per project", async ({ harness }) => {
  const { goto, requests } = harness;
  await goto("code");
  const select = harness.page.getByRole("combobox", { name: "Active project" });
  await expect(select).toHaveValue("p1");

  await harness.page.locator("section[aria-labelledby='trust-title']").getByRole("button", { name: /Trust this folder/ }).click();
  await harness.page.locator('[data-tree-row="src/app.ts"]').click();
  await expect(harness.page.getByRole("tab", { name: /app\.ts/ })).toBeVisible();

  await select.selectOption("p2");
  await expect(select).toHaveValue("p2");
  await expect(harness.page.getByRole("tab", { name: /app\.ts/ })).toHaveCount(0);
  await expect(harness.page.locator("section[aria-labelledby='trust-title'] strong")).toHaveText("C:\\work\\beta");
  expect(requests.filter((r) => r.path.includes("/projects/p2/tree"))).toEqual([]);

  await harness.page.locator("section[aria-labelledby='trust-title']").getByRole("button", { name: /Trust this folder/ }).click();
  await expect.poll(() => requests.filter((r) => r.path.includes("/projects/p2/tree")).length).toBeGreaterThan(0);
});

test("Adding a project posts only the path and never trusts it automatically", async ({ harness }) => {
  const { goto, requests, state } = harness;
  await goto("code");
  await harness.page.getByRole("button", { name: "Add a local project" }).click();
  const dialog = harness.page.getByRole("dialog", { name: "Add a local project" });
  await dialog.getByLabel("Absolute folder path").fill("C:\\work\\gamma");
  await dialog.getByRole("button", { name: "Add folder" }).click();

  const adds = requests.filter((r) => r.method === "POST" && r.path === "/api/bridge/projects");
  expect(adds).toHaveLength(1);
  expect(adds[0].body).toEqual({ path: "C:\\work\\gamma" });
  expect(Object.values(state.trusted).some(Boolean)).toBe(false);
  await expect(harness.page.getByRole("heading", { name: "Trust this local folder?" })).toBeVisible();
});
