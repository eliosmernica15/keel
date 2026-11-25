# `/new` page integration spec (coordinator instructions for the agent)

Work ONLY in `C:\Users\Admin\AppData\Local\Temp\opencode\keel-ui-worktree\keel\site`:
- `new.html`, `ui/new.css`, `ui/new.js`

Do NOT edit any other file. Do NOT commit/push/deploy.

A parallel agent is creating `ui/keel-chat.js` with global `window.KeelChat`.
Its exact API is in `CHAT_MODULE_SPEC.md` — read that file first. You may rely
on these methods: `getSettings`, `saveSettings`, `getProviders`,
`configuredProvider`, `providerModel`, `verifyKey`, `fetchModels`,
`attachFiles`, `buildPrompt`, `send`, `usage`, `PROVIDERS`.

## 1. Sidebar navigation (fix now)
- `Projects` → real link/navigation to `/projects`
- `Artifacts` → `/artifacts`
- `Plugins` → `/plugins`
- `New` → `/new` (or clears composer and stays)
- `Search` → keep opening the shared search palette
- The whole row must be clickable and the URL must actually change (use real
  `<a href="...">` elements or `location.assign`). Update `aria-current` on
  the active page.

## 2. Empty recents
- Remove all hardcoded recent chat titles from the sidebar.
- Default state: `Recents` section shows a short empty message such as
  `No recent chats yet` and `View all` is hidden/disabled.
- When the user sends a chat message, save a recent entry in localStorage
  (key `keel_new_recents_v1`) using the first ~60 chars of the prompt, and
  render it. Recents are then clickable to reload that prompt into the
  composer. `View all` only appears when there are more than a few.

## 3. Sidebar close fix
- The mobile sidebar close toggle at the top must actually hide/collapse the
  sidebar. Currently clicking it does not close reliably. Make the toggle set
  a class/state on the app root, update `aria-expanded`, and ensure the main
  area expands. Add a backdrop click and Escape to close on mobile. Ensure
  the recents filter input does not leave the sidebar stuck open. Verify the
  class names used by `new.css`/`new.js` and fix both sides.

## 4. Settings + providers (reuse repo backend)
Add a Settings dialog with panes:
- **Providers**: cards for OpenRouter and Google AI Studio with API key
  inputs (stored via `KeelChat.saveSettings({providers:{...}})`), a Verify
  button calling `KeelChat.verifyKey`, model selector populated by
  `KeelChat.fetchModels`, and a preferred provider selector. Show clearly
  that keys stay in this browser and go only to the provider.
- **General**: system instructions textarea saved via
  `KeelChat.saveSettings({ui:{instructions}})`, theme/font controls if easy.
- **Account / plan**: the existing Upgrade flow.
Wire the gear/help/account chip and the model chip to open the right pane.
Settings must be shared with `/app` (same localStorage key).

## 5. Real chat with files
- The composer sends real prompts through `KeelChat.send`. Render streamed
  deltas into assistant messages below the greeting. Show provider/model and
  usage (tokens/prompts) where space allows.
- `+` attach control opens a file input (accept common text/code files,
  images, and `.zip`). Use `KeelChat.attachFiles` to process, show removable
  attachment chips, and pass `KeelChat.buildPrompt` + images into send.
- Show a clear error if no provider key is configured, with a button that
  opens Settings → Providers.
- Keep Enter-to-send, Shift+Enter newline, and stop/clear controls if present.

## 6. Polish / safety
- Brand Keel everywhere; no dead `href="#"`; responsive to 390px; keyboard
  accessible; focus trap for dialogs; no console errors.
- Do not break the shared search palette already included in `new.html`.
- Do not introduce a second settings storage format.

VERIFY: `node --check ui/new.js`; report exact result and what you changed.
Do not claim browser verification.