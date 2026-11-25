import { defineConfig, devices } from "@playwright/test";
import path from "node:path";

// Dedicated port + build dir for the PWA identity/shortcut suite. Does not
// touch the preview (:3200), E2E (:3300), a11y (:3302) or distribution (:3310).
const PORT = Number(process.env.KEEL_PWA_PORT || 3314);
const BASE_URL = `http://127.0.0.1:${PORT}`;

export default defineConfig({
  testDir: __dirname,
  timeout: 180_000,
  expect: { timeout: 15_000 },
  workers: 1, // service-worker registration assertions share a browser profile
  retries: 0,
  reporter: [["list"]],
  outputDir: path.join(__dirname, "test-results"),
  use: {
    baseURL: BASE_URL,
    colorScheme: "light",
    viewport: { width: 1280, height: 900 },
    screenshot: "only-on-failure",
    trace: "off",
    launchOptions: { args: ["--disable-features=LocalNetworkAccessChecks"] },
  },
  projects: [
    { name: "chromium", use: { ...devices["Desktop Chrome"] } },
  ],
  webServer: {
    // Dev server: serves the same manifest/SW as production. Using dev keeps
    // this suite independent of in-flight type errors in concurrently edited
    // feature files elsewhere in the shared worktree.
    command: `npx next dev -H 127.0.0.1 -p ${PORT}`,
    url: BASE_URL,
    reuseExistingServer: process.env.KEEL_PWA_REUSE === "1",
    timeout: 300_000,
    cwd: path.resolve(__dirname, "../.."),
    stdout: "pipe",
    stderr: "pipe",
    env: {
      ...process.env,
      KEEL_DIST_DIR: ".next-pwa",
      KEEL_BRIDGE_URL: "http://127.0.0.1:8739",
      KEEL_BRIDGE_TOKEN: process.env.KEEL_E2E_BRIDGE_TOKEN ?? "local-pwa-bridge-token",
      NEXT_TELEMETRY_DISABLED: "1",
    } as Record<string, string>,
  },
});
