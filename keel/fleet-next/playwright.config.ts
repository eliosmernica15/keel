import { defineConfig, devices } from "@playwright/test";

// Dedicated port and dedicated Next build output. KEEL_DIST_DIR is supported
// by next.config.mjs so this server cannot corrupt the production `.next`
// build used by the lead's preview server on :3200.
const PORT = 3300;
const BASE_URL = `http://127.0.0.1:${PORT}`;

export default defineConfig({
  testDir: "./tests/e2e",
  fullyParallel: true,
  forbidOnly: Boolean(process.env.CI),
  retries: 0,
  workers: process.env.CI ? 1 : 3,
  timeout: 90_000,
  expect: { timeout: 12_000 },
  reporter: [
    ["list"],
    ["html", { outputFolder: "tests/e2e/report", open: "never" }],
  ],
  outputDir: "tests/e2e/test-results",
  use: {
    baseURL: BASE_URL,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    video: "off",
    colorScheme: "dark",
    viewport: { width: 1440, height: 900 },
    // Chromium 159's Local Network Access check blocks Next's dev HMR
    // WebSocket on loopback; disable only that check for this test browser.
    launchOptions: { args: ["--disable-features=LocalNetworkAccessChecks"] },
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"], viewport: { width: 1440, height: 900 } },
    },
  ],
  webServer: {
    command: `npx next dev -H 127.0.0.1 -p ${PORT}`,
    url: BASE_URL,
    reuseExistingServer: false,
    timeout: 180_000,
    cwd: __dirname,
    stdout: "pipe",
    stderr: "pipe",
    env: {
      ...process.env,
      KEEL_BRIDGE_URL: "http://127.0.0.1:8739",
      KEEL_BRIDGE_TOKEN: "keel-frontend-verify-2026",
      KEEL_DIST_DIR: ".next-e2e",
      NEXT_TELEMETRY_DISABLED: "1",
    } as Record<string, string>,
  },
});
