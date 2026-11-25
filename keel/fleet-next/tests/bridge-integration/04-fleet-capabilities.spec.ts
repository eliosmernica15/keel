import { expect, test, type APIRequestContext } from "@playwright/test";
import { call, ok, unique } from "./helpers";

async function makeBot(request: APIRequestContext) {
  const created = await ok(request, "POST", "bots", {
    name: unique("capability-bot"),
    engine: "echo",
  });
  return created.bot.id as string;
}

test.describe("D — fleet tasks/routines/library and capabilities (REAL bridge)", () => {
  test("tasks: create/list/detail/events/update/assign/reorder/undo/cancel/delete", async ({ request }) => {
    const bot = await makeBot(request);
    const created = await call(request, "POST", "tasks", {
      title: unique("integration-task"),
      description: "verify the bridge task contract",
      priority: "high",
      assigned_bot_id: bot,
    });
    expect(created.status).toBe(201);
    const id = created.body.task.id;

    const listed = await ok(request, "GET", "tasks");
    expect(listed.tasks.some((t: any) => t.id === id)).toBe(true);
    const detail = await ok(request, "GET", `tasks/${id}`);
    expect(detail.task.id).toBe(id);
    const events = await ok(request, "GET", `tasks/${id}/events`);
    expect(events.task_id).toBe(id);
    expect(Array.isArray(events.events)).toBe(true);

    const updated = await ok(request, "POST", `tasks/${id}/update`, {
      status: "in_progress",
      progress: 25,
      note: "integration note",
    });
    expect(updated.task.status).toBe("in_progress");
    const assigned = await ok(request, "POST", `tasks/${id}/assign`, { assigned_bot_id: null });
    expect(assigned.task.id).toBe(id);
    const reordered = await ok(request, "POST", "tasks/reorder", { ids: [id] });
    expect(Array.isArray(reordered.tasks)).toBe(true);
    const undone = await ok(request, "POST", `tasks/${id}/undo`);
    expect(undone.task.id).toBe(id);
    const cancelled = await ok(request, "POST", `tasks/${id}/cancel`);
    expect(cancelled.task.status).toBe("cancelled");
    const deleted = await ok(request, "POST", `tasks/${id}/delete`);
    expect(deleted.deleted).toBe(true);
  });

  test("routines: create/list/detail/runs/update/enable/pause/run conflict/delete", async ({ request }) => {
    const bot = await makeBot(request);
    const created = await call(request, "POST", "routines", {
      name: unique("integration-routine"),
      bot_id: bot,
      prompt: "Say hello",
      cron_expr: "0 9 * * *",
      timezone: "UTC",
      enabled: true,
    });
    expect(created.status).toBe(201);
    const id = created.body.routine.id;

    const listed = await ok(request, "GET", "routines");
    expect(listed.routines.some((r: any) => r.id === id)).toBe(true);
    const detail = await ok(request, "GET", `routines/${id}`);
    expect(detail.routine.id).toBe(id);
    const runs = await ok(request, "GET", `routines/${id}/runs`);
    expect(runs.routine_id).toBe(id);

    const updated = await ok(request, "POST", `routines/${id}/update`, { prompt: "Updated prompt" });
    expect(updated.routine.prompt).toBe("Updated prompt");
    await ok(request, "POST", `routines/${id}/disable`);
    const disabledRun = await call(request, "POST", `routines/${id}/run`);
    expect(disabledRun.status).toBe(409);
    expect(disabledRun.body.error).toMatch(/disabled/);
    await ok(request, "POST", `routines/${id}/enable`);
    await ok(request, "POST", `routines/${id}/pause`, { reason: "integration" });
    const pausedRun = await call(request, "POST", `routines/${id}/run`);
    expect(pausedRun.status).toBe(409);
    expect(pausedRun.body.error).toMatch(/paused/);
    await ok(request, "POST", `routines/${id}/resume`);

    const deleted = await ok(request, "POST", `routines/${id}/delete`);
    expect(deleted.deleted).toBe(true);
  });

  test("library: upload (base64), list, detail, download, preview, delete", async ({ request }) => {
    const bot = await makeBot(request);
    const payload = {
      filename: "bridge-note.txt",
      bot_id: bot,
      mime: "text/plain",
      content_base64: Buffer.from("bridge-library-content").toString("base64"),
    };
    const uploaded = await call(request, "POST", "library", payload);
    expect(uploaded.status).toBe(201);
    const id = uploaded.body.file.id;

    const listed = await ok(request, "GET", "library");
    expect(listed.files.some((f: any) => f.id === id)).toBe(true);
    const detail = await ok(request, "GET", `library/${id}`);
    expect(detail.file.id).toBe(id);

    const download = await request.fetch(`${"http://127.0.0.1:3311"}/api/bridge/library/${id}/download`, {
      failOnStatusCode: false,
    });
    expect(download.status()).toBe(200);
    expect(await download.text()).toBe("bridge-library-content");
    const preview = await request.fetch(`${"http://127.0.0.1:3311"}/api/bridge/library/${id}/preview`, {
      failOnStatusCode: false,
    });
    expect(preview.status()).toBe(200);

    const deleted = await ok(request, "POST", `library/${id}/delete`);
    expect(deleted.deleted).toBe(true);
  });

  test("providers: list/catalog/hint-only credential contract and validation errors", async ({ request }) => {
    const providers = await ok(request, "GET", "providers");
    expect(Array.isArray(providers.providers)).toBe(true);
    expect(Array.isArray(providers.session_keys)).toBe(true);

    const name = providers.providers[0]?.name ?? "anthropic";
    const catalog = await call(request, "POST", "providers/catalog", {
      name,
      source: "offline",
    });
    expect(catalog.status).toBe(200);
    expect(Array.isArray(catalog.body.models)).toBe(true);
    expect(catalog.body.source).toBe("offline");

    const unknown = await call(request, "POST", "providers/credential", {
      name: "not_a_real_provider_xyz",
      key: "throwaway-key",
    });
    expect(unknown.status).toBe(400);
    expect(unknown.body.error).toBe("unknown_provider");
    expect(unknown.text).not.toContain("throwaway-key");

    const badKey = await call(request, "POST", "providers/save", { name, key: "" });
    expect(badKey.status).toBe(400);
    expect(badKey.body.error).toBe("bad_key");

    const cleared = await call(request, "POST", "providers/credential/clear", {
      name: "not_a_real_provider_xyz",
    });
    expect(cleared.status).toBe(200);
    const removed = await call(request, "POST", "providers/remove", {
      name: "not_a_real_provider_xyz",
    });
    expect(removed.status).toBe(200);
    expect(removed.body.error).toBe("not_saved");
  });

  test("skills/MCP/connectors/commands/workflows/settings system endpoints", async ({ request }) => {
    const skills = await ok(request, "GET", "skills");
    expect(Array.isArray(skills.skills)).toBe(true);
    const managed = await ok(request, "GET", "skills/manage");
    expect(Array.isArray(managed.skills)).toBe(true);
    const badInstall = await call(request, "POST", "skills/install", {});
    expect(badInstall.status).toBe(400);
    const badRemove = await call(request, "POST", "skills/remove", {});
    expect(badRemove.status).toBe(400);
    const badEnable = await call(request, "POST", "skills/enable", {});
    expect(badEnable.status).toBe(400);

    const servers = await ok(request, "GET", "mcp/servers");
    expect(Array.isArray(servers.servers)).toBe(true);
    const health = await ok(request, "POST", "mcp/health");
    // NOTE: UI-BACKEND-CONTRACT.md:52 claims `{health:[...]}`; the real bridge
    // returns a name->bool map (mcp.py:385 `health_all() -> dict[str, bool]`).
    // Assert what the authoritative runtime actually returns.
    expect(health.health).toBeTruthy();
    expect(typeof health.health).toBe("object");
    expect(Array.isArray(health.health)).toBe(false);

    const connectors = await call(request, "GET", "connectors");
    expect(connectors.status).toBe(200);
    const unknownConnector = await call(request, "POST", "connectors/test", { name: "missing-connector" });
    expect(unknownConnector.status).toBe(404);
    // Validation-only probes: no settings are written by these calls.
    const badAdd = await call(request, "POST", "connectors/add", { name: "", command: "" });
    expect([200, 400]).toContain(badAdd.status);
    const missingRemove = await call(request, "POST", "connectors/remove", { name: "missing-connector" });
    expect(missingRemove.status).toBe(200);

    const commands = await ok(request, "GET", "commands");
    expect(Array.isArray(commands.commands)).toBe(true);
    const missingCommand = await call(request, "POST", "commands/execute", { name: "missing-command" });
    expect(missingCommand.status).toBe(404);
    const workflows = await ok(request, "GET", "workflows");
    expect(Array.isArray(workflows.workflows)).toBe(true);
    const missingWorkflow = await call(request, "POST", "workflows/execute", { name: "missing-workflow" });
    expect(missingWorkflow.status).toBe(404);

    const usage = await ok(request, "GET", "usage");
    expect(usage.usage).toBeTruthy();
    const awake = await ok(request, "GET", "keep-awake");
    expect(awake !== undefined).toBe(true);
    const setAwake = await ok(request, "POST", "keep-awake", { on: false });
    expect(setAwake !== undefined).toBe(true);
  });
});
