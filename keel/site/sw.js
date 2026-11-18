/* Keel webapp service worker — v7 (mirror build).
   The public mirror is static; there is no /api. Navigations and same-origin
   assets are network-first so deploys land immediately, with cache fallback
   for offline. Cross-origin traffic (provider APIs) is never touched. */

const VERSION = "keel-shell-v7";
const SHELL = [
  "/",
  "/ui/style.css",
  "/ui/app.js",
  "/manifest.webmanifest",
  "/ui/icons/icon-192.png",
  "/ui/icons/icon-512.png",
  "/ui/fonts/inter-400.woff2",
  "/ui/fonts/space-grotesk-400.woff2",
  "/ui/fonts/jetbrains-mono-400.woff2",
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

  event.respondWith(
    fetch(event.request).then((resp) => {
      if (resp && resp.ok && event.request.method === "GET") {
        const clone = resp.clone();
        caches.open(VERSION).then((cache) => cache.put(event.request, clone));
      }
      return resp;
    }).catch(() =>
      caches.match(event.request).then((cached) => cached || caches.match("/"))
    )
  );
});
