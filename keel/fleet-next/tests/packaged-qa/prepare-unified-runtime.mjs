#!/usr/bin/env node
/* Agent G — assemble a COMPLETE standalone runtime for the dev-mode unified
 * Electron probe. Copies only build OUTPUT (never source/config) into this
 * test folder's tmp/ directory so KEEL_RENDERER_UNIFIED_DIR can point at it.
 *
 *   node tests/packaged-qa/prepare-unified-runtime.mjs
 */
import { cpSync, mkdirSync, rmSync, existsSync, writeFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const KEEL = resolve(__dirname, "../../..");
const NEXT = join(KEEL, "fleet-next");
const OUT = join(__dirname, "tmp", "unified-runtime");

for (const p of [
  join(NEXT, ".next", "standalone", "server.js"),
  join(NEXT, ".next", "static"),
  join(NEXT, "public"),
]) {
  if (!existsSync(p)) throw new Error(`missing build output: ${p}`);
}

rmSync(OUT, { recursive: true, force: true });
mkdirSync(OUT, { recursive: true });
cpSync(join(NEXT, ".next", "standalone"), OUT, { recursive: true });
cpSync(join(NEXT, ".next", "static"), join(OUT, ".next", "static"), { recursive: true });
cpSync(join(NEXT, "public"), join(OUT, "public"), { recursive: true });
writeFileSync(
  join(__dirname, "qa-logs", "unified-runtime-path.txt"),
  OUT + "\n",
);
console.log(OUT);
