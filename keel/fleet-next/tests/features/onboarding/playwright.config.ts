import { defineConfig, devices } from "@playwright/test";
import path from "node:path";

// Dedicated port + build output so this workstream's runs never collide with
// the shared tests/e2e suite (port 3300 / .next-e2e) or the lead's :3200 preview.
const root = path.resolve(__dirname, "../../..");
const PORT = 3311;
const BASE_URL = `http://127.0.0.1:${PORT}`;

export default defineConfig({
  testDir: __dirname,
  fullyParallel: true,
  forbidOnly: Boolean(process.env.CI),
  retries: 0,
  workers: 1,
  timeout: 120_000,
  expect: { timeout: 12_000 },
  reporter: [["list"]],
  outputDir: path.join(__dirname, "test-results"),
  use: {
    baseURL: BASE_URL,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    video: "off",
    colorScheme: "dark",
    viewport: { width: 1440, height: 900 },
    launchOptions: { args: ["--disable-features=LocalNetworkAccessChecks"] },
  },
  projects: [
    { name: "chromium", use: { ...devices["Desktop Chrome"], viewport: { width: 1440, height: 900 } } },
  ],
  webServer: {
    command: `npx next dev -H 127.0.0.1 -p ${PORT}`,
    url: BASE_URL,
    reuseExistingServer: false,
    // Concurrent workstreams can make a cold Next dev compile slow; give the
    // readiness probe enough headroom instead of flaking on shared CPU.
    timeout: 360_000,
    cwd: root,
    stdout: "pipe",
    stderr: "pipe",
    env: {
      ...process.env,
      KEEL_BRIDGE_URL: "http://127.0.0.1:8739",
      // Throwaway local token, never a provider key or production credential.
      KEEL_BRIDGE_TOKEN: process.env.KEEL_E2E_BRIDGE_TOKEN ?? "local-e2e-bridge-token",
      KEEL_DIST_DIR: ".next-e2e-onboarding",
      NEXT_TELEMETRY_DISABLED: "1",
    } as Record<string, string>,
  },
});
