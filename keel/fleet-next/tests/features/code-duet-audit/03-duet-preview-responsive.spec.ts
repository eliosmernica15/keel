import { expect, test } from "./fixtures";

// FIXTURE-BASED audit tests for Duet's two implemented-but-unverified panes:
// the bridge-supplied local preview and the narrow-width drawer behaviour.

async function trustDuet(page: import("@playwright/test").Page) {
  const gate = page.locator("section[aria-labelledby='duet-trust-title']");
  await expect(gate).toBeVisible();
  await gate.getByRole("button", { name: "Trust" }).click();
  await expect(gate).toHaveCount(0);
}

test("local preview iframe appears only for a bridge-supplied loopback URL", async ({ harness }) => {
  const { goto, page } = harness;
  harness.state.previewUrl = "http://127.0.0.1:4321/app";
  await goto("duet");
  await trustDuet(page);
  await page.getByRole("tablist", { name: "Duet workspace tabs" }).getByRole("tab", { name: /^Browser/ }).click();

  await expect(page.getByRole("heading", { name: "Local preview" })).toBeVisible();
  const iframe = page.locator("iframe");
  await expect(iframe).toHaveCount(1);
  await expect(iframe).toHaveAttribute("src", "http://127.0.0.1:4321/app");
  await expect(iframe).toHaveAttribute("title", "Local preview of the selected project");
  await expect(iframe).toHaveAttribute("sandbox", "allow-scripts allow-forms allow-modals");
  await expect(page.locator("code").filter({ hasText: "http://127.0.0.1:4321" })).toBeVisible();
  await expect(page.getByText(/port 4321/)).toBeVisible();
  await expect(page.getByText(/sandboxed iframe for a loopback URL/)).toBeVisible();

  // A non-loopback URL from the same field must NOT become a general browser.
  harness.state.previewUrl = "https://example.com/dashboard";
  await page.reload();
  await expect(page.getByRole("tabpanel", { name: "duet", exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Local preview is not exposed by this bridge" })).toBeVisible();
  await expect(page.locator("iframe")).toHaveCount(0);
  await expect(page.getByText(/Keel will not guess a port or open a general browser/)).toBeVisible();
});

test("narrow Duet shows one drawer at a time and toggles between them", async ({ harness }) => {
  const { goto, page } = harness;
  await page.setViewportSize({ width: 700, height: 900 });
  await goto("duet");

  await expect(page.locator('[data-narrow="true"]')).toBeVisible();
  const explorer = page.getByRole("complementary", { name: "Duet project explorer" });
  const context = page.getByRole("complementary", { name: "Duet context panel" });
  await expect(explorer).toBeVisible();
  await expect(context).toHaveCount(0);

  // KNOWN APP DEFECT (reported to lead): at narrow widths the explorer drawer
  // overlays the main trust gate, so its Trust button cannot be clicked until
  // the drawer is closed. Close it here to reach the gate and continue the
  // one-drawer-at-a-time assertions; this workaround is NOT an app fix.
  await page.getByRole("button", { name: "Toggle project explorer", exact: true }).click();
  await expect(explorer).toHaveCount(0);
  await trustDuet(page);
  await page.getByRole("button", { name: "Toggle project explorer", exact: true }).click();
  await expect(explorer).toBeVisible();

  await page.getByRole("button", { name: "Toggle context pane", exact: true }).click();
  await expect(context).toBeVisible();
  await expect(explorer).toHaveCount(0);

  await page.getByRole("button", { name: "Toggle project explorer", exact: true }).click();
  await expect(explorer).toBeVisible();
  await expect(context).toHaveCount(0);
});
