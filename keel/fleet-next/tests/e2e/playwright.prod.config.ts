import { defineConfig, devices } from "@playwright/test";
import path from "node:path";

const BASE_URL = "http://127.0.0.1:3300";

export default defineConfig({
  testDir: __dirname,
  timeout: 60_000,
  expect: { timeout: 10_000 },
  reporter: [["list"], ["html", { outputFolder: path.join(__dirname, "report"), open: "never" }]],
  outputDir: path.join(__dirname, "test-results"),
  use: {
    baseURL: BASE_URL,
    colorScheme: "dark",
    viewport: { width: 1440, height: 900 },
    screenshot: "off",
    trace: "off",
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"], viewport: { width: 1440, height: 900 } },
    },
  ],
  webServer: {
    // The primary dev config reuses .next-e2e, so rebuild before starting.
    command: "npx next build && npx next start -H 127.0.0.1 -p 3300",
    url: BASE_URL,
    reuseExistingServer: false,
    timeout: 120_000,
    cwd: path.resolve(__dirname, "../.."),
    env: {
      ...process.env,
      KEEL_BRIDGE_URL: "http://127.0.0.1:8739",
      // Throwaway local-bridge token for tests only (see playwright.config.ts).
      KEEL_BRIDGE_TOKEN: process.env.KEEL_E2E_BRIDGE_TOKEN ?? "local-e2e-bridge-token",
      KEEL_DIST_DIR: ".next-e2e",
    } as Record<string, string>,
  },
});
