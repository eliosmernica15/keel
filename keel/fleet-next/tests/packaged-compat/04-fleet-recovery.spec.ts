import type { Locator, Page } from "@playwright/test";
import {
  test, expect, openApp, gotoTop, findCall, resetObservations,
  FIXTURE_MARKDOWN, FIXTURE_ROWS,
} from "./fixtures";

/**
 * FIXTURE-based Fleet transcript and task recovery on the packaged origin.
 * Assertions are made on the real mutation bodies recorded by the fixture
 * bridge after they pass through the same-origin BFF.
 */
async function openHistory(page: Page): Promise<Locator> {
  await openApp(page);
  await gotoTop(page, "Fleet");
  await expect(page.getByRole("heading", { name: "Fleet", exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Select Compat task" }).locator("..")
    .getByRole("button", { name: "Details" }).click();
  const drawer = page.getByRole("dialog", { name: "Compat task details" });
  await expect(drawer).toBeVisible();
  await drawer.getByRole("tab", { name: "Activity / History" }).click();
  await expect(drawer.getByRole("heading", { name: "Transcript" })).toBeVisible();
  return drawer;
}

test("FIXTURE: Markdown export stays a relative same-origin BFF attachment", async ({ page, consoleErrors }) => {
  const drawer = await openHistory(page);
  const link = drawer.getByRole("link", { name: "Download Markdown transcript" });
  await expect(link).toBeVisible();
  await expect(link).toHaveAttribute("href", "/api/bridge/bots/bot-1/export.md");
  await expect(link).toHaveAttribute("download", "Compat-task.md");

  const payload = await page.evaluate(async () => {
    const response = await fetch("/api/bridge/bots/bot-1/export.md", { cache: "no-store" });
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

  const [download] = await Promise.all([page.waitForEvent("download"), link.click()]);
  expect(download.suggestedFilename()).toBe("Compat-task.md");
  expect(consoleErrors).toEqual([]);
});

test("FIXTURE: rewind and restore post the exact bridge contract through the BFF", async ({ page, request, consoleErrors }) => {
  await resetObservations(request);
  const drawer = await openHistory(page);

  await drawer.getByRole("button", { name: /Rewind transcript/ }).click();
  const dialog = page.getByRole("dialog", { name: "Rewind transcript?" });
  await expect(dialog).toBeVisible();
  await dialog.getByLabel("Rewind from sequence").selectOption("2");
  await expect(dialog.getByText(/2 row\(s\) deleted/)).toBeVisible();
  await dialog.getByRole("button", { name: /Delete rows from seq 2/ }).click();

  const rewind = await findCall(request, "POST", "bots/bot-1/rewind");
  expect(rewind?.body).toEqual({ from_seq: 2 });
  await expect(drawer.getByText(/Deleted 2 transcript row\(s\) from sequence 2/)).toBeVisible();

  await drawer.getByRole("button", { name: "Restore rows" }).click();
  const restore = await findCall(request, "POST", "bots/bot-1/restore");
  expect(restore?.body).toEqual({ rows: FIXTURE_ROWS.slice(1) });
  await expect(drawer.getByText(/Restored 2 transcript row\(s\) from sequence 2/)).toBeVisible();
  expect(consoleErrors).toEqual([]);
});

test("FIXTURE: task delete undo reaches the single-snapshot bridge route", async ({ page, request, consoleErrors }) => {
  await resetObservations(request);
  await openApp(page);
  await gotoTop(page, "Fleet");
  await page.getByRole("tab", { name: /Tasks/ }).click();
  await page.getByRole("button", { name: "Open task QA undo target" }).click();
  await page.getByRole("button", { name: "Delete", exact: true }).click();
  const confirm = page.getByRole("dialog", { name: "Delete task?" });
  await expect(confirm.getByText(/only one previous state is kept/i)).toBeVisible();
  await confirm.getByRole("button", { name: "Delete task" }).click();
  expect((await findCall(request, "POST", "tasks/t1/delete"))?.method).toBe("POST");

  await page.getByRole("button", { name: "Undo delete" }).click();
  expect((await findCall(request, "POST", "tasks/t1/undo"))?.method).toBe("POST");
  await expect(page.getByText(/QA undo target. restored/)).toBeVisible();
  expect(consoleErrors).toEqual([]);
});
