import { defineConfig, devices } from "@playwright/test";
import path from "node:path";

// Independent QA accessibility suite. Dedicated port/build dir so it never
// interferes with the lead's :3200 preview or the E2E suite's :3300 server.
const PORT = 3302;
const BASE_URL = `http://127.0.0.1:${PORT}`;

export default defineConfig({
  testDir: __dirname,
  timeout: 90_000,
  expect: { timeout: 12_000 },
  workers: 2,
  retries: 0,
  reporter: [["list"]],
  outputDir: path.join(__dirname, "test-results"),
  use: {
    baseURL: BASE_URL,
    colorScheme: "dark",
    viewport: { width: 1440, height: 900 },
    screenshot: "only-on-failure",
    trace: "retain-on-failure",
    launchOptions: { args: ["--disable-features=LocalNetworkAccessChecks"] },
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: {
    command: `npx next dev -H 127.0.0.1 -p ${PORT}`,
    url: BASE_URL,
    // Reuse a QA-owned server when one was started manually (KEEL_A11Y_REUSE=1),
    // so repeated audit runs do not pay a cold Next compile under parallel load.
    reuseExistingServer: process.env.KEEL_A11Y_REUSE === "1",
    timeout: 300_000,
    cwd: path.resolve(__dirname, "../.."),
    stdout: "pipe",
    stderr: "pipe",
    env: {
      ...process.env,
      KEEL_BRIDGE_URL: "http://127.0.0.1:8739",
      KEEL_BRIDGE_TOKEN: process.env.KEEL_E2E_BRIDGE_TOKEN ?? "local-e2e-bridge-token",
      KEEL_DIST_DIR: ".next-a11y",
      NEXT_TELEMETRY_DISABLED: "1",
    } as Record<string, string>,
  },
});
