# Keel — public mirror

**https://keel-desktop.vercel.app** — the mirror of the Keel desktop app,
rendered as the same static UI, but with **no local backend**. Everything on
this page runs in your browser.

- **Chat** streams directly from your browser to **OpenRouter** or **Google
  AI Studio** using a key you paste in Settings → Providers. The key is
  verified against the provider, then stored only in this browser's
  `localStorage`, and is sent nowhere except your provider — never to us
  (there is no "us"; this is a static site).
- **What it cannot do**: reach your disk, run an agent, bind a folder, list
  files, or expose connectors/skills — those belong to the local app
  (`keel serve`). Anything that would need them says so honestly in the UI.
- **The real thing**: clone
  [eliosmernica15/keel](https://github.com/eliosmernica15/keel),
  `cd keel`, `python -m keel serve`, then install from the browser icon on
  the printed page. That app runs entirely on your machine.

This mirror keeps the local app's design 1:1 (two surfaces — Keel Desktop and
Keel Code — popovers, menus, theme, settings). It is intentionally not a
byte-identical build: the bridge layer is replaced by client-side BYOK so the
page can actually do something useful off your machine.

State that is kept, per your browser: prompts (`Recents`), settings and
provider keys (`keel_mirror_settings_v1`), visit counters for this tab.
Clearing site data removes all of it.
