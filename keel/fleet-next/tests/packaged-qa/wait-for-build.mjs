#!/usr/bin/env node
/* Agent G — wait until the in-flight electron-builder run finishes and the
 * unpacked EXE actually contains the Fleet Next runtime. */
import { execFileSync } from "node:child_process";
import { statSync, existsSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const KEEL = resolve(__dirname, "../../..");
const EXE = join(KEEL, "dist", "win-unpacked", "Keel.exe");
const NEXT_SERVER = join(KEEL, "dist", "win-unpacked", "resources", "fleet-next", "server.js");
const BASELINE = new Date("2026-11-25T02:30:00").getTime();
const DEADLINE = Date.now() + 12 * 60 * 1000;

function builderRunning() {
  try {
    const out = execFileSync("powershell", ["-NoProfile", "-Command",
      "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*electron-builder --win*' -and ($_.Name -eq 'cmd.exe' -or $_.Name -eq 'node.exe') } | ForEach-Object { $_.ProcessId }",
    ], { encoding: "utf8", timeout: 20000 });
    return out.split(/\r?\n/).map((s) => s.trim()).filter(Boolean).length > 0;
  } catch { return false; }
}

while (Date.now() < DEADLINE) {
  const running = builderRunning();
  const hasNext = existsSync(NEXT_SERVER);
  let fresh = false;
  try { fresh = statSync(EXE).mtimeMs > BASELINE; } catch { /* absent */ }
  console.log(`[${new Date().toISOString()}] builder=${running} fleetNext=${hasNext} exeFresh=${fresh}`);
  if (!running && hasNext && fresh) {
    console.log("READY");
    process.exit(0);
  }
  await new Promise((r) => setTimeout(r, 10000));
}
console.log("TIMEOUT");
process.exit(1);
