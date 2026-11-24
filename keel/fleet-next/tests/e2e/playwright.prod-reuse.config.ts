import { defineConfig, devices } from "@playwright/test";
import path from "node:path";

/**
 * QA-owned variant of playwright.prod.config.ts for loaded machines: the
 * production build in `.next-e2e` is created once (verified separately) and
 * the server is started manually, so Playwright never races a cold build
 * against the webServer 120 s window. Never touches the lead's :3200/.next.
 */
const BASE_URL = "http://127.0.0.1:3300";

export default defineConfig({
  testDir: __dirname,
  timeout: 60_000,
  expect: { timeout: 10_000 },
  reporter: [["list"], ["html", { outputFolder: path.join(__dirname, "report"), open: "never" }]],
  outputDir: path.join(__dirname, "test-results"),
  use: {
    baseURL: BASE_URL,
    colorScheme: "dark",
    viewport: { width: 1440, height: 900 },
    screenshot: "off",
    trace: "off",
  },
  projects: [
    { name: "chromium", use: { ...devices["Desktop Chrome"], viewport: { width: 1440, height: 900 } } },
  ],
  webServer: {
    command: "npx next start -H 127.0.0.1 -p 3300",
    url: BASE_URL,
    reuseExistingServer: true,
    timeout: 60_000,
    cwd: path.resolve(__dirname, "../.."),
    env: {
      ...process.env,
      KEEL_BRIDGE_URL: "http://127.0.0.1:8739",
      KEEL_BRIDGE_TOKEN: process.env.KEEL_E2E_BRIDGE_TOKEN ?? "local-e2e-bridge-token",
      KEEL_DIST_DIR: ".next-e2e",
    } as Record<string, string>,
  },
});
