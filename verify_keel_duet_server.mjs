#!/usr/bin/env node
/* Tiny static server for local verification of the Keel Duet page. */
import { createServer } from 'node:http';
import { readFile, stat } from 'node:fs/promises';
import { resolve, extname, join, normalize } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = resolve(fileURLToPath(new URL('.', import.meta.url)), 'keel/site');
const PORT = Number(process.env.PORT || 4173);
const TYPES = { '.html':'text/html; charset=utf-8', '.css':'text/css; charset=utf-8',
  '.js':'text/javascript; charset=utf-8', '.json':'application/json; charset=utf-8',
  '.svg':'image/svg+xml', '.png':'image/png', '.jpg':'image/jpeg', '.ico':'image/x-icon',
  '.webmanifest':'application/manifest+json', '.xml':'application/xml' };

createServer(async (req, res) => {
  try {
    let p = decodeURIComponent(new URL(req.url, 'http://x').pathname);
    if (p === '/product/keel-duet') p = '/product/keel-duet.html';
    if (p === '/terms') p = '/eula.html';
    if (p.endsWith('/')) p += 'index.html';
    const safe = normalize(p).replace(/^(\.\.[/\\])+/, '');
    let file = join(ROOT, safe);
    try { if ((await stat(file)).isDirectory()) file = join(file, 'index.html'); } catch {}
    const body = await readFile(file);
    res.writeHead(200, { 'Content-Type': TYPES[extname(file)] || 'application/octet-stream',
      'Cache-Control': 'no-store' });
    res.end(body);
  } catch {
    res.writeHead(404, { 'Content-Type': 'text/plain; charset=utf-8' });
    res.end('Not found');
  }
}).listen(PORT, () => console.log(`Duet verification server: http://localhost:${PORT}/product/keel-duet`));
