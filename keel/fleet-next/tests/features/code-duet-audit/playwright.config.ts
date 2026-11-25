import { defineConfig, devices } from "@playwright/test";
import path from "node:path";

// Agent E audit suite. Dedicated port and Next dist dir so it never collides
// with the owner's :3401 code-duet suite or the shared :3200/:3300 servers.
const PORT = 3402;
const BASE_URL = `http://127.0.0.1:${PORT}`;
const ROOT = path.resolve(__dirname, "../../..");

export default defineConfig({
  testDir: __dirname,
  testMatch: "*.spec.ts",
  fullyParallel: false,
  workers: 1,
  forbidOnly: Boolean(process.env.CI),
  retries: 0,
  timeout: 150_000,
  expect: { timeout: 15_000 },
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
    timeout: 180_000,
    cwd: ROOT,
    stdout: "pipe",
    stderr: "pipe",
    env: {
      ...process.env,
      KEEL_BRIDGE_URL: "http://127.0.0.1:8792",
      KEEL_BRIDGE_TOKEN: "local-code-duet-audit-token",
      KEEL_DIST_DIR: ".next-code-duet-audit",
      NEXT_TELEMETRY_DISABLED: "1",
    } as Record<string, string>,
  },
});
