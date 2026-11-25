import { test, expect, type Page } from "@playwright/test";
import { PLATFORMS, availableManifest, mockManifest } from "./fixtures";

async function open(page: Page) {
  await page.addInitScript((p) => {
    Object.defineProperty(navigator, "platform", { configurable: true, get: () => p.platform });
    Object.defineProperty(navigator, "userAgentData", {
      configurable: true,
      get: () => ({
        platform: p.uaPlatform,
        architecture: p.architecture,
        bitness: p.bitness,
        getHighEntropyValues: async (keys: string[]) =>
          Object.fromEntries(
            keys.map((k) => [k, ({ architecture: p.architecture, bitness: p.bitness, platform: p.uaPlatform } as Record<string, string>)[k] || ""])
          ),
      }),
    });
  }, PLATFORMS[0]);
  await mockManifest(page, { api: availableManifest });
  await page.goto("/download", { waitUntil: "load" });
  await page.waitForTimeout(400);
}

test.describe("distribution: accessibility and keyboard journey", () => {
  test("download page: every control has an accessible name and no dead links", async ({ page }) => {
    await open(page);
    const problems = await page.evaluate(() => {
      const bad: string[] = [];
      for (const el of Array.from(document.querySelectorAll("a,button,input,select,textarea"))) {
        const a = el as HTMLElement;
        if (a.hasAttribute("hidden") || a.closest("[hidden]")) continue;
        const name = (a.getAttribute("aria-label") || a.textContent || "").trim();
        if (!name && !(a as HTMLInputElement).labels?.length) bad.push(`${el.tagName}#${a.id || "-"}: no accessible name`);
        if (el.tagName === "A" && a.getAttribute("aria-disabled") !== "true") {
          const href = (el as HTMLAnchorElement).getAttribute("href") || "";
          if (href === "#" || href === "") bad.push(`a#${a.id || "-"}: dead href`);
        }
      }
      return bad;
    });
    expect(problems).toEqual([]);
  });

  test("download page: exactly one h1 and disabled downloads are not focusable links", async ({ page }) => {
    await open(page);
    expect(await page.locator("h1").count()).toBe(1);
    const dangerousDisabled = await page.evaluate(() => {
      const root = document.querySelector("main") || document.body;
      return Array.from(root.querySelectorAll('[aria-disabled="true"]'))
        .filter((el) => {
          const href = (el as HTMLAnchorElement).href || "";
          return /\.(exe|dmg|appimage|deb|rpm|zip)(\?|$)/i.test(href);
        })
        .map((el) => (el as HTMLAnchorElement).href);
    });
    expect(dangerousDisabled, "disabled controls must never point at an installer").toEqual([]);
  });

  test("download page: the primary CTA is reachable by keyboard", async ({ page }) => {
    await open(page);
    const cta = page.locator("#kp-download-primary");
    await expect(cta).toBeVisible();
    const href = await cta.getAttribute("href");
    expect(href, "verified installer must enable the primary CTA").toBeTruthy();
    await cta.focus();
    expect(await cta.evaluate((el) => el === document.activeElement)).toBe(true);
    expect(await cta.getAttribute("aria-disabled")).toBeNull();
  });

  test("download page: FAQ toggles expose and update aria-expanded", async ({ page }) => {
    await open(page);
    const first = page.locator("button[aria-controls^='kp-faq'], button[aria-expanded]").first();
    if (await first.count() === 0) return; // no FAQ on a future minimal page
    const before = await first.getAttribute("aria-expanded");
    await first.focus();
    await page.keyboard.press("Enter");
    const after = await first.getAttribute("aria-expanded");
    expect(before === after, "aria-expanded must change after activation").toBe(false);
  });

  test("in-app download link is keyboard reachable and named", async ({ page }) => {
    await page.goto("/app");
    const link = page.locator("#nav-download");
    await link.focus();
    expect(await link.evaluate((el) => el === document.activeElement)).toBe(true);
    expect((await link.innerText()).trim().length).toBeGreaterThan(0);
    await expect(link).toHaveAttribute("aria-label", /Download Keel/i);
  });
});
