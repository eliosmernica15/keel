/**
 * Runtime verification of the traced standalone server.
 *
 *    npm run verify:standalone
 *
 * Starts a throwaway loopback "bridge", launches the built server with dummy
 * runtime credentials, checks hydration shell / CSP / PWA assets / BFF proxy,
 * then relaunches the *same artifact* without credentials to prove env is read
 * at runtime rather than frozen into the build.
 */
import { spawn } from "node:child_process";
import http from "node:http";
import net from "node:net";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

const appDir = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const distDir = path.resolve(appDir, process.env.KEEL_DIST_DIR || ".next");
const server = path.join(distDir, "standalone", "server.js");
const results = [];
function assert(name, ok, detail = "") {
  results.push({ name, pass: Boolean(ok), detail: String(detail) });
  console.log(`${ok ? "PASS" : "FAIL"}  ${name}${detail ? ` — ${detail}` : ""}`);
}
async function freePort() {
  return new Promise((resolve, reject) => {
    const s = net.createServer();
    s.on("error", reject);
    s.listen(0, "127.0.0.1", () => {
      const { port } = s.address();
      s.close(() => resolve(port));
    });
  });
}
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function waitReady(port, child) {
  for (let i = 0; i < 80; i++) {
    if (child.exitCode !== null) throw new Error(`server exited early (${child.exitCode})`);
    try {
      const r = await fetch(`http://127.0.0.1:${port}/`, { signal: AbortSignal.timeout(1000) });
      if (r.status === 200) {
        await r.arrayBuffer();
        return;
      }
    } catch {
      /* not listening yet */
    }
    await sleep(250);
  }
  throw new Error("server did not become ready within 20s");
}
function launch(port, envOverrides) {
  const env = { ...process.env, ...envOverrides, PORT: String(port) };
  for (const k of Object.keys(envOverrides)) {
    if (envOverrides[k] === undefined) delete env[k];
  }
  const child = spawn(process.execPath, [server], {
    cwd: path.dirname(server),
    env,
    stdio: ["ignore", "pipe", "pipe"],
  });
  let log = "";
  child.stdout.on("data", (d) => (log += d));
  child.stderr.on("data", (d) => (log += d));
  return { child, get log() { return log; } };
}
async function stop(entry) {
  if (!entry?.child || entry.child.exitCode !== null) return;
  entry.child.kill("SIGTERM");
  for (let i = 0; i < 20 && entry.child.exitCode === null; i++) await sleep(100);
  if (entry.child.exitCode === null) entry.child.kill("SIGKILL");
}

// Dummy bridge: echoes the injected token and path so the BFF hop is proven.
const DUMMY_TOKEN = "runtime-token-alpha-9f3c";
const bridge = http.createServer((req, res) => {
  if (req.url?.startsWith("/api/fleet/events")) {
    res.writeHead(200, { "Content-Type": "text/event-stream", "Cache-Control": "no-cache" });
    res.end("data: ok\n\n");
    return;
  }
  const body = JSON.stringify({
    ok: true,
    tokenSeen: req.headers["x-keel-token"] ?? null,
    pathSeen: req.url,
  });
  res.writeHead(200, { "Content-Type": "application/json" });
  res.end(body);
});
await new Promise((resolve) => bridge.listen(0, "127.0.0.1", resolve));
const bridgePort = bridge.address().port;

let phase1;
let phase2;
try {
  const port1 = await freePort();
  // HOSTNAME is deliberately set to 0.0.0.0: the hardened artifact must
  // ignore it and still bind loopback only.
  phase1 = launch(port1, {
    HOSTNAME: "0.0.0.0",
    KEEL_BRIDGE_URL: `http://127.0.0.1:${bridgePort}`,
    KEEL_BRIDGE_TOKEN: DUMMY_TOKEN,
  });
  await waitReady(port1, phase1.child);
  const base1 = `http://127.0.0.1:${port1}`;

  const page = await fetch(`${base1}/`);
  const html = await page.text();
  assert("GET / returns 200", page.status === 200, `HTTP ${page.status}`);
  assert("React shell + bootstrap chunks", html.includes("/_next/static/") && html.includes("Keel"), "HTML contains Next chunks and app title");
  assert("manifest link in document", html.includes("/manifest.webmanifest"), "layout.tsx link preserved");
  const csp = page.headers.get("content-security-policy") ?? "";
  assert("production CSP present, no unsafe-eval", csp.includes("default-src 'self'") && !csp.includes("unsafe-eval"), csp);
  assert("nosniff / no-referrer headers", page.headers.get("x-content-type-options") === "nosniff" && page.headers.get("referrer-policy") === "no-referrer", "both set");
  assert("poweredByHeader disabled", page.headers.get("x-powered-by") === null, "no X-Powered-By");

  const manifestRes = await fetch(`${base1}/manifest.webmanifest`);
  const manifest = await manifestRes.json();
  assert("PWA manifest route works", manifestRes.status === 200 && manifest.name === "Keel" && manifest.display === "standalone", `HTTP ${manifestRes.status}`);
  assert("PWA icons in manifest", manifest.icons?.some((i) => i.src === "/icon-512.png"), "icon-512.png present");

  const swRes = await fetch(`${base1}/sw.js`);
  const sw = await swRes.text();
  assert("service worker served", swRes.status === 200 && sw.includes("keel-shell-v3"), `HTTP ${swRes.status}`);
  assert("service worker never caches /api/", sw.includes('url.pathname.startsWith("/api/")'), "API bypass verified");

  for (const asset of ["/icon.svg", "/icon-192.png", "/icon-512.png", "/fonts/inter-400.woff2"]) {
    const r = await fetch(`${base1}${asset}`);
    assert(`public asset ${asset}`, r.status === 200, `HTTP ${r.status}, ${r.headers.get("content-type")}`);
  }

  const bff = await fetch(`${base1}/api/bridge/providers?x=1`);
  const bffBody = await bff.json();
  assert("BFF route is a live server handler", bff.status === 200, `HTTP ${bff.status}`);
  assert("BFF injects RUNTIME token from env", bffBody.tokenSeen === DUMMY_TOKEN, `upstream saw tokenSeen=${bffBody.tokenSeen === DUMMY_TOKEN ? "expected dummy token" : "<unexpected>"}`);
  assert("BFF rewrites to bridge path", bffBody.pathSeen === "/api/fleet/providers?x=1", String(bffBody.pathSeen));

  const sse = await fetch(`${base1}/api/bridge/events`);
  const sseText = await sse.text();
  assert("BFF SSE path works", sse.status === 200 && sseText.includes("data: ok") && (sse.headers.get("content-type") || "").includes("text/event-stream"), `HTTP ${sse.status}`);

  assert("server logs loopback bind", phase1.log.includes(`127.0.0.1:${port1}`) && !phase1.log.includes("0.0.0.0"), "log shows 127.0.0.1 only");
  const lan = Object.values(os.networkInterfaces())
    .flat()
    .find((i) => i && i.family === "IPv4" && !i.internal);
  if (lan) {
    let externallyReachable = false;
    try {
      const r = await fetch(`http://${lan.address}:${port1}/`, { signal: AbortSignal.timeout(1500) });
      await r.arrayBuffer();
      externallyReachable = true;
    } catch {
      /* expected: loopback only */
    }
    assert("not reachable via LAN address", !externallyReachable, `${lan.address}:${port1}`);
  } else {
    console.log("SKIP  LAN bind probe — no non-loopback IPv4 interface");
  }

  await stop(phase1);
  phase1 = undefined;

  // Same artifact, no runtime credentials: must refuse, not use build values.
  const port2 = await freePort();
  phase2 = launch(port2, { KEEL_BRIDGE_URL: "", KEEL_BRIDGE_TOKEN: "" });
  await waitReady(port2, phase2.child);
  const denied = await fetch(`http://127.0.0.1:${port2}/api/bridge/providers`);
  const deniedBody = await denied.json();
  assert(
    "no-credential server returns bridge_unavailable",
    denied.status === 502 && deniedBody.error === "bridge_unavailable",
    `HTTP ${denied.status}, error=${deniedBody.error}`,
  );
} finally {
  await stop(phase1);
  await stop(phase2);
  await new Promise((resolve) => bridge.close(resolve));
}

const failed = results.filter((r) => !r.pass);
console.log(`\n${results.length - failed.length}/${results.length} runtime checks passed`);
if (failed.length) process.exit(1);
