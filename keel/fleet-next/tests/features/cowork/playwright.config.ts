import { defineConfig, devices } from "@playwright/test";
import path from "node:path";

// Isolated server for the Cowork feature suite. Never uses port 3200 or the
// shared `.next` build directory used by the lead's preview server.
const PORT = 3355;
const BASE_URL = `http://127.0.0.1:${PORT}`;
const APP_ROOT = path.resolve(__dirname, "../../..");

export default defineConfig({
  // Only this feature's specs run under the documented command. The APP_ROOT
  // below is the Next.js project root for the isolated web server, not the
  // test collection root (other feature configs use __dirname too).
  testDir: __dirname,
  fullyParallel: true,
  forbidOnly: Boolean(process.env.CI),
  retries: 0,
  workers: 2,
  timeout: 90_000,
  expect: { timeout: 12_000 },
  reporter: [["list"]],
  outputDir: path.join(__dirname, "test-results"),
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
  webServer: {
    command: `npx next dev -H 127.0.0.1 -p ${PORT}`,
    url: BASE_URL,
    reuseExistingServer: false,
    timeout: 180_000,
    cwd: APP_ROOT,
    stdout: "pipe",
    stderr: "pipe",
    env: {
      ...process.env,
      KEEL_BRIDGE_URL: "http://127.0.0.1:8739",
      KEEL_BRIDGE_TOKEN: "local-cowork-test-token",
      KEEL_DIST_DIR: ".next-cowork-tests",
      NEXT_TELEMETRY_DISABLED: "1",
    } as Record<string, string>,
  },
});
