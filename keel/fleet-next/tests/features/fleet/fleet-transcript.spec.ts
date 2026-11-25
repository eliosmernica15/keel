import { type Page } from "@playwright/test";
import {
  test, testWithExpectedHttpError, expect, openApp, gotoTop,
  routeFleetBridge, callWithPath, ROWS,
} from "./fixtures";

async function openHistory(page: Page) {
  await openApp(page);
  await gotoTop(page, "Fleet");
  await page.getByRole("button", { name: "Select Alpha" }).locator("..")
    .getByRole("button", { name: "Details" }).click();
  const drawer = page.getByRole("dialog", { name: "Alpha details" });
  await drawer.getByRole("tab", { name: "Activity / History" }).click();
  return drawer;
}

test("Markdown export is a real download; rewind and restore post the exact bridge payloads", async ({ page, consoleErrors }) => {
  void consoleErrors;
  const fixture = await routeFleetBridge(page);
  const drawer = await openHistory(page);

  // The export link is the bridge's real GET route with a real download attr.
  const link = drawer.getByRole("link", { name: "Download Markdown transcript" });
  await expect(link).toBeVisible();
  await expect(link).toHaveAttribute("href", "/api/bridge/bots/b_alpha/export.md");
  await expect(link).toHaveAttribute("download", "Alpha.md");
  const [download] = await Promise.all([page.waitForEvent("download"), link.click()]);
  expect(download.suggestedFilename()).toBe("Alpha.md");

  // Confirmation shows the exact sequence point and the rows it will delete.
  await drawer.getByRole("button", { name: "Rewind transcript…" }).click();
  const dialog = page.getByRole("dialog", { name: "Rewind transcript?" });
  await expect(dialog).toBeVisible();
  await expect(dialog.getByLabel("Rewind from sequence")).toHaveValue("2");
  await expect(dialog.getByText(/Exact history point: sequence/)).toContainText("1 row(s) deleted (seq 2–2)");
  await dialog.getByLabel("Rewind from sequence").selectOption("1");
  await expect(dialog.getByText(/Exact history point: sequence/)).toContainText("2 row(s) deleted (seq 1–2)");

  await dialog.getByRole("button", { name: "Delete rows from seq 1" }).click();
  const rewindCall = callWithPath(fixture.calls, "POST bots/b_alpha/rewind");
  expect(rewindCall?.method).toBe("POST");
  expect(rewindCall?.path).toBe("bots/b_alpha/rewind");
  expect(rewindCall?.body).toEqual({ from_seq: 1 });

  // Success is claimed only from the bridge's response, and deleted rows are
  // held in memory for recovery (never written to localStorage).
  await expect(drawer.getByText("Deleted 2 transcript row(s) from sequence 1.")).toBeVisible();
  await expect(drawer.getByText(/Rewound from sequence 1 · 2 row\(s\) deleted/)).toBeVisible();
  await expect(drawer.getByText("0 rows")).toBeVisible();
  await expect(drawer.getByText(/Restored \d+ transcript row/)).toHaveCount(0);

  await drawer.getByRole("button", { name: "Restore rows" }).click();
  const restoreCall = callWithPath(fixture.calls, "POST bots/b_alpha/restore");
  expect(restoreCall?.method).toBe("POST");
  expect(restoreCall?.path).toBe("bots/b_alpha/restore");
  expect(restoreCall?.body).toEqual({
    rows: ROWS.b_alpha.map((row) => ({ bot_id: "b_alpha", ...(row as Record<string, unknown>) })),
  });

  await expect(drawer.getByText(/Restored 2 transcript row\(s\) from sequence 1/)).toBeVisible();
  await expect(drawer.getByText(/new sequence numbers/)).toBeVisible();
  await expect(drawer.getByRole("button", { name: "Restore rows" })).toHaveCount(0);
  await expect(drawer.getByText("2 rows")).toBeVisible();
});

testWithExpectedHttpError("Rewind confirmation is explicit; Escape cancels only the dialog, and a bridge error claims no success", async ({ page, consoleErrors }) => {
  void consoleErrors;
  const fixture = await routeFleetBridge(page, { rewindMode: "bad_seq" });
  const drawer = await openHistory(page);

  await drawer.getByRole("button", { name: "Rewind transcript…" }).click();
  const dialog = page.getByRole("dialog", { name: "Rewind transcript?" });
  await expect(dialog).toBeVisible();
  await expect(dialog.getByText(/Every transcript row with sequence number/)).toBeVisible();
  await expect(dialog.getByLabel("Rewind from sequence")).toHaveValue("2");

  // A dialog-scoped Escape must not close the enclosing details drawer.
  await page.keyboard.press("Escape");
  await expect(dialog).toHaveCount(0);
  await expect(drawer).toBeVisible();

  // Cancel closes the dialog without posting anything.
  await drawer.getByRole("button", { name: "Rewind transcript…" }).click();
  await dialog.getByRole("button", { name: "Cancel" }).click();
  await expect(dialog).toHaveCount(0);
  expect(fixture.calls.filter((c) => c.path.endsWith("/rewind"))).toHaveLength(0);

  // The bridge refused this sequence: show the real error, keep the ledger.
  await drawer.getByRole("button", { name: "Rewind transcript…" }).click();
  await dialog.getByRole("button", { name: "Delete rows from seq 2" }).click();
  await expect(dialog.getByText("Rewind failed: from_seq must be positive")).toBeVisible();
  await expect(drawer.getByText(/Deleted \d+ transcript row/)).toHaveCount(0);
  await expect(drawer.getByRole("button", { name: "Restore rows" })).toHaveCount(0);
  await expect(drawer.getByText("2 rows")).toBeVisible();
  expect(callWithPath(fixture.calls, "POST bots/b_alpha/rewind")?.body).toEqual({ from_seq: 2 });
});

testWithExpectedHttpError("Unavailable export and failed restore are honest; recovery is discarded when the drawer closes", async ({ page, consoleErrors }) => {
  void consoleErrors;
  const fixture = await routeFleetBridge(page, { exportMode: "unavailable", restoreMode: "failure" });
  const drawer = await openHistory(page);

  await expect(drawer.getByText(/Markdown export unavailable/)).toBeVisible();
  await expect(drawer.getByRole("link", { name: "Download Markdown transcript" })).toHaveCount(0);

  await drawer.getByRole("button", { name: "Rewind transcript…" }).click();
  const dialog = page.getByRole("dialog", { name: "Rewind transcript?" });
  await expect(dialog.getByText(/Exact history point: sequence/)).toContainText("1 row(s) deleted (seq 2–2)");
  await dialog.getByRole("button", { name: "Delete rows from seq 2" }).click();
  await expect(drawer.getByText(/Rewound from sequence 2 · 1 row\(s\) deleted/)).toBeVisible();

  await drawer.getByRole("button", { name: "Restore rows" }).click();
  await expect(drawer.getByText("Restore failed: restore_rows failed")).toBeVisible();
  await expect(drawer.getByText(/Restored \d+ transcript row/)).toHaveCount(0);
  // Recovery stays available for a retry instead of being silently dropped.
  await expect(drawer.getByRole("button", { name: "Restore rows" })).toBeVisible();
  expect(callWithPath(fixture.calls, "POST bots/b_alpha/restore")?.body).toEqual({
    rows: [{ bot_id: "b_alpha", ...(ROWS.b_alpha[1] as Record<string, unknown>) }],
  });

  // Closing the drawer discards the in-memory snapshot; reopening shows only
  // the bridge's real rows, with no phantom restore action.
  await page.keyboard.press("Escape");
  await expect(drawer).toHaveCount(0);
  await page.getByRole("button", { name: "Select Alpha" }).locator("..")
    .getByRole("button", { name: "Details" }).click();
  const again = page.getByRole("dialog", { name: "Alpha details" });
  await again.getByRole("tab", { name: "Activity / History" }).click();
  await expect(again.getByRole("button", { name: "Restore rows" })).toHaveCount(0);
  await expect(again.getByText("1 rows")).toBeVisible();
});

test("In-flight rewind is guarded: the confirm button is busy and only one request is sent", async ({ page, consoleErrors }) => {
  void consoleErrors;
  const fixture = await routeFleetBridge(page, { rewindMode: "slow" });
  const drawer = await openHistory(page);

  await drawer.getByRole("button", { name: "Rewind transcript…" }).click();
  const dialog = page.getByRole("dialog", { name: "Rewind transcript?" });
  const confirm = dialog.getByRole("button", { name: "Delete rows from seq 2" });
  await confirm.click();
  await expect(confirm).toBeDisabled();
  await expect(confirm).toHaveAttribute("aria-busy", "true");

  await expect(drawer.getByText(/Rewound from sequence 2 · 1 row\(s\) deleted/)).toBeVisible();
  expect(fixture.calls.filter((c) => c.path.endsWith("/rewind"))).toHaveLength(1);
});
