import {
  test, testWithExpectedHttpError, expect, openApp, gotoTop, routeFleetBridge, callWithPath,
} from "./fixtures";

async function openFleet(page: import("@playwright/test").Page) {
  await openApp(page);
  await gotoTop(page, "Fleet");
  await expect(page.getByRole("heading", { name: "Fleet", exact: true })).toBeVisible();
}

test("Fleet agent roster, creation, details config, policy revoke and audit filtering use real bridge routes", async ({ page, consoleErrors }) => {
  void consoleErrors;
  const fixture = await routeFleetBridge(page);
  await openFleet(page);

  await expect(page.getByRole("button", { name: "Select Alpha" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Select Beta" })).toBeVisible();
  await expect(page.getByRole("tab", { name: /Agents/ })).toContainText("3");
  // Row-derived status: Alpha's last turn completed; Echo is labelled scripted.
  await expect(page.getByText("Turn complete · 1 steps").first()).toBeVisible();
  await expect(page.getByText("scripted (Echo)").first()).toBeVisible();

  // Creation sends exactly the bridge's create_bot fields.
  await page.getByRole("button", { name: "New agent" }).click();
  const create = page.getByRole("dialog", { name: "New agent" });
  await create.getByLabel("Name").fill("Gamma");
  await create.getByLabel("Role").fill("planner");
  await create.getByLabel("Notes").fill("operator note");
  await create.getByLabel("Engine").selectOption("echo");
  await create.getByRole("button", { name: "Create agent" }).click();
  const createCall = callWithPath(fixture.calls, "POST bots");
  expect(createCall?.path).toBe("bots");
  expect(createCall?.body).toEqual({ name: "Gamma", role: "planner", engine: "echo", notes: "operator note" });
  await expect(page.getByText("Agent Gamma created.")).toBeVisible();

  // Details drawer: config write, standing-policy revoke, audit filter.
  await page.getByRole("button", { name: "Select Alpha" }).locator("..")
    .getByRole("button", { name: "Details" }).click();
  const drawer = page.getByRole("dialog", { name: "Alpha details" });
  await expect(drawer).toBeVisible();
  for (const name of ["Studio / Profile", "Engine", "Notes", "Tasks", "Permissions", "Activity / History"]) {
    await expect(drawer.getByRole("tab", { name })).toBeVisible();
  }
  await drawer.getByRole("tab", { name: "Engine" }).click();
  await drawer.getByLabel("Reasoning effort").selectOption("high");
  await drawer.getByRole("button", { name: "Save engine" }).click();
  const updateCall = callWithPath(fixture.calls, "/update");
  expect(updateCall?.path).toBe("bots/b_alpha/update");
  expect(updateCall?.body).toEqual(expect.objectContaining({ engine: "provider", provider: "auto", reasoning_effort: "high" }));

  await drawer.getByRole("tab", { name: "Permissions" }).click();
  await expect(drawer.getByText("shell")).toBeVisible();
  await drawer.getByRole("button", { name: "Revoke" }).click();
  const revokeCall = callWithPath(fixture.calls, "/policies/revoke");
  expect(revokeCall?.body).toEqual({ tool_name: "shell" });
  await expect(page.getByText("Standing permission for shell revoked.")).toBeVisible();

  await drawer.getByRole("tab", { name: "Activity / History" }).click();
  await expect(drawer.getByText(/fingerprint fp1/).first()).toBeVisible();
  await drawer.getByLabel("Filter by result").selectOption("policy_revoked");
  await expect(drawer.getByText(/fingerprint policy/)).toBeVisible();
  await expect(drawer.getByText(/fingerprint fp1/)).toHaveCount(0);
  await drawer.getByLabel("Filter by result").selectOption("timeout");
  await expect(drawer.getByText("No matching decisions")).toBeVisible();

  // Agent deletion is irreversible: require an exact name before calling the bridge.
  await page.getByRole("button", { name: "Select Alpha" }).locator("..").getByRole("button", { name: "Delete" }).click();
  const deleteDialog = page.getByRole("dialog", { name: "Delete Alpha?" });
  const deleteButton = deleteDialog.getByRole("button", { name: "Delete agent" });
  await expect(deleteDialog.getByText(/permanently removes the agent's conversation rows and Library files/i)).toBeVisible();
  await expect(deleteButton).toBeDisabled();
  await deleteDialog.getByLabel("Type agent name to confirm").fill("Alpha ");
  await expect(deleteButton).toBeDisabled();
  await deleteDialog.getByLabel("Type agent name to confirm").fill("Alpha");
  await expect(deleteButton).toBeEnabled();
  await deleteButton.click();
  expect(callWithPath(fixture.calls, "POST bots/b_alpha/delete")?.body).toEqual({});
  await expect(page.getByText("Agent Alpha deleted.")).toBeVisible();
});

testWithExpectedHttpError("Group creation posts bot_ids; a 409 round is honest and Send re-enables only after real terminal rows", async ({ page, consoleErrors }) => {
  void consoleErrors;
  const fixture = await routeFleetBridge(page, { groupMessageMode: "conflict" });
  await openFleet(page);

  await page.getByRole("tab", { name: /Groups/ }).click();
  await expect(page.getByRole("tab", { name: /Groups/ })).toContainText("1");
  await expect(page.getByRole("button", { name: "Open group Ops" })).toBeVisible();

  await page.getByRole("button", { name: "New group" }).click();
  const dialog = page.getByRole("dialog", { name: "New group" });
  await dialog.getByLabel("Group name").fill("Ops");
  await dialog.getByLabel("Include Alpha").check();
  await dialog.getByLabel("Include Beta").check();
  await dialog.getByRole("button", { name: "Create group" }).click();
  const created = callWithPath(fixture.calls, "POST groups");
  expect(created?.body).toEqual({ name: "Ops", bot_ids: ["b_alpha", "b_beta"] });

  await page.getByRole("button", { name: "Open group Ops" }).click();
  await expect(page.getByRole("textbox", { name: "Group message" })).toBeVisible();
  await page.getByRole("textbox", { name: "Group message" }).fill("Hello group");
  await page.getByRole("button", { name: "Send" }).click();
  await expect(page.getByText(/bridge refused a second message with 409\/busy/)).toBeVisible();
  const sendCall = callWithPath(fixture.calls, "/messages");
  expect(sendCall?.body).toEqual({ content: "Hello group" });
  const send = page.getByRole("button", { name: "Send" });
  await expect(send).toBeDisabled();

  // The recheck reads the real group ledger; terminal member_status rows close
  // the round and make the composer usable again.
  fixture.groupRows = [
    ...fixture.groupRows,
    { seq: 5, group_id: "g1", author: "system", kind: "member_status", body: { bot_id: "b_alpha", status: "done" }, created_at: "2026-11-24T10:00:10Z" },
    { seq: 6, group_id: "g1", author: "system", kind: "member_status", body: { bot_id: "b_beta", status: "done" }, created_at: "2026-11-24T10:00:11Z" },
  ];
  await page.getByRole("button", { name: "Recheck round" }).click();
  await expect(page.getByText(/bridge refused a second message/)).toHaveCount(0);
  await expect(send).toBeEnabled();
  fixture.groupMessageMode = "ok";
  await page.getByRole("textbox", { name: "Group message" }).fill("Second message");
  await send.click();
  expect(fixture.calls.filter((c) => c.path.endsWith("/messages"))).toHaveLength(2);
});

test("Task CRUD payloads, cancel route and recoverable delete/undo are exercised through the bridge", async ({ page, consoleErrors }) => {
  void consoleErrors;
  const fixture = await routeFleetBridge(page);
  await openFleet(page);
  await page.getByRole("tab", { name: /Tasks/ }).click();

  await page.getByRole("tabpanel", { name: "fleet" }).getByRole("button", { name: "New task" }).click();
  const create = page.getByRole("dialog", { name: "New task" });
  await create.getByLabel("Title").fill("Write parity notes");
  await create.getByLabel("Description").fill("Using real bridge payloads");
  await create.getByLabel("Priority").selectOption("high");
  await create.getByLabel("Assignee").selectOption("b_alpha");
  await create.getByRole("button", { name: "Create task" }).click();
  expect(callWithPath(fixture.calls, "POST tasks")?.body).toEqual({
    title: "Write parity notes", description: "Using real bridge payloads",
    priority: "high", assigned_bot_id: "b_alpha",
  });
  await expect(page.getByText("Task “Write parity notes” created.")).toBeVisible();

  await page.getByRole("button", { name: "Open task Review draft" }).click();
  await page.getByLabel("Status", { exact: true }).selectOption("completed");
  await page.getByLabel("Progress %").fill("100");
  await page.getByLabel("Note (recorded in task history)").fill("done by operator");
  await page.getByRole("button", { name: "Save changes" }).click();
  const update = callWithPath(fixture.calls, "/t2/update");
  expect(update?.body).toEqual({ status: "completed", progress: 100, note: "done by operator" });

  await page.getByLabel("Assignee").selectOption("b_alpha");
  expect(callWithPath(fixture.calls, "/t2/assign")?.body).toEqual({ assigned_bot_id: "b_alpha" });

  await page.getByRole("button", { name: "Cancel task" }).click();
  const cancel = callWithPath(fixture.calls, "/t2/cancel");
  expect(cancel?.method).toBe("POST");

  await page.getByRole("button", { name: "Delete", exact: true }).click();
  const confirm = page.getByRole("dialog", { name: "Delete task?" });
  await confirm.getByRole("button", { name: "Delete task" }).click();
  expect(callWithPath(fixture.calls, "/t2/delete")?.method).toBe("POST");
  await expect(page.getByText("The bridge keeps one previous-state snapshot for tasks; this is the real restore path.")).toBeVisible();
  await page.getByRole("button", { name: "Undo delete" }).click();
  expect(callWithPath(fixture.calls, "/t2/undo")?.method).toBe("POST");
  await expect(page.getByText("Task “Review draft” restored.")).toBeVisible();
});

testWithExpectedHttpError("Routines run 409, pause reason, enable/disable and reported history", async ({ page, consoleErrors }) => {
  void consoleErrors;
  const fixture = await routeFleetBridge(page, { runMode: "conflict" });
  await openFleet(page);
  await page.getByRole("tab", { name: /Routines/ }).click();
  await page.getByRole("button", { name: "Open routine Morning sweep" }).click();
  await expect(page.getByRole("heading", { name: "Morning sweep" })).toBeVisible();
  await expect(page.getByText("skipped_missed").first()).toBeVisible();
  await expect(page.getByText(/Missed scheduled run/)).toBeVisible();
  await expect(page.getByText(/Next run \(reported by bridge\)/)).toBeVisible();

  await page.getByRole("button", { name: "Run now" }).click();
  await expect(page.getByText("Run not started: routine is already running")).toBeVisible();
  expect(callWithPath(fixture.calls, "/r1/run")?.method).toBe("POST");

  await page.getByRole("button", { name: "Pause" }).click();
  expect(callWithPath(fixture.calls, "/r1/pause")?.body).toEqual({ reason: "paused from UI" });
  await page.getByRole("button", { name: "Disable" }).click();
  expect(callWithPath(fixture.calls, "/r1/disable")?.method).toBe("POST");
  await page.getByRole("button", { name: "Edit" }).click();
  const edit = page.getByRole("dialog", { name: "Edit Morning sweep" });
  await edit.getByLabel("Cron expression").fill("0 10 * * *");
  await edit.getByRole("button", { name: "Save routine" }).click();
  expect(callWithPath(fixture.calls, "/r1/update")?.body).toEqual(expect.objectContaining({ cron_expr: "0 10 * * *" }));
});

test("Library upload, preview of every file type and delete confirmation are backed by real routes", async ({ page, consoleErrors }) => {
  void consoleErrors;
  const fixture = await routeFleetBridge(page);
  await openFleet(page);
  await page.getByRole("tab", { name: /Library/ }).click();
  await expect(page.getByText("chart.png")).toBeVisible();
  await expect(page.getByText("blob.bin")).toBeVisible();

  // A real preview route exists for every file (non-image types are text/plain).
  await expect(page.getByRole("button", { name: "Preview" })).toHaveCount(2);

  await page.getByRole("button", { name: "Upload" }).click();
  const upload = page.getByRole("dialog", { name: "Upload to library" });
  await upload.getByLabel("Agent (required by bridge)").selectOption("b_alpha");
  await upload.locator("#upload-file").setInputFiles({ name: "note.txt", mimeType: "text/plain", buffer: Buffer.from("hello") });
  await upload.getByRole("button", { name: "Upload", exact: true }).click();
  await expect(page.getByText("File uploaded to the library.")).toBeVisible();
  const uploadCall = callWithPath(fixture.calls, "POST library");
  expect(uploadCall?.path).toBe("library");
  expect(uploadCall?.body).toEqual({ filename: "note.txt", bot_id: "b_alpha", content_base64: Buffer.from("hello").toString("base64"), mime: "text/plain" });

  await page.getByRole("button", { name: "Delete chart.png" }).click();
  const del = page.getByRole("dialog", { name: "Delete library file?" });
  await expect(del.getByText(/no restore endpoint for library deletions/)).toBeVisible();
  await del.getByRole("button", { name: "Delete file" }).click();
  expect(callWithPath(fixture.calls, "/f1/delete")?.method).toBe("POST");

  await page.getByRole("button", { name: "Preview" }).first().click();
  await expect(page.locator('iframe[src="/api/bridge/library/f1/preview"]')).toBeVisible();
});

test("Global audit filtering matches real event/decision/outcome values", async ({ page, consoleErrors }) => {
  void consoleErrors;
  await routeFleetBridge(page);
  await openFleet(page);
  await page.getByRole("tab", { name: /Decision history/ }).click();
  await expect(page.getByText("shell · requested").first()).toBeVisible();
  await expect(page.getByText("shell · policy_revoked").first()).toBeVisible();

  await page.getByLabel("Filter by agent").selectOption("b_alpha");
  await page.getByLabel("Filter by tool").fill("send_to_bot");
  await expect(page.getByText("send_to_bot · outcome").first()).toBeVisible();
  await expect(page.getByText("shell · requested")).toHaveCount(0);
  await page.getByLabel("Filter by result").selectOption("executed");
  await expect(page.getByText("send_to_bot · outcome").first()).toBeVisible();
  await page.getByLabel("Filter by date").fill("2026-11-23");
  await expect(page.getByText("No entries match these filters")).toBeVisible();
});

test("Parent/child delegation is presented only from real row fields", async ({ page, consoleErrors }) => {
  void consoleErrors;
  await routeFleetBridge(page);
  await openFleet(page);

  // Parent side: `delegated` on a send_to_bot step row.
  await expect(page.getByText("this agent → Child")).toBeVisible();
  await expect(page.getByRole("button", { name: "Open conversation" })).toBeVisible();

  // Child side: `delegated_from` on the child's user row.
  await page.getByRole("button", { name: "Select Child" }).click();
  await expect(page.getByText("Alpha → this agent")).toBeVisible();
  await expect(page.getByRole("button", { name: "Open parent conversation" })).toBeVisible();
});

testWithExpectedHttpError("An unavailable bridge is reported honestly and shows no placeholder data", async ({ page, consoleErrors }) => {
  void consoleErrors;
  await routeFleetBridge(page, { botsUnavailable: true });
  await openFleet(page);
  await gotoTop(page, "Fleet");
  await expect(page.getByText("Local bridge unavailable.")).toBeVisible();
  await expect(page.getByText(/No offline placeholder data is shown/)).toBeVisible();
  await expect(page.getByRole("button", { name: "Select Alpha" })).toHaveCount(0);
  await page.getByRole("button", { name: "Retry" }).first().click();
  await expect(page.getByText("Local bridge unavailable.")).toBeVisible();
});
