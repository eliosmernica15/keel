import { defineConfig } from "@playwright/test";
import path from "node:path";

// Agent G — packaged Electron QA. No webServer: every test either reads source
// or launches its own process and is self-cleaning.
const PORT = Number(process.env.KEEL_QA_PORT || 3311);

export default defineConfig({
  testDir: __dirname,
  testMatch: /.*\.spec\.ts$/,
  timeout: 90_000,
  expect: { timeout: 10_000 },
  workers: 1,
  retries: 0,
  reporter: [["list"]],
  outputDir: path.join(__dirname, "test-results"),
  use: {
    baseURL: `http://127.0.0.1:${PORT}`,
    screenshot: "only-on-failure",
    trace: "off",
  },
  projects: [{ name: "source-and-runtime" }],
});
