import type { Page } from "@playwright/test";
import { expect, test } from "./fixtures";

// FIXTURE-BASED audit tests. File/read envelopes (binary / truncated) are
// injected with context.route; no app code is changed.

async function trustAndOpen(page: Page, path: string) {
  await expect(page.getByRole("combobox", { name: "Active project" })).toHaveValue("p1");
  const gate = page.locator("section[aria-labelledby='trust-title']");
  await expect(gate).toBeVisible();
  await gate.getByRole("button", { name: /Trust this folder/ }).click();
  await expect(gate).toHaveCount(0);
  await page.locator(`[data-tree-row="${path}"]`).click();
  await expect(page.getByRole("tab", { name: new RegExp(path.split("/").pop()!.replace(".", "\\.")) })).toBeVisible();
}

test("binary file read yields an honest no-preview state with no edit affordance", async ({ harness }) => {
  const { goto, requests } = harness;
  harness.state.fileMeta["p1:src/app.ts"] = { binary: true, encoding: "base64" };
  await goto("code");
  await trustAndOpen(harness.page, "src/app.ts");

  await expect(harness.page.getByRole("heading", { name: "Binary file — no inline preview" })).toBeVisible();
  await expect(harness.page.getByText(/does not expose a project-file download endpoint/)).toBeVisible();
  await expect(harness.page.getByRole("button", { name: "Edit" })).toHaveCount(0);
  await expect(harness.page.locator("textarea")).toHaveCount(0);
  await expect(harness.page.locator('pre[aria-label^="Read-only"]')).toHaveCount(0);
  expect(requests.filter((r) => r.method === "POST" && r.path.endsWith("/file/write"))).toEqual([]);
});

test("truncated file read disables editing so the bridge prefix cannot be written back", async ({ harness }) => {
  const { goto, requests } = harness;
  harness.state.fileMeta["p1:src/app.ts"] = {
    content: 'const greeting = "hello";\n',
    truncated: true,
  };
  await goto("code");
  await trustAndOpen(harness.page, "src/app.ts");

  await expect(harness.page.getByText("Truncated by bridge read limit")).toBeVisible();
  await expect(harness.page.getByText(/editing and writing are disabled/)).toBeVisible();
  await expect(harness.page.getByRole("button", { name: "Edit" })).toBeDisabled();
  await expect(harness.page.locator("textarea")).toHaveCount(0);
  expect(requests.filter((r) => r.method === "POST" && r.path.endsWith("/file/write"))).toEqual([]);
});

// Regression for the Agent E defect: reloading a dirty buffer must confirm
// before discarding unsaved edits (same rule as closeTab).
test("reload asks before discarding an unsaved edit", async ({ harness }) => {
  const { goto } = harness;
  await goto("code");
  await trustAndOpen(harness.page, "src/app.ts");

  await harness.page.getByRole("button", { name: "Edit" }).click();
  const editor = harness.page.getByRole("textbox", { name: "Editing src/app.ts" });
  await editor.fill(`${await editor.inputValue()}// unsaved work\n`);
  await expect(harness.page.getByText("Unsaved", { exact: true })).toBeVisible();

  // Register the handler BEFORE clicking: a native confirm blocks the click
  // action until it is dismissed.
  let dialogMessage = "";
  harness.page.once("dialog", async (dialog) => {
    dialogMessage = dialog.message();
    await dialog.dismiss();
  });
  await harness.page.getByRole("button", { name: "Reload file from disk" }).click();
  await expect.poll(() => dialogMessage).toContain("unsaved edits");
  await expect(harness.page.getByRole("textbox", { name: "Editing src/app.ts" })).toContainText("// unsaved work");
});
