import { test, expect, type Page } from "@playwright/test";
import { spawn, execFileSync, type ChildProcess } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { mockManifest } from "./fixtures";

const ROOT = path.resolve(__dirname, "../../..");
const REPO = path.resolve(ROOT, ".."); // worktree root (git cwd)
const BASE = process.env.KEEL_QA_BASELINE || "c80c2e1";
const EVIDENCE = path.join(__dirname, "evidence");
const BASE_PORT = 3311;

// Files this round is allowed to touch (distribution + the in-app/PWA link).
const ALLOWED_PREFIX = [
  "keel/site/download.html",
  "keel/site/download.json",
  "keel/site/api/download-manifest.js",
  "keel/site/ui/download",
  "keel/site/ui/landing-download.js",
  "keel/site/manifest.webmanifest",
  "keel/site/sw.js",
  "keel/site/vercel.json",
  "keel/site/app.html",
  "keel/site/tests/", // QA/test scaffolding, not a user-facing page
];

function allowed(f: string) {
  return ALLOWED_PREFIX.some((prefix) => f === prefix || f.startsWith(prefix));
}

function git(args: string[]) {
  return execFileSync("git", args, { cwd: REPO, encoding: "utf8", maxBuffer: 20 * 1024 * 1024 });
}

async function snapshot(page: Page, route: string, name: string) {
  await mockManifest(page);
  await page.goto(route.startsWith("http") ? route : route, { waitUntil: "load" });
  await page.evaluate(() => document.fonts.ready);
  // The floating news toast animates into place on a timer; exclude it from
  // the visual diff so only real page content is compared.
  await page.addStyleTag({ content: ".l-news,.kp-news{display:none !important}" });
  await page.waitForTimeout(250);
  const buffer = await page.screenshot({ fullPage: true, animations: "disabled" });
  fs.mkdirSync(EVIDENCE, { recursive: true });
  fs.writeFileSync(path.join(EVIDENCE, name), buffer);
  return buffer;
}

test.describe("distribution: landing-page and unrelated-page regression gate", () => {
  test("no unrelated site file changed since the pre-round commit", () => {
    const changed = git(["diff", "--name-only", BASE, "--", "keel/site"])
      .split("\n")
      .map((s) => s.trim())
      .filter(Boolean);
    const unexpected = changed.filter((f) => !allowed(f));
    expect(unexpected, `unexpected site changes vs ${BASE}: ${unexpected.join(", ")}`).toEqual([]);
  });

  test("app.html changes (if any) are limited to the contextual download link", () => {
    const diff = git(["diff", "-U0", BASE, "--", "keel/site/app.html"]);
    const changedLines = diff
      .split("\n")
      .filter((line) => /^[+-]/.test(line) && !line.startsWith("+++") && !line.startsWith("---"));
    const offScope = changedLines.filter((line) => !/download/i.test(line));
    expect(offScope, JSON.stringify(offScope)).toEqual([]);
  });

  test("marketing homepage and unrelated pages are pixel-identical to the baseline", async ({ browser, page }) => {
    const temp = fs.mkdtempSync(path.join(os.tmpdir(), "keel-qa-baseline-"));
    const archive = path.join(temp, "site.tar");
    fs.writeFileSync(archive, execFileSync("git", ["archive", "--format=tar", BASE, "keel/site"], {
      cwd: REPO,
      maxBuffer: 50 * 1024 * 1024,
    }));
    execFileSync("tar", ["-xf", archive, "-C", temp]);
    const baselineSite = path.join(temp, "keel", "site");
    expect(fs.existsSync(path.join(baselineSite, "index.html"))).toBe(true);

    const proc: ChildProcess = spawn("node", ["tests/distribution-qa/server.mjs"], {
      cwd: path.join(ROOT, "fleet-next"),
      env: { ...process.env, KEEL_QA_PORT: String(BASE_PORT), KEEL_QA_SITE_DIR: baselineSite },
      stdio: ["ignore", "pipe", "pipe"],
      windowsHide: true,
    });
    try {
      await new Promise<void>((resolve, reject) => {
        const timer = setTimeout(() => reject(new Error("baseline server did not start")), 20_000);
        const check = async () => {
          try {
            const r = await fetch(`http://127.0.0.1:${BASE_PORT}/index.html`);
            if (r.ok) { clearTimeout(timer); resolve(); }
            else setTimeout(check, 200);
          } catch { setTimeout(check, 200); }
        };
        check();
      });

      for (const [route, file] of [
        ["/", "landing-current.png"],
        ["/privacy", "privacy-current.png"],
        ["/downloads", "downloads-current.png"],
      ] as const) {
        const baselineContext = await browser.newContext({ viewport: { width: 1280, height: 900 }, colorScheme: "light" });
        const baselinePage = await baselineContext.newPage();
        const before = await snapshot(
          baselinePage,
          `http://127.0.0.1:${BASE_PORT}${route}`,
          file.replace("-current", "-baseline")
        );
        await baselineContext.close();

        const after = await snapshot(page, route, file);
        expect(before.equals(after), `${route} pixel drift vs ${BASE}`).toBe(true);
      }
    } finally {
      proc.kill();
    }
  });
});
