import { defineConfig, devices } from "@playwright/test";
import path from "node:path";

// Isolated port + isolated Next build so this workstream never disturbs the
// lead's preview server or the shared E2E server.
const PORT = 3317;
const BASE_URL = `http://127.0.0.1:${PORT}`;

export default defineConfig({
  testDir: __dirname,
  testMatch: "*.spec.ts",
  timeout: 90_000,
  expect: { timeout: 12_000 },
  fullyParallel: false,
  workers: 1,
  retries: 0,
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
    cwd: path.resolve(__dirname, "../../.."),
    stdout: "pipe",
    stderr: "pipe",
    env: {
      ...process.env,
      KEEL_BRIDGE_URL: "http://127.0.0.1:8739",
      // Throwaway local token for tests only — never a provider credential.
      KEEL_BRIDGE_TOKEN: process.env.KEEL_E2E_BRIDGE_TOKEN ?? "local-e2e-bridge-token",
      KEEL_DIST_DIR: ".next-caps-settings",
      NEXT_TELEMETRY_DISABLED: "1",
    } as Record<string, string>,
  },
});
