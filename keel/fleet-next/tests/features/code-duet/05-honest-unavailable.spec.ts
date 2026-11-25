import { expect, test } from "./fixtures";

test("Duet browser tab is an honest unavailable state, not a fake preview", async ({ harness }) => {
  const { goto, requests } = harness;
  await goto("duet");
  await harness.page.locator("section[aria-labelledby='duet-trust-title']").getByRole("button", { name: "Trust" }).click();
  await harness.page.getByRole("tablist", { name: "Duet workspace tabs" }).getByRole("tab", { name: /^Browser/ }).click();

  await expect(harness.page.getByRole("heading", { name: "Local preview is not exposed by this bridge" })).toBeVisible();
  await expect(harness.page.getByText(/Keel will not guess a port or open a general browser/)).toBeVisible();
  await expect(harness.page.locator("iframe")).toHaveCount(0);
  expect(requests.filter((r) => /preview|diff|apply/.test(r.path))).toEqual([]);
});

test("Review offers no apply, revert or file-diff controls", async ({ harness }) => {
  const { goto } = harness;
  await goto("duet");
  await harness.page.locator("section[aria-labelledby='duet-trust-title']").getByRole("button", { name: "Trust" }).click();
  await harness.page.getByRole("tablist", { name: "Duet workspace tabs" }).getByRole("tab", { name: /^Review/ }).click();

  await expect(harness.page.getByText("Read-only", { exact: true })).toBeVisible();
  await expect(harness.page.getByRole("button", { name: /apply|revert/i })).toHaveCount(0);
  await expect(harness.page.getByText(/Apply \/ revert actions are intentionally not offered/)).toBeVisible();
});
