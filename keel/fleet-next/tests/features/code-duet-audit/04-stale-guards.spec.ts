import { expect, test } from "./fixtures";

// FIXTURE-BASED audit test for the review-pair stale-response guard. Next dev
// runs with reactStrictMode: true (next.config.mjs:6), so opening the pair tab
// issues two bots reads; the slower older one must never win.

const OLD_REVIEWER = {
  id: "old-reviewer", name: "Alpha Reviewer", role: "Independent reviewer", model: "old-critic",
};
const NEW_REVIEWER = {
  id: "new-reviewer", name: "Beta Reviewer", role: "Independent reviewer", model: "new-critic",
};

test("a delayed older bots response cannot overwrite newer reviewer identity", async ({ harness }) => {
  const { goto, page, state } = harness;
  state.routeHook = ({ path, method, call }) => {
    if (method === "GET" && path === "bots") {
      // StrictMode issues two reads on mount: make the first slow + stale.
      return call === 1
        ? { delayMs: 1600, body: { bots: [OLD_REVIEWER] } }
        : { body: { bots: [NEW_REVIEWER] } };
    }
    return undefined;
  };

  await goto("duet");
  await page.getByRole("button", { name: "Open review pair (builder and reviewer)" }).click();

  const reviewer = page.locator('[data-pair-role="reviewer"]');
  await expect(reviewer).toContainText("Beta Reviewer");
  await expect(reviewer).toContainText("new-critic");
  await expect(reviewer.getByText("Alpha Reviewer")).toHaveCount(0);

  // Let the delayed stale response land; it must be discarded.
  await page.waitForTimeout(2000);
  await expect(reviewer).toContainText("Beta Reviewer");
  await expect(reviewer.getByText("Alpha Reviewer")).toHaveCount(0);
  expect(state.calls["GET bots"]).toBeGreaterThanOrEqual(2);
});
