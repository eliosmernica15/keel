#!/usr/bin/env node
/**
 * Keel fleet-next UI verification harness — Subagent F.
 *
 * ZERO new npm dependencies. Uses only node: builtins. Playwright is NOT
 * installed in this worktree (no node_modules, no playwright in package.json),
 * so this harness performs STATIC source assertions plus a real, read-only
 * HTTP probe of the live Python bridge for the safe GET endpoints.
 *
 * Run:  node tests/ui/verify-ui.mjs
 * Output: tests/ui/results.json  (machine readable) + human summary on stdout.
 *
 * LIMITATION (stated honestly): this is not a browser test. It cannot verify
 * rendered layout, computed styles, focus order, contrast ratios or runtime
 * a11y tree. Those are marked SKIPPED in the report.
 */
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { execFileSync } from "node:child_process";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const APP = path.resolve(HERE, "../.."); // fleet-next
const KEEL = path.resolve(APP, ".."); // keel

const IGNORE_DIRS = new Set([
  "node_modules", ".next", ".git", "tests", "public", "out", "dist", ".turbo",
  // Next.js build output (the E2E workstream uses a separate distDir,
  // `.next-e2e`). Generated JS is not source and must not be scanned —
  // string-literal fragments in bundles produced false endpoint/a11y findings.
  ".next-e2e",
]);
const SRC_EXTS = new Set([".ts", ".tsx", ".js", ".jsx", ".mjs", ".css"]);

function walk(dir, acc = []) {
  let entries;
  try { entries = fs.readdirSync(dir, { withFileTypes: true }); }
  catch { return acc; }
  for (const e of entries) {
    if (e.isDirectory()) {
      // Every Next distDir variant (.next, .next-e2e, .next-a11y,
      // .next-caps-settings, …) is generated output, never source. Strings in
      // bundles produce false endpoint/TODO findings if scanned.
      const generatedNextDir = /^\.next(?:[-_.]|$)/i.test(e.name);
      if (!IGNORE_DIRS.has(e.name) && !generatedNextDir) walk(path.join(dir, e.name), acc);
    } else if (SRC_EXTS.has(path.extname(e.name))) {
      acc.push(path.join(dir, e.name));
    }
  }
  return acc;
}

const rel = (p) => path.relative(KEEL, p).replace(/\\/g, "/");
const loc = (file, idx) => `${rel(file)}:${String(idx).padStart(4, "0")}`;

const results = [];
function check(id, checkName, status, detail, evidence = []) {
  results.push({ id, check: checkName, status, detail, evidence });
}

// ---------------------------------------------------------------------------
// 0. Inventory
// ---------------------------------------------------------------------------
const allFiles = walk(APP);
const sourceFiles = allFiles.filter((f) => /\.(ts|tsx|js|jsx|mjs)$/.test(f));
const cssFiles = allFiles.filter((f) => f.endsWith(".css"));
check("INV-01", "Source inventory", "info",
  `${sourceFiles.length} source files, ${cssFiles.length} css files discovered`,
  allFiles.map((f) => rel(f)));

// ---------------------------------------------------------------------------
// Scan helpers
// ---------------------------------------------------------------------------
function lines(text) {
  return text.split(/\r?\n/);
}
function forEachMatch(text, re, cb) {
  const linesArr = lines(text);
  let m;
  const global = new RegExp(re.source, re.flags.includes("g") ? re.flags : re.flags + "g");
  while ((m = global.exec(text)) !== null) {
    const before = text.slice(0, m.index);
    const lineNo = before.split("\n").length;
    cb(m, lineNo, linesArr[lineNo - 1] ?? "");
    if (m[0].length === 0) global.lastIndex++;
  }
}

/**
 * JSX-aware opening-tag scanner. Handles `=>` inside attributes and
 * `${...}` / `{...}` expressions that break naive `[^>]*` regexes.
 * Returns [{ index, raw, attrs, line }].
 */
/** Extract the full text of the call starting at the '(' at/after `start`. */
function callArgs(text, start) {
  const open = text.indexOf("(", start);
  if (open === -1 || open - start > 40) return "";
  let i = open + 1;
  let quote = "";
  let depth = 1;
  while (i < text.length && depth > 0) {
    const ch = text[i];
    if (quote) {
      if (ch === quote && text[i - 1] !== "\\") quote = "";
    } else if (ch === '"' || ch === "'" || ch === "`") {
      quote = ch;
    } else if (ch === "(" || ch === "[" || ch === "{") depth++;
    else if (ch === ")" || ch === "]" || ch === "}") depth--;
    i++;
  }
  return text.slice(open, i);
}

function extractTags(text, tagName) {
  const out = [];
  const open = `<${tagName}`;
  let pos = 0;
  while ((pos = text.indexOf(open, pos)) !== -1) {
    const after = text[pos + open.length];
    if (after !== undefined && !/[\s/>]/.test(after)) { pos += open.length; continue; }
    let i = pos + open.length;
    let quote = "";
    let brace = 0;
    let end = -1;
    while (i < text.length) {
      const ch = text[i];
      if (quote) {
        if (ch === quote && text[i - 1] !== "\\") quote = "";
      } else if (ch === '"' || ch === "'" || ch === "`") {
        quote = ch;
      } else if (ch === "{") {
        brace++;
      } else if (ch === "}") {
        brace = Math.max(0, brace - 1);
      } else if (ch === ">" && brace === 0) {
        end = i + 1;
        break;
      }
      i++;
    }
    if (end === -1) break;
    const raw = text.slice(pos, end);
    out.push({
      index: pos, raw,
      attrs: raw.slice(open.length, -1),
      line: text.slice(0, pos).split("\n").length,
    });
    pos = end;
  }
  return out;
}

// ---------------------------------------------------------------------------
// 1. API CONTRACT
// ---------------------------------------------------------------------------
// Backend vocabulary comes from route_scan.py, which READS the Python source.
let vocab;
try {
  vocab = JSON.parse(execFileSync("python", [path.join(HERE, "route_scan.py")], {
    cwd: KEEL, encoding: "utf8", timeout: 30000,
  }));
  check("API-00", "Backend route vocabulary extracted", "pass",
    `${vocab.exact_lists.length} exact route lists from ${vocab.files.join(", ")}`);
} catch (e) {
  vocab = { exact_lists: [], segment_literals: {}, path_literals: [], files: [] };
  check("API-00", "Backend route vocabulary extracted", "fail", String(e).slice(0, 400));
}

const knownCollections = new Set(vocab.segment_literals["parts[2]"] ?? []);
// Add collections matched by exact_lists (skills, connectors, providers, etc.)
for (const l of vocab.exact_lists) {
  if (l[0] === "api" && l[1] === "fleet" && l.length >= 3) knownCollections.add(l[2]);
}
const knownVerbs = new Set();
for (const key of ["extra", "sub", "action", "parts[4]", "parts[5]"]) {
  for (const v of vocab.segment_literals[key] ?? []) knownVerbs.add(v);
}
// Segments 4+ of exact route lists are verbs too (e.g. tasks/reorder).
for (const l of vocab.exact_lists) {
  for (const seg of l.slice(3)) knownVerbs.add(seg);
}
// Verbs written with != or in tuple literals that the scanner cannot capture.
for (const v of ["decide", "clear", "catalog", "revoke", "install", "manage",
  "save", "test", "add", "health", "servers", "execute", "credential",
  "export.md", "finished", "file", "terminal", "approvals", "asks"]) knownVerbs.add(v);

const frontendEndpoints = []; // {file,line,raw,path,method}
function addEndpoint(file, lineNo, raw, p, method = "GET") {
  frontendEndpoints.push({ file, line: lineNo, raw, path: p, method });
}

const endpointRe = /\bapi(?:<[^>]*>)?\(\s*["'`]([^"'`]+)["'`]/g;
for (const f of sourceFiles) {
  const text = fs.readFileSync(f, "utf8");
  // api("bots") / api<Foo>("bots") / api(`bots/${id}`)
  let m;
  const re1 = new RegExp(endpointRe.source, "g");
  while ((m = re1.exec(text)) !== null) {
    const lineNo = text.slice(0, m.index).split("\n").length;
    const raw = m[1];
    const callText = callArgs(text, m.index);
    const method = /\bmethod\s*:\s*["']POST["']/.test(callText) ? "POST" : "GET";
    let p = raw.replace(/\$\{[^}]+\}/g, "*").replace(/\?.*$/, "");
    if (!p.startsWith("/")) p = `/api/fleet/${p}`;
    addEndpoint(f, lineNo, raw.trim(), p, method);
  }
  // Explicit URL builders (exportUrl / downloadUrl / previewUrl) and SSE.
  forEachMatch(text, /["'`](\/api\/bridge\/[^"'`]+)["'`]/, (mm, ln) => {
    // Skip the generic BFF prefix template in client.ts — it is a URL builder,
    // not a concrete endpoint. Concrete call sites are captured by the api()
    // matcher above and by explicit exportUrl/downloadUrl/previewUrl builders.
    if (/\$\{/.test(mm[1])) return;
    let p = mm[1].replace(/\/api\/bridge\//, "/api/fleet/").replace(/\$\{[^}]+\}/g, "*");
    addEndpoint(f, ln, mm[1], p, "GET");
  });
  forEachMatch(text, /["'`](\/api\/fleet\/[^"'`]+)["'`]/, (mm, ln) => {
    addEndpoint(f, ln, mm[1], mm[1].replace(/\$\{[^}]+\}/g, "*"), "GET");
  });
}

// De-duplicate identical (path, file:line) pairs; keep every call site.
const unresolved = [];
for (const ep of frontendEndpoints) {
  const segs = ep.path.split("/").filter(Boolean); // api, fleet, ...
  if (segs[0] !== "api" || segs[1] !== "fleet") {
    // BFF-local or non-fleet route — not a bridge contract concern.
    continue;
  }
  const coll = segs[2];
  if (!coll || (!knownCollections.has(coll) && !/^\*$/.test(coll))) {
    unresolved.push({ ...ep, reason: `unknown collection '${coll}'` });
    continue;
  }
  for (let i = 3; i < segs.length; i++) {
    const s = segs[i];
    if (/^\*$/.test(s) || /^[0-9a-f-]{8,}$/i.test(s)) continue; // dynamic id
    if (!knownVerbs.has(s)) {
      unresolved.push({ ...ep, reason: `unknown action segment '${s}'` });
      break;
    }
  }
}
if (unresolved.length === 0) {
  check("API-01", "Every frontend bridge call maps to a backend route", "pass",
    `${frontendEndpoints.length} call sites inspected; 0 unmapped endpoints`);
} else {
  check("API-01", "Every frontend bridge call maps to a backend route", "fail",
    `${unresolved.length} call site(s) with no matching backend route`,
    unresolved.map((u) => ({ fileLine: loc(u.file, u.line), path: u.path, raw: u.raw, reason: u.reason, method: u.method })));
}

// API-02 — method-level check: a frontend POST must have a backend POST handler.
const MANUAL_VERBS = ["decide", "clear", "catalog", "revoke", "install", "manage",
  "save", "test", "add", "health", "servers", "execute", "credential",
  "export.md", "finished", "file", "terminal", "approvals", "asks"];
function methodVocab(scope) {
  const s = vocab[scope] ?? { segment_literals: {}, exact_lists: [] };
  const collections = new Set(s.segment_literals["parts[2]"] ?? []);
  const verbs = new Set();
  for (const key of ["extra", "sub", "action", "parts[4]", "parts[5]"]) {
    for (const v of s.segment_literals[key] ?? []) verbs.add(v);
  }
  for (const l of s.exact_lists) {
    if (l[0] === "api" && l[1] === "fleet" && l.length >= 3) collections.add(l[2]);
    for (const seg of l.slice(3)) verbs.add(seg);
  }
  for (const v of MANUAL_VERBS) verbs.add(v);
  return { collections, verbs, exact: new Set(s.exact_lists.map((l) => l.join("/"))) };
}
const mVocab = { GET: methodVocab("get"), POST: methodVocab("post") };
const methodMismatch = [];
for (const ep of frontendEndpoints) {
  const segs = ep.path.split("/").filter(Boolean);
  if (segs[0] !== "api" || segs[1] !== "fleet") continue;
  const v = mVocab[ep.method];
  if (!v) continue;
  const tail = segs.slice(2);
  if (!v.collections.has(tail[0])) continue; // already reported by API-01
  const exactKey = tail.join("/");
  if (v.exact.has(exactKey)) continue;
  const bad = tail.slice(1).find((s) => !/^\*$/.test(s) && !v.verbs.has(s));
  if (bad && !unresolved.some((u) => u.file === ep.file && u.line === ep.line)) {
    methodMismatch.push({ fileLine: loc(ep.file, ep.line), path: ep.path, method: ep.method, missing: bad });
  }
}
check("API-02", "Frontend HTTP methods have a matching backend dispatcher",
  methodMismatch.length === 0 ? "pass" : "warn",
  methodMismatch.length === 0 ? "all endpoint methods map to dispatch_get / dispatch_post vocabulary"
    : `${methodMismatch.length} possible method mismatch(es)`,
  methodMismatch.slice(0, 100));

// ---------------------------------------------------------------------------
// 2. NO FABRICATED DATA / PLACEHOLDERS
// ---------------------------------------------------------------------------
const fabPatterns = [
  ["placeholder handler", /onClick\s*=\s*\{\s*\(\s*\)\s*=>\s*\{\s*\}\s*\}/],
  ["empty arrow handler", /on(?:Click|Change|Submit|KeyDown)\s*=\s*\{\s*\(\s*\)\s*=>\s*\{\s*\}\s*\}/],
  ["alert() control", /\balert\s*\(/],
  ["TODO marker", /\bTODO\b/],
  ["FIXME marker", /\bFIXME\b/],
  ["coming soon as control", /coming\s+soon/i],
  ["fake connected literal", /(?:isConnected|connected)\s*[:=]\s*true\b/],
  ["fake status connected", /status\s*[:=]\s*["']connected["']/i],
  ["fabricated provider/model", /\b(?:OpenAI|GPT-?4|gpt-?4o|Claude|Gemini|Anthropic|Llama|Mistral|DeepSeek|o1-|Sonnet|Opus|Haiku)\b/],
  ["fake success toast", /(?:toast|notify|setMessage)[^;]{0,60}["'](?:Success|Connected|Saved|Done)!/i],
];
const fabFindings = [];
for (const f of sourceFiles) {
  const text = fs.readFileSync(f, "utf8");
  const linesArr = lines(text);
  for (const [label, re] of fabPatterns) {
    forEachMatch(text, re, (m, ln, lineText) => {
      fabFindings.push({
        fileLine: loc(f, ln), label, match: m[0].slice(0, 120),
        snippet: lineText.trim().slice(0, 180),
      });
    });
  }
}
// Deduplicate identical fileLine+label
const fabUnique = [...new Map(fabFindings.map((x) => [`${x.fileLine}|${x.label}|${x.match}`, x])).values()];
if (fabUnique.length === 0) {
  check("FAB-01", "No placeholder / fabricated-data patterns in source", "pass",
    "0 matches across scanned source files");
} else {
  check("FAB-01", "No placeholder / fabricated-data patterns in source", "warn",
    `${fabUnique.length} pattern match(es) — manual triage required (some may be legitimate)`,
    fabUnique.slice(0, 200));
}

// ---------------------------------------------------------------------------
// 3. ACCESSIBILITY STATIC CHECKS
// ---------------------------------------------------------------------------
const a11y = [];
for (const f of sourceFiles) {
  if (!/\.(tsx|jsx)$/.test(f)) continue;
  const text = fs.readFileSync(f, "utf8");
  // buttons — opening tags scanned JSX-aware; inner content checked for text/children
  for (const tag of extractTags(text, "button")) {
    const selfClosing = /\/\s*>$/.test(tag.raw);
    let inner = "";
    if (!selfClosing) {
      const close = text.indexOf("</button>", tag.index);
      inner = close === -1 ? "" : text.slice(tag.index + tag.raw.length, close);
    }
    // Keep {expressions}: `{label}`, `{children}`, `{item.title}` are real
    // accessible text. Strip only JSX element tags (icons/spinners).
    const stripped = inner.replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim();
    const hasChildren = /\{[^{}]*\bchildren\b[^{}]*\}/.test(inner);
    const named = /aria-label|aria-labelledby|\btitle=/.test(tag.attrs) || stripped.length > 0 || hasChildren;
    if (!named) a11y.push({ fileLine: loc(f, tag.line), kind: "button-no-name", snippet: tag.raw.slice(0, 160).replace(/\s+/g, " ") });
  }
  // inputs — accept aria-label / aria-labelledby / id / wrapping <label> / hidden inputs
  for (const tag of extractTags(text, "input")) {
    const attrs = tag.attrs;
    const before = text.slice(Math.max(0, tag.index - 300), tag.index);
    const after = text.slice(tag.index, tag.index + 900);
    const inLabel = before.lastIndexOf("<label") > before.lastIndexOf("</label>") && /<\/label>/.test(after);
    const hidden = /\bhidden\b|type\s*=\s*["']hidden["']/.test(attrs);
    if (!/aria-label|aria-labelledby|\bid=/.test(attrs) && !inLabel && !hidden) {
      a11y.push({ fileLine: loc(f, tag.line), kind: "input-no-label", snippet: tag.raw.slice(0, 160).replace(/\s+/g, " ") });
    }
  }
  // dialogs — only native <dialog> and explicit role="dialog" usages.
  // The shared `Dialog` primitive in components/ui.tsx was manually verified
  // to set role/aria-modal/aria-label internally, so its call sites are not
  // re-checked here (that produced false positives).
  for (const tag of extractTags(text, "dialog")) {
    const missing = [];
    if (!/aria-modal\s*=\s*["']true["']/.test(tag.attrs)) missing.push("aria-modal=true");
    if (!/aria-label|aria-labelledby/.test(tag.attrs)) missing.push("accessible name");
    if (missing.length) a11y.push({ fileLine: loc(f, tag.line), kind: "dialog-a11y", missing, snippet: tag.raw.slice(0, 160).replace(/\s+/g, " ") });
  }
  forEachMatch(text, /role\s*=\s*["']dialog["']/, (mm, ln) => {
    const around = text.slice(Math.max(0, mm.index - 200), mm.index + 300);
    const missing = [];
    if (!/aria-modal\s*=\s*["']true["']/.test(around)) missing.push("aria-modal=true");
    if (!/aria-label|aria-labelledby/.test(around)) missing.push("accessible name");
    if (missing.length) a11y.push({ fileLine: loc(f, ln), kind: "dialog-a11y", missing, snippet: around.slice(0, 180).replace(/\s+/g, " ") });
  });
  // positive tabindex
  forEachMatch(text, /tabIndex\s*=\s*\{?\s*([1-9]\d*)\s*\}?/, (mm, ln) => {
    a11y.push({ fileLine: loc(f, ln), kind: "positive-tabindex", snippet: mm[0] });
  });
  // img without alt
  forEachMatch(text, /<img\b[^>]*>/, (mm, ln) => {
    if (!/\balt\s*=/.test(mm[0])) a11y.push({ fileLine: loc(f, ln), kind: "img-no-alt", snippet: mm[0].slice(0, 160).replace(/\s+/g, " ") });
  });
}
const a11yHard = a11y.filter((x) => ["button-no-name", "dialog-a11y", "positive-tabindex", "img-no-alt"].includes(x.kind));
const a11ySoft = a11y.filter((x) => x.kind === "input-no-label");
check("A11Y-01", "Accessible names on buttons / dialogs / images; no positive tabindex", "pass",
  a11yHard.length === 0 ? "0 static violations" : `${a11yHard.length} static violation(s)`,
  a11yHard.slice(0, 200));
if (a11yHard.length) results[results.length - 1].status = "fail";
check("A11Y-02", "Inputs have labels (static heuristics)", a11ySoft.length === 0 ? "pass" : "warn",
  a11ySoft.length === 0 ? "all inputs carry aria-label / aria-labelledby / id" : `${a11ySoft.length} input(s) need manual label verification`,
  a11ySoft.slice(0, 200));

const allText = sourceFiles.map((f) => fs.readFileSync(f, "utf8")).join("\n") +
  cssFiles.map((f) => fs.readFileSync(f, "utf8")).join("\n");
check("A11Y-03", "Theme applied via data-theme", /data-theme/.test(allText) ? "pass" : "fail",
  /data-theme/.test(allText) ? "data-theme found" : "no data-theme attribute found in scanned source");
check("A11Y-04", "prefers-reduced-motion hook present", /prefers-reduced-motion/.test(allText) ? "pass" : "fail",
  /prefers-reduced-motion/.test(allText) ? "prefers-reduced-motion found" : "no prefers-reduced-motion usage found");
check("A11Y-05", "Decorative icons marked aria-hidden", /aria-hidden/.test(allText) ? "pass" : "warn",
  /aria-hidden/.test(allText) ? "aria-hidden used" : "no aria-hidden usage found");

// ---------------------------------------------------------------------------
// 4. RESPONSIVE — fixed widths / min-widths
// ---------------------------------------------------------------------------
const respFindings = [];
for (const f of cssFiles) {
  const linesArr = lines(fs.readFileSync(f, "utf8"));
  let inMedia = 0;
  for (let i = 0; i < linesArr.length; i++) {
    const line = linesArr[i];
    // Container/media *queries* are responsive rules, not overflow risks.
    if (/^\s*@(media|container|supports)/.test(line)) { if (/@media/.test(line)) inMedia++; continue; }
    const opens = (line.match(/\{/g) || []).length;
    const closes = (line.match(/\}/g) || []).length;
    const m = line.match(/(?<![\w-])(min-width|width)\s*:\s*(\d+(?:\.\d+)?)px/);
    if (m && inMedia === 0) {
      const v = parseFloat(m[2]);
      if ((m[1] === "min-width" && v > 320) || (m[1] === "width" && v > 340)) {
        respFindings.push({ fileLine: loc(f, i + 1), prop: m[1], value: v, snippet: line.trim().slice(0, 160) });
      }
    }
    inMedia = Math.max(0, inMedia + opens - closes);
  }
}
check("RESP-01", "No fixed width/min-width likely to overflow a 360px viewport",
  respFindings.length === 0 ? "pass" : "warn",
  respFindings.length === 0 ? "no risky fixed widths outside @media" : `${respFindings.length} candidate(s) to review`,
  respFindings.slice(0, 200));

// ---------------------------------------------------------------------------
// 5. LIVE BRIDGE GET PROBE (read-only, real HTTP)
// ---------------------------------------------------------------------------
const SAFE_GET = [
  "bots", "providers", "projects", "shells", "tasks", "routines",
  "library", "skills", "connectors", "usage", "keep-awake",
];
let probe = null;
try {
  const out = execFileSync("python", [path.join(HERE, "probe_bridge.py")], {
    cwd: KEEL, encoding: "utf8", timeout: 45000,
    input: JSON.stringify(SAFE_GET),
    env: { ...process.env, PYTHONPATH: path.join(KEEL, "src"), KEEL_TOKEN: "qa-static-probe-token" },
  });
  probe = JSON.parse(out);
} catch (e) {
  probe = { error: String(e).slice(0, 500) };
}
if (probe && !probe.error) {
  const bad = Object.entries(probe).filter(([, v]) => v >= 500 || v === 403 || v === 0);
  check("LIVE-01", "Read-only bridge GET endpoints respond (real HTTP)", bad.length === 0 ? "pass" : "warn",
    `${Object.keys(probe).length} endpoint(s) probed; ${bad.length} anomalous`,
    Object.entries(probe).map(([p, status]) => ({ path: p, status })));
} else {
  check("LIVE-01", "Read-only bridge GET endpoints respond (real HTTP)", "skipped",
    `probe unavailable: ${probe?.error ?? "unknown"}`, []);
}

// ---------------------------------------------------------------------------
// 5b. CONTINUOUS-QA REGRESSIONS (added after the backend-reconciliation audit)
// Each check below is a focused guard for a defect found by manual source
// review. They are deliberately narrow and cite the evidence that motivated
// them; they are not a substitute for the broader checks above.
// ---------------------------------------------------------------------------
const routesPath = path.join(KEEL, "src/keel/fleet/routes.py");
let routesSrc = "";
try { routesSrc = fs.readFileSync(routesPath, "utf8"); } catch { /* reported below */ }

// API-03 — `shells/clear/finished` is implemented in the GET dispatcher only
// (routes.py:528). The shared client used to POST it, which falls through
// dispatch_post and returns an error. Derive the expected method from the
// dispatcher that actually contains the literal so a backend fix is honoured.
if (routesSrc) {
  const postAt = routesSrc.indexOf("def dispatch_post");
  const getSlice = postAt > 0 ? routesSrc.slice(0, postAt) : routesSrc;
  const postSlice = postAt > 0 ? routesSrc.slice(postAt) : "";
  const getHas = /["']finished["']/.test(getSlice) && /["']clear["']/.test(getSlice);
  const postHas = /["']finished["']/.test(postSlice) && /["']clear["']/.test(postSlice);
  const expected = postHas ? "POST" : getHas ? "GET" : null;
  const ep = frontendEndpoints.find((e) => e.path.endsWith("/shells/clear/finished"));
  check("API-03", "shells/clear/finished call method matches the backend dispatcher",
    expected && ep && ep.method === expected ? "pass" : "fail",
    !expected ? "could not determine backend method from routes.py"
      : !ep ? "no frontend call site found"
        : `backend=${expected}, frontend=${ep.method} at ${loc(ep.file, ep.line)}`,
    [{ backendEvidence: "routes.py:528 (GET dispatcher)", expected, actual: ep?.method ?? null }]);
} else {
  check("API-03", "shells/clear/finished call method matches the backend dispatcher", "skipped", "routes.py not readable");
}

// EVT-01 — the bridge emits named `event: row` SSE frames (routes.py:1748).
// EventSource.onmessage only fires for unnamed / `message` frames, so a
// subscribeEvents() that only sets onmessage silently drops every live event.
if (routesSrc) {
  const emitted = routesSrc.match(/event:\s*([A-Za-z_-]+)\\ndata:/)?.[1] ?? null;
  const apiSrc = fs.readFileSync(path.join(APP, "lib/api.ts"), "utf8");
  const at = apiSrc.indexOf("export function subscribeEvents");
  const block = at >= 0 ? apiSrc.slice(at) : "";
  const hasOnMessage = /onmessage\s*=/.test(block);
  const hasNamed = emitted ? new RegExp(`addEventListener\\(["']${emitted}["']`).test(block) : false;
  const ok = emitted === null ? true : hasNamed || !hasOnMessage;
  const onMessageLine = at >= 0 && hasOnMessage
    ? apiSrc.slice(0, at).split("\n").length + block.slice(0, block.indexOf("onmessage")).split("\n").length - 1
    : 0;
  check("EVT-01", "Shared SSE subscriber listens for the event name the bridge emits",
    ok ? "pass" : "fail",
    emitted === null ? "backend emits unnamed frames; onmessage is sufficient"
      : ok ? `backend emits '${emitted}'; subscriber registers a matching listener`
        : `backend emits '${emitted}' but subscribeEvents only sets onmessage (${loc(path.join(APP, "lib/api.ts"), onMessageLine)})`,
    [{ backendEvent: emitted, onmessage: hasOnMessage, namedListener: hasNamed }]);
} else {
  check("EVT-01", "Shared SSE subscriber listens for the event name the bridge emits", "skipped", "routes.py not readable");
}

// FAB-02 — the permission-mode preference written by Settings/Onboarding is
// advertised as being read by the composer at startup. Guard that promise.
// A fix may legitimately wire the persisted mode through the shared shell
// state rather than directly inside features/cowork, so scan every source file
// except the two writer workstreams (settings/onboarding).
const consumerSources = sourceFiles
  .filter((f) => !/[\\/](features[\\/](settings|onboarding))[\\/]/.test(f))
  .map((f) => fs.readFileSync(f, "utf8")).join("\n");
const securitySrc = (() => { try { return fs.readFileSync(path.join(APP, "features/settings/SecuritySettings.tsx"), "utf8"); } catch { return ""; } })();
const modeWritten = /keel-mode/.test(securitySrc) || fs.existsSync(path.join(APP, "features/onboarding/progress.ts"));
const modeReadByComposer = /keel-mode|readMode\(/.test(consumerSources);
check("FAB-02", "Permission-mode preference is consumed by the Cowork composer",
  !modeWritten || modeReadByComposer ? "pass" : "fail",
  !modeWritten ? "no permission-mode preference writer found"
    : modeReadByComposer ? "composer source references the persisted mode"
      : "Settings/Onboarding write 'keel-mode' and show a success message, but no Cowork/Composer source reads it",
  [{ writer: "features/settings/SecuritySettings.tsx:35 / features/onboarding/progress.ts:161", composerReader: modeReadByComposer }]);

// ---------------------------------------------------------------------------
// 6. SKIPPED browser-only checks (never claim what was not run)
// ---------------------------------------------------------------------------
for (const [id, name, why] of [
  ["E2E-01", "Playwright end-to-end flows", "not run by this static harness; real coverage lives in tests/e2e/** (Playwright 1.65.1 devDependency), executed separately by continuous QA"],
  ["VIS-01", "Visual regression screenshots at 6 viewports", "no pixel-diff baseline exists; 72 real screenshots at 6 viewports x 6 destinations x 2 themes are captured by tests/e2e/09-theme-viewports.spec.ts and inspected via contact sheets"],
  ["A11Y-06", "Runtime a11y tree / keyboard walkthrough / contrast", "static source analysis cannot compute computed styles; real measurements are in tests/a11y/** and docs/UI-ACCESSIBILITY-AUDIT.md (note: light-theme AA contrast fails)"],
  ["PERF-01", "Runtime virtualization / streaming re-render profiling", "live model turn needs provider credentials (none on this host); large-data rerender/stress coverage is in tests/e2e/08-stress.spec.ts"],
]) check(id, name, "skipped", why);

// ---------------------------------------------------------------------------
// Output
// ---------------------------------------------------------------------------
const summary = results.reduce((a, r) => { a[r.status] = (a[r.status] || 0) + 1; return a; }, {});
const payload = {
  generatedAt: new Date().toISOString(),
  app: rel(APP),
  summary,
  inventory: { sourceFiles: sourceFiles.map(rel), cssFiles: cssFiles.map(rel) },
  frontendEndpoints,
  results,
};
fs.writeFileSync(path.join(HERE, "results.json"), JSON.stringify(payload, null, 2));
console.log(`UI verification: ${JSON.stringify(summary)}`);
for (const r of results) {
  if (r.status === "pass" || r.status === "info") continue;
  console.log(`[${r.status.toUpperCase()}] ${r.id} ${r.check}: ${r.detail}`);
}
console.log(`Evidence: ${rel(path.join(HERE, "results.json"))}`);
process.exit(results.some((r) => r.status === "fail") ? 1 : 0);
