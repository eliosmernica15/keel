/* Keel webapp service worker — app shell only (v17).
 *
 * The installed PWA opens /app (the real web mirror). Only that document, its
 * CSS/JS and static icons/fonts are precached. Release metadata (/download.json
 * and /api/*) and installer binaries (.exe/.dmg/.deb/.rpm/.AppImage/.zip/.pkg)
 * are never cached: stale availability or a stale binary must never be served.
 *
 * Network-first with a cache fallback, plus versioned caches that are deleted
 * on activation, so a new deploy cannot be trapped behind an old worker.
 */

const VERSION = "keel-shell-v17";
const SHELL = [
  "/app",
  "/ui/style.css",
  "/ui/app.js",
  "/ui/management.js",
  "/manifest.webmanifest",
  "/ui/icons/icon-192.png",
  "/ui/icons/icon-512.png",
  "/ui/icons/icon.png",
  "/ui/fonts/inter-400.woff2",
  "/ui/fonts/space-grotesk-400.woff2",
  "/ui/fonts/jetbrains-mono-400.woff2",
];
const CACHEABLE = new Set(SHELL);

/* Belt and braces: even if a path were added to SHELL by mistake, these
   responses are never allowed into a cache. */
const NEVER_CACHE = [
  /^\/api\//,
  /^\/download\.json$/,
  /\.(exe|msi|dmg|pkg|deb|rpm|AppImage|zip|tar\.gz|tar\.xz|bin)$/i,
];

function isCacheable(url, request, response) {
  if (!request || request.method !== "GET") return false;
  if (url.origin !== location.origin) return false;
  if (NEVER_CACHE.some((pattern) => pattern.test(url.pathname))) return false;
  if (response && (response.status !== 200 || response.headers.has("Content-Disposition"))) return false;
  return CACHEABLE.has(url.pathname);
}

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(VERSION)
      .then((cache) => cache.addAll(SHELL).catch(() => { /* install with what is reachable */ }))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((key) => key !== VERSION).map((key) => caches.delete(key))))
      .then(() => self.clients.claim())
  );
});

/* Allow the page to ask a waiting worker to take over immediately. */
self.addEventListener("message", (event) => {
  if (event && event.data && event.data.type === "SKIP_WAITING") self.skipWaiting();
});

self.addEventListener("fetch", (event) => {
  const request = event.request;
  const url = new URL(request.url);
  if (url.origin !== location.origin || request.method !== "GET") return;

  if (NEVER_CACHE.some((pattern) => pattern.test(url.pathname))) return;

  if (request.mode === "navigate") {
    event.respondWith(
      fetch(request).then((response) => {
        if (isCacheable(url, request, response)) {
          const clone = response.clone();
          caches.open(VERSION).then((cache) => cache.put(url.pathname, clone));
        }
        return response;
      }).catch(() =>
        caches.match(request).then((cached) => cached || caches.match("/app"))
      )
    );
    return;
  }

  if (!CACHEABLE.has(url.pathname)) return;

  event.respondWith(
    fetch(request).then((response) => {
      if (isCacheable(url, request, response)) {
        const clone = response.clone();
        caches.open(VERSION).then((cache) => cache.put(request, clone));
      }
      return response;
    }).catch(() =>
      caches.match(request).then((cached) => cached || Response.error())
    )
  );
});
