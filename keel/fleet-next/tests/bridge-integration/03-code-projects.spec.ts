import { execFileSync } from "child_process";
import fs from "fs";
import path from "path";
import { expect, test, type APIRequestContext } from "@playwright/test";
import { call, ok, unique, WORKSPACE_DIR } from "./helpers";

async function makeProject(request: APIRequestContext) {
  const dir = path.join(WORKSPACE_DIR, unique("project"));
  fs.mkdirSync(dir, { recursive: true });
  const created = await call(request, "POST", "projects", {
    path: dir,
    name: "bridge-integration-project",
  });
  expect(created.status).toBe(201);
  const id = created.body.project.id as string;
  return { id, dir };
}

test.describe("C — code/projects: tree, files, review, terminal (REAL bridge)", () => {
  test("projects: create/list/trust gate/tree/file write+read/open/model/chat/remove", async ({ request }) => {
    const { id, dir } = await makeProject(request);

    const projects = await ok(request, "GET", "projects");
    expect(projects.projects.some((p: any) => p.id === id)).toBe(true);

    // Trust is explicit and revocable: reads are refused until trusted.
    const untrusted = await call(request, "GET", `projects/${id}/tree`);
    expect(untrusted.status).toBe(403);
    expect(untrusted.body.error).toBe("workspace_not_trusted");

    const trusted = await ok(request, "POST", `projects/${id}/trust`, { trusted: true });
    // SQLite stores 1; the contract only promises truthiness after trust.
    expect(Boolean(trusted.project.trusted)).toBe(true);

    const tree = await ok(request, "GET", `projects/${id}/tree`);
    expect(Array.isArray(tree.entries)).toBe(true);

    const written = await ok(request, "POST", `projects/${id}/file/write`, {
      path: "src/bridge.txt",
      content: "bridge-integration-file-content",
    });
    expect(written.ok).toBe(true);
    expect(fs.readFileSync(path.join(dir, "src", "bridge.txt"), "utf8")).toBe(
      "bridge-integration-file-content",
    );

    const read = await ok(
      request,
      "GET",
      `projects/${id}/file/read?path=${encodeURIComponent("src/bridge.txt")}`,
    );
    expect(read.path).toBe("src/bridge.txt");
    expect(read.content).toBe("bridge-integration-file-content");
    expect(read.binary).toBe(false);

    const escape = await call(
      request,
      "GET",
      `projects/${id}/file/read?path=${encodeURIComponent("../../Windows/win.ini")}`,
    );
    expect([400, 404]).toContain(escape.status);

    const opened = await ok(request, "POST", `projects/${id}/open`);
    expect(opened.project.id).toBe(id);
    const modeled = await ok(request, "POST", `projects/${id}/model`, { model: "bridge-model" });
    expect(modeled.project.model).toBe("bridge-model");
    const chat = await ok(request, "POST", `projects/${id}/chat`);
    expect(chat.bot.id).toBeTruthy();

    const removed = await ok(request, "POST", `projects/${id}/remove`);
    expect(removed.removed).toBe(true);
  });

  test("review: read-only git text from a trusted workspace", async ({ request }) => {
    const { id, dir } = await makeProject(request);
    execFileSync("git", ["init", "-q"], { cwd: dir });

    const beforeTrust = await call(request, "GET", `projects/${id}/review`);
    expect(beforeTrust.status).toBe(403);
    await ok(request, "POST", `projects/${id}/trust`, { trusted: true });

    const review = await ok(request, "GET", `projects/${id}/review`);
    expect(review.is_git).toBe(true);
    expect(typeof review.status).toBe("string");
    expect(typeof review.log).toBe("string");
    expect(typeof review.diff_stat).toBe("string");
  });

  test("terminal: real handle + output polling, shells listing, kill and clear", async ({ request }) => {
    const { id } = await makeProject(request);
    await ok(request, "POST", `projects/${id}/trust`, { trusted: true });

    const started = await call(request, "POST", `projects/${id}/terminal/exec`, {
      command: "echo bridge-terminal-ok",
    });
    expect(started.status).toBe(202);
    expect(started.body.handle).toBeTruthy();
    expect(typeof started.body.pid).toBe("number");

    const handle = started.body.handle as string;
    await expect.poll(async () => {
      const out = await ok(request, "GET", `shells/${handle}/output`);
      return out.running === false && String(out.output).includes("bridge-terminal-ok");
    }, { timeout: 15_000 }).toBe(true);

    const shells = await ok(request, "GET", "shells");
    expect(Array.isArray(shells.shells)).toBe(true);
    expect(typeof shells.running).toBe("number");

    const killed = await ok(request, "POST", `shells/${handle}/kill`);
    expect(killed.ok).toBe(true);

    // The bridge exposes this as GET (routes.py:528); lib/api.ts uses GET too.
    const cleared = await ok(request, "GET", "shells/clear/finished");
    expect(typeof cleared.cleared).toBe("number");
  });

  test("untrusted terminal execution is refused", async ({ request }) => {
    const { id } = await makeProject(request);
    const result = await call(request, "POST", `projects/${id}/terminal/exec`, { command: "echo nope" });
    expect(result.status).toBe(403);
    expect(result.body.error).toBe("workspace_not_trusted");
  });
});
