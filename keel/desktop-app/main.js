/* Keel Desktop — Electron shell.
   Spawns the keel sidecar (Python bridge on 127.0.0.1), waits for its
   printed URL line on stderr, then loads it in a framed BrowserWindow.
   Fully offline/self-contained: no network calls beyond 127.0.0.1 and the
   provider the user configures. */
import { app, BrowserWindow, shell, Menu } from "electron";
import { spawn } from "child_process";
import { randomBytes } from "crypto";
import { join, dirname } from "path";
import { existsSync, createWriteStream } from "fs";
import { fileURLToPath } from "url";

const __dirname = dirname(fileURLToPath(import.meta.url));

let mainWindow = null;
let splash = null;
let sidecar = null;
let sidecarPort = 0;
let sidecarToken = "";
let quitting = false;

const LOG = () => join(app.getPath("userData"), "sidecar.log");

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

function uiRoot() {
  const res = process.resourcesPath;
  const candidates = [
    join(res, "site"),          // mirror build (shipped in production)
    join(res, "desktop", "ui"), // legacy layout
    join(res, "ui"),
  ];
  for (const c of candidates) if (existsSync(join(c, "index.html"))) return c;
  return null;
}

async function waitForSidecarUrl(proc, ms = 30000) {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error("sidecar did not print its URL within 30s")), ms);
    let buf = "";
    const onData = (chunk) => {
      buf += chunk.toString();
      const m = buf.match(/keel webapp running at (http:\/\/127\.0\.0\.1:\d+\/\?t=[A-Za-z0-9_-]+)/);
      if (m) {
        clearTimeout(timer);
        proc.stdout.removeAllListeners("data");
        proc.stderr.removeAllListeners("data");
        resolve(m[1]);
      }
    };
    proc.stdout.on("data", onData);
    proc.stderr.on("data", onData);
    proc.on("error", (err) => { clearTimeout(timer); reject(err); });
    proc.on("exit", (code) => { clearTimeout(timer); reject(new Error(`sidecar exited early (code ${code})`)); });
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
  mainWindow.on("closed", () => { mainWindow = null; });

  // external links open in the user's browser, never inside the shell
  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    if (/^https?:\/\//.test(url) && !url.startsWith("http://127.0.0.1")) {
      shell.openExternal(url);
      return { action: "deny" };
    }
    return { action: "allow" };
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
      const m = url.match(/^(http:\/\/127\.0\.0\.1:(\d+)\/\?t=[A-Za-z0-9_-]+)/);
      if (m) sidecarPort = Number(m[2]), sidecarToken = new URL(url).searchParams.get("t") || sidecarToken;
      createWindow();
      if (splash) splash.close();
    } catch (err) {
      if (splash) splash.close();
      const { dialog } = await import("electron");
      dialog.showErrorBox("Keel failed to start", String(err.message || err));
      app.exit(1);
    }
  });

  app.on("window-all-closed", () => { app.quit(); });
  app.on("before-quit", () => {
    quitting = true;
    if (sidecar) {
      try { sidecar.kill("SIGTERM"); } catch { /* already gone */ }
    }
  });
}
