// Keel unified PWA — offline-capable app shell without pinning users to an
// old build. Bridge traffic is never cached.
const SHELL = ["/", "/manifest.webmanifest", "/icon.svg", "/icon-192.png"];
const SHELL_CACHE = "keel-shell-v3"; // bump on shell changes; activate clears old caches

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(SHELL_CACHE).then((cache) => cache.addAll(SHELL)).then(() => self.skipWaiting()),
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== SHELL_CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim()),
  );
});

self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);
  if (url.origin !== self.location.origin) return;
  if (url.pathname.startsWith("/api/")) return; // never cache bridge traffic

  if (url.pathname === "/") {
    // Network-first for the document so a rebuilt app is picked up on the
    // next visit; fall back to the cached shell only when offline.
    event.respondWith(
      fetch(event.request)
        .then((response) => {
          const copy = response.clone();
          caches.open(SHELL_CACHE).then((cache) => cache.put("/app-shell", copy));
          return response;
        })
        .catch(() => caches.match("/app-shell").then((cached) => cached || caches.match("/"))),
    );
    return;
  }

  if (SHELL.includes(url.pathname)) {
    event.respondWith(
      caches.match(event.request).then((cached) => cached || fetch(event.request)),
    );
    return;
  }

  event.respondWith(
    fetch(event.request).catch(() => caches.match("/app-shell").then((cached) => cached || Response.error())),
  );
});
