#!/usr/bin/env node
/* assert-ui-entrypoints.js — packaging/pathing assertion for Keel's UI roots.
 *
 * READ-ONLY. No dependencies beyond Node built-ins. Run from anywhere:
 *
 *   node keel/desktop-app/scripts/assert-ui-entrypoints.js
 *   node keel/desktop-app/scripts/assert-ui-entrypoints.js \
 *        --resources "C:\path\to\Keel\win-unpacked\resources"
 *
 * It asserts the CURRENT, deliberately-unchanged entry-point contract:
 *   Electron  -> KEEL_UI_DIR = uiRoot()  = <resources>/site (packaged)
 *   Tauri     -> frontendDist           = <repo>/desktop/ui
 *   keel serve-> UI_DIR                 = KEEL_UI_DIR or <root>/desktop/ui
 *   /fleet    -> <root>/desktop/fleet (classic, via keel.fleet.routes)
 *   public /app -> <root>/site/app.html (static mirror)
 *   fleet-next is NOT a static UI root and must NOT be wired into any of them.
 *
 * The optional --resources mode inspects an ACTUAL unpacked Electron build.
 * It never launches or modifies it. A production binary being present is not
 * evidence that it was run: this script only checks the shipped path layout.
 */

import { readFileSync, existsSync, statSync } from "fs";
import { dirname, join, resolve, relative, isAbsolute } from "path";
import { fileURLToPath } from "url";
import { createHash } from "crypto";

const __dirname = dirname(fileURLToPath(import.meta.url));
const DESKTOP_APP = resolve(__dirname, "..");
const KEEL = resolve(DESKTOP_APP, "..");

let resourcesArg = null;
for (let i = 2; i < process.argv.length; i++) {
  if (process.argv[i] === "--resources") resourcesArg = process.argv[++i];
  else if (process.argv[i] === "-h" || process.argv[i] === "--help") {
    console.log("usage: node assert-ui-entrypoints.js [--resources <unpacked-resources-dir>]");
    process.exit(0);
  }
}
const resourcesDir = resourcesArg || process.env.KEEL_DIST_RESOURCES || null;

const results = [];
function check(name, ok, detail) {
  results.push({ name, ok: !!ok, detail });
  console.log(`${ok ? "PASS" : "FAIL"}  ${name}${detail ? ` — ${detail}` : ""}`);
}
function info(name, detail) {
  console.log(`INFO  ${name}${detail ? ` — ${detail}` : ""}`);
}
function read(rel) {
  try { return readFileSync(resolve(KEEL, rel), "utf8"); }
  catch (e) { check(`read ${rel}`, false, e.message); return ""; }
}
function fileExists(rel) {
  const p = isAbsolute(rel) ? rel : resolve(KEEL, rel);
  return existsSync(p) && statSync(p).isFile();
}
function dirExists(p) {
  return existsSync(p) && statSync(p).isDirectory();
}

console.log("Keel UI entry-point assertion");
console.log(`repo (keel/): ${KEEL}`);
console.log(`resources:    ${resourcesDir || "(not supplied — source-tree checks only)"}`);
console.log("");

/* ------------------------------------------------------------------ Electron */
const mainJs = read("desktop-app/main.js");
const pkg = JSON.parse(read("desktop-app/package.json") || "{}");

const uiRootBody = (mainJs.match(/function uiRoot\(\)\s*\{([\s\S]*?)\n\}/) || [])[1] || "";
const uiRootOrder = [...uiRootBody.matchAll(/join\(res,\s*([^)]+)\)/g)]
  .map((m) => m[1].trim());
check("Electron uiRoot() candidate order is site, desktop/ui, ui",
  JSON.stringify(uiRootOrder.slice(0, 3)) ===
    JSON.stringify(['"site"', '"desktop", "ui"', '"ui"']),
  uiRootOrder.slice(0, 3).join(" -> "));
check("Electron gates each candidate on index.html",
  /existsSync\(join\(c,\s*"index\.html"\)\)/.test(mainJs));
check("Electron feeds uiRoot() into the sidecar as KEEL_UI_DIR",
  /KEEL_UI_DIR\s*=\s*uiRoot\(\)/.test(mainJs));
check("Electron loads the sidecar over 127.0.0.1 (not a static file root)",
  /loadURL\(`http:\/\/127\.0\.0\.1:/.test(mainJs));

const siteResource = (pkg.build?.extraResources || []).find((r) => r.to === "site");
check("electron-builder ships ../site -> resources/site",
  !!siteResource && siteResource.from === "../site",
  siteResource ? `${siteResource.from} -> ${siteResource.to}` : "missing");
check("source site/index.html + site/app.html both exist",
  fileExists("site/index.html") && fileExists("site/app.html"));
info("Why this matters",
  "site/index.html satisfies uiRoot() first; the bridge then serves site/app.html at '/'.");

if (resourcesDir) {
  const res = resolve(resourcesDir);
  const chosen = join(res, "site");
  check("--resources dir exists", dirExists(res), res);
  check("packaged resources/site/index.html present", fileExists(join(res, "site", "index.html")));
  check("packaged resources/site/app.html present", fileExists(join(res, "site", "app.html")));
  const packagedRoot = dirExists(join(res, "site")) && fileExists(join(res, "site", "index.html"))
    ? "site" : null;
  check("packaged uiRoot() resolves to resources/site", packagedRoot === "site",
    packagedRoot ? join(res, packagedRoot) : "no candidate with index.html");

  // Dependency-free app.asar main.js integrity check (asar = 4B header size,
  // JSON header, then file bytes at 16 + headerSize + offset).
  const asar = join(res, "app.asar");
  if (fileExists(asar)) {
    try {
      const buf = readFileSync(asar);
      const headerSize = buf.readUInt32LE(12);
      const header = JSON.parse(buf.slice(16, 16 + headerSize).toString("utf8"));
      const entry = header.files?.["main.js"];
      if (!entry || entry.files) throw new Error("app.asar has no top-level main.js");
      const shipped = buf.slice(16 + headerSize + Number(entry.offset),
                                16 + headerSize + Number(entry.offset) + Number(entry.size));
      const src = readFileSync(resolve(KEEL, "desktop-app", "main.js"));
      const sha = (b) => createHash("sha256").update(b).digest("hex");
      check("packaged app.asar main.js matches source main.js",
        sha(shipped) === sha(src),
        `${sha(shipped).slice(0, 12)} vs ${sha(src).slice(0, 12)}`);
    } catch (e) {
      check("app.asar main.js check", false, e.message);
    }
  } else {
    info("app.asar", "not present in supplied resources; skipped integrity check");
  }
}

/* --------------------------------------------------------------------- Tauri */
const tauriText = read("desktop/src-tauri/tauri.conf.json");
const tauri = JSON.parse(tauriText || "{}");
const frontendDist = tauri.build?.frontendDist || "";
const tauriUi = resolve(KEEL, "desktop", "src-tauri", frontendDist);
check("Tauri frontendDist resolves to desktop/ui",
  frontendDist === "../ui" && relative(KEEL, tauriUi).replace(/\\/g, "/") === "desktop/ui",
  `${frontendDist} -> ${relative(KEEL, tauriUi)}`);
check("Tauri UI root has index.html", fileExists(join(tauriUi, "index.html")));
check("Tauri config does not reference fleet-next", !/fleet-next/i.test(tauriText));

/* --------------------------------------------------------------- keel serve */
const webapp = read("src/keel/webapp.py");
check("webapp UI_DIR defaults to <bundle>/desktop/ui",
  /_BUNDLE_ROOT\s*\/\s*"desktop"\s*\/\s*"ui"/.test(webapp));
check("webapp honours KEEL_UI_DIR override", /os\.environ\.get\("KEEL_UI_DIR"\)/.test(webapp));
check("webapp '/' prefers app.html then index.html",
  /UI_DIR\s*\/\s*"app\.html"[\s\S]{0,160}UI_DIR\s*\/\s*"index\.html"/.test(webapp));
check("webapp '/app' also prefers app.html then index.html",
  /path in \("\/app", "\/app\.html"\)/.test(webapp));
check("classic /fleet is dispatched by keel.fleet.routes",
  /_fleet_routes\.dispatch_get/.test(webapp));
const routes = read("src/keel/fleet/routes.py");
check("classic Fleet UI root is desktop/fleet",
  /"desktop"\s*\/\s*"fleet"/.test(routes));
check("webapp does not reference fleet-next", !/fleet-next/i.test(webapp));

/* --------------------------------------------------------------- parity gate */
check("Electron build config does not ship/repoint to fleet-next",
  !/fleet-next/i.test(JSON.stringify(pkg.build)));
check("Electron main.js does not reference fleet-next", !/fleet-next/i.test(mainJs));
check("fleet-next exists (candidate, not shipped)",
  dirExists(resolve(KEEL, "fleet-next")));
const nextCfg = read("fleet-next/next.config.mjs");
check("fleet-next is NOT a static export (needs a Next server + BFF)",
  !/output\s*:\s*["']export["']/.test(nextCfg));
check("fleet-next BFF route exists",
  fileExists(resolve(KEEL, "fleet-next", "app", "api", "bridge", "[...path]", "route.ts")));
info("Gate G4/G6",
  "Repointing a shipped renderer to fleet-next needs a real package build + parity gate; this script fails if that repoint is attempted.");

/* --------------------------------------------------------------------- summary */
const failed = results.filter((r) => !r.ok);
console.log("");
console.log(`SUMMARY: ${results.length - failed.length}/${results.length} checks passed`);
if (failed.length) {
  console.error("FAILED: " + failed.map((f) => f.name).join("; "));
  process.exit(1);
}
console.log("All current entry-point assertions hold. No shipped renderer was changed.");
