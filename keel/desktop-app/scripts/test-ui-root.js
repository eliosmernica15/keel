#!/usr/bin/env node
/* test-ui-root.js — behavioural unit test for desktop-app/main.js::uiRoot().
 *
 * Executes the ACTUAL uiRoot() source extracted from main.js against a mocked
 * filesystem and environment. No Electron, no network, no build required:
 *
 *   node keel/desktop-app/scripts/test-ui-root.js
 *
 * This is what proves the renderer-precedence fix, not just a regex check:
 * a packaged layout containing BOTH resources/desktop/ui and resources/site
 * must resolve to the full local UI, and the restricted mirror must only be
 * reachable through the explicit rollback profile.
 */

import { readFileSync } from "fs";
import { dirname, join, resolve, sep } from "path";
import { fileURLToPath } from "url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const mainSource = readFileSync(resolve(__dirname, "..", "main.js"), "utf8");
const fnSource = (mainSource.match(/function uiRoot\(\)\s*\{([\s\S]*?)\n\}/) || [])[1];
if (!fnSource) {
  console.error("FAIL  could not extract uiRoot() from main.js");
  process.exit(1);
}

let existing = new Set();
const results = [];
function check(name, ok, detail) {
  results.push({ name, ok: !!ok });
  console.log(`${ok ? "PASS" : "FAIL"}  ${name}${detail ? ` — ${detail}` : ""}`);
}

// Rebuild the function with injected join/existsSync/process. `join` is the
// real Node path.join so Windows separators behave exactly as in production.
// A fresh instance is created per case so each environment stays isolated.
function makeUIRoot(env, resources) {
  existing = new Set(Object.keys(resources).filter((k) => resources[k]));
  const fakeProcess = { resourcesPath: "R", env };
  return new Function(
    "join", "existsSync", "process",
    `return function uiRoot() {${fnSource}};`,
  )(join, (p) => existing.has(String(p).replace(/\//g, sep)), fakeProcess);
}

console.log("Keel uiRoot() behavioural test (source-extracted, no Electron)");
console.log("");

const local = join("R", "desktop", "ui", "index.html");
const mirror = join("R", "site", "index.html");
const legacy = join("R", "ui", "index.html");
const custom = join("C", "custom-ui", "index.html");

// Case 1 — packaged layout: both roots shipped. Local MUST win.
let got = makeUIRoot({}, { [local]: true, [mirror]: true })();
check("packaged: local desktop/ui wins over site",
  got === join("R", "desktop", "ui"), String(got));

// Case 2 — only the mirror exists (the old shipped layout). Must NOT fall back.
got = makeUIRoot({}, { [mirror]: true })();
check("mirror-only layout: default is null, never site", got === null, String(got));

// Case 3 — explicit rollback profile restores legacy mirror behaviour.
got = makeUIRoot({ KEEL_UI_PROFILE: "mirror" }, { [mirror]: true })();
check("KEEL_UI_PROFILE=mirror: rollback to site", got === join("R", "site"), String(got));

// Case 4 — case-insensitive profile value.
got = makeUIRoot({ KEEL_UI_PROFILE: "MIRROR" }, { [mirror]: true })();
check("KEEL_UI_PROFILE is case-insensitive", got === join("R", "site"), String(got));

// Case 5 — advanced explicit override, only when it has index.html.
got = makeUIRoot({ KEEL_UI_DIR: join("C", "custom-ui") }, { [custom]: true, [local]: true })();
check("explicit KEEL_UI_DIR overrides local root", got === join("C", "custom-ui"), String(got));
got = makeUIRoot({ KEEL_UI_DIR: join("C", "custom-ui") }, { [local]: true })();
check("bogus KEEL_UI_DIR is ignored (no index.html)", got === join("R", "desktop", "ui"), String(got));

// Case 6 — legacy local layout and empty dev layout.
got = makeUIRoot({}, { [legacy]: true })();
check("legacy resources/ui still resolves", got === join("R", "ui"), String(got));
got = makeUIRoot({}, {})();
check("no resources: null (dev branch uses repo desktop/ui)", got === null, String(got));

const failed = results.filter((r) => !r.ok);
console.log("");
console.log(`SUMMARY: ${results.length - failed.length}/${results.length} uiRoot() cases passed`);
if (failed.length) {
  console.error("FAILED: " + failed.map((f) => f.name).join("; "));
  process.exit(1);
}
console.log("Renderer precedence verified: full local UI by default, mirror rollback-only.");
