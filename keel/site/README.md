# Keel — public web surface

**https://keel-desktop.vercel.app**

## Layout

| Route | Serves | What it is |
|---|---|---|
| `/` | `/index.html` | The Keel landing page (marketing) |
| `/app` | `/app.html` | The web mirror of the Keel app (BYOK chat, no agent, no disk) |
| `/download` | `/download.html` | Platform download cards, rendered from the release manifest |
| `/api/download-manifest` | serverless function | Same-origin proxy for the latest GitHub Release manifest |
| `/download.json` | static | Committed fallback manifest; all channels unavailable until a verified release is published |

The download surface only enables a button when the manifest marks the channel
`available: true`, points at an HTTPS URL, and carries a positive byte size and
SHA-256. The landing page and `/download` share that rule. The release workflow
publishes the manifest only after downloading every uploaded file over public
HTTPS and matching its checksum. See `../docs/HOSTING.md`.

Desktop and web share the same design language: same tokens, fonts and icons.
The desktop app (`desktop/ui/`) embeds the same mirror-family UI served by the
local Python bridge; the landing page is static and makes no network calls
beyond the static files themselves.

## The web mirror (`/app`) — what it does

- **Chat** streams directly from your browser to **OpenRouter** or **Google
  AI Studio** using a key you paste in Settings → Providers. The key is
  verified against the provider, stored only in this browser's
  `localStorage`, and is sent nowhere except your provider — never to us
  (there is no "us"; this is a static site).
- **Two surfaces**, same as the local app: Keel Desktop and Keel Code.
  - **Keel Desktop** — attach Documents / Images / Spreadsheets / Code
    files. Text files are inlined as read-only context; images are sent to
    the vision model of the provider you linked (both support vision).
  - **Keel Code** — attach anything: files, images, **.zip archives**
    (unpacked in your browser; text entries become read-only context), and
    whole desktop folders (their text files are attached the same way).
    This is a scratch-context workflow, not an agent run — nothing edits
    or executes your disk from this page.
- Caps: 8 files per message, 4 MB each, 12 MB total per send. Binary files
  are skipped with a note. Attachments never leave your browser except as
  part of a message to your linked provider.

## What it cannot do

Bind a folder as an agent workspace, run an agent, execute shell commands,
or read PDFs/Office binaries without exporting them to text. That is the
**local app** (the `keel` repository → `cd keel` → `python -m keel serve`) —
it runs entirely on your machine; its `+` menu uploads files to a local
`~/.keel/uploads/` folder and the agent reads, copies and unpacks them
itself (e.g. `.zip` via the shell), and its folder picker binds the
agent's working directory.

## Screenshot gallery

`site/screenshots/index.html` is generated from **actual captures of the running
Keel desktop UI** (main workspace, accessibility settings, execution policies,
operator admin) — not stock images. Regenerate it with:

```
python -c "from keel.document_gaps import build_screenshot_gallery; build_screenshot_gallery(['site/assets/screenshots'],'site/screenshots')"
```

Captures contain no tokens, credentials or private filesystem paths.

## State kept in your browser

Recents, settings, provider keys (`keel_mirror_settings_v1`), visit counters
for this tab. Clearing site data removes all of it.
