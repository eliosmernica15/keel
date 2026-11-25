import { defineConfig, devices } from "@playwright/test";
import path from "node:path";

/**
 * Focused check of the ACTUAL packaged runtime: Next's traced standalone
 * server.js, on a non-3000 loopback port, with the BFF holding the token.
 * Bridge responses remain FIXTURE data from fixture-bridge.mjs.
 */
const APP_PORT = Number(process.env.KEEL_COMPAT_STANDALONE_PORT ?? 3473);
const BRIDGE_PORT = Number(process.env.KEEL_COMPAT_BRIDGE_PORT ?? 3472);
const BASE_URL = `http://127.0.0.1:${APP_PORT}`;
const APP_ROOT = path.resolve(__dirname, "../..");
const TOKEN = "local-packaged-compat-token";

export default defineConfig({
  testDir: __dirname,
  testMatch: /07-standalone.*\.spec\.ts/,
  timeout: 90_000,
  expect: { timeout: 12_000 },
  reporter: [["list"]],
  outputDir: path.join(__dirname, "test-results-standalone"),
  workers: 1,
  use: {
    baseURL: BASE_URL,
    colorScheme: "dark",
    viewport: { width: 1440, height: 900 },
    screenshot: "off",
    trace: "off",
    launchOptions: { args: ["--disable-features=LocalNetworkAccessChecks"] },
  },
  projects: [
    { name: "chromium", use: { ...devices["Desktop Chrome"], viewport: { width: 1440, height: 900 } } },
  ],
  webServer: [
    {
      name: "fixture bridge (FIXTURE)",
      command: "node tests/packaged-compat/fixture-bridge.mjs",
      url: `http://127.0.0.1:${BRIDGE_PORT}/__fixture/observations`,
      reuseExistingServer: false,
      timeout: 60_000,
      cwd: APP_ROOT,
      stdout: "pipe",
      stderr: "pipe",
      env: {
        ...process.env,
        KEEL_COMPAT_BRIDGE_PORT: String(BRIDGE_PORT),
        KEEL_BRIDGE_TOKEN: TOKEN,
      } as Record<string, string>,
    },
    {
      name: "standalone Next server.js on a non-3000 loopback port",
      command: "npx next build && node tests/packaged-compat/standalone-runtime.mjs",
      url: BASE_URL,
      reuseExistingServer: false,
      timeout: 300_000,
      cwd: APP_ROOT,
      stdout: "pipe",
      stderr: "pipe",
      env: {
        ...process.env,
        KEEL_BRIDGE_URL: `http://127.0.0.1:${BRIDGE_PORT}`,
        KEEL_BRIDGE_TOKEN: TOKEN,
        KEEL_DIST_DIR: ".next-packaged-compat",
        KEEL_COMPAT_STANDALONE_PORT: String(APP_PORT),
        NEXT_TELEMETRY_DISABLED: "1",
      } as Record<string, string>,
    },
  ],
});
