/* Keel Desktop — Electron shell.
   Spawns the keel sidecar (Python bridge on 127.0.0.1), waits for its
   printed URL line on stderr, then loads it in a framed BrowserWindow.
   Fully offline/self-contained: no network calls beyond 127.0.0.1 and the
   provider the user configures. */
import { app, BrowserWindow, shell, Menu } from "electron";
import { spawn, execFileSync } from "child_process";
import { randomBytes } from "crypto";
import { join, dirname } from "path";
import { existsSync, createWriteStream, writeFileSync } from "fs";
import http from "http";
import net from "net";
import { fileURLToPath } from "url";
// Agent F owns this module. Contract:
//   resolveRenderer({ resourcesPath, env }) ->
//     { mode: "unified"|"legacy"|"mirror", uiDir: string|null, reason: string }
import { resolveRenderer } from "./renderer-policy.js";

const __dirname = dirname(fileURLToPath(import.meta.url));

let mainWindow = null;
let splash = null;
let failureWindow = null;
let sidecar = null;
let uiServer = null;
let sidecarPort = 0;
let sidecarToken = "";
let quitting = false;
let shuttingDown = false;
let uiExitNotified = false;

const LOG = () => join(app.getPath("userData"), "sidecar.log");
const UI_LOG = () => join(app.getPath("userData"), "ui-server.log");

function readyTimeoutMs() {
  const raw = Number(process.env.KEEL_RENDERER_READY_TIMEOUT_MS);
  return Number.isFinite(raw) && raw > 0 ? Math.floor(raw) : 30000;
}

// Diagnostics only. Never write a token value to a log; at most its length
// and a four-character prefix, as required by the integration contract.
function appendLog(file, line) {
  try {
    createWriteStream(file, { flags: "a" }).end(`${line}\n`);
  } catch {
    /* logging must never break startup */
  }
}

// Single place that stops a spawned child. Every exit path must go through
// here: window close, before-quit, and the startup-failure path (which can
// close the app without emitting before-quit).
function stopChild(proc) {
  if (!proc) return;
  if (proc.exitCode !== null || proc.signalCode !== null) return;
  try {
    if (process.platform === "win32") {
      // The PyInstaller one-file sidecar launches a child process that owns
      // the listening socket. TerminateProcess (what proc.kill() does on
      // Windows) only kills the bootloader and leaves that child orphaned —
      // this is what previously kept keel.exe holding the built artifact
      // open. /T walks the whole tree; /F forces it. The same applies to the
      // Fleet Next server, which can spawn its own worker processes.
      execFileSync("taskkill", ["/PID", String(proc.pid), "/T", "/F"],
                   { stdio: "ignore", windowsHide: true, timeout: 5000 });
    } else {
      proc.kill("SIGTERM");
    }
  } catch {
    try { proc.kill(); } catch { /* already gone */ }
  }
}

function stopSidecar() {
  if (!sidecar) return;
  const proc = sidecar;
  sidecar = null;
  stopChild(proc);
}

function stopUiServer() {
  if (!uiServer) return;
  const proc = uiServer;
  uiServer = null;
  stopChild(proc);
}

function stopAllChildren() {
  // Mark shutdown first so child "exit" listeners do not mistake an
  // intentional teardown for a crash and pop up a second error dialog.
  shuttingDown = true;
  // Stop the bridge first so the UI server cannot keep issuing requests to a
  // dying upstream, then tear down the UI server. Both are idempotent.
  stopSidecar();
  stopUiServer();
}

function bundledSidecar() {
  const res = process.resourcesPath;
  const candidates = [
    join(res, "keel", "keel.exe"),
    join(res, "keel", "keel"),
    join(res, "sidecar", "keel.exe"),
    join(res, "sidecar", "keel"),
  ];
  for (const c of candidates) if (existsSync(c)) return c;
  return null;
}

// The packaged desktop product MUST render the full local UI (desktop/ui),
// not the restricted browser-only mirror (site/app.html). The mirror is kept
// only as an explicit rollback/diagnostic path:
//   KEEL_UI_PROFILE=mirror  -> force resources/site (legacy behaviour)
//   KEEL_UI_DIR=<dir>       -> explicit override (advanced; must have index.html)
// Returning null is intentional: it lets the frozen sidecar serve the
// desktop/ui it bundles itself (sidecar.spec:29) when no local root is shipped.
function uiRoot() {
  const res = process.resourcesPath;
  const explicit = process.env.KEEL_UI_DIR;
  if (explicit && existsSync(join(explicit, "index.html"))) return explicit;
  if (String(process.env.KEEL_UI_PROFILE || "").toLowerCase() === "mirror") {
    const mirror = join(res, "site");
    if (existsSync(join(mirror, "index.html"))) return mirror;
  }
  const candidates = [
    join(res, "desktop", "ui"), // full local UI (shipped in production)
    join(res, "ui"),            // legacy local layout
  ];
  for (const c of candidates) if (existsSync(join(c, "index.html"))) return c;
  return null;
}

async function waitForSidecarUrl(proc, ms = 30000) {
  return new Promise((resolve, reject) => {
    let buf = "";
    let settled = false;
    const timer = setTimeout(() => fail(new Error("sidecar did not print its URL within 30s")), ms);

    // Remove only our own listeners. removeAllListeners("data") would also
    // detach the pipe(log) stream installed in startSidecar(), silencing the
    // diagnostic log for the rest of the session.
    function cleanup() {
      clearTimeout(timer);
      proc.stdout.removeListener("data", onData);
      proc.stderr.removeListener("data", onData);
      proc.removeListener("error", onError);
      proc.removeListener("exit", onExit);
    }
    function fail(err) {
      if (settled) return;
      settled = true;
      cleanup();
      reject(err);
    }
    function onData(chunk) {
      buf += chunk.toString();
      const m = buf.match(/keel webapp running at (\S+)/);
      if (!m) return;
      let url;
      try {
        url = new URL(m[1]); // accepts any token charset; validates loopback + token
        if (url.protocol !== "http:" || url.hostname !== "127.0.0.1") throw new Error("bad url");
        if (!url.searchParams.get("t")) throw new Error("missing token");
      } catch {
        fail(new Error(`sidecar printed an invalid URL: ${m[1]}`));
        return;
      }
      if (settled) return;
      settled = true;
      cleanup();
      resolve(m[1]); // preserve the exact token string from the bridge
    }
    function onError(err) { fail(err); }
    function onExit(code) { fail(new Error(`sidecar exited early (code ${code})`)); }

    proc.stdout.on("data", onData);
    proc.stderr.on("data", onData);
    proc.on("error", onError);
    proc.on("exit", onExit);
  });
}

// `uiDir` comes from renderer-policy.js and is non-null only for legacy /
// mirror. Unified mode passes null: the standalone Next app owns `/`, and the
// sidecar is used purely as the API bridge.
function startSidecar(uiDir) {
  sidecarToken = randomBytes(18).toString("base64url");
  const env = {
    ...process.env,
    KEEL_TOKEN: sidecarToken,
    KEEL_NO_BANNER: "1",
  };

  const bin = bundledSidecar();
  let cmd, args;
  if (bin) {
    // production: bundled PyInstaller binary, fully self-contained
    env.KEEL_UI_DIR = uiDir || undefined;
    cmd = bin;
    args = ["serve", "--port", "0"];
  } else if (process.env.KEEL_SIDE_CAR) {
    // developer override: path to a keel.py bundle. `undefined` removes the
    // variable entirely; null would be stringified to "null" by spawn().
    env.KEEL_UI_DIR = uiDir || undefined;
    cmd = process.env.KEEL_SIDE_CAR;
    args = ["serve", "--port", "0"];
  } else {
    // day-to-day development: system Python running the repo
    const repoRoot = join(
      process.env.KEEL_REPO || join(process.cwd(), ".."),
    );
    env.PYTHONPATH = join(repoRoot, "src");
    env.KEEL_UI_DIR = uiDir || join(repoRoot, "desktop", "ui");
    cmd = process.env.KEEL_PYTHON || "python";
    args = ["-m", "keel", "serve", "--port", "0"];
  }

  // tee stderr/stdout into userData for diagnosis
  try {
    const log = createWriteStream(LOG(), { flags: "a" });
    env.PYTHONIOENCODING = "utf-8";
    sidecar = spawn(cmd, args, { env, stdio: ["ignore", "pipe", "pipe"], windowsHide: true });
    sidecar.stdout.pipe(log);
    sidecar.stderr.pipe(log);
  } catch (err) {
    throw new Error(`failed to spawn sidecar: ${err.message}`);
  }
  // --port 0: the bridge binds an ephemeral loopback port and prints the real
  // one, which waitForSidecarUrl already parses. No choose/bind race.
  return waitForSidecarUrl(sidecar, readyTimeoutMs());
}

// ---------------------------------------------------------------------------
// Unified renderer host: packaged Fleet Next standalone server.
// The sidecar stays the only credential holder; its token is handed to the
// Next process through the environment and injected by its BFF. Electron only
// ever loads a token-free loopback URL, so no credential can reach the loaded
// HTML/JS or localStorage.
// ---------------------------------------------------------------------------

// Ask the OS for a free loopback port instead of guessing one. The socket is
// released before the child binds it; the readiness probe below confirms the
// child actually owns the port before any window is opened.
function reserveLoopbackPort() {
  return new Promise((resolve, reject) => {
    const server = net.createServer();
    server.once("error", reject);
    server.listen(0, "127.0.0.1", () => {
      const address = server.address();
      const port = address && typeof address === "object" ? address.port : 0;
      server.close(() => resolve(port));
    });
  });
}

function fleetNextRuntimeDir(uiDir) {
  const candidates = [
    process.env.KEEL_RENDERER_UNIFIED_DIR, // contract §4.2 diagnostic override
    uiDir,                                 // from renderer-policy.js
    join(process.resourcesPath, "fleet-next"),
  ];
  for (const dir of candidates) {
    if (typeof dir === "string" && dir && existsSync(join(dir, "server.js"))) {
      return dir;
    }
  }
  return null;
}

// No system Node is shipped with the packaged app. The Electron executable
// becomes a plain Node host via ELECTRON_RUN_AS_NODE, set in the CHILD env
// only (contract §1.3).
function nodeExecutable() {
  return process.execPath;
}

function nextPort() {
  const raw = Number(process.env.KEEL_RENDERER_PORT);
  if (Number.isInteger(raw) && raw > 0 && raw < 65536) return raw;
  return null;
}

// Resolve only when the server really answers HTTP on the chosen port. A
// stdout "ready" line is captured for diagnostics but is not trusted on its
// own: a process can print it before the listener is up.
function waitForUiServer(proc, port, ms = 30000) {
  return new Promise((resolve, reject) => {
    let settled = false;
    let output = "";
    const url = `http://127.0.0.1:${port}/`;

    function cleanup() {
      clearTimeout(timer);
      clearInterval(poll);
      proc.stdout.removeListener("data", onData);
      proc.stderr.removeListener("data", onData);
      proc.removeListener("error", onError);
      proc.removeListener("exit", onExit);
    }
    function done(err) {
      if (settled) return;
      settled = true;
      cleanup();
      if (err) reject(err); else resolve(url);
    }
    function onData(chunk) {
      output += chunk.toString();
      if (output.length > 8000) output = output.slice(-4000);
    }
    function onError(err) {
      done(new Error(`failed to start the Keel UI server: ${err.message}`));
    }
    function onExit(code, signal) {
      const tail = output.trim().slice(-300);
      done(new Error(`the Keel UI server exited before it was ready ` +
                     `(code ${code === null ? signal : code})` +
                     (tail ? `: ${tail}` : "")));
    }
    function probe() {
      if (settled) return;
      const req = http.get({ host: "127.0.0.1", port, path: "/", timeout: 1000 },
                           (res) => {
        res.resume();
        // 200 is the standalone server's real ready signal. A 404 here means
        // the wrong process owns the port or static chunks were not shipped.
        if (res.statusCode === 200) done(null);
      });
      req.on("timeout", () => req.destroy());
      req.on("error", () => { /* not listening yet — keep polling */ });
    }

    const timer = setTimeout(() => {
      const tail = output.trim().slice(-300);
      done(new Error(`the Keel UI server did not become ready within ${ms / 1000}s ` +
                     `on 127.0.0.1:${port}` + (tail ? `: ${tail}` : "")));
    }, ms);
    const poll = setInterval(probe, 100);

    proc.stdout.on("data", onData);
    proc.stderr.on("data", onData);
    proc.on("error", onError);
    proc.on("exit", onExit);
    probe();
  });
}

async function startUiServer(sidecarUrl, uiDir) {
  const parsed = new URL(sidecarUrl); // already validated by waitForSidecarUrl
  const token = parsed.searchParams.get("t") || "";
  if (!token) {
    throw new Error("the sidecar returned an unusable bridge token");
  }
  appendLog(UI_LOG(), `bridge token accepted: length=${token.length} prefix=${token.slice(0, 4)}…`);

  const runtimeDir = fleetNextRuntimeDir(uiDir);
  if (!runtimeDir) {
    throw new Error(
      "the Fleet Next standalone runtime is missing: expected server.js at " +
      join(process.resourcesPath, "fleet-next", "server.js"));
  }
  for (const required of [".next/static", "public"]) {
    if (!existsSync(join(runtimeDir, required))) {
      throw new Error(`the Fleet Next runtime is incomplete: missing ${required} in ${runtimeDir}`);
    }
  }

  const node = nodeExecutable();
  const script = join(runtimeDir, "server.js");
  const timeout = readyTimeoutMs();
  const maxAttempts = 2; // one retry for the reserve/release port race

  for (let attempt = 1; attempt <= maxAttempts; attempt += 1) {
    const port = nextPort() || await reserveLoopbackPort();
    const env = {
      ...process.env,
      // No token in the URL: the BFF injects it server-side as a header.
      KEEL_BRIDGE_URL: `http://127.0.0.1:${parsed.port}`,
      KEEL_BRIDGE_TOKEN: token,
      // Generated Next standalone server.js reads HOSTNAME (default 0.0.0.0),
      // not HOST. Setting HOST alone would expose the UI on all interfaces.
      HOSTNAME: "127.0.0.1",
      PORT: String(port),
      NODE_ENV: "production",
      NEXT_TELEMETRY_DISABLED: "1",
      ELECTRON_RUN_AS_NODE: "1", // CHILD env only — never in the main process
    };

    let proc;
    try {
      proc = spawn(node, [script], {
        env,
        cwd: runtimeDir,
        stdio: ["ignore", "pipe", "pipe"],
        windowsHide: true,
      });
    } catch (err) {
      throw new Error(`failed to spawn the Keel UI server (${node} ${script}): ${err.message}`);
    }
    uiServer = proc;

    try {
      const log = createWriteStream(UI_LOG(), { flags: "a" });
      proc.stdout.pipe(log);
      proc.stderr.pipe(log);
    } catch {
      // Losing the diagnostic log must never prevent the UI from starting.
    }
    // An unhandled spawn 'error' crashes the whole shell (main.js:207-209).
    const spawnError = (err) => {
      appendLog(UI_LOG(), `spawn error: ${err.name}`);
    };
    proc.on("error", spawnError);

    try {
      await waitForUiServer(proc, port, timeout);
    } catch (err) {
      proc.removeListener("error", spawnError);
      stopUiServer();
      const earlyExit = proc.exitCode !== null || proc.signalCode !== null;
      if (attempt < maxAttempts && earlyExit && !nextPort()) {
        appendLog(UI_LOG(), `UI server exited during startup on port ${port}; retrying once`);
        continue;
      }
      throw err;
    }
    proc.removeListener("error", spawnError);

    // A post-ready crash is reported honestly; it never silently falls back
    // to another renderer.
    proc.on("exit", (code, signal) => {
      if (shuttingDown || uiExitNotified) return;
      uiExitNotified = true;
      appendLog(UI_LOG(), `UI server exited after ready: ${code === null ? signal : code}`);
      if (!mainWindow) return;
      import("electron").then(({ dialog }) => {
        dialog.showErrorBox(
          "Keel interface stopped",
          "The Keel interface server stopped unexpectedly. Restart Keel to continue.");
      });
    });

    return `http://127.0.0.1:${port}/`;
  }
  throw new Error("the Keel UI server could not be started after two attempts");
}

function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, (ch) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[ch]));
}

// Branded, readable failure screen. Keeping the app alive until the user
// dismisses it guarantees we never leave a blank window behind.
async function showFailureScreen(err) {
  const message = String((err && err.message) || err || "Unknown error");
  const { dialog } = await import("electron");
  const file = join(app.getPath("userData"), "startup-failure.html");
  const html = `<!doctype html>
<html lang="en"><head><meta charset="utf-8" /><title>Keel — could not start</title>
<style>
  :root { color-scheme: dark; }
  * { margin: 0; padding: 0; box-sizing: border-box; }
  html, body { height: 100%; overflow: hidden; }
  body {
    font-family: "Segoe UI", system-ui, sans-serif;
    background: radial-gradient(1200px 700px at 50% -10%, #2a150c 0%, #080604 60%);
    color: #e8e0d4; display: grid; place-items: center; user-select: none;
  }
  .card { width: min(560px, 88vw); text-align: center; }
  .mark { width: 72px; height: 72px; display: block; margin: 0 auto 12px; }
  .mark path { stroke: #e07a4f; }
  h1 { font-size: 24px; font-weight: 600; }
  .sub { margin-top: 6px; font-size: 13px; color: #9a8f82; }
  .detail { margin-top: 18px; padding: 14px 16px; border: 1px solid rgba(224,122,79,.35);
    border-radius: 8px; background: rgba(8,6,4,.65); font: 12px/1.5 Consolas, monospace;
    color: #e8c3b1; text-align: left; white-space: pre-wrap; word-break: break-word;
    max-height: 180px; overflow: auto; }
  .note { margin-top: 18px; font-size: 12px; color: #6f655a; }
</style></head><body><div class="card">
  <svg class="mark" viewBox="0 0 48 48" fill="none" aria-label="Keel">
    <g stroke-width="3" stroke-linecap="round" stroke-linejoin="round">
      <path d="M20 3v9M20 28v9M3 20h9M28 20h9M8 8l6.5 6.5M25.5 25.5L32 32M32 8l-6.5 6.5M14.5 25.5L8 32" />
      <path d="M12 4.6l3.7 8M24.3 27.4l3.7 8M35.4 12l-8 3.7M12.6 24.3l-8 3.7M28 4.6l-3.7 8M15.7 27.4L12 35.4M35.4 28l-8-3.7M12.6 15.7l-8 3.7" stroke-width="2.4" />
    </g>
  </svg>
  <h1>Keel could not start</h1>
  <p class="sub">your agents, your files, your machine</p>
  <div class="detail">${escapeHtml(message)}</div>
  <p class="note">Close this window to quit. Check sidecar.log / ui-server.log in your Keel data folder.</p>
</div></body></html>`;

  try {
    writeFileSync(file, html, "utf8");
    failureWindow = new BrowserWindow({
      width: 620,
      height: 400,
      resizable: false,
      backgroundColor: "#080604",
      title: "Keel — could not start",
      icon: join(__dirname, "build", "icon.ico"),
      webPreferences: { contextIsolation: true, sandbox: true, nodeIntegration: false },
    });
    failureWindow.setMenuBarVisibility(false);
    failureWindow.webContents.on("did-fail-load", () => {
      if (failureWindow) failureWindow.close();
      stopAllChildren(); // app.exit() bypasses before-quit — clean up here too
      dialog.showErrorBox("Keel failed to start", message);
      app.exit(1);
    });
    failureWindow.on("closed", () => {
      failureWindow = null;
      stopAllChildren();
      process.exitCode = 1; // startup failed even though the window was branded
      app.quit();
    });
    failureWindow.loadFile(file);
    return;
  } catch {
    if (failureWindow) { try { failureWindow.close(); } catch { /* gone */ } }
    failureWindow = null;
  }
  // Last resort: a native dialog is still a clear, non-blank failure surface.
  stopAllChildren(); // app.exit() bypasses before-quit — clean up here too
  dialog.showErrorBox("Keel failed to start", message);
  app.exit(1);
}

function updatePlatform() {
  if (process.platform === "win32") return "windows";
  if (process.platform === "darwin") return "macos";
  return "linux";
}

function checkForUpdates() {
  const manifest = process.env.KEEL_UPDATE_MANIFEST_URL;
  const key = process.env.KEEL_UPDATE_PUBLIC_KEY_PATH || "";
  // Fail closed: an advisory plan is produced only from a manifest whose
  // Ed25519 signature can be checked. No key => no plan (SEC-F-06).
  if (!manifest || !key) return;
  const binary = bundledSidecar();
  const args = binary
    ? [binary, "release", "update-check"]
    : [process.env.KEEL_PYTHON || "python", "-m", "keel", "release", "update-check"];
  args.push("--manifest", manifest, "--current", app.getVersion(),
            "--platform", updatePlatform());
  if (key) args.push("--public-key", key);
  if (process.env.KEEL_UPDATE_ALLOW_HTTP === "1") args.push("--allow-http");

  let stdout = "";
  const child = spawn(args[0], args.slice(1), {
    env: { ...process.env, KEEL_NO_BANNER: "1" },
    stdio: ["ignore", "pipe", "ignore"],
    windowsHide: true,
  });
  child.stdout.on("data", (chunk) => { stdout += chunk.toString(); });
  // A failed spawn emits 'error'; without a listener Node throws and the
  // whole shell crashes over an advisory, best-effort update check.
  child.on("error", () => {});
  child.on("close", (code) => {
    if (code !== 0 || !stdout.trim()) return;
    try {
      const plan = JSON.parse(stdout.trim());
      const statePath = join(app.getPath("userData"), "update-state.json");
      writeFileSync(statePath, JSON.stringify({
        checkedAt: new Date().toISOString(),
        plan,
      }, null, 2));
    } catch {
      // Update metadata is advisory; a malformed response must never break startup.
    }
  });
}

function createSplash(iconPath) {
  splash = new BrowserWindow({
    width: 480,
    height: 320,
    frame: false,
    transparent: true,
    alwaysOnTop: true,
    skipTaskbar: true,
    resizable: false,
    webPreferences: { contextIsolation: true, sandbox: true },
  });
  splash.loadFile(join(__dirname, "splash.html"));
  splash.webContents.on("did-finish-load", () => splash.center());
  splash.on("closed", () => { splash = null; });
  return splash;
}

function createWindow(loadUrl) {
  mainWindow = new BrowserWindow({
    width: 1280,
    height: 800,
    minWidth: 900,
    minHeight: 620,
    backgroundColor: "#080604",
    title: "Keel",
    autoHideMenuBar: true,
    icon: join(__dirname, "build", "icon.ico"),
    webPreferences: {
      contextIsolation: true,
      sandbox: true,
      nodeIntegration: false,
      preload: undefined,
    },
  });
  mainWindow.setMenuBarVisibility(false);
  // legacy/mirror keep the exact token-bearing sidecar URL; unified loads the
  // token-free Fleet Next origin (the BFF owns the credential).
  mainWindow.loadURL(loadUrl ||
    `http://127.0.0.1:${sidecarPort}/?t=${sidecarToken}`);
  mainWindow.on("closed", () => {
    mainWindow = null;
    stopAllChildren(); // never leave the bridge or UI server running
  });

  // Loopback (our own bridge) stays in the shell; other web links open in
  // the user's browser. Any other scheme (file:, javascript:, data:) is
  // refused outright — it must never load inside the Electron renderer.
  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    let parsed;
    try { parsed = new URL(url); } catch { return { action: "deny" }; }
    if (parsed.protocol === "http:" || parsed.protocol === "https:") {
      if (parsed.hostname === "127.0.0.1" || parsed.hostname === "localhost") {
        return { action: "allow" };
      }
      shell.openExternal(url);
      return { action: "deny" };
    }
    return { action: "deny" };
  });
}

app.on("second-instance", () => {
  if (mainWindow) {
    if (mainWindow.isMinimized()) mainWindow.restore();
    mainWindow.focus();
  }
});

const gotLock = app.requestSingleInstanceLock();
if (!gotLock) {
  app.quit();
} else {
  Menu.setApplicationMenu(null);
  app.whenReady().then(async () => {
    const iconPath = join(__dirname, "build", "icon.ico");
    if (existsSync(iconPath)) createSplash(iconPath);
    try {
      const renderer = resolveRenderer({
        resourcesPath: process.resourcesPath,
        env: process.env,
      });
      appendLog(LOG(), `renderer policy: mode=${renderer.mode}; ${renderer.reason}`);
      if (renderer.mode === "mirror" && !renderer.uiDir) {
        throw new Error(`the mirror renderer was requested but its assets are missing: ${renderer.reason}`);
      }
      if (renderer.mode === "unified" && !renderer.uiDir &&
          !fleetNextRuntimeDir(null)) {
        throw new Error(
          `the unified renderer was requested but its runtime is missing: ${renderer.reason}`);
      }

      // Only legacy / mirror roots are handed to the sidecar. Unified mode
      // passes null so the sidecar is API-only and cannot serve a competing UI.
      const url = await startSidecar(renderer.mode === "unified" ? null : renderer.uiDir);
      const parsed = new URL(url); // already validated by waitForSidecarUrl
      sidecarPort = Number(parsed.port);
      sidecarToken = parsed.searchParams.get("t") || sidecarToken;

      let loadUrl = `http://127.0.0.1:${sidecarPort}/?t=${sidecarToken}`;
      if (renderer.mode === "unified") {
        // Only open Electron after the packaged Next server really answers
        // HTTP on its own loopback port. The token stays server-side.
        loadUrl = await startUiServer(url, renderer.uiDir);
      }

      createWindow(loadUrl);
      checkForUpdates();
      if (splash) splash.close();
    } catch (err) {
      if (splash) splash.close();
      // A failure path can bypass before-quit/window-all-closed, so clean up
      // every child here as well.
      stopAllChildren();
      await showFailureScreen(err);
    }
  });

  app.on("window-all-closed", () => { app.quit(); });
  app.on("before-quit", () => {
    quitting = true;
    stopAllChildren();
  });
}
