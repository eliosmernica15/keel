// Visual/QA audit of the live Keel site using headless Chrome + CDP over --dump-dom
// and --screenshot. No third-party dependencies.
import { execFile } from "node:child_process";
import { mkdir, writeFile } from "node:fs/promises";
import { promisify } from "node:util";
import { resolve } from "node:path";

const run = promisify(execFile);
const CHROME = "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe";
const BASE = process.argv[2] || "https://keel-desktop.vercel.app";
const OUT = resolve(process.argv[3] || "C:/Users/Admin/Desktop/Claude clone/.audit");
const ROUTES = [
  "/", "/product/overview", "/product/keel-code", "/product/cowork", "/product/keel-duet",
  "/platform/api", "/product/tag", "/product/keel-security", "/product/keel-science",
  "/product/design", "/skills", "/features/artifacts", "/marketplace/connectors-plugins",
  "/marketplace/plugins", "/keel-in-chrome", "/keel-for-google-workspace",
  "/keel-for-microsoft-365", "/login", "/new", "/download", "/downloads", "/pricing", "/roadmap",
];

await mkdir(OUT, { recursive: true });

const probe = `(() => {
  const de = document.documentElement;
  const broken = [...document.images].filter(i => !i.complete || i.naturalWidth === 0).map(i => i.getAttribute('src') || '(no src)');
  const cssMissing = [...document.styleSheets].filter(s => { try { return s.cssRules.length === 0; } catch { return false; } }).length;
  const h1 = document.querySelector('h1');
  const ctas = document.querySelectorAll('a[href], button').length;
  const dead = [...document.querySelectorAll('a[href="#"], a[href=""], button:not([type]):not([data-action])')].length;
  return JSON.stringify({
    overflow: de.scrollWidth - de.clientWidth,
    docHeight: de.scrollHeight,
    brokenImages: broken.slice(0, 6),
    brokenCount: broken.length,
    emptyStyleSheets: cssMissing,
    h1: h1 ? h1.textContent.trim().replace(/\\s+/g, ' ').slice(0, 80) : null,
    title: document.title,
    interactive: ctas,
    suspicious: dead,
    font: getComputedStyle(document.body).fontFamily.slice(0, 48),
  });
})()`;

const rows = [];
for (const route of ROUTES) {
  const url = BASE + route;
  const profile = `${OUT}/profile-${route.replace(/[^a-z0-9]/gi, "_") || "root"}`;
  const args = [
    "--headless=new", "--disable-gpu", "--hide-scrollbars", "--no-first-run",
    "--no-default-browser-check", `--user-data-dir=${profile}`,
    "--window-size=1440,1000", "--virtual-time-budget=4000",
    "--run-all-compositor-stages-before-draw",
    `--screenshot=${OUT}/${route.replace(/[^a-z0-9]/gi, "_") || "root"}.png`,
    url,
  ];
  try {
    await run(CHROME, args, { timeout: 60000, windowsHide: true });
    const dom = await run(CHROME, [
      "--headless=new", "--disable-gpu", "--no-first-run", "--no-default-browser-check",
      `--user-data-dir=${profile}`, "--virtual-time-budget=3000", "--dump-dom", url,
    ], { timeout: 60000, windowsHide: true, maxBuffer: 40 * 1024 * 1024 });
    const html = dom.stdout || "";
    const navLinks = [...html.matchAll(/href="(\/[^"#?]*)"/g)].map(m => m[1]);
    const internal = [...new Set(navLinks)];
    rows.push({ route, ok: html.length > 2000, bytes: html.length, internalLinks: internal.length });
  } catch (error) {
    rows.push({ route, ok: false, error: String(error.message).slice(0, 160) });
  }
  console.log(`${rows.at(-1).ok ? "OK  " : "FAIL"} ${route} ${rows.at(-1).bytes ?? ""}`);
}

await writeFile(`${OUT}/audit.json`, JSON.stringify(rows, null, 2));
console.log(`\nScreenshots + audit.json written to ${OUT}`);
