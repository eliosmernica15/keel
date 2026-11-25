#!/usr/bin/env node
/* Packaged-EXE verification of the Settings -> Privacy deep link.
 *
 *   node tests/packaged-qa/privacy-exe-probe.mjs
 *
 * Launches the REAL packaged Keel.exe, connects over CDP, navigates to the
 * default unified renderer with #settings-privacy, asserts the Privacy & data
 * design renders and that its bridge-backed usage section responds, then
 * saves a screenshot. Never edits application source.
 */
import { spawn, execFileSync } from "node:child_process";
import { mkdirSync, writeFileSync } from "node:fs";
import { join, resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "@playwright/test";

const __dirname = dirname(fileURLToPath(import.meta.url));
const KEEL = resolve(__dirname, "../../..");
const EXE = join(KEEL, "dist", "win-unpacked", "Keel.exe");
const OUT = join(__dirname, "evidence");
const PORT = Number(process.env.KEEL_QA_CDP_PORT || 9350);
mkdirSync(OUT, { recursive: true });

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const checks = [];
function check(name, ok, detail = "") {
  checks.push({ name, pass: Boolean(ok), detail });
  console.log(`${ok ? "PASS" : "FAIL"}  ${name}${detail ? ` — ${detail}` : ""}`);
}

async function waitCdp() {
  for (let i = 0; i < 120; i++) {
    try {
      const r = await fetch(`http://127.0.0.1:${PORT}/json/version`, {
        signal: AbortSignal.timeout(1000),
      });
      if (r.ok) return;
    } catch { /* not listening yet */ }
    await sleep(250);
  }
  throw new Error("CDP endpoint did not become ready");
}

// A previous interrupted probe can leave an Electron tree holding the CDP
// port; clear only processes belonging to this packaged app before starting.
function cleanupStale() {
  try {
    const out = execFileSync("powershell", ["-NoProfile", "-Command",
      `Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*win-unpacked*' -and ($_.Name -eq 'Keel.exe' -or $_.Name -eq 'keel.exe') } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue; $_.ProcessId }`],
    { encoding: "utf8", timeout: 15000 });
    if (out.trim()) console.log(`cleaned stale packaged processes: ${out.trim().replace(/\s+/g, ",")}`);
  } catch { /* nothing to clean */ }
}
cleanupStale();

const proc = spawn(EXE, [`--remote-debugging-port=${PORT}`], {
  cwd: KEEL,
  env: { ...process.env }, // no renderer override: verify the shipped default
  windowsHide: true,
  stdio: ["ignore", "pipe", "pipe"],
});
let procLog = "";
proc.stdout.on("data", (d) => (procLog += d.toString()));
proc.stderr.on("data", (d) => (procLog += d.toString()));

let browser;
try {
  await waitCdp();
  browser = await chromium.connectOverCDP(`http://127.0.0.1:${PORT}`);
  let page;
  for (let i = 0; i < 80; i++) {
    const contexts = browser.contexts();
    const pages = contexts.flatMap((c) => c.pages());
    if (pages.length && pages[0].url().startsWith("http://127.0.0.1:")) {
      page = pages[0];
      break;
    }
    await sleep(250);
  }
  if (!page) throw new Error("no packaged renderer page appeared over CDP");
  await page.waitForLoadState("domcontentloaded").catch(() => {});
  const loadedUrl = page.url();
  check("default packaged renderer is the token-free unified origin",
    /^http:\/\/127\.0\.0\.1:\d+\/$/.test(loadedUrl), loadedUrl);

  // Genuine fresh-install flow: no persisted surface, just the URL hash.
  // Skip the first-run tour overlay so the Settings design itself is testable.
  await sleep(1200);
  await page.evaluate(() => localStorage.setItem("keel-onboarding-done", "true"));
  const base = loadedUrl.replace(/#.*$/, "");
  await page.goto(`${base}#settings-privacy`);
  await page.reload();
  try {
    await page.getByRole("heading", { name: "Privacy & data", exact: true }).first()
      .waitFor({ state: "visible", timeout: 20000 });
  } catch (err) {
    console.log("DIAG url:", page.url());
    console.log("DIAG storage:", await page.evaluate(() => JSON.stringify(localStorage)));
    console.log("DIAG text:", (await page.locator("body").innerText()).slice(0, 700));
    throw err;
  }

  check("deep link displays the Privacy & data design",
    await page.getByRole("heading", { name: "Privacy & data", exact: true }).first().isVisible());
  check("bridge-backed usage section rendered",
    await page.getByText("Usage reported by the bridge", { exact: true }).isVisible());
  check("storage/retention note rendered",
    await page.getByText("Storage, retention and export", { exact: true }).isVisible());
  check("privacy navigation entry is active",
    await page.locator('aside[aria-label="Settings navigation"]')
      .getByRole("button", { name: /Privacy & data/ }).count() > 0);

  // Function: the Reload button re-issues the real bridge usage request.
  const requests = [];
  page.on("request", (r) => {
    if (r.url().includes("/api/bridge/")) requests.push(r.url());
  });
  await page.getByRole("button", { name: "Reload" }).click();
  await sleep(1200);
  check("Reload re-queries the bridge through the same-origin BFF",
    requests.some((u) => u.includes("usage")), requests.slice(0, 3).join(" | "));

  const storage = await page.evaluate(() => JSON.stringify(localStorage));
  check("no bridge token in browser storage", !/[?&]t=|token/i.test(storage), storage.slice(0, 160));

  const screenshot = join(OUT, "packaged-settings-privacy.png");
  await page.screenshot({ path: screenshot, fullPage: true });
  check("screenshot captured", true, screenshot);

  await browser.close(); // CDP disconnect; Electron itself needs a process-tree stop
  browser = null;
  try { execFileSync("taskkill", ["/PID", String(proc.pid), "/T", "/F"], { stdio: "ignore" }); }
  catch { /* already gone */ }
  await sleep(1500);
  check("packaged app and children stopped", proc.exitCode !== null || proc.signalCode !== null,
    `exit=${proc.exitCode} signal=${proc.signalCode}`);
} catch (err) {
  check("probe completed without error", false, String(err && err.stack || err));
} finally {
  if (browser) { try { await browser.close(); } catch { /* already gone */ } }
  if (proc.exitCode === null && proc.signalCode === null) {
    try { execFileSync("taskkill", ["/PID", String(proc.pid), "/T", "/F"], { stdio: "ignore" }); }
    catch { try { proc.kill(); } catch { /* already gone */ } }
  }
}

const failed = checks.filter((c) => !c.pass);
const report = { checks, procLogTail: procLog.slice(-1000) };
writeFileSync(join(__dirname, "qa-logs", "privacy-exe-probe.json"), JSON.stringify(report, null, 2));
console.log(`\nSUMMARY: ${checks.length - failed.length}/${checks.length} passed`);
process.exit(failed.length ? 1 : 0);
