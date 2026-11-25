import { defineConfig, devices } from "@playwright/test";
import path from "node:path";

// Agent G — independent frontend acceptance. Dedicated port, dedicated Next
// build output and dedicated result directory so this suite never collides
// with the lead's :3200 preview or any other workstream's runner.
const PORT = Number(process.env.KEEL_ACCEPTANCE_PORT || 3351);
const BASE_URL = `http://127.0.0.1:${PORT}`;

export default defineConfig({
  testDir: __dirname,
  timeout: 90_000,
  expect: { timeout: 12_000 },
  fullyParallel: false,
  workers: 1,
  retries: 0,
  forbidOnly: Boolean(process.env.CI),
  reporter: [["list"]],
  outputDir: path.join(__dirname, "test-results"),
  use: {
    baseURL: BASE_URL,
    colorScheme: "dark",
    viewport: { width: 1440, height: 900 },
    screenshot: "only-on-failure",
    trace: "retain-on-failure",
    video: "off",
    acceptDownloads: true,
    launchOptions: { args: ["--disable-features=LocalNetworkAccessChecks"] },
  },
  projects: [
    { name: "chromium", use: { ...devices["Desktop Chrome"], viewport: { width: 1440, height: 900 } } },
  ],
  webServer: {
    command: `npx next dev -H 127.0.0.1 -p ${PORT}`,
    url: BASE_URL,
    reuseExistingServer: false,
    timeout: 240_000,
    cwd: path.resolve(__dirname, "../.."),
    stdout: "pipe",
    stderr: "pipe",
    env: {
      ...process.env,
      KEEL_BRIDGE_URL: "http://127.0.0.1:8739",
      KEEL_BRIDGE_TOKEN: process.env.KEEL_E2E_BRIDGE_TOKEN ?? "local-acceptance-bridge-token",
      KEEL_DIST_DIR: ".next-acceptance-final",
      NEXT_TELEMETRY_DISABLED: "1",
    } as Record<string, string>,
  },
});
