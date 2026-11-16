# Keel Desktop — public mirror

This is **the public landing page** for Keel Desktop — same Cowork-style hero,
same sidebar silhouette, same ideas list, delivered with Keel's glass design
system and Keel's own marks (no Claude or Anthropic branding, assets or copy).

**What this is not:** a runnable Keel deployment. The real coding harness is a
local program (`desktop\ui` + the Python bridge) that binds `127.0.0.1` on the
operator's machine and talks to their chosen provider via stdio. It is not
reachable from the internet by design and is not deployed here.

Clicking anything on this page that needs a live agent — e.g. Send — tells you
exactly this: Keel runs on your machine. Clone `github.com/eliosmernica15/keel`,
`python -m keel serve`, and open the printed URL. Your keys never leave your
disk.

This site ships:
- static HTML + inlined CSS (no framework, no dependencies to build)
- a service worker for offline shell (v4)
- Keel's bundled fonts (Inter, Space Grotesk, JetBrains Mono) and icons
- zero tracking, zero analytics, zero external network calls

Contents are verified — every file on this site is committed to the same git
repo the site is deployed from.
