import { defineConfig, devices } from "@playwright/test";
import path from "node:path";

// Agent D — final QA verification of the /download page (D-DP-01..).
// Dedicated port (3311) and the real static site tree via the distribution
// QA server (keel/site + vercel.json semantics). Never modifies site files.
const PORT = Number(process.env.KEEL_QA_PORT || 3311);
const BASE_URL = `http://127.0.0.1:${PORT}`;

export default defineConfig({
  testDir: __dirname,
  timeout: 60_000,
  expect: { timeout: 10_000 },
  workers: 1,
  retries: 0,
  reporter: [["list"]],
  outputDir: path.join(__dirname, "results", "pw"),
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
    env: { ...process.env, KEEL_QA_PORT: String(PORT) } as Record<string, string>,
  },
});
