import { test, expect, mockBridge, openSession, BOT } from "./fixtures";

const rows = [{
  seq: 1, bot_id: BOT.id, kind: "message", role: "user",
  body: { content: "first message" }, created_at: "2026-11-24T10:00:00Z",
}];

test("export points at the real export.md route; import is explicitly unavailable", async ({ page, consoleErrors }) => {
  const bridge = await mockBridge(page, { rows });
  await openSession(page);

  // bridge.exportUrl is the BFF path that proxies the verified Python route
  // GET /api/fleet/bots/:id/export.md (routes.py:344-357).
  const link = page.getByRole("link", { name: /Export/ });
  await expect(link).toHaveAttribute("href", `/api/bridge/bots/${BOT.id}/export.md`);
  await expect(link).toHaveAttribute("download", "");

  // No transcript import route exists in the bridge. The UI must say so,
  // rather than presenting a disabled-looking but fake upload workflow.
  await expect(page.getByRole("button", { name: "Import transcript unavailable" })).toBeDisabled();
  await expect(page.getByRole("note")).toContainText("no bridge route accepts the exported Markdown");
  expect(bridge.requests.filter((r) => /import/i.test(r.path))).toEqual([]);
  expect(consoleErrors).toEqual([]);
});
