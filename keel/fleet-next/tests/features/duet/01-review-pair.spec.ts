import { expect, test } from "./fixtures";

// Review Pair acceptance: structured reviewer findings come from real bot
// rows, "Send to builder" uses real task + message routes, the builder has no
// resolve control, and only the user can resolve/dismiss locally.

const BUILDER = {
  id: "builder-b",
  name: "Alpha Builder",
  role: "Builder — implementation agent",
  provider: "local",
  model: "local-coder",
  notes: "Build the requested change.",
};
const REVIEWER = {
  id: "reviewer-r",
  name: "Gamma Reviewer",
  role: "Independent reviewer — comment only",
  provider: "local",
  model: "local-critic",
  notes: "Read-only independent review prompt.",
};

const REVIEWER_ROWS = [
  {
    seq: 21,
    kind: "message",
    created_at: "2026-11-28T09:01:00Z",
    body: {
      role: "assistant",
      content:
        'Findings from the diff:\n{"comments":[{"file":"src/app.ts","line":12,' +
        '"severity":"high","message":"Null guard missing for greeting",' +
        '"suggestion":"Add if (!value) return null;"}]}',
    },
  },
  {
    seq: 22,
    kind: "message",
    created_at: "2026-11-28T09:02:00Z",
    body: { role: "assistant", content: "Please add a regression test." },
  },
];

test("reviewer finding renders inline with file, line, severity and suggestion", async ({ harness }) => {
  const { gotoDuet, openPair, page, state } = harness;
  state.bots = [BUILDER, REVIEWER];
  state.botRows = { "reviewer-r": REVIEWER_ROWS, "builder-b": [] };
  await gotoDuet();
  await openPair();

  const comment = page.locator('[data-pair-comment="21"]');
  await expect(comment).toBeVisible();
  await expect(comment).toHaveAttribute("data-comment-file", "src/app.ts");
  await expect(comment).toHaveAttribute("data-comment-severity", "high");
  await expect(comment).toContainText("src/app.ts:12");
  await expect(comment).toContainText("Null guard missing for greeting");
  await expect(comment).toContainText("Suggestion:");
  await expect(comment).toContainText("Add if (!value) return null;");
  await expect(comment.getByText("Structured finding")).toBeVisible();
  await expect(page.locator('[data-pair-comment="22"]')).toContainText("Please add a regression test.");
});

test("request review calls the real messages route with real diff context", async ({ harness }) => {
  const { gotoDuet, openPair, page, requests, state } = harness;
  state.bots = [BUILDER, REVIEWER];
  state.botRows = { "reviewer-r": REVIEWER_ROWS };
  await gotoDuet();
  await openPair();

  await page.getByLabel("Review target").selectOption("src/app.ts");
  await page.getByRole("button", { name: /Request review/ }).click();
  await expect(page.locator('[data-pair-notice="true"]')).toContainText("Review requested through POST");

  const sent = requests.filter(
    (r) => r.method === "POST" && r.path === "/api/bridge/bots/reviewer-r/messages",
  );
  expect(sent).toHaveLength(1);
  const content = String((sent[0].body as { content?: unknown })?.content ?? "");
  expect(content).toContain("src/app.ts");
  expect(content).toContain("1 file changed");
  expect((sent[0].body as { mode?: unknown })?.mode).toBe("plan");
  await expect(page.getByText(/Review requested through POST \/api\/bridge\/bots\/reviewer-r\/messages/)).toBeVisible();
});

test("Send to builder creates a real task and posts a real builder message", async ({ harness }) => {
  const { gotoDuet, openPair, page, requests, state } = harness;
  state.bots = [BUILDER, REVIEWER];
  state.botRows = { "reviewer-r": REVIEWER_ROWS };
  await gotoDuet();
  await openPair();

  const comment = page.locator('[data-pair-comment="21"]');
  await comment.getByRole("button", { name: /Send to builder/ }).click();
  await expect(page.locator('[data-pair-notice="true"]')).toContainText("Task t_1 created");

  const tasks = requests.filter((r) => r.method === "POST" && r.path === "/api/bridge/tasks");
  expect(tasks).toHaveLength(1);
  expect((tasks[0].body as { assigned_bot_id?: unknown }).assigned_bot_id).toBe("builder-b");
  expect(String((tasks[0].body as { description?: unknown }).description ?? "")).toContain(
    "Null guard missing for greeting",
  );
  const messages = requests.filter(
    (r) => r.method === "POST" && r.path === "/api/bridge/bots/builder-b/messages",
  );
  expect(messages).toHaveLength(1);
  expect(String((messages[0].body as { content?: unknown }).content ?? "")).toContain("t_1");
  await expect(comment).toContainText("Sent to builder · task t_1");
  expect(state.tasks).toHaveLength(1);
});

test("builder cannot resolve; only the user can resolve or dismiss", async ({ harness }) => {
  const { gotoDuet, openPair, page, requests, state } = harness;
  state.bots = [BUILDER, REVIEWER];
  state.botRows = { "reviewer-r": REVIEWER_ROWS };
  await gotoDuet();
  await openPair();

  const builder = page.locator('[data-pair-role="builder"]');
  expect(await builder.getByRole("button", { name: /resolve|dismiss/i }).count()).toBe(0);
  await expect(page.locator('[data-pair-rule="builder-cannot-resolve"]')).toBeVisible();
  expect(requests.filter((r) => /resolve|dismiss/i.test(r.path))).toEqual([]);

  const comment = page.locator('[data-pair-comment="21"]');
  await comment.getByRole("button", { name: /Resolve/ }).click();
  await expect(comment).toContainText("resolved locally");
  await expect(page.getByText(/does not exist on this bridge/)).toBeVisible();

  const plain = page.locator('[data-pair-comment="22"]');
  await plain.getByRole("button", { name: /Dismiss/ }).click();
  await expect(plain).toContainText("dismissed locally");

  // Real reviewer comments also appear inline in the Review tab, and a
  // dismissed one is hidden there without inventing a replacement.
  await page.locator('[role="tab"][title="Review"]').click();
  const strip = page.locator('[data-review-inline="true"]');
  await expect(strip).toBeVisible();
  await expect(strip).toContainText("src/app.ts:12");
  await expect(strip).toContainText("high");
  await expect(strip).not.toContainText("Please add a regression test.");
});

test("without a reviewer the pane offers a real create action and no review state", async ({ harness }) => {
  const { gotoDuet, openPair, page, requests, state } = harness;
  state.bots = [BUILDER];
  state.botRows = {};
  state.policies["reviewer-r"] = [
    { bot_id: "reviewer-r", tool_name: "write_file", decision: "always" },
    { bot_id: "reviewer-r", tool_name: "run_shell", decision: "always" },
  ];
  await gotoDuet();
  await openPair();

  await expect(page.getByRole("heading", { name: "Independent reviewer not configured by this bridge" })).toBeVisible();
  await expect(page.getByText(/does not report an independent reviewer/)).toBeVisible();
  await expect(page.locator("[data-pair-comment]")).toHaveCount(0);

  await page.getByRole("button", { name: /Create comment-only reviewer/ }).click();
  await expect(page.locator('[data-pair-notice="true"]')).toContainText("Standing edit/shell permissions revoked");
  const created = requests.filter((r) => r.method === "POST" && r.path === "/api/bridge/bots");
  expect(created).toHaveLength(1);
  expect(String((created[0].body as { role?: unknown })?.role ?? "")).toMatch(/comment only/i);
  const revoked = requests.filter(
    (r) => r.method === "POST" && r.path === "/api/bridge/bots/reviewer-r/policies/revoke",
  );
  expect(revoked.map((r) => (r.body as { tool_name?: unknown }).tool_name).sort()).toEqual([
    "run_shell", "write_file",
  ]);
  await expect(page.locator('[data-pair-role="reviewer"]')).toHaveAttribute("data-pair-state", "configured");
  await expect(page.getByText(/Standing edit\/shell approvals for this reviewer/)).toBeVisible();
});
