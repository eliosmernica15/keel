#!/usr/bin/env node
/* Agent G — independent Electron integration probe.
 *
 * Launches either the Electron development shell or the real packaged EXE with
 * --remote-debugging-port, attaches over CDP, records what the renderer
 * actually loaded (URL, title, text, localStorage), snapshots child processes
 * (Python sidecar / packaged Next server), then closes the window and verifies
 * the children are gone.
 *
 * Usage:
 *   node tests/packaged-qa/electron-probe.mjs dev
 *   node tests/packaged-qa/electron-probe.mjs exe
 *
 * This script never modifies application source. All evidence is written under
 * tests/packaged-qa/evidence and tests/packaged-qa/qa-logs.
 */
import { spawn, execFileSync } from "node:child_process";
import { mkdirSync, writeFileSync, existsSync, readFileSync } from "node:fs";
import { join, resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const KEEL = resolve(__dirname, "../../..");
const DESKTOP_APP = join(KEEL, "desktop-app");
const EXE = join(KEEL, "dist", "win-unpacked", "Keel.exe");
const ELECTRON = join(DESKTOP_APP, "node_modules", "electron", "dist", "electron.exe");
const EVIDENCE = join(__dirname, "evidence");
const LOGS = join(__dirname, "qa-logs");
mkdirSync(EVIDENCE, { recursive: true });
mkdirSync(LOGS, { recursive: true });

const MODE = (process.argv[2] || "dev").toLowerCase();
if (!["dev", "exe"].includes(MODE)) {
  console.error("mode must be 'dev' or 'exe'");
  process.exit(2);
}
// Explicit overrides avoid depending on the caller's shell syntax:
//   node electron-probe.mjs dev KEEL_RENDERER=unified KEEL_RENDERER_UNIFIED_DIR=...
const overrides = {};
for (const arg of process.argv.slice(3)) {
  const i = arg.indexOf("=");
  if (i > 0) overrides[arg.slice(0, i)] = arg.slice(i + 1);
}
// Use a unique CDP port when other agents are probing Electron concurrently;
// otherwise we can attach to their browser instead of our own launched child.
const PORT = Number(overrides.KEEL_QA_CDP_PORT) || (MODE === "dev" ? 9333 : 9334);
const stamp = new Date().toISOString().replace(/[:.]/g, "-");
const logPath = join(LOGS, `electron-${MODE}-${stamp}.log`);
const jsonPath = join(LOGS, `electron-${MODE}-${stamp}.json`);
const logStream = writeFileSync(logPath, "");

function log(line) {
  const text = `[${new Date().toISOString()}] ${line}`;
  console.log(text);
  writeFileSync(logPath, text + "\n", { flag: "a" });
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

function ps(cmdlineNeedle) {
  try {
    const psScript =
      `Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*${cmdlineNeedle}*' } | ` +
      `ForEach-Object { "{0}|{1}|{2}" -f $_.ProcessId, $_.ParentProcessId, $_.CommandLine }`;
    const out = execFileSync("powershell", ["-NoProfile", "-Command", psScript], {
      encoding: "utf8",
      timeout: 20000,
    });
    return out
      .split(/\r?\n/)
      .map((s) => s.trim())
      .filter(Boolean)
      // Ignore the probe's own WMI query process and its pwsh wrapper.
      .filter((s) => !s.includes("Get-CimInstance Win32_Process"));
  } catch (e) {
    return [`ERROR: ${e.message}`];
  }
}

function listeners(pid) {
  try {
    const out = execFileSync("netstat", ["-ano", "-p", "tcp"], {
      encoding: "utf8",
      timeout: 20000,
    });
    return out
      .split(/\r?\n/)
      .filter((l) => /LISTENING/i.test(l) && l.trim().endsWith(String(pid)))
      .map((l) => l.trim().replace(/\s+/g, " "));
  } catch {
    return [];
  }
}

function killTree(pid) {
  try {
    execFileSync("taskkill", ["/PID", String(pid), "/T", "/F"], {
      stdio: "ignore",
      windowsHide: true,
      timeout: 10000,
    });
    return true;
  } catch {
    return false;
  }
}

async function waitForCdp(port, ms = 45000) {
  const deadline = Date.now() + ms;
  while (Date.now() < deadline) {
    try {
      const res = await fetch(`http://127.0.0.1:${port}/json/version`, {
        signal: AbortSignal.timeout(1500),
      });
      if (res.ok) return await res.json();
    } catch { /* not up yet */ }
    await sleep(400);
  }
  return null;
}

function scenario() {
  if (MODE === "dev") {
    if (!existsSync(ELECTRON)) throw new Error(`electron.exe missing: ${ELECTRON}`);
    return {
      cmd: ELECTRON,
      args: [".", `--remote-debugging-port=${PORT}`],
      cwd: DESKTOP_APP,
      env: {
        ...process.env,
        KEEL_REPO: KEEL,
        KEEL_PYTHON: "python",
        KEEL_NO_BANNER: "1",
      },
    };
  }
  if (!existsSync(EXE)) throw new Error(`packaged EXE missing: ${EXE}`);
  return {
    cmd: EXE,
    args: [`--remote-debugging-port=${PORT}`],
    cwd: KEEL,
    env: { ...process.env, KEEL_NO_BANNER: "1" },
  };
}

const result = {
  mode: MODE,
  startedAt: new Date().toISOString(),
  host: process.platform,
  logPath,
  jsonPath,
  checks: {},
  errors: [],
};

let child = null;
let browser = null;
try {
  const s = scenario();
  Object.assign(s.env, overrides);
  log(`launching ${s.cmd} ${s.args.join(" ")} (cwd=${s.cwd}) overrides=${JSON.stringify(overrides)}`);
  result.command = { cmd: s.cmd, args: s.args, cwd: s.cwd, overrides };
  child = spawn(s.cmd, s.args, {
    cwd: s.cwd,
    env: s.env,
    stdio: ["ignore", "pipe", "pipe"],
    windowsHide: true,
  });
  child.stdout.on("data", (d) => writeFileSync(logPath, d, { flag: "a" }));
  child.stderr.on("data", (d) => writeFileSync(logPath, d, { flag: "a" }));
  child.on("error", (e) => log(`child error: ${e.message}`));
  child.on("exit", (code, sig) => log(`child exit: code=${code} sig=${sig}`));

  result.checks.preLaunchChildren = {
    keelServe: ps("keel serve"),
    nextServer: ps("next start"),
  };

  const ver = await waitForCdp(PORT);
  result.checks.cdp = ver
    ? { ok: true, browser: ver.Browser, webSocketDebuggerUrl: ver.webSocketDebuggerUrl }
    : { ok: false };
  if (!ver) throw new Error("CDP endpoint did not appear within 45s");

  const { chromium } = await import("@playwright/test");
  browser = await chromium.connectOverCDP(`http://127.0.0.1:${PORT}`);
  // The splash opens immediately while both children start. Poll for the real
  // app window instead of assuming it is ready after a fixed 1.5 s sleep.
  let pages = [];
  for (let i = 0; i < 120; i += 1) {
    pages = browser.contexts().flatMap((c) => c.pages());
    const hasApp = pages.some((p) => {
      const u = p.url();
      return u.startsWith("http://") ||
        (u.startsWith("file://") && !u.includes("splash.html"));
    });
    if (hasApp) break;
    await sleep(500);
  }
  await sleep(800); // let the renderer settle after navigation
  result.checks.windows = await Promise.all(
    pages.map(async (p) => ({
      url: p.url(),
      title: await p.title().catch(() => ""),
    })),
  );

  // Branding / surface evidence from the first non-devtools page. Failure
  // screens are file:// windows, so accept those too.
  const appPage = pages.find((p) => {
    const u = p.url();
    return (u.startsWith("http://") || u.startsWith("file://")) &&
      !u.startsWith("devtools://");
  });
  if (appPage) {
    await appPage.screenshot({ path: join(EVIDENCE, `electron-${MODE}-${stamp}.png`), fullPage: false });
    result.checks.renderer = await appPage.evaluate(() => ({
      href: location.href,
      title: document.title,
      text: (document.body?.innerText || "").slice(0, 5000),
      localStorage: Object.fromEntries(
        Object.keys(localStorage).map((k) => [k, String(localStorage.getItem(k)).slice(0, 240)]),
      ),
      sessionStorage: Object.fromEntries(
        Object.keys(sessionStorage).map((k) => [k, String(sessionStorage.getItem(k)).slice(0, 240)]),
      ),
      userAgent: navigator.userAgent,
      hasBridgeTokenInHtml: /[?&]t=[A-Za-z0-9_-]{12,}/.test(document.documentElement.outerHTML),
    }));
    result.checks.screenshot = join(EVIDENCE, `electron-${MODE}-${stamp}.png`);

    if (overrides.KEEL_QA_UI_CHECK === "1") {
      const ui = {};
      try {
        // Dismiss the onboarding layer the same way a user can.
        for (let i = 0; i < 10; i += 1) {
          const skip = appPage.getByRole("button", { name: /skip for now|close/i }).first();
          if (!(await skip.count()) || !(await skip.isVisible())) break;
          await skip.click();
          await sleep(250);
        }
        ui.onboardingDismissed = true;
      } catch (e) { ui.onboardingDismissed = `error: ${e.message}`; }

      try {
        // BFF round-trip from inside the renderer: same-origin, no token in URL.
        ui.bff = await appPage.evaluate(async () => {
          const r = await fetch("/api/bridge/bots", { cache: "no-store" });
          const t = await r.text();
          return { status: r.status, body: t.slice(0, 600), tokenInBody: /[?&]t=[A-Za-z0-9_-]{12,}/.test(t) };
        });
      } catch (e) { ui.bff = `error: ${e.message}`; }

      ui.surfaces = {};
      for (const label of ["Cowork", "Code", "Duet", "Fleet", "Capabilities", "Settings"]) {
        try {
          const btn = appPage.getByRole("button", { name: label, exact: true }).first();
          if (!(await btn.count())) { ui.surfaces[label] = "button-not-found"; continue; }
          await btn.click();
          await sleep(500);
          ui.surfaces[label] = await appPage.evaluate(() => ({
            path: location.pathname,
            heading: (document.querySelector("main h1, main h2, h1, h2")?.textContent || "").trim().slice(0, 120),
            text: (document.body?.innerText || "").slice(0, 260),
          }));
          await appPage.screenshot({
            path: join(EVIDENCE, `electron-${MODE}-surface-${label.toLowerCase()}-${stamp}.png`),
          });
        } catch (e) { ui.surfaces[label] = `error: ${e.message}`; }
      }

      try {
        ui.theme = await appPage.evaluate(() => ({
          attr: document.documentElement.dataset.theme || null,
          colorScheme: getComputedStyle(document.documentElement).colorScheme,
          persisted: Object.fromEntries(
            Object.entries(localStorage).filter(([k]) => /theme/i.test(k)),
          ),
        }));
        // Explicit persistence probe: set the documented key, reload, confirm
        // the chosen theme survives and is applied before paint.
        await appPage.evaluate(() =>
          localStorage.setItem("keel-theme-v2", JSON.stringify("dark")));
        await appPage.reload();
        await sleep(700);
        ui.themeAfterReload = await appPage.evaluate(() => ({
          attr: document.documentElement.dataset.theme || null,
          colorScheme: getComputedStyle(document.documentElement).colorScheme,
          persisted: localStorage.getItem("keel-theme-v2"),
        }));
      } catch (e) { ui.theme = `error: ${e.message}`; }

      try {
        // Take the REAL token from the sidecar log (main.js tees its printed
        // URL there) and hunt for that exact string in every browser-facing
        // resource: HTML, JS chunks and source maps.
        const userLog = join(process.env.APPDATA || "", "keel-desktop", "sidecar.log");
        const log = readFileSync(userLog, "utf8");
        const urls = [...log.matchAll(/keel webapp running at (\S+)/g)].map((m) => m[1]);
        if (!urls.length) throw new Error("no sidecar URL in sidecar.log");
        const token = new URL(urls[urls.length - 1]).searchParams.get("t") || "";
        if (!token) throw new Error("no token in last sidecar URL");
        const target = appPage.url().replace(/\/$/, "");
        const scanned = [];
        const htmlRes = await fetch(target + "/");
        const html = await htmlRes.text();
        scanned.push({ resource: "/", status: htmlRes.status, leak: html.includes(token) });
        const jsUrls = [...new Set(
          [...html.matchAll(/(?:src|href)="([^" ]+\.js[^" ]*)"/g)].map((m) => m[1]),
        )];
        for (const u of jsUrls) {
          const abs = u.startsWith("http") ? u : target + (u.startsWith("/") ? u : "/" + u);
          try {
            const r = await fetch(abs);
            const body = await r.text();
            scanned.push({ resource: u, status: r.status, leak: body.includes(token) });
            const maps = [...body.matchAll(/sourceMappingURL=([^\s]+)/g)].map((m) => m[1]);
            for (const map of maps) {
              const mapAbs = new URL(map, abs).href;
              const mr = await fetch(mapAbs);
              const mb = await mr.text();
              scanned.push({ resource: mapAbs.slice(-90), status: mr.status, leak: mb.includes(token) });
            }
          } catch (e) { scanned.push({ resource: u, status: "fetch-error", leak: null, error: e.message }); }
        }
        ui.tokenLeakScan = {
          tokenLength: token.length,
          tokenPrefix: token.slice(0, 4) + "…",
          resources: scanned,
          anyLeak: scanned.some((s) => s.leak === true),
        };
      } catch (e) { ui.tokenLeakScan = `error: ${e.message}`; }

      try {
        const link = appPage.getByRole("link", { name: /get keel desktop/i }).first();
        ui.externalLink = (await link.count()) ? await link.getAttribute("href") : "not-found";
        const before = browser.contexts().flatMap((c) => c.pages()).length;
        if (await link.count()) { await link.click(); await sleep(900); }
        const after = browser.contexts().flatMap((c) => c.pages()).length;
        ui.externalLinkElectronTargets = { before, after };
      } catch (e) { ui.externalLink = `error: ${e.message}`; }

      result.checks.ui = ui;
    }
  } else {
    result.errors.push("no http app page found in Electron CDP targets");
  }

  result.checks.runningChildren = {
    keelServe: ps("keel serve"),
    nextServer: ps("next start"),
    nextServerAlt: ps("next-server"),
    bundledKeel: ps("keel.exe serve"),
    standaloneServer: ps("server.js"),
    fleetNextRuntime: ps("fleet-next"),
  };

  log(`windows: ${JSON.stringify(result.checks.windows)}`);
  // Loopback-only socket assertion for OUR children (parent = Electron pid).
  const childPids = [];
  for (const key of ["keelServe", "standaloneServer", "bundledKeel"]) {
    for (const line of result.checks.runningChildren[key] || []) {
      const [pid, parent] = line.split("|");
      if (Number(parent) === child.pid) childPids.push({ key, pid: Number(pid) });
    }
  }
  result.checks.listeners = childPids.map((c) => ({
    ...c,
    sockets: listeners(c.pid),
  }));
  result.checks.nonLoopbackListeners = result.checks.listeners.filter((c) =>
    c.sockets.some((s) => !/127\.0\.0\.1|\[::1\]/.test(s)),
  );
} catch (err) {
  result.errors.push(String(err && err.stack ? err.stack : err));
  log(`ERROR: ${err.message}`);
} finally {
  try { if (browser) await browser.close(); } catch { /* ignore */ }
  if (child && child.exitCode === null && child.signalCode === null) {
    log(`terminating electron tree pid=${child.pid}: ${killTree(child.pid)}`);
    await sleep(1200);
  }
  result.checks.afterCloseChildren = {
    keelServe: ps("keel serve"),
    nextServer: ps("next start"),
    nextServerAlt: ps("next-server"),
    bundledKeel: ps("keel.exe serve"),
    standaloneServer: ps("server.js"),
    fleetNextRuntime: ps("fleet-next"),
  };
  result.finishedAt = new Date().toISOString();
  writeFileSync(jsonPath, JSON.stringify(result, null, 2));
  log(`result written to ${jsonPath}`);
}
