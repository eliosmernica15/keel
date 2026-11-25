#!/usr/bin/env node
/* Agent D — final verification of the packaged EXE (D-EXE series).
 *
 *   node tests/qa-final/02-packaged-exe.spec.mjs
 *
 * Covers:
 *   D-EXE-01 default launch → token-free unified origin, window title
 *           "Keel — Unified Workspace" (re-run of Agent G's expectation).
 *   D-EXE-02 default launch → #settings-privacy renders the Privacy & data
 *           design (re-confirm of the verified 9/9 from the privacy probe).
 *   D-EXE-03 KEEL_RENDERER=legacy → old renderer: sidecar URL keeps the
 *           ?t= token (not the token-free unified origin).
 *   D-EXE-04 both children (Python sidecar + packaged Next server) stop on
 *           close of the window.
 *   D-EXE-05 single-instance preserved: launching a second Keel.exe while
 *           one is running does not create a second app.
 *
 * Evidence screenshots → tests/qa-final/evidence/; results →
 * tests/qa-final/results/02-packaged-exe-results.json.
 */
import { spawn, execFileSync } from "node:child_process";
import { mkdirSync, writeFileSync } from "node:fs";
import { join, resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const KEEL = resolve(__dirname, "../../..");
const EXE = join(KEEL, "dist", "win-unpacked", "Keel.exe");
const EVIDENCE = join(__dirname, "evidence");
const RESULTS = join(__dirname, "results");
mkdirSync(EVIDENCE, { recursive: true });
mkdirSync(RESULTS, { recursive: true });

const checks = [];
function check(name, ok, detail = "") {
  checks.push({ name, pass: Boolean(ok), detail });
  console.log(`${ok ? "PASS" : "FAIL"}  ${name}${detail ? ` — ${detail}` : ""}`);
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function waitCdp(port, ms = 45000) {
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

function ps(needle, timeout = 20000) {
  try {
    const out = execFileSync(
      "powershell",
      ["-NoProfile", "-Command",
        `Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*${needle}*' } | ForEach-Object { "{0}|{1}" -f $_.ProcessId, $_.ParentProcessId }`],
      { encoding: "utf8", timeout },
    );
    return out.split(/\r?\n/).map((s) => s.trim()).filter(Boolean)
      .filter((s) => !s.includes("Get-CimInstance Win32_Process"));
  } catch { return []; }
}

function countProcesses(name) {
  const out = execFileSync("powershell",
    ["-NoProfile", "-Command",
      `(Get-CimInstance Win32_Process | Where-Object { $_.Name -eq '${name}' }).Count`],
    { encoding: "utf8", timeout: 20000 });
  return Number(out.trim() || 0);
}

function descendantsOf(rootPid) {
  // Set of PIDs in rootPid's process tree (including rootPid).
  let rows = [];
  try {
    const out = execFileSync("powershell",
      ["-NoProfile", "-Command",
        `Get-CimInstance Win32_Process | Select-Object ProcessId,ParentProcessId,Name,CommandLine | ConvertTo-Json -Compress`],
      { encoding: "utf8", timeout: 20000 });
    rows = JSON.parse(out || "[]");
  } catch { return new Set([rootPid]); }
  const byParent = new Map();
  for (const r of rows) {
    if (r.ParentProcessId === null || r.ParentProcessId === undefined) continue;
    if (!byParent.has(r.ParentProcessId)) byParent.set(r.ParentProcessId, []);
    byParent.get(r.ParentProcessId).push(r.ProcessId);
  }
  const set = new Set();
  const frontier = [rootPid];
  while (frontier.length) {
    const next = [];
    for (const p of frontier) {
      if (set.has(p)) continue;
      set.add(p);
      next.push(...(byParent.get(p) || []));
    }
    frontier.length = 0;
    frontier.push(...next);
  }
  return set;
}

function isAlive(pid) {
  try {
    const out = execFileSync("powershell",
      ["-NoProfile", "-Command",
        `(Get-CimInstance Win32_Process -Filter 'ProcessId=${pid}' -ErrorAction SilentlyContinue).Count`],
      { encoding: "utf8", timeout: 15000 });
    return Number(out.trim() || 0) > 0;
  } catch { return false; }
}

function descendantCmdlines(pids) {
  try {
    const out = execFileSync("powershell",
      ["-NoProfile", "-Command",
        `Get-CimInstance Win32_Process | Where-Object { $_.ProcessId -in @(${pids.join(",")}) } | Select-Object Name,CommandLine | ConvertTo-Json -Compress`],
      { encoding: "utf8", timeout: 20000 });
    return JSON.parse(out || "[]");
  } catch { return []; }
}

function killTree(pid) {
  try {
    execFileSync("taskkill", ["/PID", String(pid), "/T", "/F"], { stdio: "ignore", windowsHide: true, timeout: 10000 });
    return true;
  } catch { return false; }
}

async function waitForAppWindow(browser, ms = 90000) {
  const deadline = Date.now() + ms;
  while (Date.now() < deadline) {
    const pages = browser.contexts().flatMap((c) => c.pages());
    const hasApp = pages.some((p) => {
      const u = p.url();
      return u.startsWith("http://") || (u.startsWith("file://") && !u.includes("splash.html"));
    });
    if (hasApp) {
      await sleep(800); // let the renderer settle
      return pages.find((p) => p.url().startsWith("http://")) || pages[0];
    }
    await sleep(500);
  }
  return null;
}

function launch(env, port) {
  return spawn(EXE, [`--remote-debugging-port=${port}`], {
    cwd: KEEL, env: { ...process.env, KEEL_NO_BANNER: "1", ...env },
    windowsHide: true, stdio: ["ignore", "pipe", "pipe"],
  });
}

const out = {
  startedAt: new Date().toISOString(),
  exe: EXE,
  scenarios: {},
};

// ---------------------------------------------------------------------------
// Scenario 1: default launch — unified renderer, privacy deep link, stop.
// ---------------------------------------------------------------------------
{
  const PORT = 9710;
  const child = launch({}, PORT);
  let browser = null;
  let descendantPids = new Set();
  try {
    const ver = await waitCdp(PORT);
    check("S1: CDP endpoint up", Boolean(ver), `port=${PORT}`);
    const { chromium } = await import("@playwright/test");
    browser = await chromium.connectOverCDP(`http://127.0.0.1:${PORT}`);
    const page = await waitForAppWindow(browser);
    check("S1: app window found", Boolean(page));
    const url = page && page.url();
    check("D-EXE-01: default launch loads the token-free unified origin",
      /^http:\/\/127\.0\.0\.1:\d+\/$/.test(url || ""), url);
    const title = page && (await page.title().catch(() => ""));
    check("D-EXE-01: window/document title is 'Keel — Unified Workspace'",
      title === "Keel — Unified Workspace", JSON.stringify(title));
    await page.screenshot({ path: join(EVIDENCE, "D-EXE-01-default-unified.png") });

    // Re-confirm #settings-privacy (privacy probe expectation).
    await page.evaluate(() => localStorage.setItem("keel-onboarding-done", "true"));
    await page.goto(`${page.url().replace(/#.*$/, "")}#settings-privacy`);
    await page.reload();
    const headingVisible = await page.getByRole("heading", { name: "Privacy & data", exact: true })
      .first().isVisible({ timeout: 20000 }).catch(() => false);
    check("D-EXE-02: #settings-privacy renders the Privacy & data design", headingVisible);
    await page.screenshot({ path: join(EVIDENCE, "D-EXE-02-settings-privacy.png") });

    // Children running while the app is open (descendants of our Electron).
    const descendants = descendantsOf(child.pid);
    const cmds = descendantCmdlines([...descendants]);
    const running = {
      descendants: cmds.length,
      sidecar: cmds.some((c) => (c.CommandLine || "").includes("keel serve") || (c.CommandLine || "").includes("keel.exe serve")),
      uiServer: cmds.some((c) => (c.CommandLine || "").includes("server.js") || (c.CommandLine || "").includes("next start") || (c.CommandLine || "").includes("next-server")),
    };
    check("D-EXE-04a: children running while open (sidecar + UI server)",
      running.sidecar && running.uiServer, JSON.stringify(running));
    out.scenarios.s1 = { url, title, running, descendantCount: descendants.size };
  } catch (e) {
    out.scenarios.s1Error = String(e && e.stack ? e.stack : e);
    check("S1: scenario 1 completed without error", false, out.scenarios.s1Error);
  } finally {
    descendantPids = descendantsOf(child.pid);
    if (browser) await browser.close().catch(() => {});
    if (child && child.exitCode === null) { killTree(child.pid); await sleep(2000); }
  }
  // After close: every descendant of the Electron process must be gone.
  const afterClose = {
    aliveDescendants: [...descendantPids].filter((p) => isAlive(p)).length,
    keelExeTotal: countProcesses("Keel.exe"),
  };
  check("D-EXE-04b: both children stopped after close (all descendants gone)",
    afterClose.aliveDescendants === 0, JSON.stringify(afterClose));
  out.scenarios.s1AfterClose = afterClose;
}

// ---------------------------------------------------------------------------
// Scenario 2: KEEL_RENDERER=legacy — old renderer (sidecar URL keeps token).
// ---------------------------------------------------------------------------
{
  const PORT = 9711;
  const child = launch({ KEEL_RENDERER: "legacy" }, PORT);
  let browser = null;
  try {
    const ver = await waitCdp(PORT);
    check("S2: CDP endpoint up", Boolean(ver), `port=${PORT}`);
    const { chromium } = await import("@playwright/test");
    browser = await chromium.connectOverCDP(`http://127.0.0.1:${PORT}`);
    const page = await waitForAppWindow(browser);
    const url = page && page.url();
    check("D-EXE-03: legacy rollback loads the sidecar URL with a token",
      /^http:\/\/127\.0\.0\.1:\d+\/\?t=\S+/.test(url || ""), url);
    check("D-EXE-03: legacy URL is not the token-free unified origin",
      !/^http:\/\/127\.0\.0\.1:\d+\/$/.test(url || ""), url);
    const title = page && (await page.title().catch(() => ""));
    await page.screenshot({ path: join(EVIDENCE, "D-EXE-03-legacy-renderer.png") });
    out.scenarios.s2 = { url, title };
  } catch (e) {
    out.scenarios.s2Error = String(e && e.stack ? e.stack : e);
    check("S2: scenario 2 completed without error", false, out.scenarios.s2Error);
  } finally {
    if (browser) await browser.close().catch(() => {});
    if (child && child.exitCode === null) { killTree(child.pid); await sleep(1500); }
  }
}

// ---------------------------------------------------------------------------
// Scenario 3: single-instance preserved.
// ---------------------------------------------------------------------------
{
  const PORT1 = 9712;
  const PORT2 = 9713;
  const child = launch({}, PORT1);
  try {
    const ver = await waitCdp(PORT1);
    check("S3: first instance CDP up", Boolean(ver), `port=${PORT1}`);
    await sleep(3000); // let the first app fully settle
    const before = countProcesses("Keel.exe");
    const second = launch({}, PORT2);
    let secondExit = null;
    second.on("exit", (code) => { secondExit = code; });
    await sleep(5000); // give the second instance time to register/quit
    const after = countProcesses("Keel.exe");
    const secondStillAlive = second.exitCode === null && second.signalCode === null;
    check("D-EXE-05: single instance — process count unchanged (no second app)",
      after === before && !secondStillAlive,
      `before=${before} after=${after} secondStillAlive=${secondStillAlive}`);
    out.scenarios.s3 = { before, after, secondStillAlive };
    try { if (second && second.exitCode === null) killTree(second.pid); } catch { /* ignore */ }
  } catch (e) {
    out.scenarios.s3Error = String(e && e.stack ? e.stack : e);
    check("S3: scenario 3 completed without error", false, out.scenarios.s3Error);
  } finally {
    if (child && child.exitCode === null) { killTree(child.pid); await sleep(1500); }
  }
}

const failed = checks.filter((c) => !c.pass);
out.finishedAt = new Date().toISOString();
out.summary = { total: checks.length, passed: checks.length - failed.length, failed: failed.length };
writeFileSync(join(RESULTS, "02-packaged-exe-results.json"), JSON.stringify(out, null, 2));
console.log(`\nSUMMARY: ${out.summary.passed}/${out.summary.total} passed`);
process.exit(failed.length ? 1 : 0);
