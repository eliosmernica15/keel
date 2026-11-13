/* Keel webapp service worker — caches the app shell so the window opens
   offline. API calls always go to the network (they hit the local bridge);
   if the network fails, the app shell still loads in offline/demo mode. */

const VERSION = "keel-shell-v1";
const SHELL = [
  "/",
  "/ui/index.html",
  "/ui/style.css",
  "/ui/app.js",
  "/manifest.webmanifest",
  "/ui/icons/icon-192.png",
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
  if (url.origin !== location.origin) {
    return; // never touch cross-origin traffic
  }
  if (url.pathname.startsWith("/api/")) {
    return; // network only — the local bridge owns this
  }
  // app shell: cache first, refresh in background (stale-while-revalidate)
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
