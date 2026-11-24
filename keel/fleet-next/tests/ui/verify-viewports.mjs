#!/usr/bin/env node
/**
 * Continuous-QA: read-only browser verification for the unified frontend.
 *
 * Ownership: keel/fleet-next/tests/ui/** only. This script never mutates
 * backend data: it only navigates surfaces (GETs), toggles the local command
 * palette and reads layout/DOM facts. It writes tests/ui/viewport-results.json.
 *
 * Run:  node tests/ui/verify-viewports.mjs [baseUrl]
 * Default baseUrl: http://127.0.0.1:3200/ (a server started by another
 * workstream; this script never starts one).
 */
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const BASE = process.argv[2] ?? "http://127.0.0.1:3200/";
const VIEWPORTS = [
  { name: "360x800", width: 360, height: 800 },
  { name: "390x844", width: 390, height: 844 },
  { name: "768x1024", width: 768, height: 1024 },
  { name: "1024x768", width: 1024, height: 768 },
  { name: "1280x800", width: 1280, height: 800 },
  { name: "1440x900", width: 1440, height: 900 },
];
const SURFACES = [
  { name: "Cowork", tab: true, marker: "cowork" },
  { name: "Code", tab: true, marker: "code" },
  { name: "Duet", tab: true, marker: "duet" },
  { name: "Fleet", tab: true, marker: "fleet" },
  { name: "Capabilities", tab: false, marker: "Capabilities" },
  { name: "Settings", tab: false, marker: "Settings" },
];

const out = {
  generatedAt: new Date().toISOString(),
  base: BASE,
  note: "Read-only. No POST/PUT/DELETE is issued by this script. Onboarding is suppressed via localStorage only.",
  viewports: [],
  consoleErrors: [],
  commandPalette: null,
  error: null,
};

let browser;
try {
  browser = await chromium.launch({ headless: true });
  for (const vp of VIEWPORTS) {
    const ctx = await browser.newContext({ viewport: { width: vp.width, height: vp.height } });
    // Suppress the first-run wizard without touching backend state.
    await ctx.addInitScript(() => {
      try { localStorage.setItem("keel-onboarding-done", "true"); } catch { /* ignore */ }
    });
    const page = await ctx.newPage();
    const errors = [];
    page.on("console", (m) => { if (m.type() === "error") errors.push(m.text().slice(0, 300)); });
    page.on("pageerror", (e) => errors.push(`pageerror: ${String(e).slice(0, 300)}`));
    const surfaces = [];
    try {
      await page.goto(BASE, { waitUntil: "domcontentloaded", timeout: 30000 });
      await page.waitForSelector(".keel-app", { timeout: 15000 });
      // `.keel-app` is in the SSR HTML; wait for a mount-time effect to run so
      // that React handlers are attached before any click.
      await page.waitForFunction(
        () => !document.body.innerText.includes("Checking bridge"),
        null, { timeout: 15000 },
      );
      for (const s of SURFACES) {
        const nav = s.tab
          ? page.getByRole("tab", { name: s.name, exact: true })
          : page.locator(".keel-nav-item", { hasText: s.name });
        await nav.first().click({ timeout: 10000 });
        // Assert that the click actually switched surfaces; otherwise the
        // overflow measurements below would all describe the same view.
        await page.waitForFunction(
          (marker) => {
            const body = document.body.innerText;
            return body.includes(`Surface: ${marker}`) ||
              Array.from(document.querySelectorAll(".keel-canvas h1"))
                .some((h) => (h.textContent ?? "").trim() === marker);
          },
          s.marker, { timeout: 10000 },
        );
        const metrics = await page.evaluate(() => ({
          innerWidth: window.innerWidth,
          scrollWidth: document.documentElement.scrollWidth,
          bodyScrollWidth: document.body.scrollWidth,
          clientWidth: document.documentElement.clientWidth,
        }));
        surfaces.push({
          surface: s.name,
          ...metrics,
          overflow: metrics.scrollWidth > metrics.innerWidth || metrics.bodyScrollWidth > metrics.innerWidth,
        });
      }
    } catch (e) {
      out.error = `${vp.name}: ${String(e).slice(0, 400)}`;
    }
    if (errors.length) out.consoleErrors.push({ viewport: vp.name, messages: errors });
    out.viewports.push({ ...vp, surfaces });
    await ctx.close();
  }

  // Focus-trap probe on a normal desktop viewport (read-only UI interaction).
  const ctx = await browser.newContext({ viewport: { width: 1280, height: 800 } });
  await ctx.addInitScript(() => {
    try { localStorage.setItem("keel-onboarding-done", "true"); } catch { /* ignore */ }
  });
  const page = await ctx.newPage();
  await page.goto(BASE, { waitUntil: "domcontentloaded", timeout: 30000 });
  await page.waitForSelector(".keel-app", { timeout: 15000 });
  await page.waitForFunction(
    () => !document.body.innerText.includes("Checking bridge"),
    null, { timeout: 15000 },
  );
  // Click the visible control instead of Ctrl+K: headless Chromium reserves
  // Ctrl+K for its own omnibox shortcut, so the page may never see it.
  await page.getByRole("button", { name: "Command palette (Ctrl+K)" }).click({ timeout: 10000 });
  await page.waitForSelector(".keel-cmd", { timeout: 5000 });
  const before = await page.evaluate(() => ({
    focused: document.activeElement?.getAttribute("aria-label") ?? document.activeElement?.tagName ?? null,
    insideDialog: Boolean(document.activeElement?.closest?.(".keel-cmd")),
  }));
  await page.keyboard.press("Tab");
  const afterTab = await page.evaluate(() => ({
    focused: document.activeElement?.getAttribute("aria-label") ?? document.activeElement?.tagName ?? null,
    insideDialog: Boolean(document.activeElement?.closest?.(".keel-cmd")),
  }));
  await page.keyboard.press("Escape");
  const afterEscape = await page.evaluate(() => ({
    dialogOpen: Boolean(document.querySelector(".keel-cmd")),
  }));
  out.commandPalette = { before, afterTab, afterEscape };
  await ctx.close();
} catch (e) {
  out.error = String(e).slice(0, 500);
} finally {
  await browser?.close();
}

fs.writeFileSync(path.join(HERE, "viewport-results.json"), JSON.stringify(out, null, 2));
const bad = out.viewports.flatMap((v) => v.surfaces.filter((s) => s.overflow).map((s) => `${v.name}/${s.surface}`));
console.log(JSON.stringify({
  viewports: out.viewports.length,
  surfacesChecked: out.viewports.reduce((n, v) => n + v.surfaces.length, 0),
  overflow: bad,
  consoleErrorViewports: out.consoleErrors.map((x) => x.viewport),
  paletteFocusEscapes: out.commandPalette && !out.commandPalette.afterTab.insideDialog,
  error: out.error,
}, null, 2));
