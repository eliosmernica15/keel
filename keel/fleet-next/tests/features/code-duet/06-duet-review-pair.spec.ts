import type { Page } from "@playwright/test";
import { expect, test } from "./fixtures";

// Duet Review Pair acceptance: builder/reviewer identity and review state come
// only from real bridge bots and bot rows. The reviewer is comment-only.

const BUILDER = {
  id: "builder-b",
  name: "Alpha Builder",
  role: "Builder — implementation agent",
  provider: "local",
  model: "local-coder",
  notes: "Build the requested change and run verification.",
};
const REVIEWER = {
  id: "reviewer-r",
  name: "Gamma Reviewer",
  role: "Independent reviewer",
  provider: "local",
  model: "local-critic",
  notes: "Read-only independent review prompt.",
};

const BUILDER_ROWS = [
  {
    seq: 11, kind: "message", created_at: "2026-11-24T09:00:00Z",
    body: { role: "user", content: "Please review the changes in src/app.ts." },
  },
];
const REVIEWER_ROWS = [
  {
    seq: 21, kind: "message", created_at: "2026-11-24T09:01:00Z",
    body: { role: "assistant", content: "Finding: src/app.ts has no null check for greeting." },
  },
  {
    seq: 22, kind: "message", created_at: "2026-11-24T09:02:00Z",
    body: { role: "assistant", content: "Revision requested: add the null check before save." },
  },
];

async function openPair(page: Page) {
  await page.getByRole("button", { name: "Open review pair (builder and reviewer)" }).click();
  await expect(page.getByRole("tab", { name: "Review pair" })).toHaveAttribute("aria-selected", "true");
}

test("Review pair names an explicit builder and independent reviewer from real bot records", async ({ harness }) => {
  const { goto, requests } = harness;
  harness.state.bots = [BUILDER, REVIEWER];
  harness.state.botRows = { "builder-b": BUILDER_ROWS, "reviewer-r": REVIEWER_ROWS };
  await goto("duet");
  await openPair(harness.page);

  const builder = harness.page.locator('[data-pair-role="builder"]');
  const reviewer = harness.page.locator('[data-pair-role="reviewer"]');
  await expect(builder).toBeVisible();
  await expect(reviewer).toBeVisible();
  await expect(builder).toContainText("Alpha Builder");
  await expect(builder).toContainText("Builder — implementation agent");
  await expect(builder).toContainText("local-coder");
  await expect(reviewer).toContainText("Gamma Reviewer");
  await expect(reviewer).toContainText("Independent reviewer");
  await expect(reviewer).toContainText("local-critic");
  await expect(reviewer).toContainText("Comment-only");
  // Every identity field was reported, so no "not reported" placeholder is
  // invented here; the explicit-absence case has its own test below.
  await expect(builder.getByText("not reported by bridge")).toHaveCount(0);

  await expect(harness.page.getByText("Please review the changes in src/app.ts.")).toBeVisible();
  await expect(harness.page.locator('[data-pair-comment="21"]')).toContainText(
    "Finding: src/app.ts has no null check for greeting.",
  );
  await expect(harness.page.locator('[data-pair-comment="22"]')).toBeVisible();
  await expect(harness.page.getByText("revision requested", { exact: true })).toBeVisible();
  await expect(harness.page.getByText(/Inferred from the reviewer's last real message row \(seq 22\)/)).toBeVisible();

  expect(requests.some((r) => r.method === "GET" && r.path === "/api/bridge/bots")).toBe(true);
  expect(requests.some((r) => r.method === "GET" && r.path === "/api/bridge/bots/builder-b/rows")).toBe(true);
  expect(requests.some((r) => r.method === "GET" && r.path === "/api/bridge/bots/reviewer-r/rows")).toBe(true);
});

test("The reviewer is comment-only: no edit, save, write, trust or execute control", async ({ harness }) => {
  const { goto, requests, state } = harness;
  harness.state.bots = [BUILDER, REVIEWER];
  harness.state.botRows = { "builder-b": BUILDER_ROWS, "reviewer-r": REVIEWER_ROWS };
  const original = state.files["p1:src/app.ts"];
  await goto("duet");
  await openPair(harness.page);

  const reviewer = harness.page.locator('[data-pair-role="reviewer"]');
  expect(await reviewer.getByRole("button").count()).toBe(0);
  await expect(reviewer.getByRole("textbox")).toHaveCount(0);
  await expect(reviewer.getByText(/cannot edit files, write files or run tools in Keel/)).toBeVisible();

  const pane = harness.page.locator('[data-pair-root="true"]');
  expect(await pane.getByRole("button", { name: /edit|save|write|run|trust|apply|revert/i }).count()).toBe(0);
  expect(await pane.getByRole("textbox").count()).toBe(0);
  expect(state.files["p1:src/app.ts"]).toBe(original);
  expect(requests.filter((r) => r.method === "POST" && /file\/write|terminal\/exec|\/trust/.test(r.path))).toEqual([]);
  expect(requests.filter((r) => /preview|diff|apply/.test(r.path))).toEqual([]);
});

test("An absent independent reviewer is reported honestly rather than invented", async ({ harness }) => {
  const { goto } = harness;
  harness.state.bots = [BUILDER];
  harness.state.botRows = { "builder-b": BUILDER_ROWS };
  await goto("duet");
  await openPair(harness.page);

  const reviewer = harness.page.locator('[data-pair-role="reviewer"]');
  await expect(reviewer).toHaveAttribute("data-pair-state", "unconfigured");
  await expect(reviewer.getByRole("heading", { name: "Independent reviewer not configured by this bridge" })).toBeVisible();
  await expect(reviewer.getByText(/none carries a reviewer role and is distinct from the builder/)).toBeVisible();
  await expect(harness.page.getByText(/does not report an independent reviewer/)).toBeVisible();
  await expect(harness.page.locator("[data-pair-comment]")).toHaveCount(0);
  expect(await reviewer.getByRole("button").count()).toBe(0);
});

test("With no bots at all both roles are honestly unconfigured", async ({ harness }) => {
  const { goto } = harness;
  await goto("duet");
  await openPair(harness.page);

  await expect(harness.page.getByRole("heading", { name: "Builder not configured by this bridge" })).toBeVisible();
  await expect(harness.page.getByRole("heading", { name: "Independent reviewer not configured by this bridge" })).toBeVisible();
  expect(await harness.page.locator('[data-pair-root="true"]').getByRole("button", { name: /edit|save|write|run|trust/i }).count()).toBe(0);
});

test("Review state has honest empty states when the bridge rows carry no review activity", async ({ harness }) => {
  const { goto } = harness;
  harness.state.bots = [BUILDER, REVIEWER];
  harness.state.botRows = { "builder-b": [], "reviewer-r": [] };
  await goto("duet");
  await openPair(harness.page);

  await expect(harness.page.getByText("not reported by bridge").first()).toBeVisible();
  await expect(harness.page.getByText(
    "The independent reviewer has not posted any comment rows in its real bot transcript.",
  )).toBeVisible();
  await expect(harness.page.getByText(
    "The bridge has no review-status field. The reviewer's real messages contain no explicit accept or revision wording.",
  )).toBeVisible();
  await expect(harness.page.locator("[data-pair-comment]")).toHaveCount(0);
});

test("Accept status is derived only from the reviewer's real last message", async ({ harness }) => {
  const { goto } = harness;
  harness.state.bots = [BUILDER, REVIEWER];
  harness.state.botRows = {
    "builder-b": BUILDER_ROWS,
    "reviewer-r": [
      { seq: 31, kind: "message", body: { role: "assistant", content: "Initial finding: check the type guard." } },
      { seq: 32, kind: "message", body: { role: "assistant", content: "Approved — looks good, no issues." } },
    ],
  };
  await goto("duet");
  await openPair(harness.page);

  await expect(harness.page.getByText("accepted", { exact: true })).toBeVisible();
  await expect(harness.page.locator('[data-pair-comment="31"]')).toBeVisible();
  await expect(harness.page.locator('[data-pair-comment="32"]')).toBeVisible();
});

test("Review pair tab persists in the project-scoped Duet layout and adds no default tab", async ({ harness }) => {
  const { goto } = harness;
  harness.state.bots = [BUILDER, REVIEWER];
  harness.state.botRows = { "builder-b": BUILDER_ROWS, "reviewer-r": REVIEWER_ROWS };
  await goto("duet");

  const strip = harness.page.getByRole("tablist", { name: "Duet workspace tabs" });
  expect((await strip.getByRole("tab").allTextContents()).map((t) => t.trim())).toEqual([
    "Review", "Terminal", "Open file", "Browser",
  ]);
  await openPair(harness.page);
  await expect(reviewerCard(harness.page)).toBeVisible();

  await harness.page.reload();
  await expect(strip.getByRole("tab", { name: "Review pair" })).toHaveAttribute("aria-selected", "true");
  await expect(reviewerCard(harness.page)).toBeVisible();

  // Another project's layout must not inherit this tab.
  await harness.page.getByRole("combobox", { name: "Active project" }).selectOption("p2");
  await expect(strip.getByRole("tab", { name: "Review pair" })).toHaveCount(0);
  await harness.page.getByRole("combobox", { name: "Active project" }).selectOption("p1");
  await expect(strip.getByRole("tab", { name: "Review pair" })).toBeVisible();
});

function reviewerCard(page: Page) {
  return page.locator('[data-pair-role="reviewer"]');
}
