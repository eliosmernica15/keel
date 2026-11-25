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
import { fileURLToPath } from "url";

const __dirname = dirname(fileURLToPath(import.meta.url));

let mainWindow = null;
let splash = null;
let sidecar = null;
let sidecarPort = 0;
let sidecarToken = "";
let quitting = false;

const LOG = () => join(app.getPath("userData"), "sidecar.log");

// Single place that stops the sidecar. Every exit path must go through here:
// window close, before-quit, and the startup-failure path (which uses
// app.exit() and therefore never emits before-quit).
function stopSidecar() {
  if (!sidecar) return;
  const proc = sidecar;
  sidecar = null;
  if (proc.exitCode !== null || proc.signalCode !== null) return;
  try {
    if (process.platform === "win32") {
      // The PyInstaller one-file sidecar launches a child process that owns
      // the listening socket. TerminateProcess (what proc.kill() does on
      // Windows) only kills the bootloader and leaves that child orphaned —
      // this is what previously kept keel.exe holding the built artifact
      // open. /T walks the whole tree; /F forces it.
      execFileSync("taskkill", ["/PID", String(proc.pid), "/T", "/F"],
                   { stdio: "ignore", windowsHide: true, timeout: 5000 });
    } else {
      proc.kill("SIGTERM");
    }
  } catch {
    try { proc.kill(); } catch { /* already gone */ }
  }
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

function startSidecar() {
  sidecarToken = randomBytes(18).toString("base64url");
  sidecarPort = 8700 + Math.floor(Math.random() * 2000); // 8700–10700, plenty of headroom
  const env = {
    ...process.env,
    KEEL_TOKEN: sidecarToken,
    KEEL_NO_BANNER: "1",
  };

  const bin = bundledSidecar();
  let cmd, args;
  if (bin) {
    // production: bundled PyInstaller binary, fully self-contained
    env.KEEL_UI_DIR = uiRoot() || undefined;
    cmd = bin;
    args = ["serve", "--port", String(sidecarPort)];
  } else if (process.env.KEEL_SIDE_CAR) {
    // developer override: path to a keel.py bundle
    env.KEEL_UI_DIR = uiRoot();
    cmd = process.env.KEEL_SIDE_CAR;
    args = ["serve", "--port", String(sidecarPort)];
  } else {
    // day-to-day development: system Python running the repo
    const repoRoot = join(
      process.env.KEEL_REPO || join(process.cwd(), ".."),
    );
    env.PYTHONPATH = join(repoRoot, "src");
    env.KEEL_UI_DIR = uiRoot() || join(repoRoot, "desktop", "ui");
    cmd = process.env.KEEL_PYTHON || "python";
    args = ["-m", "keel", "serve", "--port", String(sidecarPort)];
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
  return waitForSidecarUrl(sidecar);
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

function createWindow() {
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
  mainWindow.loadURL(`http://127.0.0.1:${sidecarPort}/?t=${sidecarToken}`);
  mainWindow.on("closed", () => {
    mainWindow = null;
    stopSidecar(); // never leave the bridge running after the shell closes
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
      const url = await startSidecar();
      const parsed = new URL(url); // already validated by waitForSidecarUrl
      sidecarPort = Number(parsed.port);
      sidecarToken = parsed.searchParams.get("t") || sidecarToken;
      createWindow();
      checkForUpdates();
      if (splash) splash.close();
    } catch (err) {
      if (splash) splash.close();
      // app.exit() skips before-quit/window-all-closed, so clean up here too.
      stopSidecar();
      const { dialog } = await import("electron");
      dialog.showErrorBox("Keel failed to start", String(err.message || err));
      app.exit(1);
    }
  });

  app.on("window-all-closed", () => { app.quit(); });
  app.on("before-quit", () => {
    quitting = true;
    stopSidecar();
  });
}
