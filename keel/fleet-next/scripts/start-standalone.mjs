/**
 * Launch the traced standalone server for Electron (or manual smoke tests).
 *
 *    npm run start:standalone            # http://127.0.0.1:3000
 *    PORT=3310 npm run start:standalone
 *
 * Bridge credentials are read from the *launching process environment* only.
 * This script deliberately never reads .env.local and never embeds a token.
 */
import { spawn } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const appDir = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const distDir = path.resolve(appDir, process.env.KEEL_DIST_DIR || ".next");
const server = path.join(distDir, "standalone", "server.js");
if (!fs.existsSync(server)) {
  console.error(`Missing ${path.relative(appDir, server)} — run npm run build:standalone first.`);
  process.exit(1);
}
const env = {
  ...process.env,
  // The artifact itself is also hardened; belt and braces at launch time.
  HOSTNAME: "127.0.0.1",
  PORT: process.env.PORT || "3000",
};
const child = spawn(process.execPath, [server], {
  cwd: path.dirname(server),
  env,
  stdio: "inherit",
});
for (const sig of ["SIGINT", "SIGTERM"]) {
  process.on(sig, () => child.kill(sig));
}
child.on("exit", (code, signal) => process.exit(signal ? 1 : (code ?? 1)));
