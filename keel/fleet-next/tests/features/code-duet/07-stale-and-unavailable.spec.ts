import type { Page } from "@playwright/test";
import { expect, test } from "./fixtures";

// Regression coverage for stale bridge responses and honest 502/504 states.
// Every delay/failure is injected with context.route in our own fixture; no
// application code is mocked inside the bundle and no data is fabricated.

const NEW_TREE = { entries: [{ path: "new-only.ts", type: "file", size: 12 }] };
const NEW_REVIEW = {
  is_git: true,
  status: "?? new.ts\n",
  log: "aaaa111 newest commit\n",
  diff_stat: "1 file changed, 1 insertion(+)\n",
};

async function trustAndOpen(page: Page, path: string) {
  await expect(page.getByRole("combobox", { name: "Active project" })).toHaveValue("p1");
  await expect(page.locator("section[aria-labelledby='trust-title'], [data-tree-row]").first()).toBeVisible();
  const gate = page.locator("section[aria-labelledby='trust-title']");
  if (await gate.count()) {
    await gate.getByRole("button", { name: /Trust this folder/ }).click();
    await expect(gate).toHaveCount(0);
  }
  await page.locator(`[data-tree-row="${path}"]`).click();
  await expect(page.getByRole("tab", { name: new RegExp(path.split("/").pop()!.replace(".", "\\.")) })).toBeVisible();
}

test("A delayed projects response cannot overwrite a newer trusted state", async ({ harness }) => {
  const { goto, requests, state } = harness;
  // Initial StrictMode reads are slow; the refresh triggered by the trust
  // POST is fast. The stale untrusted payloads must be discarded.
  state.routeHook = ({ path, method, call }) =>
    method === "GET" && path === "projects" && call <= 2 ? { delayMs: 1800 } : undefined;

  await goto("code");
  const gate = harness.page.locator("section[aria-labelledby='trust-title']");
  await expect(gate).toBeVisible();
  await gate.getByRole("button", { name: /Trust this folder/ }).click();
  await expect(gate).toHaveCount(0);

  await harness.page.waitForTimeout(2100); // let both stale responses land
  await expect(gate).toHaveCount(0);
  await expect(harness.page.getByText("Trusted workspace")).toBeVisible();
  expect(requests.filter((r) => r.method === "POST" && r.path.endsWith("/trust"))).toHaveLength(1);
});

test("A delayed tree response cannot overwrite a newer file list", async ({ harness }) => {
  const { goto, state } = harness;
  let superseding = false;
  state.routeHook = ({ path, method }) => {
    if (method === "GET" && path === "projects/p1/tree") {
      return superseding ? { body: NEW_TREE } : { delayMs: 1800 };
    }
    return undefined;
  };

  await goto("code");
  // Trust waits for the gate, not the tree, so the first tree read is still
  // in flight here.
  await expect(harness.page.getByRole("combobox", { name: "Active project" })).toHaveValue("p1");
  await expect(harness.page.locator("section[aria-labelledby='trust-title']")).toBeVisible();
  await harness.page.locator("section[aria-labelledby='trust-title']")
    .getByRole("button", { name: /Trust this folder/ }).click();
  await expect(harness.page.locator("section[aria-labelledby='trust-title']")).toHaveCount(0);

  superseding = true;
  await harness.page.getByRole("button", { name: "Refresh file tree" }).click();
  await expect(harness.page.locator('[data-tree-row="new-only.ts"]')).toBeVisible();
  await expect(harness.page.locator('[data-tree-row="src/app.ts"]')).toHaveCount(0);

  await harness.page.waitForTimeout(2100);
  await expect(harness.page.locator('[data-tree-row="new-only.ts"]')).toBeVisible();
  await expect(harness.page.locator('[data-tree-row="src/app.ts"]')).toHaveCount(0);
});

test("A delayed review response cannot overwrite a newer Git review", async ({ harness }) => {
  const { goto, state } = harness;
  let superseding = false;
  state.routeHook = ({ path, method }) => {
    if (method === "GET" && path === "projects/p1/review") {
      return superseding ? { body: NEW_REVIEW } : { delayMs: 1800 };
    }
    return undefined;
  };

  await goto("code");
  await expect(harness.page.getByRole("combobox", { name: "Active project" })).toHaveValue("p1");
  await expect(harness.page.locator("section[aria-labelledby='trust-title']")).toBeVisible();
  await harness.page.locator("section[aria-labelledby='trust-title']")
    .getByRole("button", { name: /Trust this folder/ }).click();
  await expect(harness.page.locator("section[aria-labelledby='trust-title']")).toHaveCount(0);

  // The header (and its Refresh control) stays mounted while a read is
  // pending, so the newer request can supersede the older one.
  const refresh = harness.page.getByRole("button", { name: "Refresh review" });
  await expect(refresh).toBeVisible();
  superseding = true;
  await refresh.click();
  await expect(harness.page.getByText("aaaa111 newest commit")).toBeVisible();
  await harness.page.waitForTimeout(2100);
  await expect(harness.page.getByText("aaaa111 newest commit")).toBeVisible();
  await expect(harness.page.getByText("9abc123 initial commit")).toHaveCount(0);
});

test("A 502 tree response shows an honest unavailable state with no fake files", async ({ harness }) => {
  const { goto, requests, state } = harness;
  let failing = true;
  state.routeHook = ({ path, method }) =>
    method === "GET" && path === "projects/p1/tree" && failing
      ? { fail: { status: 502, body: { error: "bridge_unavailable" } } }
      : undefined;

  await goto("code");
  await expect(harness.page.getByRole("combobox", { name: "Active project" })).toHaveValue("p1");
  await expect(harness.page.locator("section[aria-labelledby='trust-title']")).toBeVisible();
  await harness.page.locator("section[aria-labelledby='trust-title']")
    .getByRole("button", { name: /Trust this folder/ }).click();
  await expect(harness.page.locator("section[aria-labelledby='trust-title']")).toHaveCount(0);

  const banner = harness.page.getByRole("alert").filter({ hasText: "bridge_unavailable" });
  await expect(banner).toBeVisible();
  await expect(banner.getByRole("button", { name: "Retry" })).toBeVisible();
  await expect(harness.page.locator("[data-tree-row]")).toHaveCount(0);
  await expect(harness.page.getByText("No files were found in this project.")).toBeVisible();

  const before = requests.filter((r) => r.method === "GET" && r.path.includes("/projects/p1/tree")).length;
  failing = false;
  await banner.getByRole("button", { name: "Retry" }).click();
  await expect(harness.page.locator('[data-tree-row="src/app.ts"]')).toBeVisible();
  await expect(banner).toHaveCount(0);
  expect(requests.filter((r) => r.method === "GET" && r.path.includes("/projects/p1/tree")).length).toBeGreaterThan(before);
});

test("A 504 review response shows honest unavailable state and no git data", async ({ harness }) => {
  const { goto, requests, state } = harness;
  let failing = true;
  state.routeHook = ({ path, method }) =>
    method === "GET" && path === "projects/p1/review" && failing
      ? { fail: { status: 504, raw: "" } } // BFF-style bodyless timeout
      : undefined;

  await goto("code");
  await expect(harness.page.getByRole("combobox", { name: "Active project" })).toHaveValue("p1");
  await expect(harness.page.locator("section[aria-labelledby='trust-title']")).toBeVisible();
  await harness.page.locator("section[aria-labelledby='trust-title']")
    .getByRole("button", { name: /Trust this folder/ }).click();
  await expect(harness.page.locator("section[aria-labelledby='trust-title']")).toHaveCount(0);

  await expect(harness.page.getByRole("heading", { name: "Bridge unavailable" })).toBeVisible();
  await expect(harness.page.getByText("http 504")).toBeVisible();
  await expect(harness.page.getByText("Read-only", { exact: true })).toHaveCount(1);
  await expect(harness.page.getByText("9abc123 initial commit")).toHaveCount(0);
  await expect(harness.page.locator("[class*='statusRow']")).toHaveCount(0);

  const before = requests.filter((r) => r.path.endsWith("/api/bridge/projects/p1/review")).length;
  failing = false;
  await harness.page.getByRole("button", { name: "Retry" }).click();
  await expect(harness.page.getByText("9abc123 initial commit")).toBeVisible();
  expect(requests.filter((r) => r.path.endsWith("/api/bridge/projects/p1/review")).length).toBeGreaterThan(before);
});

test("A read retry never repeats a trust POST; trust fires exactly once", async ({ harness }) => {
  const { goto, requests, state } = harness;
  let projectsFailing = true;
  state.routeHook = ({ path, method }) =>
    method === "GET" && path === "projects" && projectsFailing
      ? { fail: { status: 502, body: { error: "bridge_unavailable" } } }
      : undefined;
  const trustPosts = () => requests.filter((r) => r.method === "POST" && r.path.endsWith("/trust"));

  await goto("code");
  const banner = harness.page.getByRole("alert").filter({ hasText: "bridge_unavailable" });
  await expect(banner).toBeVisible();
  expect(trustPosts()).toEqual([]);

  projectsFailing = false;
  await banner.getByRole("button", { name: "Retry" }).click();
  await expect(banner).toHaveCount(0);
  const gate = harness.page.locator("section[aria-labelledby='trust-title']");
  await expect(gate).toBeVisible();
  await gate.getByRole("button", { name: /Trust this folder/ }).click();
  await expect(gate).toHaveCount(0);
  await expect.poll(() => trustPosts().length).toBe(1);

  // A second read failure and its Retry must not re-issue the trust POST.
  projectsFailing = true;
  await harness.page.getByRole("button", { name: "Refresh project state" }).click();
  await expect(banner).toBeVisible();
  projectsFailing = false;
  await banner.getByRole("button", { name: "Retry" }).click();
  await expect(banner).toHaveCount(0);
  expect(trustPosts()).toHaveLength(1);
});

test("A failed write is honest and its retry does not repeat the write POST", async ({ harness }) => {
  const { goto, requests, state } = harness;
  await goto("code");
  await trustAndOpen(harness.page, "src/app.ts");

  await harness.page.getByRole("button", { name: "Edit" }).click();
  const editor = harness.page.getByRole("textbox", { name: "Editing src/app.ts" });
  await editor.fill(`${await editor.inputValue()}// saved after one retry\n`);
  await harness.page.getByRole("button", { name: /^Save/ }).click();
  await expect(harness.page.getByRole("dialog", { name: "Confirm file save" })).toBeVisible();

  let writesFailing = true;
  state.routeHook = ({ path, method }) =>
    method === "POST" && path === "projects/p1/file/write" && writesFailing
      ? { fail: { status: 504, body: { error: "bridge_unreachable" } } }
      : undefined;
  await harness.page.getByRole("dialog", { name: "Confirm file save" })
    .getByRole("button", { name: "Write to disk" }).click();

  await expect(harness.page.getByRole("heading", { name: "Could not save this file" })).toBeVisible();
  await expect(harness.page.getByText(/no write was retried automatically/)).toBeVisible();
  await expect(harness.page.getByText("bridge_unreachable")).toBeVisible();
  const writes = () => requests.filter((r) => r.method === "POST" && r.path.endsWith("/file/write"));
  await expect.poll(() => writes().length).toBe(1);

  // This button only returns to the editor; it is not a silent re-POST.
  await harness.page.getByRole("button", { name: "Return to editor" }).click();
  expect(writes()).toHaveLength(1);
  await expect(harness.page.getByRole("textbox", { name: "Editing src/app.ts" })).toContainText("saved after one retry");

  // An explicit, confirmed second save is the only way to issue a second POST.
  writesFailing = false;
  await harness.page.getByRole("button", { name: /^Save/ }).click();
  await harness.page.getByRole("dialog", { name: "Confirm file save" })
    .getByRole("button", { name: "Write to disk" }).click();
  await expect.poll(() => writes().length).toBe(2);
  expect(state.files["p1:src/app.ts"]).toContain("saved after one retry");
});
