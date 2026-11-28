// Real browser audit over Chrome DevTools Protocol. No third-party modules.
import { spawn } from "node:child_process";
import { mkdir, writeFile } from "node:fs/promises";
import { resolve } from "node:path";

const CHROME = "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe";
const BASE = process.argv[2] || "https://keel-desktop.vercel.app";
const OUT = resolve(process.argv[3] || "C:/Users/Admin/Desktop/Claude clone/.audit/cdp");
const PORT = 9333;
const ROUTES = [
  "/", "/product/overview", "/product/keel-code", "/product/cowork", "/product/keel-duet",
  "/platform/api", "/product/tag", "/product/keel-security", "/product/keel-science",
  "/product/design", "/skills", "/features/artifacts", "/marketplace/connectors-plugins",
  "/marketplace/plugins", "/keel-in-chrome", "/keel-for-google-workspace",
  "/keel-for-microsoft-365", "/login", "/new", "/download", "/downloads", "/pricing", "/roadmap",
];

await mkdir(OUT, { recursive: true });
const chrome = spawn(CHROME, [
  "--headless=new", "--disable-gpu", "--hide-scrollbars", "--no-first-run",
  "--no-default-browser-check", `--remote-debugging-port=${PORT}`,
  `--user-data-dir=${OUT}/browser-profile`, "--window-size=1440,1000", "about:blank",
], { windowsHide: true, stdio: "ignore" });

const sleep = ms => new Promise(r => setTimeout(r, ms));
async function getTarget() {
  for (let i = 0; i < 40; i++) {
    try {
      const r = await fetch(`http://127.0.0.1:${PORT}/json/list`);
      const list = await r.json();
      const page = list.find(t => t.type === "page");
      if (page) return page.webSocketDebuggerUrl;
    } catch {}
    await sleep(250);
  }
  throw new Error("Chrome DevTools endpoint unavailable");
}

const wsUrl = await getTarget();
const ws = new WebSocket(wsUrl);
await new Promise((ok, fail) => { ws.onopen = ok; ws.onerror = fail; });
let seq = 0;
const pending = new Map();
ws.onmessage = (ev) => {
  const msg = JSON.parse(ev.data);
  if (msg.id && pending.has(msg.id)) {
    const { ok, fail } = pending.get(msg.id);
    pending.delete(msg.id);
    msg.error ? fail(new Error(msg.error.message)) : ok(msg.result);
  }
};
function send(method, params = {}) {
  const id = ++seq;
  return new Promise((ok, fail) => {
    pending.set(id, { ok, fail });
    ws.send(JSON.stringify({ id, method, params }));
  });
}
await send("Page.enable");
await send("Runtime.enable");

const results = [];
for (const route of ROUTES) {
  const errors = [];
  const listener = (ev) => {
    const m = JSON.parse(ev.data);
    if (m.method === "Runtime.exceptionThrown") errors.push(String(m.params?.exceptionDetails?.text || "js error").slice(0, 120));
    if (m.method === "Log.entryAdded" && m.params?.entry?.level === "error") errors.push(String(m.params.entry.text).slice(0, 120));
  };
  ws.addEventListener("message", listener);
  await send("Page.navigate", { url: BASE + route });
  await sleep(1400);
  const expr = `(() => {
    const de = document.documentElement;
    const broken = [...document.images].filter(i => !i.complete || i.naturalWidth === 0).map(i => i.getAttribute('src') || '(no src)');
    const emptyCss = [...document.styleSheets].filter(s => { try { return s.cssRules.length === 0; } catch { return false; } }).length;
    const h1 = document.querySelector('h1');
    return JSON.stringify({
      title: document.title,
      h1: h1 ? h1.textContent.trim().replace(/\\s+/g,' ').slice(0,80) : null,
      overflow: de.scrollWidth - de.clientWidth,
      height: de.scrollHeight,
      brokenImages: broken.slice(0,5), brokenCount: broken.length,
      emptyStyleSheets: emptyCss,
      font: getComputedStyle(document.body).fontFamily.slice(0,42),
      links: document.querySelectorAll('a[href^="/"]').length,
      hashLinks: document.querySelectorAll('a[href="#"], a[href=""]').length,
    });
  })()`;
  const res = await send("Runtime.evaluate", { expression: expr, returnByValue: true });
  const info = JSON.parse(res.result.value);
  const shot = await send("Page.captureScreenshot", { format: "png", captureBeyondViewport: true });
  const name = route.replace(/[^a-z0-9]/gi, "_") || "root";
  await writeFile(`${OUT}/${name}.png`, Buffer.from(shot.data, "base64"));
  ws.removeEventListener("message", listener);
  results.push({ route, ...info, jsErrors: [...new Set(errors)].slice(0, 4) });
  console.log(`${String(info.overflow).padStart(4)}px overflow | ${String(info.brokenCount).padStart(2)} broken img | ${String(info.emptyStyleSheets).padStart(2)} empty css | ${route}`);
}

await writeFile(`${OUT}/report.json`, JSON.stringify(results, null, 2));
console.log(`\nReport: ${OUT}/report.json`);
ws.close();
chrome.kill();
