# Shared Keel chat/provider module spec

Create `C:\Users\Admin\AppData\Local\Temp\opencode\keel-ui-worktree\keel\site\ui\keel-chat.js` ONLY.

Do NOT edit any other file. Do NOT commit/push/deploy.

Purpose: reuse the proven client-side provider engine from `ui/app.js` for the
public `/new` page (and any other light page). The Python backend cannot run on
static Vercel; this module is the repo's existing BYOK browser backend: keys in
localStorage `keel_mirror_settings_v1`, chat streams directly to OpenRouter or
Google AI Studio, files are inlined as read-only context, images go to vision.

Read `ui/app.js` sections: MIRROR_PROVIDER_DEFS (lines ~47-109), settings helpers
(~110-167), mirrorSend streaming (~225-330), attachments and zip (~997-1180),
settings pane code. Copy/adapt the logic — do not break app.js.

## Required global API (exact names)

`window.KeelChat` with:

- `PROVIDERS` — `{ openrouter: {...}, google: {...} }` definitions with labels,
  hints, default models, verify URL/headers, catalog URL/headers/parser, and
  `chat(key, model, messages)` returning `{url, init, extractDelta, extractUsage}`.
  Include OpenRouter attribution headers from app.js.
- `getSettings()` → settings object from `localStorage.keel_mirror_settings_v1`.
- `saveSettings(patch)` → merges (including `providers`, `providerConfig.models`,
  `ui`) like app.js `saveMirrorSettings`, persists, returns settings.
- `getProviders()` → settings.providers or `{}`.
- `configuredProvider()` → `"openrouter" | "google" | null` with a key.
- `providerModel(name)` → pinned model or provider default.
- `verifyKey(name, key)` → `Promise<boolean>` using the provider verify endpoint.
- `fetchModels(name)` → `Promise<string[]>`: try `/api/model-catalog/:name`
  first (local bridge), then the provider's live catalog.
- `attachFiles(fileList)` → `Promise<{files, skipped}>`; each file object:
  `{name, bytes, kind:'text'|'image', content?, mime?, data?}`. Reuse caps:
  8 files, 4 MB each, 12 MB total. Text/code files inline as UTF-8; images
  become base64 data. `.zip` archives are unpacked in-browser (stored + deflate
  via `DecompressionStream`) and their text entries become separate file
  objects; non-text/binary entries are reported in `skipped`.
- `buildPrompt(text, files)` → string containing the user's text plus a
  `[Attached files — read-only context]` block with names/sizes/content.
- `send({messages, provider, model, instructions, images, onDelta, onDone, onError})`
  → `Promise`. `messages` is an array of `{role:'user'|'assistant'|'system',
  content}`. Choose provider: explicit named provider with a key, else
  `configuredProvider()`. If none, call `onError(new Error('no-provider'))`
  and resolve without network. Stream SSE: call `onDelta(delta, fullText)` for
  each delta; call `onDone({provider, model, usage})` on completion; call
  `onError(err)` on failure. Never throw to the caller.
- `usage()` → `{prompts, replies, tokens}` from sessionStorage key
  `keel_mirror_usage_v1`; bump counters internally on send/reply/tokens.

## Rules
- No external libraries, no network except the provider endpoints and
  same-origin `/api/model-catalog/*`.
- Keys must never be logged or sent anywhere except the chosen provider.
- ES5-compatible-ish vanilla JS, IIFE, `"use strict"`, no console errors.
- Must work when `/api/*` endpoints 404 (static mirror).
- Export only via `window.KeelChat`; do not touch DOM.

VERIFY: `node --check` on the file; report exact result. Report the exported
API list. Do not claim browser verification.