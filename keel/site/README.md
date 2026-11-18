# Keel — public mirror

**https://keel-desktop.vercel.app** — the mirror of the Keel desktop app,
served as the same static UI, but with **no local backend**. Everything on
this page runs in your browser.

## What it does

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
- Caps: 8 files per message, 4 MB each, 12 MB total per send. Binary
  files are skipped with a note. Attachments never leave your browser
  except as part of a message to your linked provider.

## What it cannot do

Bind a folder as an agent workspace, run an agent, execute shell commands,
or read PDFs/Office binaries without exporting them to text. That is the
**local app** (`keel` repository → `cd keel` → `python -m keel serve`) —
it runs entirely on your machine; its `+` menus upload files to a local
`~/.keel/uploads/` folder and the agent reads, copies and unpacks them
itself (e.g. `.zip` via the shell), and its folder picker binds the
agent's working directory.

## State kept per your browser

Recents, settings, provider keys (`keel_mirror_settings_v1`), visit
counters for this tab. Clearing site data removes all of it.
