import { expect, test } from "./fixtures";

async function trustAndOpen(page: import("@playwright/test").Page, path: string) {
  // Wait for hydration before deciding whether a trust gate exists. Under
  // parallel load the tabpanel can be visible before the project list lands;
  // checking too early used to skip trust and then time out on the tree.
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

test("File tree filter and read-only syntax-highlighted viewer use real read payloads", async ({ harness }) => {
  const { goto, requests } = harness;
  await goto("code");
  const gate = harness.page.locator("section[aria-labelledby='trust-title']");
  await gate.getByRole("button", { name: /Trust this folder/ }).click();

  await harness.page.getByLabel("Filter files").fill("notes");
  await expect(harness.page.getByText("notes.md", { exact: true }).first()).toBeVisible();
  await expect(harness.page.locator('[data-tree-row="src/app.ts"]')).toHaveCount(0);
  await harness.page.getByLabel("Filter files").fill("");

  await harness.page.locator('[data-tree-row="src/app.ts"]').click();
  const reads = requests.filter((r) => r.method === "GET" && r.path.includes("/file/read"));
  // React StrictMode legitimately re-runs mount effects in next dev, so the
  // same read can be issued twice; what matters is that it is a real GET.
  await expect.poll(() => reads.length).toBeGreaterThan(0);
  const readUrl = new URL(`http://local${reads[0].path}`);
  expect(readUrl.searchParams.get("path")).toBe("src/app.ts");

  await expect(harness.page.locator('pre[aria-label^="Read-only"]')).toBeVisible();
  await expect(harness.page.locator('[class*="tok_keyword"]').first()).toBeVisible();
  await expect(harness.page.locator('[class*="tok_comment"]').first()).toBeVisible();
  await expect(harness.page.locator("textarea")).toHaveCount(0);
  await expect(harness.page.getByText("Read-only by default")).toBeVisible();
});

test("Guarded write requires explicit confirmation and reports save state", async ({ harness }) => {
  const { goto, requests } = harness;
  await goto("code");
  await trustAndOpen(harness.page, "src/app.ts");

  await harness.page.getByRole("button", { name: "Edit" }).click();
  const editor = harness.page.getByRole("textbox", { name: "Editing src/app.ts" });
  const original = await editor.inputValue();
  const edited = `${original}const added = true;\n`;
  await editor.fill(edited);

  await expect(harness.page.getByText("Unsaved", { exact: true })).toBeVisible();
  await expect(
    harness.page.getByRole("tab", { name: /app\.ts/ }).getByLabel("Unsaved changes"),
  ).toBeVisible();

  const writes = () => requests.filter((r) => r.method === "POST" && r.path.endsWith("/file/write"));
  await harness.page.getByRole("button", { name: /^Save/ }).click();
  const dialog = harness.page.getByRole("dialog", { name: "Confirm file save" });
  await expect(dialog).toBeVisible();
  await expect(dialog.getByText(/Write the edited buffer/)).toBeVisible();
  await dialog.getByRole("button", { name: "Cancel" }).click();
  expect(writes()).toEqual([]);

  await harness.page.getByRole("button", { name: /^Save/ }).click();
  await dialog.getByRole("button", { name: "Write to disk" }).click();
  await expect.poll(() => writes().length).toBe(1);
  expect(writes()[0].body).toEqual({ path: "src/app.ts", content: edited });
  await expect(dialog).toHaveCount(0);
  await expect(harness.page.getByText("Unsaved", { exact: true })).toHaveCount(0);
  await expect(harness.page.locator('pre[aria-label^="Read-only"]')).toContainText("const added = true;");
});

test("An unsaved buffer and its change indicator survive switching file tabs", async ({ harness }) => {
  const { goto, requests } = harness;
  await goto("code");
  await trustAndOpen(harness.page, "src/app.ts");

  await harness.page.getByRole("button", { name: "Edit" }).click();
  const editor = harness.page.getByRole("textbox", { name: "Editing src/app.ts" });
  await editor.fill(`${await editor.inputValue()}// still unsaved\n`);

  await harness.page.locator('[data-tree-row="notes.md"]').click();
  await expect(harness.page.getByRole("tab", { name: /notes\.md/ })).toBeVisible();
  await harness.page.getByRole("tab", { name: /app\.ts/ }).click();

  await expect(harness.page.getByRole("textbox", { name: "Editing src/app.ts" })).toContainText("// still unsaved");
  await expect(
    harness.page.getByRole("tab", { name: /app\.ts/ }).getByLabel("Unsaved changes"),
  ).toBeVisible();
  expect(requests.filter((r) => r.method === "POST" && r.path.endsWith("/file/write"))).toEqual([]);

  // Closing a dirty file asks before discarding; cancelling keeps the buffer.
  harness.page.once("dialog", (d) => void d.dismiss());
  await harness.page.getByRole("button", { name: "Close src/app.ts" }).click();
  await expect(harness.page.getByRole("tab", { name: /app\.ts/ })).toBeVisible();
});
