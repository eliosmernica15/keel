// Build-artifact preparation + launcher for the standalone Next runtime — the
// exact process shape Electron starts (server.js, not `next start`).
// No source file is modified; .next/static and public are copied into the
// traced standalone output as Next's packaging step requires.

import fs from "node:fs";
import path from "node:path";
import { spawn } from "node:child_process";

const root = process.cwd();
const dist = path.join(root, process.env.KEEL_DIST_DIR || ".next-packaged-compat");
const standalone = path.join(dist, "standalone");

// With a custom distDir the traced server embeds that distDir name in its
// config, so it resolves /_next/static from <standalone>/<distDirName>/static.
// Default builds use <standalone>/.next/static. Copy to both: harmless, and
// keeps this harness valid for either packaging layout.
const sourceStatic = path.join(dist, "static");
const staticTargets = [
  path.join(standalone, ".next", "static"),
  path.join(standalone, path.basename(dist), "static"),
];
for (const target of staticTargets) {
  fs.cpSync(sourceStatic, target, { recursive: true });
}
fs.cpSync(path.join(root, "public"), path.join(standalone, "public"), { recursive: true });

const child = spawn(process.execPath, [path.join(standalone, "server.js")], {
  cwd: standalone,
  env: {
    ...process.env,
    HOSTNAME: "127.0.0.1",
    PORT: process.env.KEEL_COMPAT_STANDALONE_PORT || "3473",
    NODE_ENV: "production",
    NEXT_TELEMETRY_DISABLED: "1",
  },
  stdio: "inherit",
});

for (const signal of ["SIGINT", "SIGTERM"]) {
  process.on(signal, () => { if (child.exitCode === null) child.kill(signal); });
}
child.on("exit", (code, signal) => {
  process.exit(code ?? (signal ? 1 : 0));
});
