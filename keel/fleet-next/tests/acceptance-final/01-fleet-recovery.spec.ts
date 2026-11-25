import { openApp, gotoTop, expect, test, routeAcceptanceBridge, callWithPath,
  FIXTURE_MARKDOWN, FIXTURE_DELETED_ROWS } from "./fixtures";

/**
 * Agent G independent acceptance — Fleet transcript recovery.
 *
 * All bridge responses are labelled FIXTURES (see fixtures.ts). The assertions
 * are on the REAL mutation bodies the UI sends to the bridge:
 *   POST bots/:id/rewind  { from_seq: N }
 *   POST bots/:id/restore { rows: <the exact rows returned by rewind> }
 *   POST tasks/:id/undo   (the real single-snapshot restore path)
 * No success state is accepted without a matching bridge payload.
 */

async function openAlphaHistory(page: import("@playwright/test").Page) {
  await openApp(page);
  await gotoTop(page, "Fleet");
  await expect(page.getByRole("heading", { name: "Fleet", exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Select Alpha" }).locator("..")
    .getByRole("button", { name: "Details" }).click();
  const drawer = page.getByRole("dialog", { name: "Alpha details" });
  await expect(drawer).toBeVisible();
  await drawer.getByRole("tab", { name: "Activity / History" }).click();
  await expect(drawer.getByRole("heading", { name: "Transcript" })).toBeVisible();
  return drawer;
}

test("Fleet Markdown export is a real bridge attachment with the exact fixture bytes", async ({ page, consoleErrors }) => {
  void consoleErrors;
  await routeAcceptanceBridge(page);
  const drawer = await openAlphaHistory(page);

  const link = drawer.getByRole("link", { name: "Download Markdown transcript" });
  await expect(link).toBeVisible();
  await expect(link).toHaveAttribute("href", "/api/bridge/bots/b_alpha/export.md");
  await expect(link).toHaveAttribute("download", "Alpha.md");

  // Assert the real payload through the intercepted in-page fetch. (Chromium's
  // download manager bypasses page.route, so the click itself only proves a
  // download is triggered; the bytes are asserted here.)
  const payload = await page.evaluate(async () => {
    const response = await fetch("/api/bridge/bots/b_alpha/export.md", { cache: "no-store" });
    return {
      ok: response.ok,
      contentType: response.headers.get("content-type"),
      disposition: response.headers.get("content-disposition"),
      body: await response.text(),
    };
  });
  expect(payload.ok).toBeTruthy();
  expect(payload.contentType).toMatch(/text\/markdown/);
  expect(payload.disposition).toMatch(/attachment/);
  expect(payload.body).toBe(FIXTURE_MARKDOWN);

  const [download] = await Promise.all([
    page.waitForEvent("download"),
    link.click(),
  ]);
  expect(download.suggestedFilename()).toBe("Alpha.md");
});

test("a non-Markdown bridge response produces an honest unavailable state, no link", async ({ page, consoleErrors }) => {
  void consoleErrors;
  await routeAcceptanceBridge(page, { exportMode: "invalid" });
  const drawer = await openAlphaHistory(page);

  await expect(drawer.getByText(/Markdown export unavailable/)).toBeVisible();
  await expect(drawer.getByRole("link", { name: /Download Markdown transcript/ })).toHaveCount(0);
});

test("Fleet rewind sends {from_seq} and restore sends the exact rows the bridge returned", async ({ page, consoleErrors }) => {
  void consoleErrors;
  const fixture = await routeAcceptanceBridge(page);
  const drawer = await openAlphaHistory(page);

  await drawer.getByRole("button", { name: /Rewind transcript/ }).click();
  const dialog = page.getByRole("dialog", { name: "Rewind transcript?" });
  await expect(dialog).toBeVisible();

  // seq 2 is a real row in the FIXTURE transcript; rows 2 and 3 are deleted.
  await dialog.getByLabel("Rewind from sequence").selectOption("2");
  await expect(dialog.getByText(/2 row\(s\) deleted/)).toBeVisible();
  await dialog.getByRole("button", { name: /Delete rows from seq 2/ }).click();

  const rewind = callWithPath(fixture.calls, "POST bots/b_alpha/rewind");
  expect(rewind?.path).toBe("bots/b_alpha/rewind");
  expect(rewind?.body).toEqual({ from_seq: 2 });
  await expect(drawer.getByText(/Deleted 2 transcript row\(s\) from sequence 2/)).toBeVisible();

  const restoreButton = drawer.getByRole("button", { name: "Restore rows" });
  await expect(restoreButton).toBeVisible();
  await restoreButton.click();

  const restore = callWithPath(fixture.calls, "POST bots/b_alpha/restore");
  expect(restore?.path).toBe("bots/b_alpha/restore");
  expect(restore?.body).toEqual({ rows: FIXTURE_DELETED_ROWS });
  await expect(drawer.getByText(/Restored 2 transcript row\(s\) from sequence 2/)).toBeVisible();
  await expect(drawer.getByText(/re-appends them with new sequence numbers/)).toBeVisible();
  await expect(restoreButton).toHaveCount(0);
});

test("an empty rewind response is never shown as a successful restore", async ({ page, consoleErrors }) => {
  void consoleErrors;
  const fixture = await routeAcceptanceBridge(page, { rewindMode: "empty" });
  const drawer = await openAlphaHistory(page);

  await drawer.getByRole("button", { name: /Rewind transcript/ }).click();
  const dialog = page.getByRole("dialog", { name: "Rewind transcript?" });
  await dialog.getByLabel("Rewind from sequence").selectOption("2");
  await dialog.getByRole("button", { name: /Delete rows from seq 2/ }).click();

  expect(callWithPath(fixture.calls, "POST bots/b_alpha/rewind")?.body).toEqual({ from_seq: 2 });
  await expect(drawer.getByRole("alert").filter({ hasText: /no deleted rows.*nothing was rewound/i })).toBeVisible();
  await expect(drawer.getByRole("button", { name: "Restore rows" })).toHaveCount(0);
  expect(callWithPath(fixture.calls, "bots/b_alpha/restore")).toBeUndefined();
});

test("Escape cancels the rewind dialog without closing the drawer", async ({ page, consoleErrors }) => {
  void consoleErrors;
  await routeAcceptanceBridge(page);
  const drawer = await openAlphaHistory(page);

  await drawer.getByRole("button", { name: /Rewind transcript/ }).click();
  await expect(page.getByRole("dialog", { name: "Rewind transcript?" })).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog", { name: "Rewind transcript?" })).toHaveCount(0);
  await expect(drawer).toBeVisible();
});

test("task delete undo posts the bridge's single-snapshot restore route", async ({ page, consoleErrors }) => {
  void consoleErrors;
  const fixture = await routeAcceptanceBridge(page);
  await openApp(page);
  await gotoTop(page, "Fleet");
  await page.getByRole("tab", { name: /Tasks/ }).click();

  await page.getByRole("button", { name: "Open task QA undo target" }).click();
  await page.getByRole("button", { name: "Delete", exact: true }).click();
  const confirm = page.getByRole("dialog", { name: "Delete task?" });
  await expect(confirm.getByText(/only one previous state is kept/i)).toBeVisible();
  await confirm.getByRole("button", { name: "Delete task" }).click();
  expect(callWithPath(fixture.calls, "POST tasks/t1/delete")?.method).toBe("POST");

  await page.getByRole("button", { name: "Undo delete" }).click();
  const undo = callWithPath(fixture.calls, "POST tasks/t1/undo");
  expect(undo?.method).toBe("POST");
  await expect(page.getByText(/task .QA undo target. restored/i)).toBeVisible();
});
