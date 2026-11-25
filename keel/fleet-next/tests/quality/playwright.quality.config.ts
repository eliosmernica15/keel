import { defineConfig, devices } from "@playwright/test";
import path from "node:path";

// Agent F shared QA suite (finalization round). Dedicated port and build dir:
// never touches the lead's :3000/:3200, the E2E :3300 or the a11y :3302.
const PORT = 3306;
const BASE_URL = `http://127.0.0.1:${PORT}`;

export default defineConfig({
  testDir: __dirname,
  timeout: 90_000,
  expect: { timeout: 12_000 },
  workers: 1,
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
    reuseExistingServer: process.env.KEEL_QUALITY_REUSE === "1",
    timeout: 300_000,
    cwd: path.resolve(__dirname, "../.."),
    stdout: "pipe",
    stderr: "pipe",
    env: {
      ...process.env,
      KEEL_BRIDGE_URL: "http://127.0.0.1:8739",
      KEEL_BRIDGE_TOKEN: process.env.KEEL_E2E_BRIDGE_TOKEN ?? "local-e2e-bridge-token",
      KEEL_DIST_DIR: ".next-quality",
      NEXT_TELEMETRY_DISABLED: "1",
    } as Record<string, string>,
  },
});
