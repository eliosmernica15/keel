import { defineConfig } from "@playwright/test";
import os from "os";
import path from "path";

// ---------------------------------------------------------------------------
// Bridge integration verification harness.
//
// REAL stack (genuine round-trips, no mocks):
//   * real Python fleet bridge started from THIS worktree's src/keel
//   * real Next.js BFF (/api/bridge/[...path]) with a throwaway token
//
// FIXTURE stack (deterministic header/error inspection only; every test that
// uses it is labelled FIXTURE in its title):
//   * mock_bridge.py  — echoes received headers / returns canned statuses
//   * an unconfigured Next BFF — to exercise bridge_unavailable honestly
//
// Ports are deliberately distinct from every other suite in this repo.
// ---------------------------------------------------------------------------

const REAL_BRIDGE_PORT = 8797;
const MOCK_BRIDGE_PORT = 8798;
const NEXT_PORT = 3311;
const MOCK_NEXT_PORT = 3312;
const UNCONFIGURED_NEXT_PORT = 3313;

// A throwaway credential. It is not, and never was, a provider key or a
// production secret. The real bridge is launched with this exact token.
const TOKEN = process.env.KEEL_BRIDGE_INTEGRATION_TOKEN ?? "bridge-int-throwaway-4f8c2a91";

const STATE_DIR = path.join(os.tmpdir(), "keel-bridge-integration-state");
const WORKSPACE_DIR = path.join(os.tmpdir(), "keel-bridge-integration-workspace");

const nextEnv = (bridgeUrl: string, token: string, distDir: string) => ({
  ...process.env,
  KEEL_BRIDGE_URL: bridgeUrl,
  KEEL_BRIDGE_TOKEN: token,
  KEEL_DIST_DIR: distDir,
  KEEL_INTEGRATION_WORKSPACE: WORKSPACE_DIR,
  NEXT_TELEMETRY_DISABLED: "1",
} as Record<string, string>);

export default defineConfig({
  testDir: ".",
  testMatch: "*.spec.ts",
  fullyParallel: false,
  forbidOnly: Boolean(process.env.CI),
  retries: 0,
  workers: 1,
  timeout: 120_000,
  expect: { timeout: 15_000 },
  reporter: [["list"]],
  outputDir: "test-results",
  use: {
    baseURL: `http://127.0.0.1:${NEXT_PORT}`,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    video: "off",
    launchOptions: { args: ["--disable-features=LocalNetworkAccessChecks"] },
  },
  projects: [{ name: "chromium", use: { browserName: "chromium" } }],
  webServer: [
    {
      name: "real python fleet bridge (from this worktree)",
      command: `python tests/bridge-integration/bridge_server.py --port ${REAL_BRIDGE_PORT} --token ${TOKEN} --state "${STATE_DIR}"`,
      url: `http://127.0.0.1:${REAL_BRIDGE_PORT}/__bridge_ready`,
      reuseExistingServer: false,
      timeout: 120_000,
      cwd: __dirname.replace(/[/\\]tests[/\\]bridge-integration$/, ""),
      stdout: "pipe",
      stderr: "pipe",
    },
    {
      name: "FIXTURE mock upstream bridge",
      command: `python tests/bridge-integration/mock_bridge.py --port ${MOCK_BRIDGE_PORT}`,
      url: `http://127.0.0.1:${MOCK_BRIDGE_PORT}/__bridge_ready`,
      reuseExistingServer: false,
      timeout: 60_000,
      cwd: __dirname.replace(/[/\\]tests[/\\]bridge-integration$/, ""),
      stdout: "pipe",
      stderr: "pipe",
    },
    {
      name: "real Next BFF -> real bridge",
      command: `npx next dev -H 127.0.0.1 -p ${NEXT_PORT}`,
      url: `http://127.0.0.1:${NEXT_PORT}`,
      reuseExistingServer: false,
      timeout: 240_000,
      cwd: __dirname.replace(/[/\\]tests[/\\]bridge-integration$/, ""),
      stdout: "pipe",
      stderr: "pipe",
      env: nextEnv(`http://127.0.0.1:${REAL_BRIDGE_PORT}`, TOKEN, ".next-bridge-int-real"),
    },
    {
      name: "FIXTURE Next BFF -> mock upstream",
      command: `npx next dev -H 127.0.0.1 -p ${MOCK_NEXT_PORT}`,
      url: `http://127.0.0.1:${MOCK_NEXT_PORT}`,
      reuseExistingServer: false,
      timeout: 240_000,
      cwd: __dirname.replace(/[/\\]tests[/\\]bridge-integration$/, ""),
      stdout: "pipe",
      stderr: "pipe",
      env: nextEnv(`http://127.0.0.1:${MOCK_BRIDGE_PORT}`, TOKEN, ".next-bridge-int-mock"),
    },
    {
      name: "FIXTURE Next BFF with no bridge config",
      command: `npx next dev -H 127.0.0.1 -p ${UNCONFIGURED_NEXT_PORT}`,
      url: `http://127.0.0.1:${UNCONFIGURED_NEXT_PORT}`,
      reuseExistingServer: false,
      timeout: 240_000,
      cwd: __dirname.replace(/[/\\]tests[/\\]bridge-integration$/, ""),
      stdout: "pipe",
      stderr: "pipe",
      env: nextEnv("", "", ".next-bridge-int-unconfigured"),
    },
  ],
});
