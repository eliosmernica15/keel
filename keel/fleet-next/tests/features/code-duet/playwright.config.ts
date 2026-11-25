import { defineConfig, devices } from "@playwright/test";
import path from "node:path";

// Workstream-owned config: separate port, separate Next dist dir and a single
// worker so this suite never collides with the lead's :3200 preview or the
// shared :3300 e2e suite.
const PORT = 3401;
const BASE_URL = `http://127.0.0.1:${PORT}`;
const ROOT = path.resolve(__dirname, "../../.."); // keel/fleet-next

export default defineConfig({
  testDir: __dirname,
  testMatch: "*.spec.ts",
  fullyParallel: false,
  workers: 1,
  forbidOnly: Boolean(process.env.CI),
  retries: 0,
  // Headroom for shared CI/dev machines where several feature suites and
  // their Next dev servers compile concurrently.
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
    cwd: ROOT,
    stdout: "pipe",
    stderr: "pipe",
    env: {
      ...process.env,
      KEEL_BRIDGE_URL: "http://127.0.0.1:8791",
      KEEL_BRIDGE_TOKEN: "local-code-duet-test-token",
      KEEL_DIST_DIR: ".next-code-duet-tests",
      NEXT_TELEMETRY_DISABLED: "1",
    } as Record<string, string>,
  },
});
