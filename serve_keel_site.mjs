#!/usr/bin/env node
/* Tiny static server for local QA of keel/site with Vercel-like rewrites. */
import { createServer } from 'node:http';
import { readFile, stat } from 'node:fs/promises';
import { resolve, extname, dirname, normalize } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), 'keel/site');
const PORT = Number(process.env.PORT || 3100);

// Mirrors keel/site/vercel.json. The article routes resolve to the top-level
// .html copies (Vercel clean-URL file resolution); the index.html rewrites in
// vercel.json remain as a fallback. /app is intentionally absent: app.html is
// only the local Electron mirror diagnostic and is not a public route.
const REWRITES = {
  '/download': '/download.html',
  '/downloads': '/downloads.html',
  '/login': '/login.html',
  '/new': '/new.html',
  '/plugins': '/plugins.html',
  '/projects': '/projects.html',
  '/artifacts': '/artifacts.html',
  '/keel-in-chrome': '/keel-in-chrome.html',
  '/chrome-web-store': '/chrome-web-store.html',
  '/privacy': '/privacy.html',
  '/terms': '/terms.html',
  '/notices': '/notices.html',
  '/roadmap': '/roadmap.html',
  '/eula': '/eula.html',
  '/trademark': '/trademark.html',
  '/requirements': '/requirements.html',
  '/product/overview': '/product-overview.html',
  '/product/keel-code': '/product/keel-code.html',
  '/product/tag': '/product/tag.html',
  '/product/keel-duet': '/product/keel-duet.html',
  '/product/keel-science': '/product/keel-science.html',
  '/product/keel-security': '/product/keel-security.html',
  '/product/cowork': '/product/cowork.html',
  '/platform/api': '/platform/api.html',
  '/pricing': '/pricing.html',
  '/cowork': '/product/cowork.html',
  '/keel-code': '/product/keel-code.html',
  '/resources/articles': '/resources/articles/index.html',
  '/resources/articles/introducing-keel-ship': '/resources/articles/introducing-keel-ship.html',
  '/resources/articles/introducing-keel-code': '/resources/articles/introducing-keel-code.html',
  '/resources/articles/keel-ship-session-format': '/resources/articles/keel-ship-session-format.html',
  // Trailing-slash variants must behave exactly like production clean URLs.
  '/download/': '/download.html',
  '/downloads/': '/downloads.html',
  '/login/': '/login.html',
  '/new/': '/new.html',
  '/plugins/': '/plugins.html',
  '/projects/': '/projects.html',
  '/artifacts/': '/artifacts.html',
  '/keel-in-chrome/': '/keel-in-chrome.html',
  '/privacy/': '/privacy.html',
  '/terms/': '/terms.html',
  '/notices/': '/notices.html',
  '/roadmap/': '/roadmap.html',
  '/eula/': '/eula.html',
  '/trademark/': '/trademark.html',
  '/requirements/': '/requirements.html',
  '/product/cowork/': '/product/cowork.html',
  '/product/keel-code/': '/product/keel-code.html',
  '/product/tag/': '/product/tag.html',
  '/product/keel-duet/': '/product/keel-duet.html',
  '/product/keel-science/': '/product/keel-science.html',
  '/product/keel-security/': '/product/keel-security.html',
  '/product/overview/': '/product-overview.html',
  '/platform/api/': '/platform/api.html',
  '/pricing/': '/pricing.html',
  '/cowork/': '/product/cowork.html',
  '/keel-code/': '/product/keel-code.html',
  '/resources/articles/': '/resources/articles/index.html',
};

const TYPES = {
  '.html': 'text/html; charset=utf-8', '.css': 'text/css; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8', '.mjs': 'text/javascript; charset=utf-8',
  '.json': 'application/json; charset=utf-8', '.svg': 'image/svg+xml',
  '.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg',
  '.woff2': 'font/woff2', '.ttf': 'font/ttf', '.ico': 'image/x-icon',
  '.webmanifest': 'application/manifest+json', '.xml': 'application/xml',
  '.txt': 'text/plain; charset=utf-8', '.zip': 'application/zip',
};

createServer(async (req, res) => {
  try {
    const url = new URL(req.url, 'http://localhost');
    let pathname = decodeURIComponent(url.pathname);
    pathname = REWRITES[pathname] || pathname;
    if (pathname === '/') pathname = '/index.html';
    const target = resolve(ROOT, '.' + normalize(pathname));
    if (!target.startsWith(ROOT)) { res.writeHead(403).end('Forbidden'); return; }
    let info = await stat(target).catch(() => null);
    if (info && info.isDirectory()) {
      const idx = resolve(target, 'index.html');
      info = await stat(idx).catch(() => null);
      if (info) return send(res, idx);
    }
    if (!info) { res.writeHead(404, { 'Content-Type': 'text/plain' }).end('Not found: ' + pathname); return; }
    send(res, target);
  } catch (err) {
    res.writeHead(500, { 'Content-Type': 'text/plain' }).end(String(err));
  }
}).listen(PORT, '127.0.0.1', () => console.log(`Keel QA server on http://localhost:${PORT}`));

async function send(res, target) {
  const body = await readFile(target);
  res.writeHead(200, {
    'Content-Type': TYPES[extname(target).toLowerCase()] || 'application/octet-stream',
    'Cache-Control': 'no-store',
  });
  res.end(body);
}
