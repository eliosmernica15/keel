/* Keel webapp service worker - v15.
   The landing (/), the mirror app (/app.html) and the download page are all
   static, with one serverless helper at /api/download-manifest that proxies
   the published GitHub Release manifest. Navigations and same-origin assets are
   network-first so deploys land immediately, with cache fallback for offline.
   Release manifests are never cached: availability must reflect the origin.
   Cross-origin traffic (provider APIs) is never touched. */

const VERSION = "keel-shell-v15";
const SHELL = [
  "/",
  "/app.html",
  "/ui/landing.css",
  "/ui/landing.js",
  "/ui/landing-download.js",
  "/ui/style.css",
  "/ui/app.js",
  "/ui/download.js",
  "/manifest.webmanifest",
  "/ui/icons/icon-192.png",
  "/ui/icons/icon-512.png",
  "/ui/fonts/inter-400.woff2",
  "/ui/fonts/space-grotesk-400.woff2",
  "/ui/fonts/jetbrains-mono-400.woff2",
  "/assets/img/keel-app.jpg",
  "/assets/img/keel-settings-general.jpg",
  "/assets/img/keel-settings-providers.jpg",
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

  // Never cache release metadata: a stale manifest could advertise an
  // installer that has been pulled, or hide a newly verified release.
  if (url.pathname === "/download.json" || url.pathname.startsWith("/api/")) {
    return;
  }

  if (event.request.mode === "navigate") {
    event.respondWith(
      fetch(event.request).then((resp) => {
        if (resp && resp.ok) {
          const clone = resp.clone();
          caches.open(VERSION).then((cache) => cache.put(url.pathname, clone));
        }
        return resp;
      }).catch(() =>
        caches.match(event.request)
          .then((cached) => cached || caches.match("/app.html"))
          .then((cached) => cached || caches.match("/"))
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
