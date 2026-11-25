import { test, expect } from "./fixtures";
import { DESTINATIONS, gotoDestination, openApp } from "./fixtures";

const GET_ENDPOINTS = [
  "bots", "providers", "projects", "shells", "tasks", "routines",
  "library", "skills", "connectors", "usage", "keep-awake", "commands", "workflows",
];

test("no failed requests or broken HTTP responses while visiting all destinations", async ({ page, consoleErrors }) => {
  void consoleErrors;
  const failed: string[] = [];
  const httpErrors: string[] = [];
  page.on("requestfailed", (r) => {
    // A long-lived EventSource is always aborted when the page navigates
    // between destinations; that is normal teardown, not a broken request.
    if (r.url().includes("/api/bridge/events") && r.failure()?.errorText === "net::ERR_ABORTED") return;
    failed.push(`${r.method()} ${r.url()} :: ${r.failure()?.errorText ?? "?"}`);
  });
  page.on("response", (r) => {
    if (r.status() >= 400) httpErrors.push(`${r.status()} ${r.request().method()} ${r.url()}`);
  });

  await openApp(page);
  for (const dest of DESTINATIONS) {
    await gotoDestination(page, dest);
    await page.waitForTimeout(250);
  }
  console.log(`NETWORK failed=${JSON.stringify(failed)} httpErrors=${JSON.stringify(httpErrors)}`);
  expect(failed, `failed requests: ${JSON.stringify(failed)}`).toEqual([]);
  expect(httpErrors, `HTTP errors: ${JSON.stringify(httpErrors)}`).toEqual([]);
});

test("every read-only bridge endpoint used by the shell answers HTTP 200", async ({ page }) => {
  await openApp(page);
  const result: Array<{ path: string; status: number }> = [];
  for (const path of GET_ENDPOINTS) {
    const response = await page.request.get(`/api/bridge/${path}`);
    result.push({ path, status: response.status() });
  }
  console.log(`ROUTES ${JSON.stringify(result)}`);
  for (const entry of result) expect(entry.status, JSON.stringify(result)).toBe(200);
});

test("unknown application paths return a real 404, not a 500 or an empty shell", async ({ page }) => {
  const response = await page.goto("/this-route-does-not-exist");
  expect(response?.status(), "unknown route must be 404").toBe(404);
  await expect(page.locator("body")).not.toContainText("Internal Server Error");
});
