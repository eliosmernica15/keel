# Keel Design System — Obsidian & Gold (refined)

**Sources of truth:** `fleet-next/app/globals.css` (colour tokens, themes, fonts) and `fleet-next/app/ui.css` (semantic aliases, scale, primitives, shell). Feature CSS modules may consume tokens but must not redefine them.

---

## 1. Palette

Colour literals exist only in `globals.css`. `ui.css` maps them to semantic roles; components use the roles.

| Role | Alias | Dark | Light |
|---|---|---|---|
| App background | `--k-bg` | `#0A0605` ambient | `#F7F4EF` family |
| Elevated surface | `--k-surface` | translucent obsidian | translucent warm white |
| Sidebar / chrome | `--k-side` | translucent obsidian | translucent warm white |
| Card / control | `--k-card` | white 4% | white 38% |
| Primary text | `--k-text` | `#F2F0EA` | `#241F1A` family |
| Secondary text | `--k-muted` | `#8A8279` | `#6F685F` family |
| Accent | `--k-accent` | `#E6D54C` | `#8A5A07` family |
| Success | `--k-ok` | `#6FE3B0` | `#1B6B47` |
| Warning | `--k-warn` | `#E6D54C` | `#9A6A05` |
| Danger | `--k-danger` | `#F09A86` | `#C2432C` |
| Info | `--k-info` | `#8AB4FF` | `#3355B0` |

Gold is a signal, not wallpaper. Large gold fills are reserved for the primary action only. Status always pairs colour with an icon or label — never colour alone.

## 2. Typography

- Interface/body: **Inter** (self-hosted variable woff2)
- Titles/brand: **Space Grotesk**
- Code, paths, terminal, shortcuts: **JetBrains Mono**
- Styles: display, title, heading, body, label, caption, code. Avoid 11–12px for frequently used controls; 13px is the default control size.

## 3. Spacing, radii, elevation

- Spacing scale: 4 / 8 / 12 / 16 / 20 / 24 / 32 / 40 / 48 / 64px (`--k-space-1…16`)
- Radii: 7px controls (`--k-radius-sm`), 12px cards, 18px panels, 24px dialogs
- Elevation: `--k-shadow-sm` (controls), `--k-shadow-md` (dialogs/drawers)
- Focus: `:focus-visible` 2px accent ring with an app-background gap (`--k-focus-ring`)
- Layers: base 1, sticky 20, drawer 60, modal 80, toast 100

## 4. Components (build once)

`components/ui.tsx` provides: Button (primary/secondary/ghost/danger, sm/md/lg, loading), IconButton, SegmentedControl, Badge, StatusDot, Card, EmptyState, Skeleton, Spinner, Toggle, TextField, Textarea, Tabs, Dialog (focus trap + Escape + restore), Tooltip, Progress, SectionTitle, ResizeHandle (pointer + arrow-key resizing).

`components/icons.tsx` provides an original 24px line-icon set and `KeelMark`. No external icon library, no copied brand assets.

Every primitive documents/displays: default, hover, focus, active, disabled, loading, empty and error states. Feature modules must use these rather than one-off styles.

## 5. Motion

- Entrances: fade + small rise (`--k-dur`, `--k-dur-slow`), spring for drawers (`--ease-spring`)
- Hover/press: 120ms (`--k-dur-fast`)
- Streaming: animate the active indicator; **never** reflow or re-animate the whole transcript per token
- No continuously running blur/filter/shadow effects
- `prefers-reduced-motion` and the user's motion setting both collapse all durations to ~0 via `data-reduced-motion`

## 6. Themes

`layout.tsx` applies the saved theme before first paint via an inline script, so there is no flash. `AppProvider` supports dark, light and system; `resolvedTheme` follows `prefers-color-scheme` when set to system. Theme choice persists in `keel-theme-v2`.

## 7. Responsive

- Desktop: fixed sidebar (resizable 200–460px) + canvas + right panel (260–620px)
- ≤900px: sidebars become drawers with a scrim; surface labels collapse to icons
- ≤560px: brand name and optional status items hide; composer and Stop remain reachable
- Required no-overflow viewports: 360×800, 390×844, 768×1024, 1024×768, 1280×800, 1440×900

## 8. Accessibility contract

Semantic elements first; accessible names on every control; labels bound to inputs; dialogs with `role="dialog"`, `aria-modal`, focus trap, Escape and focus restoration; live regions for notices; `aria-selected` on tabs; `role="separator"` + keyboard support on resize handles; visible focus ring; reduced-motion support at every animation entry point.

## 9. Provenance

Patterns were adapted from the public references listed in the implementation plan (app shells, timelines, activity lines, approval cards, subagent trees). No logos, source files, stylesheets, screenshots or branded colour systems were copied. See `UI-REFERENCE-PROVENANCE.md`.
