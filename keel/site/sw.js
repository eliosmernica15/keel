/* Keel webapp service worker — v5.
   Navigations (the HTML page) are network-first so deploys land immediately;
   static assets are cache-first with background refresh. API traffic is
   never touched — this page is static either way. */

const VERSION = "keel-shell-v5";
const SHELL = [
  "/",
  "/manifest.webmanifest",
  "/ui/icons/icon-192.png",
  "/ui/icons/icon-512.png",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(VERSION).then((cache) => cache.addAll(SHELL))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== VERSION).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);
  if (url.origin !== location.origin) return;
  if (url.pathname.startsWith("/api/")) return;

  // Page navigations: network first — never one deploy behind.
  if (event.request.mode === "navigate") {
    event.respondWith(
      fetch(event.request).then((resp) => {
        if (resp && resp.ok) {
          const clone = resp.clone();
          caches.open(VERSION).then((cache) => cache.put("/", clone));
        }
        return resp;
      }).catch(() =>
        caches.match("/").then((cached) => cached || caches.match(event.request))
      )
    );
    return;
  }

  // Static assets: cache first, refresh in background.
  event.respondWith(
    caches.match(event.request).then((cached) => {
      const network = fetch(event.request).then((resp) => {
        if (resp && resp.ok && event.request.method === "GET") {
          const clone = resp.clone();
          caches.open(VERSION).then((cache) => cache.put(event.request, clone));
        }
        return resp;
      });
      return cached || network;
    })
  );
});
