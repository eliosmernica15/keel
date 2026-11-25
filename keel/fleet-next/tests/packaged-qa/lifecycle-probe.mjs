#!/usr/bin/env node
/* Agent G — Electron lifecycle probes (single instance + failure screen).
 * Usage:
 *   node tests/packaged-qa/lifecycle-probe.mjs failure
 *   node tests/packaged-qa/lifecycle-probe.mjs single
 */
import { spawn, execFileSync } from "node:child_process";
import { mkdirSync, writeFileSync, readFileSync } from "node:fs";
import { join, resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const KEEL = resolve(__dirname, "../../..");
const ELECTRON = join(KEEL, "desktop-app", "node_modules", "electron", "dist", "electron.exe");
const RUNTIME = join(__dirname, "tmp", "unified-runtime");
const EVIDENCE = join(__dirname, "evidence");
const LOGS = join(__dirname, "qa-logs");
mkdirSync(EVIDENCE, { recursive: true });
mkdirSync(LOGS, { recursive: true });

const MODE = (process.argv[2] || "").toLowerCase();
if (!["failure", "single"].includes(MODE)) {
  console.error("mode must be 'failure' or 'single'");
  process.exit(2);
}
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const stamp = new Date().toISOString().replace(/[:.]/g, "-");
const result = { mode: MODE, startedAt: new Date().toISOString(), checks: {}, errors: [] };

function ps(needle) {
  try {
    const out = execFileSync("powershell", ["-NoProfile", "-Command",
      `Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*${needle}*' } | ForEach-Object { "{0}|{1}|{2}" -f $_.ProcessId, $_.ParentProcessId, $_.CommandLine }`,
    ], { encoding: "utf8", timeout: 20000 });
    return out.split(/\r?\n/).map((s) => s.trim()).filter(Boolean)
      .filter((s) => !s.includes("Get-CimInstance Win32_Process"));
  } catch { return []; }
}
function killTree(pid) {
  try {
    execFileSync("taskkill", ["/PID", String(pid), "/T", "/F"], { stdio: "ignore", windowsHide: true, timeout: 10000 });
    return true;
  } catch { return false; }
}
function launch(port, extraEnv = {}) {
  const env = {
    ...process.env,
    KEEL_REPO: KEEL,
    KEEL_PYTHON: "python",
    KEEL_NO_BANNER: "1",
    KEEL_RENDERER_READY_TIMEOUT_MS: "12000",
    ...extraEnv,
  };
  return spawn(ELECTRON, [".", `--remote-debugging-port=${port}`], {
    cwd: join(KEEL, "desktop-app"), env, stdio: ["ignore", "pipe", "pipe"], windowsHide: true,
  });
}
async function cdp(port, ms = 30000) {
  const deadline = Date.now() + ms;
  while (Date.now() < deadline) {
    try {
      const r = await fetch(`http://127.0.0.1:${port}/json/version`, { signal: AbortSignal.timeout(1500) });
      if (r.ok) return await r.json();
    } catch { /* wait */ }
    await sleep(300);
  }
  return null;
}

let first = null;
let browser = null;
try {
  if (MODE === "failure") {
    first = launch(9341, {
      KEEL_RENDERER: "unified",
      KEEL_RENDERER_UNIFIED_DIR: join(__dirname, "tmp", "runtime-does-not-exist"),
    });
    const ver = await cdp(9341);
    result.checks.cdp = Boolean(ver);
    const { chromium } = await import("@playwright/test");
    browser = await chromium.connectOverCDP("http://127.0.0.1:9341");
    let pages = [];
    for (let i = 0; i < 60; i += 1) {
      pages = browser.contexts().flatMap((c) => c.pages());
      if (pages.some((p) => p.url().startsWith("file://") && !p.url().includes("splash.html"))) break;
      await sleep(400);
    }
    result.checks.windows = await Promise.all(pages.map(async (p) => ({
      url: p.url(), title: await p.title().catch(() => ""),
      text: (await p.evaluate(() => document.body?.innerText || "").catch(() => "")).slice(0, 800),
    })));
    const failure = pages.find((p) => p.url().startsWith("file://") && !p.url().includes("splash.html"));
    if (failure) {
      await failure.screenshot({ path: join(EVIDENCE, `electron-failure-screen-${stamp}.png`) });
    } else {
      result.errors.push("no branded failure window appeared");
    }
    result.checks.childrenAfterFailure = {
      keelServePort0: ps("keel serve --port 0").filter((s) => s.includes("|" + first.pid + "|")),
      standalone: ps("server.js").filter((s) => s.includes("|" + first.pid + "|")),
    };
  } else {
    // Single instance: launch the first (unified) shell, wait for its window,
    // then launch a second one with the same userData and CDP-independent PID.
    first = launch(9342, { KEEL_RENDERER: "unified", KEEL_RENDERER_UNIFIED_DIR: RUNTIME });
    const ver = await cdp(9342, 45000);
    result.checks.firstCdp = Boolean(ver);
    const { chromium } = await import("@playwright/test");
    browser = await chromium.connectOverCDP("http://127.0.0.1:9342");
    let pages = [];
    for (let i = 0; i < 100; i += 1) {
      pages = browser.contexts().flatMap((c) => c.pages());
      if (pages.some((p) => p.url().startsWith("http://"))) break;
      await sleep(400);
    }
    result.checks.firstWindow = await Promise.all(pages.map(async (p) => ({ url: p.url(), title: await p.title().catch(() => "") })));
    result.checks.childrenBeforeSecond = {
      sidecar: ps("keel serve --port 0").filter((s) => s.includes("|" + first.pid + "|")),
      next: ps("server.js").filter((s) => s.includes("|" + first.pid + "|")),
    };
    const second = launch(9343, { KEEL_RENDERER: "unified", KEEL_RENDERER_UNIFIED_DIR: RUNTIME });
    result.checks.secondPid = second.pid;
    const secondExit = await Promise.race([
      new Promise((resolve) => second.once("exit", (code, sig) => resolve({ code, sig }))),
      sleep(12000).then(() => ({ code: null, sig: "timeout" })),
    ]);
    result.checks.secondExit = secondExit;
    if (second.exitCode === null && second.signalCode === null) killTree(second.pid);
    await sleep(600);
    pages = browser.contexts().flatMap((c) => c.pages());
    result.checks.windowsAfterSecond = await Promise.all(pages.map(async (p) => ({ url: p.url(), title: await p.title().catch(() => "") })));
    result.checks.childrenAfterSecond = {
      sidecar: ps("keel serve --port 0").filter((s) => s.includes("|" + first.pid + "|")),
      next: ps("server.js").filter((s) => s.includes("|" + first.pid + "|")),
    };
  }
} catch (e) {
  result.errors.push(String(e && e.stack ? e.stack : e));
} finally {
  try { if (browser) await browser.close(); } catch { /* ignore */ }
  if (first && first.exitCode === null && first.signalCode === null) killTree(first.pid);
  await sleep(1000);
  const out = join(LOGS, `lifecycle-${MODE}-${stamp}.json`);
  writeFileSync(out, JSON.stringify(result, null, 2));
  console.log(JSON.stringify(result, null, 2));
  console.log(`result: ${out}`);
}
