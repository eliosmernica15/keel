import { defineConfig, devices } from "@playwright/test";
import path from "node:path";

/**
 * Packaged-context compatibility suite.
 *
 * The app under test is a PRODUCTION Next build (`next build` + `next start`)
 * served on a deliberately non-3000 loopback port, with the bridge token held
 * only by the server process (exactly how the Electron unified renderer hosts
 * it). All bridge responses come from a FIXTURE server; no credentials and no
 * Python runtime are involved.
 */
const APP_PORT = Number(process.env.KEEL_COMPAT_APP_PORT ?? 3471);
const BRIDGE_PORT = Number(process.env.KEEL_COMPAT_BRIDGE_PORT ?? 3472);
const BASE_URL = `http://127.0.0.1:${APP_PORT}`;
const APP_ROOT = path.resolve(__dirname, "../..");
const TOKEN = "local-packaged-compat-token";

export default defineConfig({
  testDir: __dirname,
  testMatch: /.*\.spec\.ts/,
  testIgnore: /07-standalone.*\.spec\.ts/, // runs in the standalone-runtime config
  timeout: 90_000,
  expect: { timeout: 12_000 },
  reporter: [["list"]],
  outputDir: path.join(__dirname, "test-results"),
  fullyParallel: false,
  workers: 1, // a single fixture bridge records calls for the whole suite
  forbidOnly: Boolean(process.env.CI),
  retries: 0,
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
      name: "fixture bridge (FIXTURE — not the Python runtime)",
      command: `node tests/packaged-compat/fixture-bridge.mjs`,
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
      name: "production Next app on a non-3000 loopback port",
      command: `npx next build && npx next start -H 127.0.0.1 -p ${APP_PORT}`,
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
        NEXT_TELEMETRY_DISABLED: "1",
      } as Record<string, string>,
    },
  ],
});
