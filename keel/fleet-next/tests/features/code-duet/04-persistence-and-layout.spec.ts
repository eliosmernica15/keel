import { expect, test } from "./fixtures";

async function trustCode(page: import("@playwright/test").Page) {
  const gate = page.locator("section[aria-labelledby='trust-title']");
  if (await gate.count()) await gate.getByRole("button", { name: /Trust this folder/ }).click();
  await expect(gate).toHaveCount(0);
}

test("Code tabs, right tab and resized pane survive a reload", async ({ harness }) => {
  const { goto } = harness;
  await goto("code");
  await trustCode(harness.page);
  await harness.page.locator('[data-tree-row="src/app.ts"]').click();

  const explorer = harness.page.getByRole("separator", { name: "Resize project explorer" });
  await explorer.focus();
  await harness.page.keyboard.press("ArrowRight");
  await expect(explorer).toHaveAttribute("aria-valuenow", "272");
  await expect(harness.page.getByRole("complementary", { name: "Project explorer" })).toHaveCSS("width", "272px");

  // Pointer drag must move the same handle, not just the keyboard path.
  const box = await explorer.boundingBox();
  if (box) {
    await harness.page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
    await harness.page.mouse.down();
    await harness.page.mouse.move(box.x + box.width / 2 + 24, box.y + box.height / 2, { steps: 4 });
    await harness.page.mouse.up();
    await expect(explorer).toHaveAttribute("aria-valuenow", "296");
  }

  await harness.page.getByRole("tablist", { name: "Context panels" }).getByRole("tab", { name: "Terminal" }).click();
  await harness.page.reload();

  await expect(harness.page.getByRole("tab", { name: /app\.ts/ })).toBeVisible();
  await expect(harness.page.getByRole("tablist", { name: "Context panels" }).getByRole("tab", { name: "Terminal" })).toHaveAttribute("aria-selected", "true");
  const after = harness.page.getByRole("separator", { name: "Resize project explorer" });
  await expect(after).toHaveAttribute("aria-valuenow", box ? "296" : "272");
});

test("Duet supports drag reorder, close, restore and reset", async ({ harness }) => {
  const { goto } = harness;
  await goto("duet");
  await harness.page.locator("section[aria-labelledby='duet-trust-title']").getByRole("button", { name: "Trust" }).click();

  const strip = harness.page.getByRole("tablist", { name: "Duet workspace tabs" });
  expect((await strip.getByRole("tab").allTextContents()).map((t) => t.trim())).toEqual([
    "Review", "Terminal", "Open file", "Browser",
  ]);

  await strip.getByRole("tab", { name: /^Terminal/ }).dragTo(strip.getByRole("tab", { name: /^Review/ }));
  expect((await strip.getByRole("tab").allTextContents())[0].trim()).toBe("Terminal");

  await strip.getByRole("tab", { name: /^Browser/ }).getByRole("button", { name: "Close Browser" }).click();
  await expect(strip.getByRole("tab", { name: /^Browser/ })).toHaveCount(0);

  await harness.page.getByRole("button", { name: "Restore a recently closed tab" }).click();
  await harness.page.getByRole("menuitem", { name: /Browser/ }).click();
  await expect(strip.getByRole("tab", { name: /^Browser/ })).toBeVisible();

  await harness.page.getByRole("button", { name: "Reset Duet layout" }).click();
  expect((await strip.getByRole("tab").allTextContents()).map((t) => t.trim())).toEqual([
    "Review", "Terminal", "Open file", "Browser",
  ]);
});

test("Duet tabs and pane width persist across reload and stay scoped to a project", async ({ harness }) => {
  const { goto } = harness;
  await goto("duet");
  await harness.page.locator("section[aria-labelledby='duet-trust-title']").getByRole("button", { name: "Trust" }).click();
  await harness.page.locator('[data-tree-row="src/app.ts"]').click();

  const handle = harness.page.getByRole("separator", { name: "Resize Duet file explorer" });
  await handle.focus();
  await harness.page.keyboard.press("ArrowRight");
  await expect(handle).toHaveAttribute("aria-valuenow", "272");

  const strip = harness.page.getByRole("tablist", { name: "Duet workspace tabs" });
  await strip.getByRole("tab", { name: /^Terminal/ }).getByRole("button", { name: "Close Terminal" }).click();
  await harness.page.reload();

  await expect(harness.page.getByRole("tab", { name: /app\.ts/ })).toBeVisible();
  await expect(strip.getByRole("tab", { name: /^Terminal/ })).toHaveCount(0);
  await expect(harness.page.getByRole("separator", { name: "Resize Duet file explorer" })).toHaveAttribute("aria-valuenow", "272");

  // Switching projects must never leak the other project's file tabs.
  await harness.page.getByRole("combobox", { name: "Active project" }).selectOption("p2");
  await expect(strip.getByRole("tab", { name: /app\.ts/ })).toHaveCount(0);
  await expect(harness.page.getByRole("combobox", { name: "Active project" })).toHaveValue("p2");

  // Pane geometry is project-scoped too: changing p2 must not change p1.
  const p2Handle = harness.page.getByRole("separator", { name: "Resize Duet file explorer" });
  await p2Handle.focus();
  await harness.page.keyboard.press("End");
  await expect(p2Handle).toHaveAttribute("aria-valuenow", "440");

  await harness.page.getByRole("combobox", { name: "Active project" }).selectOption("p1");
  await expect(strip.getByRole("tab", { name: /app\.ts/ })).toBeVisible();
  await expect(harness.page.getByRole("separator", { name: "Resize Duet file explorer" })).toHaveAttribute("aria-valuenow", "272");
  await harness.page.getByRole("combobox", { name: "Active project" }).selectOption("p2");
  await expect(harness.page.getByRole("separator", { name: "Resize Duet file explorer" })).toHaveAttribute("aria-valuenow", "440");
});

test("Duet file tabs keep unsaved edits and show a change indicator", async ({ harness }) => {
  const { goto, requests } = harness;
  await goto("duet");
  await harness.page.locator("section[aria-labelledby='duet-trust-title']").getByRole("button", { name: "Trust" }).click();
  await harness.page.locator('[data-tree-row="src/app.ts"]').click();

  const strip = harness.page.getByRole("tablist", { name: "Duet workspace tabs" });
  await harness.page.getByRole("button", { name: "Edit" }).click();
  const editor = harness.page.getByRole("textbox", { name: "Editing src/app.ts" });
  await editor.fill(`${await editor.inputValue()}// duet unsaved\n`);
  await expect(strip.getByRole("tab", { name: /app\.ts/ }).getByLabel("Unsaved changes")).toBeVisible();

  await harness.page.locator('[data-tree-row="notes.md"]').click();
  await strip.getByRole("tab", { name: /app\.ts/ }).click();
  await expect(harness.page.getByRole("textbox", { name: "Editing src/app.ts" })).toContainText("// duet unsaved");
  expect(requests.filter((r) => r.method === "POST" && r.path.endsWith("/file/write"))).toEqual([]);
});
