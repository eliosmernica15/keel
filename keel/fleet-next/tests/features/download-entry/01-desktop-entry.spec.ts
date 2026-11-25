import fs from "node:fs";
import path from "node:path";
import { spawnSync } from "node:child_process";
import { test, expect, openApp } from "./fixtures";

const DOWNLOAD_URL = "https://keel-desktop.vercel.app/download";
const ROOT = path.resolve(__dirname, "../../.."); // fleet-next
const REPO = path.resolve(ROOT, ".."); // keel/ — git cwd

test.describe("in-app Get Keel Desktop entry point", () => {
  test("appears exactly once with the contracted href and safe new-tab attributes", async ({ page }) => {
    await openApp(page);

    const link = page.getByRole("link", { name: "Get Keel Desktop", exact: true });
    await expect(link).toHaveCount(1);
    await expect(link).toBeVisible();

    // No duplicate control anywhere else in the unified application shell.
    await expect(page.locator(`a[href="${DOWNLOAD_URL}"]`)).toHaveCount(1);
    await expect(page.locator('a:has-text("Get Keel Desktop")')).toHaveCount(1);
    await expect(page.locator(`.keel-sidebar__foot a[href="${DOWNLOAD_URL}"]`)).toHaveCount(1);

    await expect(link).toHaveAttribute("href", DOWNLOAD_URL);
    await expect(link).toHaveAttribute("target", "_blank");
    await expect(link).toHaveAttribute("rel", "noopener noreferrer");
    await expect(link).toHaveAttribute("aria-label", "Get Keel Desktop");
  });

  test("is reachable with the keyboard alone", async ({ page }) => {
    await openApp(page);

    const link = page.getByRole("link", { name: "Get Keel Desktop", exact: true });
    await expect(link).toHaveCount(1);

    // Walk the real tab order from the top of the document; no programmatic
    // focus() is used, so this proves the link is in the keyboard tab order.
    await page.evaluate(() => {
      const active = document.activeElement;
      if (active instanceof HTMLElement) active.blur();
    });
    let reached = false;
    for (let i = 0; i < 60; i++) {
      await page.keyboard.press("Tab");
      if (await link.evaluate((el) => el === document.activeElement)) {
        reached = true;
        break;
      }
    }
    expect(reached, "Get Keel Desktop must be reachable by pressing Tab").toBe(true);
    await expect(link).toBeFocused();
    expect(await link.evaluate((el) => (el as HTMLAnchorElement).tabIndex)).toBeGreaterThanOrEqual(0);
  });

  test("marketing homepage remains untouched", () => {
    // Byte-for-byte unchanged against HEAD: no installer section or new
    // download control was added to the marketing homepage by this work.
    const diff = spawnSync("git", ["diff", "--quiet", "HEAD", "--", "site/index.html"], {
      cwd: REPO,
      encoding: "utf8",
    });
    expect(diff.error ?? null).toBeNull();
    expect(diff.status, `git diff failed: ${diff.stderr}`).toBe(0);

    const html = fs.readFileSync(path.join(REPO, "site", "index.html"), "utf8");
    expect(html).not.toContain("Get Keel Desktop");
    expect(html).not.toContain(DOWNLOAD_URL);
  });
});
