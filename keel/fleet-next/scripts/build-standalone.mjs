/**
 * Reproducible Fleet Next production build for Electron.
 *
 *    npm run build:standalone
 *
 * Optional: KEEL_DIST_DIR=<dir> isolates parallel builds (e.g. from several
 * agents) without touching the development `.next` directory.
 *
 * Produces:
 *   <distDir>/standalone/                 runnable traced Next server
 *   <distDir>/standalone/<distDir>/static copied client bundle
 *   <distDir>/standalone/public/           copied PWA assets (fonts/icons/sw)
 *   docs/standalone-asset-inventory.json   exact file/size/hash inventory
 *   docs/standalone-build.log              full build stdout/stderr
 *
 * Security invariants enforced here:
 *   - bridge env is NOT baked into the build: sentinel values are supplied to
 *     `next build` and must not appear anywhere in the traced output;
 *   - the generated standalone server is hardened to bind 127.0.0.1 only.
 */
import { spawnSync } from "node:child_process";
import crypto from "node:crypto";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const appDir = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const distDirName = process.env.KEEL_DIST_DIR || ".next";
const distDir = path.resolve(appDir, distDirName);
const distRel = path.relative(appDir, distDir).split(path.sep).join("/");
const standaloneDir = path.join(distDir, "standalone");
const docsDir = path.join(appDir, "docs");
const inventoryPath = path.join(docsDir, "standalone-asset-inventory.json");
const buildLogPath = path.join(docsDir, "standalone-build.log");

const BUILD_SENTINEL_URL = "http://127.0.0.1:1";
const BUILD_SENTINEL_TOKEN = "keel-build-time-sentinel-do-not-ship";
const LOOPBACK_LINE = "const hostname = '127.0.0.1'"; // patched below

const checks = [];
function check(name, ok, detail) {
  checks.push({ name, pass: Boolean(ok), detail: String(detail) });
  if (!ok) console.error(`  FAIL ${name}: ${detail}`);
  else console.log(`  ok   ${name}`);
}
function requireFile(rel, label) {
  const abs = path.join(standaloneDir, rel);
  check(label, fs.existsSync(abs) && fs.statSync(abs).isFile(), rel);
  return abs;
}
function sha256(buf) {
  return crypto.createHash("sha256").update(buf).digest("hex");
}
function walk(dir) {
  const out = [];
  if (!fs.existsSync(dir)) return out;
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const abs = path.join(dir, entry.name);
    if (entry.isDirectory()) out.push(...walk(abs));
    else if (entry.isFile()) out.push(abs);
  }
  return out;
}

console.log(`Fleet Next standalone build — distDir=${distRel}`);
console.log(`app=${appDir}`);

// 1. Build with deliberately fake bridge credentials. If Next ever inlines
//    process.env.KEEL_BRIDGE_* at build time, the sentinel appears in output
//    and the build fails instead of shipping a stale token.
const nextBin = path.join(appDir, "node_modules", "next", "dist", "bin", "next");
check("next binary present", fs.existsSync(nextBin), path.relative(appDir, nextBin));
if (!fs.existsSync(nextBin)) process.exit(1);

const buildEnv = {
  ...process.env,
  NODE_ENV: "production",
  KEEL_BRIDGE_URL: BUILD_SENTINEL_URL,
  KEEL_BRIDGE_TOKEN: BUILD_SENTINEL_TOKEN,
};
console.log(`Running: node ${path.relative(appDir, nextBin)} build (sentinel bridge env)`);
const build = spawnSync(process.execPath, [nextBin, "build"], {
  cwd: appDir,
  env: buildEnv,
  encoding: "utf8",
  maxBuffer: 32 * 1024 * 1024,
});
const buildOutput = `${build.stdout || ""}${build.stderr || ""}`;
fs.mkdirSync(docsDir, { recursive: true });
fs.writeFileSync(buildLogPath, buildOutput, "utf8");
process.stdout.write(buildOutput);
check("next build exit code", build.status === 0, `exit=${build.status}`);
if (build.status !== 0) process.exit(1);

// 2. Assemble the standalone deployment. Next deliberately does not copy
//    .next/static or public into .next/standalone; Electron needs both.
check("standalone dir produced", fs.existsSync(standaloneDir), distRel + "/standalone");
if (!fs.existsSync(standaloneDir)) process.exit(1);

fs.cpSync(path.join(distDir, "static"), path.join(standaloneDir, distRel, "static"), {
  recursive: true,
  force: true,
});
fs.cpSync(path.join(appDir, "public"), path.join(standaloneDir, "public"), {
  recursive: true,
  force: true,
});
console.log("Copied .next/static and public/ into standalone/");

// 3. Harden the generated entrypoint: Next defaults to 0.0.0.0. Force
//    loopback in the artifact itself so no launching process can widen it.
const serverJsPath = path.join(standaloneDir, "server.js");
const originalServerJs = fs.readFileSync(serverJsPath, "utf8");
const knownHostnameLines = [
  "const hostname = process.env.HOSTNAME || '0.0.0.0'",
  'const hostname = process.env.HOSTNAME || "0.0.0.0"',
];
const matchedHostnameLine = knownHostnameLines.find((line) => originalServerJs.includes(line));
check("standalone hostname binding line found", Boolean(matchedHostnameLine), matchedHostnameLine || "unknown template");
if (!matchedHostnameLine) process.exit(1);
const patchedServerJs = originalServerJs.replace(
  matchedHostnameLine,
  `${LOOPBACK_LINE} // KEEL: loopback-only, enforced by scripts/build-standalone.mjs`,
);
fs.writeFileSync(serverJsPath, patchedServerJs, "utf8");
check(
  "standalone binds loopback only",
  patchedServerJs.includes(LOOPBACK_LINE) &&
    !patchedServerJs.includes("process.env.HOSTNAME") &&
    !patchedServerJs.includes("'0.0.0.0'"),
  LOOPBACK_LINE,
);

// 4. Required assets / routes / manifests.
requireFile("server.js", "standalone server entry");
const staticRoot = `${distRel}/static`;
requireFile(`${distRel}/BUILD_ID`, "standalone BUILD_ID");
check(
  "client JS chunks present",
  walk(path.join(standaloneDir, staticRoot)).some((f) => f.endsWith(".js")),
  staticRoot,
);
check(
  "client CSS present",
  walk(path.join(standaloneDir, staticRoot)).some((f) => f.endsWith(".css")),
  staticRoot,
);
for (const asset of [
  "public/sw.js",
  "public/icon.svg",
  "public/icon-192.png",
  "public/icon-512.png",
  "public/fonts/inter-400.woff2",
  "public/fonts/jetbrains-mono-400.woff2",
  "public/fonts/space-grotesk-400.woff2",
]) {
  requireFile(asset, `public ${path.basename(asset)}`);
}
for (const dep of ["next", "react", "react-dom"]) {
  requireFile(`node_modules/${dep}/package.json`, `traced ${dep}`);
}
const bridgeRouteRel = `${distRel}/server/app/api/bridge/[...path]/route.js`;
const bridgeRoute = requireFile(bridgeRouteRel, "BFF route handler (compiled)");
requireFile(`${distRel}/server/app/manifest.webmanifest/route.js`, "PWA manifest route handler (compiled)");

const routesManifest = JSON.parse(fs.readFileSync(path.join(distDir, "routes-manifest.json"), "utf8"));
check(
  "BFF dynamic route registered",
  routesManifest.dynamicRoutes?.some((r) => r.page === "/api/bridge/[...path]"),
  "routes-manifest.json dynamicRoutes",
);
check(
  "PWA manifest route registered",
  routesManifest.staticRoutes?.some((r) => r.page === "/manifest.webmanifest"),
  "routes-manifest.json staticRoutes",
);
const cspHeader = routesManifest.headers?.find((h) => h.headers?.some((x) => x.key === "Content-Security-Policy"));
const csp = cspHeader?.headers?.find((x) => x.key === "Content-Security-Policy")?.value ?? "";
check("production CSP preserved", csp.includes("default-src 'self'") && !csp.includes("unsafe-eval"), csp);
check(
  "nopwn/no-referrer headers preserved",
  Boolean(cspHeader?.headers?.some((h) => h.key === "X-Content-Type-Options" && h.value === "nosniff")) &&
    Boolean(cspHeader?.headers?.some((h) => h.key === "Referrer-Policy" && h.value === "no-referrer")),
  "headers() in next.config.mjs",
);
check(
  "standalone output selected",
  JSON.parse(fs.readFileSync(path.join(distDir, "required-server-files.json"), "utf8")).config?.output === "standalone",
  "required-server-files.json output",
);

// 5. Prove the bridge credentials are runtime env, not build constants.
const compiledRoute = fs.readFileSync(bridgeRoute, "utf8");
check(
  "compiled BFF reads URL from process.env at runtime",
  compiledRoute.includes("process.env.KEEL_BRIDGE_URL"),
  "process.env.KEEL_BRIDGE_URL in route.js",
);
check(
  "compiled BFF reads token from process.env at runtime",
  compiledRoute.includes("process.env.KEEL_BRIDGE_TOKEN"),
  "process.env.KEEL_BRIDGE_TOKEN in route.js",
);
check("build sentinel URL not inlined", !compiledRoute.includes(BUILD_SENTINEL_URL), BUILD_SENTINEL_URL);
check("build sentinel token not inlined", !compiledRoute.includes(BUILD_SENTINEL_TOKEN), "sentinel token absent");
const envLocalPath = path.join(appDir, ".env.local");
if (fs.existsSync(envLocalPath)) {
  const match = fs.readFileSync(envLocalPath, "utf8").match(/^\s*KEEL_BRIDGE_TOKEN\s*=\s*(.*?)\s*$/m);
  const realToken = match?.[1];
  if (realToken && realToken.length > 3 && !realToken.startsWith("your-")) {
    check("developer token not inlined", !compiledRoute.includes(realToken), "value compared but never printed");
  }
}
const straySentinel = walk(standaloneDir).find((f) => {
  if (!/\.(js|json|html|txt|map)$/.test(f)) return false;
  try {
    const text = fs.readFileSync(f, "utf8");
    return text.includes(BUILD_SENTINEL_TOKEN);
  } catch {
    return false;
  }
});
check("no sentinel token anywhere in standalone tree", !straySentinel, straySentinel ? path.relative(standaloneDir, straySentinel) : "clean");

// 6. Exact inventory (paths are relative to <distDir>/standalone; no secrets).
const files = walk(standaloneDir)
  .map((abs) => {
    const rel = path.relative(standaloneDir, abs).split(path.sep).join("/");
    const buf = fs.readFileSync(abs);
    let category = "other";
    if (rel === "server.js") category = "serverEntry";
    else if (rel.startsWith(`${staticRoot}/`)) category = "staticAssets";
    else if (rel.startsWith("public/")) category = "publicAssets";
    else if (rel.startsWith("node_modules/")) category = "tracedNodeModules";
    else if (rel.includes("/server/app/api/") || rel.includes("/server/app/manifest.webmanifest/"))
      category = "routeHandlers";
    else if (rel.startsWith(`${distRel}/`)) category = "serverBuild";
    return { path: rel, category, bytes: buf.length, sha256: sha256(buf) };
  })
  .sort((a, b) => (a.path < b.path ? -1 : a.path > b.path ? 1 : 0));

const categorySummary = {};
for (const f of files) {
  const s = (categorySummary[f.category] ||= { files: 0, bytes: 0 });
  s.files += 1;
  s.bytes += f.bytes;
}
const nextVersion = JSON.parse(
  fs.readFileSync(path.join(appDir, "node_modules", "next", "package.json"), "utf8"),
).version;
const inventory = {
  schema: "keel/fleet-next/standalone-asset-inventory/v1",
  generatedAt: new Date().toISOString(),
  app: "keel/fleet-next",
  distDir: distRel,
  standaloneRoot: `${distRel}/standalone`,
  buildId: fs.readFileSync(path.join(distDir, "BUILD_ID"), "utf8").trim(),
  nextVersion,
  nodeVersion: process.version,
  platform: process.platform,
  bridgeEnvPolicy: {
    source: "process.env at server runtime (never inlined at build time)",
    variables: ["KEEL_BRIDGE_URL", "KEEL_BRIDGE_TOKEN"],
    bind: "127.0.0.1 (hardened in server.js by build script)",
  },
  checks,
  categorySummary,
  totalFiles: files.length,
  totalBytes: files.reduce((n, f) => n + f.bytes, 0),
  files,
};
fs.writeFileSync(inventoryPath, JSON.stringify(inventory, null, 2) + "\n", "utf8");
console.log(
  `\nInventory: ${path.relative(appDir, inventoryPath)} — ${files.length} files, ` +
    `${inventory.totalBytes} bytes (${(inventory.totalBytes / 1024 / 1024).toFixed(2)} MiB)`,
);
const failed = checks.filter((c) => !c.pass);
if (failed.length) {
  console.error(`\n${failed.length} check(s) failed; see ${path.relative(appDir, inventoryPath)}`);
  process.exit(1);
}
console.log("All standalone build checks passed.");
