# Keel — public mirror

This is the **public face of Keel**: the Keel Desktop home screen (the
greeting, the composer, the chips) and, after you press Enter, the same
screen morphed into the conversation view. Keel's own marks and design
system only — no third-party branding, assets or copy.

**What this is not:** a runnable Keel. The real agent is a local program
that binds `127.0.0.1` on your machine and talks to your chosen provider
with your keys. It is not reachable from the internet by design. On this
page, sending a message morphs the layout, echoes your prompt back, and
answers honestly: Keel runs locally. Your keys never leave your disk.

Everything here runs locally in the browser tab:

- the morph is pure CSS transitions + one JS toggle
- prompts are echoed locally (sessionStorage, this tab only, never uploaded)
- "Install ↓" triggers the browser's own install flow directly (the page
  is an installable PWA — manifest + service worker); if the browser
  won't prompt, it points at the browser's install menu. No popups.
- Share copies the URL, never a key or a message
- zero tracking, zero analytics, zero external network calls

Fonts are bundled (Inter, Space Grotesk, JetBrains Mono). The real, private
agent lives at `github.com/eliosmernica15/keel` — `python -m keel serve`.
