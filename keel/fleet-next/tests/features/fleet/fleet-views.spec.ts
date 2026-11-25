import {
  test, expect, openApp, gotoTop, routeFleetBridge, callWithPath, BOARD_TASKS,
} from "./fixtures";

async function openFleet(page: import("@playwright/test").Page) {
  await openApp(page);
  await gotoTop(page, "Fleet");
  await expect(page.getByRole("heading", { name: "Fleet", exact: true })).toBeVisible();
}

test("Kanban columns and cards come from real task rows; moves and assignments use only real routes", async ({ page, consoleErrors }) => {
  void consoleErrors;
  const fixture = await routeFleetBridge(page, { tasks: BOARD_TASKS });
  await openFleet(page);
  await page.getByRole("tab", { name: /Board/ }).click();

  await expect(page.getByRole("heading", { name: "Task board" })).toBeVisible();
  for (const column of ["Pending column", "In progress column", "Completed column", "Failed column", "Cancelled column"]) {
    await expect(page.getByRole("region", { name: column })).toBeVisible();
  }
  await expect(page.getByRole("region", { name: "Pending column" })).toContainText("Draft brief");
  await expect(page.getByRole("region", { name: "In progress column" })).toContainText("Review draft");
  await expect(page.getByText(/1 task reported with a status outside the bridge's known set/)).toBeVisible();

  // Priority is a real task field: filtering never changes a task's status.
  await page.getByRole("button", { name: "high", exact: true }).click();
  await expect(page.getByRole("region", { name: "Pending column" })).not.toContainText("Draft brief");
  await expect(page.getByRole("region", { name: "In progress column" })).toContainText("Review draft");
  await page.getByRole("button", { name: "All priorities" }).click();

  // Accessible status control posts to the verified update route.
  await page.getByLabel("Move Review draft to status").selectOption("completed");
  const update = callWithPath(fixture.calls, "/t2/update");
  expect(update?.method).toBe("POST");
  expect(update?.body).toEqual({ status: "completed" });

  // Assignment goes to the dedicated real assign route, not update.
  await page.getByLabel("Assign Draft brief").selectOption("b_beta");
  const assign = callWithPath(fixture.calls, "/t1/assign");
  expect(assign?.method).toBe("POST");
  expect(assign?.body).toEqual({ assigned_bot_id: "b_beta" });

  // A real HTML5 drag uses the same update route and never invents a status.
  // Playwright's dragTo does not start Chromium drags in this harness (the
  // moves after mouse.down produce no dragstart/drop events here), so drive
  // the real mouse sequence by hand: down on the card, move to the column,
  // up — the same events a user drag produces.
  const cancelledColumn = page.getByRole("region", { name: "Cancelled column" });
  await cancelledColumn.scrollIntoViewIfNeeded();
  const columnBox = await cancelledColumn.boundingBox();
  if (!columnBox) throw new Error("Cancelled column has no bounding box");
  const card = page.locator("article").filter({ hasText: "Fix import" });
  await card.hover();
  await page.mouse.down();
  await page.mouse.move(columnBox.x + columnBox.width / 2, columnBox.y + Math.min(columnBox.height / 2, 120), { steps: 10 });
  await page.mouse.up();
  await page.waitForTimeout(300);
  const dragUpdate = fixture.calls.filter((c) => c.path === "tasks/t4/update");
  expect(dragUpdate.length).toBeGreaterThan(0);
  expect(dragUpdate[dragUpdate.length - 1].body).toEqual({ status: "cancelled" });
});

test("Delegation map states that hierarchy is unavailable and shows only row-derived links", async ({ page, consoleErrors }) => {
  void consoleErrors;
  await routeFleetBridge(page);
  await openFleet(page);
  await page.getByRole("tab", { name: /Delegation map/ }).click();

  await expect(page.getByRole("heading", { name: "Agent organization" })).toBeVisible();
  await expect(page.getByText("Organization hierarchy is unavailable from the bridge.")).toBeVisible();
  await expect(page.getByText(/no\s+parent_id\s*\/\s*child-id column/i)).toBeVisible();
  await expect(page.getByText(/not a hierarchy tree/i)).toBeVisible();

  // Parent row: `delegated` on Alpha's step; child row: `delegated_from` on Child.
  await expect(page.getByLabel("Alpha to Child")).toHaveCount(2);
  await expect(page.getByText("delegated", { exact: true }).first()).toBeVisible();
  await expect(page.getByText("received from parent")).toBeVisible();
});

test("Delegation map shows an honest empty state when no transcript carries delegation fields", async ({ page, consoleErrors }) => {
  void consoleErrors;
  await routeFleetBridge(page, { rows: { b_alpha: [], b_beta: [], b_child: [] } });
  await openFleet(page);
  await page.getByRole("tab", { name: /Delegation map/ }).click();

  await expect(page.getByText("Organization hierarchy is unavailable from the bridge.")).toBeVisible();
  await expect(page.getByText("No delegation reported by the bridge")).toBeVisible();
  await expect(page.getByLabel("Alpha to Child")).toHaveCount(0);
});

const LIVE_ROWS: Record<string, unknown[]> = {
  b_alpha: [
    {
      seq: 1, kind: "step", created_at: "2026-11-24T10:00:01Z",
      body: { name: "Shell command", status: "running", detail: "ls -la" },
    },
  ],
  b_beta: [
    {
      seq: 1, kind: "approval", created_at: "2026-11-24T10:00:02Z",
      body: { approval_id: "a1", tool_name: "shell", status: "pending", scope: "workspace", args_summary: "ls" },
    },
  ],
  b_child: [],
};
const TURN_END_FRAME = ": ping\n\n"
  + 'event: row\ndata: {"kind":"turn_end","bot_id":"b_alpha","body":{"terminal_reason":"completed","num_steps":2,"duration_ms":1200}}\n\n'
  + ": ping\n\n";

test("Live wall derives every card from reported rows, never from guessed state", async ({ page, consoleErrors }) => {
  void consoleErrors;
  await routeFleetBridge(page, { rows: LIVE_ROWS });
  await openFleet(page);
  await page.getByRole("tab", { name: /Live wall/ }).click();

  const alpha = page.getByRole("article", { name: "Agent Alpha activity" });
  const beta = page.getByRole("article", { name: "Agent Beta activity" });
  const child = page.getByRole("article", { name: "Agent Child activity" });

  await expect(alpha.getByText("Shell command")).toBeVisible();
  await expect(alpha.getByText("working", { exact: true })).toBeVisible();
  await expect(beta.getByText("Waiting for your decision on shell")).toBeVisible();
  await expect(beta.getByText("waiting for you", { exact: true })).toBeVisible();
  await expect(child.getByText("Scripted (Echo) agent — no run reported")).toBeVisible();
  await expect(child.getByText("not reported", { exact: true })).toBeVisible();
});

test("A named SSE row frame closes a real open step on the live wall", async ({ page, consoleErrors }) => {
  void consoleErrors;
  await routeFleetBridge(page, { rows: LIVE_ROWS, sseFrames: TURN_END_FRAME });
  await openFleet(page);
  await page.getByRole("tab", { name: /Live wall/ }).click();

  const alpha = page.getByRole("article", { name: "Agent Alpha activity" });
  // The named SSE frame really closes the open step; no invented state.
  await expect(alpha.getByText("Turn complete · 2 steps")).toBeVisible();
  await expect(alpha.getByText("working", { exact: true })).toHaveCount(0);
});

test("Cost view reports 'not reported by bridge' when usage rows carry no cost", async ({ page, consoleErrors }) => {
  void consoleErrors;
  await routeFleetBridge(page, {
    rows: {
      b_alpha: [
        {
          seq: 1, kind: "usage", created_at: "2026-11-24T10:00:09Z",
          body: {
            input_tokens: 1200, output_tokens: 300, provider: "auto", model: "",
            cost_basis: "unknown (no provider-reported cost)",
          },
        },
      ],
      b_beta: [], b_child: [],
    },
  });
  await openFleet(page);
  await page.getByRole("tab", { name: /Cost/ }).click();

  await expect(page.getByRole("heading", { name: "Cost per agent" })).toBeVisible();
  await expect(page.getByText("Not reported by bridge")).toBeVisible();
  await expect(page.getByText(/No cost is estimated, converted or inferred here/)).toBeVisible();
  await expect(page.getByRole("heading", { name: "Reported token usage (not cost)" })).toBeVisible();
  await expect(page.getByText("1200")).toBeVisible();
  await expect(page.getByText("300")).toBeVisible();
  // No dollar figure is rendered anywhere in the cost view.
  await expect(page.getByRole("tabpanel", { name: "fleet" }).getByRole("main")).not.toContainText("$");
});

test("Cost view has an explicit empty state when no agent reported usage rows", async ({ page, consoleErrors }) => {
  void consoleErrors;
  await routeFleetBridge(page, { rows: { b_alpha: [], b_beta: [], b_child: [] } });
  await openFleet(page);
  await page.getByRole("tab", { name: /Cost/ }).click();

  await expect(page.getByText("Not reported by bridge")).toBeVisible();
  await expect(page.getByText("No agent reported any usage rows. Nothing is shown as a cost.")).toBeVisible();
  await expect(page.getByRole("tabpanel", { name: "fleet" }).getByRole("main")).not.toContainText("$");
});

test("Cost view renders a figure only from a bridge-reported cost_usd field", async ({ page, consoleErrors }) => {
  void consoleErrors;
  // Contract guard: this checks the render path IF a future bridge reports a
  // real cost_usd. The current bridge never emits this field (see cost tests
  // above), so this is not a claim about today's runtime data.
  await routeFleetBridge(page, {
    rows: {
      b_alpha: [
        {
          seq: 1, kind: "usage", created_at: "2026-11-24T10:00:09Z",
          body: { input_tokens: 100, output_tokens: 20, cost_usd: 0.0123, cost_basis: "provider-reported" },
        },
      ],
      b_beta: [], b_child: [],
    },
  });
  await openFleet(page);
  await page.getByRole("tab", { name: /Cost/ }).click();

  await expect(page.getByRole("heading", { name: "Reported cost by agent" })).toBeVisible();
  await expect(page.getByText("0.0123")).toBeVisible();
  await expect(page.getByText("provider-reported")).toBeVisible();
  await expect(page.getByText("Not reported by bridge")).toHaveCount(0);
});
