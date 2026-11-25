# Real-browser zoom and screen-reader fallback verification (Agent A)

This document closes the two "implemented, unverified" frontend criteria that are
automatable on this host: **native 200 % browser zoom evidence** and the
**screen-reader fallback audit**. It is evidence-based: every number below comes
from the command output quoted in section 5. Nothing in `features/`, `app/`,
`lib/`, `components/`, other test folders, `package.json` or git was changed.

## 1. What was added and how to reproduce

| File | Purpose |
|---|---|
| `fleet-next/tests/zoom-a11y/playwright.zoom-a11y.config.ts` | Isolated Chromium config: port **3304**, build dir **`.next-zoom-a11y`**, `workers: 1`. |
| `fleet-next/tests/zoom-a11y/helpers.ts` | Themed app opener, deterministic bridge stub (`/api/bridge/**`), CDP zoom/AX helpers, semantic audit fixture with strict console-error gate. |
| `fleet-next/tests/zoom-a11y/01-zoom-capability.spec.ts` | Proves what CDP / launch flags can and cannot emulate (capability probe). |
| `fleet-next/tests/zoom-a11y/02-zoom-200-cdp.spec.ts` | Six destinations × two themes under real `Emulation.setPageScaleFactor(2)`. |
| `fleet-next/tests/zoom-a11y/03-css-viewport-proxy.spec.ts` | Authoritative 720×450 CSS-reflow proxy, six destinations × two themes. |
| `fleet-next/tests/zoom-a11y/04-sr-fallback-audit.spec.ts` | Landmarks, headings, accessible names, AX live regions, focus traps/restoration, forced-colors / prefers-contrast. |
| `fleet-next/tests/zoom-a11y/05-live-announcements.spec.ts` | Dynamic status, error and streaming announcements observed in the Chromium AX tree. |
| `fleet-next/tests/zoom-a11y/evidence/zoom200-cdp-dark.png`, `...light.png` | Screenshots captured with the CDP zoom active. |

Commands (run from `fleet-next/`):

```text
npx tsc --noEmit
npx playwright test --config tests/zoom-a11y/playwright.zoom-a11y.config.ts --workers=1
```

The suite never contacts a real provider or credential: `/api/bridge/**` is
stubbed with honest empty data (or a deliberate HTTP 500 / SSE delta for the
error and streaming tests). The bridge itself is **not** running on this host
(no listener on port 8739).

## 2. Real 200 % browser zoom — capability finding (honest limitation)

Both requested mechanisms were invoked. Exact command results:

```text
CDP_ZOOM_PROBE {
  "command": "Emulation.setPageScaleFactor({pageScaleFactor:2})",
  "commandResult": "{}", "commandError": "",
  "before": {"innerWidth":1440,"innerHeight":900,"dpr":1,"vvScale":1,
             "vvWidth":1440,"vvHeight":900,"scrollWidth":1440},
  "after":  {"innerWidth":1440,"innerHeight":900,"dpr":1,"vvScale":2,
             "vvWidth":720,"vvHeight":450,"scrollWidth":1440}
}
FORCE_DSF_PROBE {
  "launchArg": "--force-device-scale-factor=2",
  "before": {"innerWidth":800,"innerHeight":600,"dpr":2,"vvScale":1,
             "vvWidth":800,"vvHeight":600,"scrollWidth":2008},
  "after":  {"innerWidth":800,"innerHeight":600,"dpr":2,"vvScale":2,
             "vvWidth":400,"vvHeight":300,"scrollWidth":2008}
}
```

Interpretation:

* `Emulation.setPageScaleFactor` is **accepted** (`"{}"`, no error) and halves
  the *visual* viewport (1440→720 CSS px, 900→450). It is the same scale a
  200 % zoomed browser shows to the user.
* It does **not** reflow the layout viewport: `innerWidth`, `devicePixelRatio`
  and `documentElement.scrollWidth` are unchanged.
* `--force-device-scale-factor=2` sets `devicePixelRatio = 2` (HiDPI), also
  without reflowing layout. It is not native Ctrl+ zoom either.

An exact tooling error was hit and worked around (recorded here rather than
silently ignored): inside the Playwright test runner, a context created with
`viewport: null` fails with

```text
browser.newContext: "deviceScaleFactor" option is not supported with null "viewport"
browserType.launchPersistentContext: "deviceScaleFactor" option is not supported with null "viewport"
```

because the runner injects `deviceScaleFactor: 1`. Clearing it with
`test.use({ deviceScaleFactor: undefined })` and passing
`deviceScaleFactor: undefined` to `launchPersistentContext` lets the Chromium
flag take effect (DPR 2 evidence above).

**Conclusion:** CDP and Chromium flags cannot emulate the *layout reflow* of a
real Ctrl+/Cmd+ browser zoom on this host. The CSS-viewport proxy therefore
remains the authoritative reflow evidence (section 4); the CDP zoom state is
kept as additional real-browser evidence (section 3). The exact native
keyboard step still required of a human is in section 6.

## 3. Real-browser zoom evidence (CDP page scale 2, both themes, six destinations)

With `Emulation.setPageScaleFactor(2)` active, for each of Cowork, Code, Duet,
Fleet, Capabilities and Settings in **dark and light** themes:

* `visualViewport.scale === 2` and `visualViewport.width === innerWidth / 2`
  (720 px at a 1440 px layout viewport) — zoom genuinely applied;
* `document.documentElement.scrollWidth === 1440 <= innerWidth` and
  `document.body.scrollWidth === 1440 <= innerWidth` — **no horizontal
  overflow**;
* landmarks `{header:1, main:1, footer:1, nav:1}`, named controls only
  (`unnamed: 0`), control counts 41–49;
* first Tab stop visible with a real focus ring
  (dark `solid 2px rgb(230,213,76)`, light `solid 2px rgb(138,90,7)`);
* controls reachable without a pointer: command palette navigates to Cowork
  and toggles the sidebar twice (its state flips and flips back). The `[` / `\`
  keyboard shortcuts are covered separately by the existing a11y suite at the
  720×450 proxy viewport; they were not re-asserted at CDP page scale 2.

Screenshots: `fleet-next/tests/zoom-a11y/evidence/zoom200-cdp-dark.png` and
`zoom200-cdp-light.png`.

## 4. CSS-viewport proxy evidence (native-zoom reflow equivalent)

`test.use({ viewport: { width: 720, height: 450 } })` plus both themes and all
six destinations produced `innerWidth === 720` and `scrollWidth === 720` for
every destination (no overflow), 40–49 named controls each, and a visible
focused first Tab stop. This is the deterministic equivalent of native 200 %
zoom's CSS layout.

## 5. Screen-reader fallback audit (Chromium, both themes)

Structural and platform-tree evidence, all six destinations:

* Landmarks present exactly once each: `header.keel-topbar`, `main#main`,
  `footer.keel-statusbar`, `nav[aria-label='Surfaces']`.
* Main headings counted per surface: Cowork 1, Code 2, Duet 2, Fleet 3,
  Capabilities 3, Settings 7 (identical in both themes).
* Zero unnamed visible controls (41–49 per surface).
* DOM live regions and the CDP `Accessibility.getFullAXTree` agree: every
  surface exposes `generic:polite` plus `alert:assertive`; Fleet additionally
  exposes `status:polite` nodes.
* Focus traps and restoration: command palette (40 × Tab, 12 × Shift+Tab stay
  inside the `aria-modal` dialog; Escape restores the trigger) and the Fleet
  "New agent" dialog (24 × Tab stay inside; Escape restores the trigger).
* High contrast: `page.emulateMedia({ forcedColors: "active" })` reports
  `matchMedia("(forced-colors: active)").matches === true` on all six surfaces;
  each focused control keeps a `solid 2px rgb(255,255,255)` (CanvasText)
  outline; `.keel-btn` keeps a `1px solid` border; `forcedColorAdjust: auto`.
* `prefers-contrast: more` enlarges the focus ring to `3px`.

Dynamic announcements observed in the AX tree:

* **Status** — Duet "Reset Duet layout" via keyboard: notice text
  `"Duet layout reset to the default tabs and panes."` appears inside a
  `role=status`, `aria-live=polite` AX node.
* **Error** — forced HTTP 500 on `/api/bridge/providers`: `role=alert` banner
  `"Forced QA providers failure"` is exposed by an assertive AX alert node.
  (The test deliberately permits the expected browser 500 console error.)
* **Streaming** — mocked SSE `type:"stream"` delta `"Hello from stream"`:
  the `[data-cowork-live="true"][aria-live="polite"]` bubble becomes visible
  inside `role="log"`, and the text is found in a polite AX live region.

## 6. Manual checks that still require a human with NVDA / VoiceOver

NVDA is not installed on this host; VoiceOver requires macOS. The platform AX
tree was verified, but the following real screen-reader walkthrough must be
performed by a person and the results recorded (not claimed here).

**NVDA on Windows (Chromium):**

1. Install NVDA from nvaccess.org, start it, focus the Chromium window. In
   Chromium, press `Ctrl`+`+` twice (or `Ctrl`+mouse-wheel up) to reach 200 %
   zoom; confirm the page reflows with no horizontal scrollbar.
2. Press `NVDA`+`↓` ("say all") on each of the six destinations. Then press
   `D` to cycle landmarks and confirm *banner*, *main*, *navigation
   "Surfaces"*, *contentinfo* are announced on each.
3. Press `H` to cycle headings; confirm every surface announces its main
   heading and Settings announces the seven headings found by the automated
   audit.
4. Press `B` / `F` to cycle buttons and form fields; spot-check that each has
   a spoken name (the automated audit found none missing).
5. Trigger Duet → command palette (`Ctrl`+`K` → "Reset Duet layout" → `Enter`):
   without moving focus, NVDA should speak
   "Duet layout reset to the default tabs and panes."
6. Disconnect the bridge (or fail `/api/bridge/providers`) on Cowork: an
   assertive alert should speak the error text immediately.
7. With a configured local provider, start a Cowork turn: streamed tokens
   should be spoken from the live bubble without arrowing into the log.
8. Open the command palette, press `Tab` 40 times and `Shift`+`Tab` 12 times:
   focus must never leave the dialog; `Escape` must restore focus to the
   "Command palette (Ctrl+K)" button (`NVDA`+`Tab` announces the object).
9. Windows Settings → Accessibility → Contrast themes → select a high-contrast
   theme; verify the 2 px focus outline and control borders remain visible.
   Repeat `1`–`8` with the contrast theme active.

**VoiceOver on macOS (Safari or Chrome):**

1. `Cmd`+`F5` to enable VoiceOver; enable "Press Tab to highlight each item"
   in Safari → Advanced. Press `Cmd`+`+` twice for 200 % zoom.
2. Open the rotor with `VO`+`U`; navigate the *Landmarks* and *Headings* lists
   and confirm banner/main/navigation/contentinfo and the per-surface headings.
3. VoiceOver Utility → Verbosity → enable "Announce notification messages"
   and live-region announcements; repeat steps 5–7 of the NVDA list and note
   the exact spoken strings.
4. `VO`+`Tab` / `VO`+`Shift`+`Tab` inside the command palette and Fleet dialog;
   confirm focus stays inside and `Escape` restores the trigger.
5. macOS System Settings → Accessibility → Display → increase contrast /
   differentiate without colour; confirm focus outlines and control bounds.

## 7. Honest status of the remaining items

* **Real native browser zoom:** the *layout* criterion is verified by the
  720×450 proxy and the CDP page-scale evidence; the literal Ctrl+/Cmd+ gesture
  on a human desktop remains a manual step (section 6), because CDP cannot
  reflow the layout viewport (section 2).
* **Screen-reader hardware/software check:** platform AX tree and all
  structural/dynamic behaviours are verified in Chromium; actual NVDA /
  VoiceOver speech and route remain externally blocked (no NVDA installed, no
  macOS host) and are documented as manual steps.
* **Optional dictation: NOT IMPLEMENTED.** There is no dictation control, flag,
  or code path in the UI. This suite does not fake or stub it; it makes no
  claim of verification for dictation. It stays "not implemented" in the
  requirements matrix.
* **Live provider turn / real streamed audio:** no provider credentials on this
  host, so the streaming test uses a deterministic mocked SSE delta. Real
  provider round-trip remains blocked.
* **Packaged Electron/Tauri GUI, renderer decision, per-agent cost/hierarchy
  routes:** unchanged external blockers owned by other agents; not touched here.
