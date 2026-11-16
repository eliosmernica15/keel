# Keel — public mirror (also: BYOK chat)

The public mirror of Keel Desktop — same shell, same glass, plus honest
bring-your-own-key chat.

**What works here**

- **Live chat with your own key, in your browser** — OpenRouter and
  Google AI Studio both allow browser access (verified against their
  CORS preflights). Paste a key in Settings → Providers →
  Verify & save: it is checked against the provider live, stored **only
  in this browser's localStorage**, and used for streaming replies.
  "Forget this key" wipes it. No Keel server exists; your prompt goes
  to your provider under your key — that's BYOK.
- The mirror UI: account drop-up, full settings (General, Providers,
  Usage with real token counters, Privacy, Import & export, Keel Code /
  Desktop, System with live SW status, Developer, Skills, Connectors,
  Plugins), dark / light / system theme, folder attach (read-only tree).
- The service worker serves navigations network-first; a strict
  Content-Security-Policy (see `vercel.json`) locks scripts to this
  origin and `connect-src` to the two permitted providers.

**What doesn't work here**

- No tools, no files, no agent loop — Keel's agent runs in the local
  app (`python -m keel serve`, then clone this repo).
- **NVIDIA NIM and Anthropic** do not permit browser calls (no
  CORS allowance). Their keys work in the local app only — this page
  says so rather than pretend.
- No accounts, no storage beyond this browser, no tracking.

Fonts bundled (Inter, Space Grotesk, JetBrains Mono).
Source of truth: github.com/eliosmernica15/keel — `keel/site/`.
