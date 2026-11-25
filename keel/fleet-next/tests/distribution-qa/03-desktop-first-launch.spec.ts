import { test, expect, type Page } from "@playwright/test";
import { spawn, execFileSync, type ChildProcess } from "node:child_process";
import fs from "node:fs";
import path from "node:path";

const ROOT = path.resolve(__dirname, "../../..");
const MAIN_JS = path.join(ROOT, "desktop-app/main.js");
const LOCAL_UI = path.join(ROOT, "desktop/ui/index.html");
const SITE_MIRROR = path.join(ROOT, "site/app.html");
const TOKEN = "qa-desktop-first-launch-token";
const PORT = 8742;

let sidecar: ChildProcess | null = null;
let bridgePromise: Promise<string> | null = null;

async function startBridge(): Promise<string> {
  if (bridgePromise) return bridgePromise;
  const env = {
    ...process.env,
    PYTHONPATH: path.join(ROOT, "src"),
    KEEL_TOKEN: TOKEN,
    KEEL_NO_BANNER: "1",
    KEEL_UI_DIR: path.dirname(LOCAL_UI),
    PYTHONIOENCODING: "utf-8",
  };
  const proc = spawn("python", ["-m", "keel", "serve", "--port", String(PORT)], {
    cwd: ROOT,
    env,
    stdio: ["ignore", "pipe", "pipe"],
    windowsHide: true,
  });
  sidecar = proc;
  bridgePromise = new Promise<string>((resolve, reject) => {
    let buf = "";
    const timer = setTimeout(() => reject(new Error("bridge did not print URL within 30s: " + buf)), 30_000);
    const onData = (chunk: Buffer) => {
      buf += chunk.toString();
      const match = buf.match(/keel webapp running at (\S+)/);
      if (!match) return;
      clearTimeout(timer);
      proc.stdout.off("data", onData);
      proc.stderr.off("data", onData);
      resolve(match[1]);
    };
    proc.stdout.on("data", onData);
    proc.stderr.on("data", onData);
    proc.on("error", reject);
    proc.on("exit", (code) => reject(new Error(`bridge exited early (${code}): ${buf}`)));
  });
  return bridgePromise;
}

test.describe("distribution: desktop first launch (real bridge, local renderer)", () => {
  test.afterAll(async () => {
    if (sidecar && sidecar.exitCode === null) {
      sidecar.kill();
      await new Promise((r) => setTimeout(r, 400));
    }
  });

  test("Electron shell selects the full local renderer, not the site mirror", async () => {
    const src = fs.readFileSync(MAIN_JS, "utf8");
    expect(src).toMatch(/join\(res, "desktop", "ui"\)/);
    expect(src).toMatch(/KEEL_UI_PROFILE=mirror/);
    // The mirror is a diagnostic override, never the default first candidate.
    const uiRootFn = src.slice(src.indexOf("function uiRoot()"), src.indexOf("async function waitForSidecarUrl"));
    const candidates = uiRootFn.match(/const candidates = \[([\s\S]*?)\];/);
    expect(candidates).not.toBeNull();
    expect(candidates![1].indexOf('"desktop", "ui"')).toBeGreaterThanOrEqual(0);
    expect(candidates![1].indexOf('"desktop", "ui"')).toBeLessThan(candidates![1].indexOf('"ui"'));
    expect(src).toMatch(/if \(String\(process\.env\.KEEL_UI_PROFILE \|\| ""\)\.toLowerCase\(\) === "mirror"\)/);
    expect(src).toMatch(/mainWindow\.loadURL\(`http:\/\/127\.0\.0\.1:\$\{sidecarPort\}\/\?t=\$\{sidecarToken\}`\)/);
    expect(src).toMatch(/contextIsolation: true/);
    expect(src).toMatch(/sandbox: true/);
    expect(src).toMatch(/nodeIntegration: false/);
  });

  test("real bridge serves the local renderer and a real API, not a mock", async () => {
    const base = await startBridge();
    const url = new URL(base);
    url.searchParams.set("t", TOKEN);

    const renderer = await fetch(url.href);
    expect(renderer.status).toBe(200);
    const html = await renderer.text();
    const localTitle = (fs.readFileSync(LOCAL_UI, "utf8").match(/<title>([^<]+)<\/title>/) || [])[1];
    const mirrorTitle = (fs.readFileSync(SITE_MIRROR, "utf8").match(/<title>([^<]+)<\/title>/) || [])[1];
    expect(localTitle).toBeTruthy();
    expect(html).toContain(localTitle!);
    if (mirrorTitle && mirrorTitle !== localTitle) expect(html).not.toContain(mirrorTitle);

    const api = await fetch(new URL("/api/fleet/bots", base), {
      headers: { "X-Keel-Token": TOKEN, Origin: url.origin },
    });
    const apiText = await api.text();
    expect(api.status, apiText.slice(0, 300)).toBe(200);
    expect(JSON.parse(apiText)).toBeTruthy();
  });

  test("existing guided tour opens once, closes by keyboard, and survives reload", async ({ browser }) => {
    const base = await startBridge();
    const url = new URL(base);
    url.searchParams.set("t", TOKEN);
    const context = await browser.newContext({ viewport: { width: 1280, height: 900 } });
    const page = await context.newPage();
    await page.goto(url.href);

    const overlay = page.locator("#tutorial-overlay");
    await expect(overlay).toBeHidden();
    const tourButton = page.locator("#btn-tutorial");
    await expect(tourButton).toBeVisible();

    // Keyboard activation, not just a mouse click.
    await tourButton.focus();
    await page.keyboard.press("Enter");
    await expect(overlay).toBeVisible();
    expect(await overlay.getAttribute("role")).toBe("dialog");
    expect(await overlay.getAttribute("aria-modal")).toBe("true");
    await expect(page.locator("#tour-title")).not.toHaveText(/^\s*$/);

    await page.keyboard.press("Escape");
    await expect(overlay).toBeHidden();

    // No second setup wizard may be introduced for the desktop first launch.
    const extraWizards = await page.evaluate(() =>
      Array.from(document.querySelectorAll("[id]")).filter((el) =>
        /(^|-)(setup|onboard|first-run)(-|$)/i.test(el.id)
      ).map((el) => el.id)
    );
    expect(extraWizards).toEqual([]);

    await page.reload();
    await expect(page.locator("#tutorial-overlay")).toBeHidden();
    await context.close();
  });

  test("no duplicate setup was added to the local renderer this round", () => {
    const changed = execFileSync("git", ["diff", "--name-only", "c80c2e1", "--", "keel/desktop/ui"], {
      cwd: path.resolve(ROOT, ".."),
      encoding: "utf8",
    });
    expect(changed.trim()).toBe("");
  });
});
