import { test, expect, mockBridge, openSession, BOT } from "./fixtures";

const approvalRow = (id: string, status: string, expiresAt: string) => ({
  seq: id === "ap-1" ? 2 : id === "ap-2" ? 3 : 4,
  bot_id: BOT.id,
  kind: "approval",
  body: {
    approval_id: id,
    tool_name: "run_shell",
    summary: `Run guarded command ${id}`,
    explanation: "Executes in the trusted project shell",
    status,
    expires_at: expiresAt,
  },
  created_at: "2026-11-24T10:00:00Z",
});

const future = new Date(Date.now() + 600_000).toISOString();
const past = new Date(Date.now() - 600_000).toISOString();

test("approval decision payloads are once / always / never and resolved rows are honoured", async ({ page, consoleErrors }) => {
  const rows = [approvalRow("ap-1", "pending", future), approvalRow("ap-2", "pending", future), approvalRow("ap-3", "pending", future)];
  const bridge = await mockBridge(page, { rows });
  await openSession(page);

  await expect(page.getByRole("heading", { name: "Approval required" })).toHaveCount(3);
  await expect(page.getByText("Waiting for you").first()).toBeVisible();

  const card = (id: string) => page.locator('section[aria-label="Permission request"]').filter({ hasText: id });
  await card("ap-1").getByRole("button", { name: "Allow once" }).click();
  await expect(card("ap-1")).toHaveCount(0);
  await expect(page.getByText("Allowed once")).toBeVisible();

  await card("ap-2").getByRole("button", { name: "Always allow" }).click();
  await expect(page.getByText("Always allowed")).toBeVisible();

  await card("ap-3").getByRole("button", { name: "Don't allow" }).click();
  await expect(page.getByText("Don't allow").last()).toBeVisible();

  const decisions = bridge.requests.filter((r) => r.method === "POST" && /\/decide$/.test(r.path));
  expect(decisions.map((r) => [r.path.split("/").slice(-2)[0], (r.body as { decision: string }).decision])).toEqual([
    ["ap-1", "once"], ["ap-2", "always"], ["ap-3", "never"],
  ]);
  expect(consoleErrors).toEqual([]);
});

test("an expired approval is shown as stale and cannot be decided", async ({ page, consoleErrors }) => {
  const bridge = await mockBridge(page, { rows: [approvalRow("ap-1", "pending", past)] });
  await openSession(page);

  await expect(page.getByRole("region", { name: "Expired approval request" })).toBeVisible();
  await expect(page.getByText("This request has expired.")).toBeVisible();
  await expect(page.getByRole("button", { name: "Allow once" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Always allow" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Don't allow" })).toHaveCount(0);
  await expect(page.getByText("Waiting for you")).toHaveCount(0);
  expect(bridge.count("POST", /\/decide$/)).toBe(0);
  expect(consoleErrors).toEqual([]);
});
