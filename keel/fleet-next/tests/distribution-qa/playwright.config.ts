import { defineConfig, devices } from "@playwright/test";
import path from "node:path";

// Dedicated port and server for Agent G distribution QA. Does not touch the
// lead's :3200/:3000, the E2E :3300, or the a11y :3302 servers.
const PORT = Number(process.env.KEEL_QA_PORT || 3310);
const BASE_URL = `http://127.0.0.1:${PORT}`;

export default defineConfig({
  testDir: __dirname,
  timeout: 60_000,
  expect: { timeout: 10_000 },
  workers: 1, // service-worker and cache tests must not share a browser profile
  retries: 0,
  reporter: [["list"]],
  outputDir: path.join(__dirname, "test-results"),
  use: {
    baseURL: BASE_URL,
    viewport: { width: 1280, height: 900 },
    colorScheme: "light",
    screenshot: "only-on-failure",
    trace: "off",
    launchOptions: { args: ["--disable-features=LocalNetworkAccessChecks"] },
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"], viewport: { width: 1280, height: 900 } } }],
  webServer: {
    command: `node tests/distribution-qa/server.mjs`,
    url: `${BASE_URL}/download.html`,
    reuseExistingServer: process.env.KEEL_QA_REUSE === "1",
    timeout: 30_000,
    cwd: path.resolve(__dirname, "../.."),
    stdout: "pipe",
    stderr: "pipe",
    env: { ...process.env } as Record<string, string>,
  },
});
