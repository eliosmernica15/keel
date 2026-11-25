import { test, expect } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";
import { execFileSync } from "node:child_process";

const ROOT = path.resolve(__dirname, "../../..");
const MAIN = path.join(ROOT, "desktop-app", "main.js");
const POLICY = path.join(ROOT, "desktop-app", "renderer-policy.js");
const PKG = path.join(ROOT, "desktop-app", "package.json");
const NEXT_CFG = path.join(ROOT, "fleet-next", "next.config.mjs");
const BFF = path.join(ROOT, "fleet-next", "app", "api", "bridge", "[...path]", "route.ts");
const LOGS = path.join(__dirname, "qa-logs");
fs.mkdirSync(LOGS, { recursive: true });

const main = fs.readFileSync(MAIN, "utf8");
const policy = fs.readFileSync(POLICY, "utf8");
const pkg = JSON.parse(fs.readFileSync(PKG, "utf8"));
const nextCfg = fs.readFileSync(NEXT_CFG, "utf8");
const bff = fs.readFileSync(BFF, "utf8");

const integrationSignals = [/KEEL_BRIDGE_TOKEN/, /KEEL_BRIDGE_URL/, /fleetNextRuntimeDir/, /output: "standalone"/];
const integrationDetected = integrationSignals.every((re) => re.test(main) || re.test(nextCfg));

let head = "unknown";
try {
  head = execFileSync("git", ["rev-parse", "--short", "HEAD"], { cwd: ROOT, encoding: "utf8" }).trim();
} catch { /* not a git worktree */ }

fs.writeFileSync(
  path.join(LOGS, "source-contract-detection.json"),
  JSON.stringify(
    {
      head,
      integrationDetected,
      worktreeDirty: execFileSync("git", ["status", "--short"], { cwd: ROOT, encoding: "utf8" }).trim(),
      signals: integrationSignals.map(String),
    },
    null,
    2,
  ),
);

test.describe("baseline Electron contracts (legacy / mirror / rollback)", () => {
  test("sidecar is spawned on an ephemeral loopback port and its URL+token are validated (main.js:133-230)", () => {
    expect(main).toMatch(/keel webapp running at (\S+)/);
    expect(main).toMatch(/url\.protocol !== "http:"/);
    expect(main).toMatch(/url\.hostname !== "127\.0\.0\.1"/);
    expect(main).toMatch(/url\.searchParams\.get\("t"\)/);
    expect(main).toMatch(/randomBytes\(18\)\.toString\("base64url"\)/);
    expect(main).toMatch(/\["serve", "--port", "0"\]/);
    expect(main).toMatch(/waitForSidecarUrl\(sidecar, readyTimeoutMs\(\)\)/);
  });

  test("legacy fallback and explicit-only mirror remain usable (renderer-policy.js:38-68,171-265)", () => {
    // One pinned constant governs the cutover. It was LEGACY until G1–G6;
    // after owner approval it may be UNIFIED. Explicit legacy rollback and
    // explicit-only mirror must hold in either state.
    expect(policy).toMatch(/export const DEFAULT_RENDERER = RENDERER_MODES\.(LEGACY|UNIFIED)/);
    expect(policy).toMatch(/RENDERER_MODES = Object\.freeze\(\{[\s\S]*UNIFIED[\s\S]*LEGACY[\s\S]*MIRROR/);
    expect(policy).toMatch(/mirror mode requires KEEL_UI_PROFILE=mirror/);
    // KEEL_UI_DIR must not silently replace an explicitly requested unified app.
    const unifiedBlock = policy.slice(
      policy.indexOf('if (e.renderer === "unified")'),
      policy.indexOf('// Invalid value'),
    );
    expect(unifiedBlock).not.toMatch(/override/);
    expect(unifiedBlock).toMatch(/findUnified\(resourcesPath, e, exists\)/);
    // Reason strings are fixed labels: no credentials or absolute paths.
    expect(policy).not.toMatch(/reason:.*token|reason:.*process\.env\./);
  });

  test("single instance, branded failure screen and splash survive (main.js:574-696)", () => {
    expect(main).toMatch(/app\.requestSingleInstanceLock\(\)/);
    expect(main).toMatch(/app\.on\("second-instance"/);
    expect(main).toMatch(/mainWindow\.focus\(\)/);
    expect(main).toMatch(/createSplash\(iconPath\)/);
    expect(main).toMatch(/async function showFailureScreen\(err\)/);
    expect(main).toMatch(/<h1>Keel could not start<\/h1>/);
    expect(main).toMatch(/dialog\.showErrorBox\("Keel failed to start"/);
    expect(main).toMatch(/app\.exit\(1\)/);
  });

  test("both children stop on every exit path (main.js:50-96,613-616,682-695)", () => {
    expect(main).toMatch(/function stopChild\(proc\)/);
    expect(main).toMatch(/execFileSync\("taskkill", \["\/PID", String\(proc\.pid\), "\/T", "\/F"\]/);
    expect(main).toMatch(/function stopAllChildren\(\)/);
    const hooks = [
      ['mainWindow.on("closed"', 400],
      ['app.on("before-quit"', 400],
      ["await showFailureScreen(err)", 0],
      ['failureWindow.on("closed"', 400],
      ['failureWindow.webContents.on("did-fail-load"', 400],
    ];
    for (const [hook, window] of hooks as [string, number][]) {
      const idx = main.indexOf(hook);
      expect(idx, `missing hook ${hook}`).toBeGreaterThanOrEqual(0);
      // The startup catch calls stopAllChildren *before* showFailureScreen.
      const from = hook === "await showFailureScreen(err)" ? Math.max(0, idx - 300) : idx;
      const slice = main.slice(from, idx + window);
      expect(slice, `${hook} must stop all children`).toMatch(/stopAllChildren\(\)/);
    }
  });

  test("external links open outside Electron; other schemes denied (main.js:621-632)", () => {
    expect(main).toMatch(/setWindowOpenHandler\(\(\{ url \}\) =>/);
    expect(main).toMatch(/shell\.openExternal\(url\)/);
    expect(main).toMatch(/parsed\.hostname === "127\.0\.0\.1" \|\| parsed\.hostname === "localhost"/);
    expect(main).toMatch(/action: "deny"/);
    expect(main).toMatch(/nodeIntegration: false/);
    expect(main).toMatch(/contextIsolation: true/);
    expect(main).toMatch(/sandbox: true/);
    expect(main).toMatch(/preload: undefined/);
  });
});

test.describe("unified Electron + Fleet Next integration contract", () => {
  test.skip(!integrationDetected, "integration code not present in this worktree");

  test("packaged standalone Next server is spawned with Electron-as-Node (main.js:232-444)", () => {
    expect(main).toMatch(/function fleetNextRuntimeDir\(uiDir\)/);
    expect(main).toMatch(/existsSync\(join\(dir, "server\.js"\)\)/);
    expect(main).toMatch(/ELECTRON_RUN_AS_NODE: "1"/);
    expect(main).toMatch(/spawn\(node, \[script\]/);
    expect(main).toMatch(/function reserveLoopbackPort\(\)/);
    expect(main).toMatch(/server\.listen\(0, "127\.0\.0\.1"/);
    expect(main).toMatch(/readyTimeoutMs\(\)/);
    expect(main).toMatch(/http\.get\(\{ host: "127\.0\.0\.1", port, path: "\/"/);
    expect(main).toMatch(/res\.statusCode === 200/);
  });

  test("Next binds loopback only (HOSTNAME, not HOST) and gets the real bridge URL + token server-side", () => {
    expect(main).toMatch(/HOSTNAME: "127\.0\.0\.1"/);
    expect(main).not.toMatch(/\bHOST: "127\.0\.0\.1"/);
    expect(main).toMatch(/KEEL_BRIDGE_URL: `http:\/\/127\.0\.0\.1:\$\{parsed\.port\}`/);
    expect(main).toMatch(/KEEL_BRIDGE_TOKEN: token/);
    expect(main.includes("/^[A-Za-z0-9_-]+$/")).toBe(true);
    expect(main).toMatch(/length=\$\{token\.length\} prefix=\$\{token\.slice\(0, 4\)\}/);
    expect(bff).toMatch(/process\.env\.KEEL_BRIDGE_TOKEN/);
    expect(bff).toMatch(/headers\.set\("x-keel-token", BRIDGE_TOKEN\)/);
    expect(bff).not.toMatch(/NEXT_PUBLIC/);
  });

  test("unified window URL is token-free; legacy/mirror keep the token URL", () => {
    expect(main.includes("return `http://127.0.0.1:${port}/`;")).toBe(true);
    expect(main).toMatch(/createWindow\(loadUrl\)/);
    // The token-bearing string exists only as the legacy/mirror fallback.
    expect(main).toMatch(/let loadUrl = `http:\/\/127\.0\.0\.1:\$\{sidecarPort\}\/\?t=\$\{sidecarToken\}`/);
    const unifiedBranch = main.slice(
      main.indexOf("if (renderer.mode === \"unified\")"),
      main.indexOf("createWindow(loadUrl)"),
    );
    expect(unifiedBranch).not.toMatch(/\?t=/);
  });

  test("package ships the complete standalone runtime and no token files", () => {
    const res = pkg.build.extraResources as Array<{ from: string; to: string }>;
    expect(res.some((r) => r.from === "../fleet-next/.next/standalone" && r.to === "fleet-next")).toBe(true);
    expect(res.some((r) => r.to === "fleet-next/.next/static")).toBe(true);
    expect(res.some((r) => r.to === "fleet-next/public")).toBe(true);
    expect(pkg.build.files).toContain("renderer-policy.js");
    const fleetEntry = res.find((r) => r.to === "fleet-next")! as { filter?: string[] };
    expect(fleetEntry.filter).toContain("!**/.env*");
    expect(fleetEntry.filter).toContain("!**/*.map");
    expect(fleetEntry.filter).toContain("!**/tests/**");
    expect(nextCfg).toMatch(/output: "standalone"/);
  });
});
