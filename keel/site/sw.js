/* Keel site service worker — retired.
 *
 * Older versions precached the local /app desktop mirror and could serve that
 * dark UI for unrelated navigation requests until several reloads. The site is
 * a fast static marketing site plus /new; it does not need an offline shell.
 * Installing this version clears every cache and unregisters itself so stale
 * mirrors can never appear again.
 */

const VERSION = "keel-shell-v18";
const NEVER_CACHE = [
  /^\/api\//,
  /^\/download\.json$/,
  /\.(exe|msi|dmg|pkg|deb|rpm|AppImage|zip|tar\.gz|tar\.xz|bin)$/i,
];

self.addEventListener("install", () => {
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.map((key) => caches.delete(key))))
      .then(() => self.registration.unregister())
      .then(() => self.clients.claim())
  );
});

/* No fetch handler: every request goes straight to the network/Vercel cache. */
