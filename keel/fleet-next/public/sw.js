// Keel Fleet PWA — app-shell cache. Network-first for everything else.
const SHELL = ["/", "/manifest.webmanifest", "/icon.svg", "/icon-192.png"];
const SHELL_CACHE = "keel-fleet-shell-v1";

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

  if (SHELL.includes(url.pathname)) {
    event.respondWith(
      caches.match(event.request).then((cached) => cached || fetch(event.request)),
    );
    return;
  }
  event.respondWith(
    fetch(event.request).catch(() => caches.match("/").then((cached) => cached || Response.error())),
  );
});
