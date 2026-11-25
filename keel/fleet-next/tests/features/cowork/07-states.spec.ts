import { test, expect, mockBridge, openApp, openSession, ignoreExpectedHttpError } from "./fixtures";

test("empty session shows honest empty states, not fake progress", async ({ page, consoleErrors }) => {
  await mockBridge(page, { rows: [] });
  await openSession(page);
  await expect(page.getByText("No messages yet")).toBeVisible();
  await expect(page.getByText(/Nothing is shown until the bridge reports a real step/)).toBeVisible();
  await expect(page.getByRole("progressbar", { name: "Reported tool steps completed" })).toHaveCount(0);
  expect(consoleErrors).toEqual([]);
});

test("session errors surface the bridge detail and Retry recovers", async ({ page, consoleErrors }) => {
  const bridge = await mockBridge(page, {
    rows: [],
    rowsError: { status: 404, body: { error: "session_expired", detail: "Session expired" } },
  });
  ignoreExpectedHttpError(page, /\/api\/bridge\/bots\/bot-1\/rows$/);
  await openSession(page);
  await expect(page.getByText("Session expired")).toBeVisible();
  const errorBanner = page.getByRole("alert").filter({ hasText: "Session expired" });
  await expect(errorBanner.getByRole("button", { name: "Retry" })).toBeVisible();

  bridge.rowsError = undefined;
  await errorBanner.getByRole("button", { name: "Retry" }).click();
  await expect(page.getByText("Session expired")).toHaveCount(0);
  await expect(page.getByText("No messages yet")).toBeVisible();
  expect(consoleErrors).toEqual([]);
});

test("browser offline state is shown and cleared without claiming bridge health", async ({ page, consoleErrors }) => {
  await page.addInitScript(() => {
    (window as unknown as { __netOnline: boolean }).__netOnline = true;
    Object.defineProperty(navigator, "onLine", {
      configurable: true,
      get: () => (window as unknown as { __netOnline: boolean }).__netOnline,
    });
  });
  await mockBridge(page, { rows: [] });
  await openApp(page);

  await expect(page.getByText(/You appear to be offline/)).toHaveCount(0);
  await page.evaluate(() => {
    (window as unknown as { __netOnline: boolean }).__netOnline = false;
    window.dispatchEvent(new Event("offline"));
  });
  await expect(page.getByText(/You appear to be offline/)).toBeVisible();
  await page.evaluate(() => {
    (window as unknown as { __netOnline: boolean }).__netOnline = true;
    window.dispatchEvent(new Event("online"));
  });
  await expect(page.getByText(/You appear to be offline/)).toHaveCount(0);
  expect(consoleErrors).toEqual([]);
});
