/* Route/config checks for removing the public /app page and pointing CTAs at
 * /login. The QA server is the real serve_keel_site.mjs.
 * Run: node --test keel/site/tests/auth-routes.test.mjs
 */
import test, { before, after } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import net from "node:net";
import { spawn } from "node:child_process";
import { fileURLToPath } from "node:url";

const SITE = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const REPO = path.resolve(SITE, "..", "..");
const SERVER = path.join(REPO, "serve_keel_site.mjs");
const read = (relative) => fs.readFileSync(path.join(SITE, relative), "utf8");
const vercel = JSON.parse(read("vercel.json"));

// app.html and the Electron mirror renderer stay on disk for the explicit
// local KEEL_UI_PROFILE=mirror diagnostic; they are not public pages.
const LOCAL_ONLY = new Set(["app.html", path.join("ui", "app.js"), path.join("ui", "management.js")]);

function publicSiteFiles() {
  const files = [];
  function walk(directory) {
    for (const entry of fs.readdirSync(directory, { withFileTypes: true })) {
      const absolute = path.join(directory, entry.name);
      const relative = path.relative(SITE, absolute).split(path.sep).join("/");
      if (entry.isDirectory()) {
        if (relative !== "tests" && relative !== "screenshots" && relative !== "store-assets") walk(absolute);
      } else if (/\.(html|js)$/.test(entry.name) && !LOCAL_ONLY.has(relative)) {
        files.push(relative);
      }
    }
  }
  walk(SITE);
  return files;
}

test("no app rewrite, header or redirect remains in vercel.json", () => {
  for (const route of vercel.rewrites) {
    assert.ok(!/^\/app\/?$/.test(route.source), `rewrite still exposes ${route.source}`);
    assert.notEqual(route.destination, "/app.html");
  }
  for (const rule of vercel.redirects) {
    assert.ok(!/^\/app(\.html)?$/.test(rule.source), `redirect still exposes ${rule.source}`);
  }
  for (const rule of vercel.headers) {
    assert.ok(!/^\/app\/?$/.test(rule.source), `header still exposes ${rule.source}`);
  }
  assert.ok(vercel.rewrites.some((r) => r.source === "/login" && r.destination === "/login.html"));
  assert.ok(vercel.rewrites.some((r) => r.source === "/new" && r.destination === "/new.html"));
});

test("the public sitemap does not list /app", () => {
  const xml = read("sitemap.xml");
  assert.ok(!xml.includes("/app<"), "sitemap still lists /app");
  assert.match(xml, /<loc>https:\/\/keel-desktop\.vercel\.app\/login<\/loc>/);
});

test("app.html is excluded from the Vercel upload", () => {
  const lines = fs.readFileSync(path.join(REPO, ".vercelignore"), "utf8")
    .split(/\r?\n/).map((line) => line.trim());
  assert.ok(lines.includes("keel/site/app.html"), "missing .vercelignore entry");
  assert.match(read("app.html"), /LOCAL-ONLY DIAGNOSTIC/);
});

test("no public HTML or JS links to /app", () => {
  const quoted = /["']\/app(?:\/|\.html)?["']/g;
  const absolute = /vercel\.app\/app\b/g;
  const prose = /\bto \/app\b/g;
  const offenders = [];
  for (const file of publicSiteFiles()) {
    const source = fs.readFileSync(path.join(SITE, file), "utf8");
    for (const pattern of [quoted, absolute, prose]) {
      pattern.lastIndex = 0;
      const match = source.match(pattern);
      if (match) offenders.push(`${file}: ${match.slice(0, 3).join(", ")}`);
    }
  }
  assert.deepEqual(offenders, [], `public /app links remain:\n${offenders.join("\n")}`);
});

test("landing CTAs route to /login, and signed-in visitors are forwarded to /new", () => {
  const landing = read("ui/landing.js");
  assert.match(landing, /\/login\?intent=/);
  const auth = read("ui/auth.js");
  assert.match(auth, /if \(existing\) \{\s*root\.location\.replace\(destination\(query\.get\('next'\)\)\);/);
  assert.match(auth, /var base = fallback &&[\s\S]*DEFAULT_NEXT/);
  const login = read("login.html");
  assert.match(login, /auth-tab-signup/);
  assert.match(login, /auth-tab-reset/);
});

let serverProcess;
let base;

async function freePort() {
  const probe = net.createServer();
  await new Promise((resolve) => probe.listen(0, "127.0.0.1", resolve));
  const port = probe.address().port;
  await new Promise((resolve) => probe.close(resolve));
  return port;
}

before(async () => {
  const port = await freePort();
  let output = "";
  serverProcess = spawn(process.execPath, [SERVER], {
    cwd: REPO,
    env: { ...process.env, PORT: String(port) },
    stdio: ["ignore", "pipe", "pipe"]
  });
  serverProcess.stdout.on("data", (chunk) => { output += String(chunk); });
  serverProcess.stderr.on("data", (chunk) => { output += String(chunk); });
  const deadline = Date.now() + 10000;
  while (!output.includes("Keel QA server") && Date.now() < deadline) {
    await new Promise((resolve) => setTimeout(resolve, 25));
    if (serverProcess.exitCode !== null) break;
  }
  assert.match(output, /Keel QA server/, "QA server did not start");
  base = `http://127.0.0.1:${port}`;
});

after(async () => {
  if (serverProcess && serverProcess.exitCode === null) {
    serverProcess.kill();
    await new Promise((resolve) => serverProcess.once("exit", resolve));
  }
});

test("QA server no longer resolves /app but still serves the local diagnostic file", async () => {
  const removed = await fetch(base + "/app");
  assert.equal(removed.status, 404, "/app must not be routable locally");
  const removedSlash = await fetch(base + "/app/");
  assert.equal(removedSlash.status, 404, "/app/ must not be routable locally");
  const local = await fetch(base + "/app.html");
  assert.equal(local.status, 200, "app.html remains available for the local mirror diagnostic");
  const login = await fetch(base + "/login");
  assert.equal(login.status, 200);
  assert.match(await login.text(), /data-auth-tab="signin"/);
  const next = await fetch(base + "/new");
  assert.equal(next.status, 200);
  assert.match(await next.text(), /data-auth-gate="new"/);
});
