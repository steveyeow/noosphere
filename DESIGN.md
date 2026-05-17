# Noosphere Design System

The visual language is aligned with Apple's current system design (the "Liquid
Glass" / iOS 26 · macOS 26 era): **separation by space, surface tint, soft depth,
and typography — not strokes.** Borders are the exception, not the scaffolding.

This file is the source of truth. All styling lives in one place:
`noosphere/api/static/styles.css`, driven by `:root` custom properties with a
`.dark` / `prefers-color-scheme` mirror. Change tokens first; only touch a
component rule when a stroke is structural.

## Principles

1. **Borderless.** Regions are told apart by a surface-tint step + soft
   elevation + whitespace + type weight. A 1px hairline (`--brd`) is a
   low-contrast last resort for dense lists only — never a box around a card.
2. **Concentric radii.** Use the `--r-*` scale. Outer containers take the
   larger radius; nested elements step down so corners stay concentric.
3. **Depth, not outline.** Cards and panels lift with `--shCard` and rise to
   `--shM` on hover. Figure/ground comes from shadow + fill, not a ring.
4. **Restrained glass — chrome only.** Translucent `--gl` + `--glBlur` is for
   *floating, transient* chrome: popovers, dropdowns, command pickers,
   tooltips. Reading surfaces (doc rows, wiki, entity bodies, chat, large
   modals) stay **solid and opaque** for legibility. This is where Apple
   landed after walking back its own beta transparency.
5. **Density preserved.** Spacing and type scale are essentially unchanged —
   this is a knowledge tool, not a marketing page. We adopted the geometry and
   depth cues, not inflated whitespace.
6. **Light and dark are equal.** Every token has a dark value; verify both.

## Tokens (`styles.css` `:root`)

### Surfaces (elevation ladder)
| Token | Light | Dark | Use |
|---|---|---|---|
| `--bg` | `#f5f5f7` | `#1c1c1e` | App base; recessed chrome (sidebar, rpanel) |
| `--bg3` | `#fafafa` | `#242426` | Content area — one step above base |
| `--bg2` | `#fff` | `#2c2c2e` | Raised surface — cards, rows, panels, modals |
| `--bgH` | `#eeeef0` | `#3a3a3c` | Hover fill; filled-input rest; segmented track |
| `--bg1` | `#eeeef0` | `#3a3a3c` | Recessed inset (code blocks) |
| `--accSoft` | `rgba(29,29,31,.055)` | `rgba(245,245,247,.07)` | Filled control rest (buttons, chips) |

Separation between two adjacent regions = a tint step on this ladder, plus
optional `--shCard`. Do not add a border to create it.

### Depth
| Token | Use |
|---|---|
| `--shCard` | Resting elevation for cards/rows/panels |
| `--shM` | Hover / active lift |
| `--shPop` | Floating chrome (popovers, menus, modals) |
| `--sh` / `--shL` | Subtle / large legacy depth |
| `--ring` / `--ringA` | Soft focus ring (replaces border-color focus) |

### Radius (concentric scale)
`--r-xs 6` · `--r-sm 9` · `--r-md 13` · `--r-lg 18` · `--r-xl 24` ·
`--r-pill 999`. Rows/inputs `--r-md`; cards/composers `--r-lg`; modals
`--r-xl`; buttons/chips/segments `--r-pill`.

### Glass (chrome only)
`--gl` (≈0.72 frosted surface) + `--glBlur` (`saturate(180%) blur(20px)`) +
`--glB` (edge highlight). Apply all three together on floating chrome.

### Hairline
`--brd` / `--bd` are intentionally near-invisible (`.045` light / `.06` dark).
They survive only as faint inset separators inside dense lists.

## Component patterns

- **Card / row** (`.doc-item`, `.ep-doc`, `.mc-card`, `.cv-ins-card`, …):
  `background:var(--bg2); border-radius:var(--r-md|--r-lg);
  box-shadow:var(--shCard)`; hover → `var(--shM)` + `translateY(-1px..-2px)`.
  No border.
- **Button / chip** (`.btn-ghost`, `.cv-act-btn`, `.home-chip`, `.btn-xs`, …):
  filled `var(--accSoft)`, `border:none`, `border-radius:var(--r-pill)`;
  hover → `var(--bgH)`. Primary stays `--btnBg`.
- **Input** (`.mc-search`, `.gs-bar`, `.cmp-chat-input`, `.settings-input`, …):
  filled `var(--bgH)`, `border:none`, `--r-sm|--r-md`; focus →
  `background:var(--bg2); box-shadow:var(--ring)`.
- **Segmented control** (`.cv-tabs`, `.mc-toggle`, `.cv-ins-winbar`): pill
  track; active segment = `var(--bg2)` + `var(--sh)` (or `--bgH` fill where
  the page is already near-white, e.g. `.cv-tab--active`).
- **Floating chrome** (`.sb-popover`, `.srcs-pop`, `.mc-menu`,
  `.term-cmd-picker`, `.gs-results`, …): `background:var(--gl)` +
  `backdrop-filter:var(--glBlur)` + `box-shadow:var(--shPop)`, `border:none`,
  concentric radius.
- **Modal panel** (`.pro-modal`, `.settings-modal`, `.acm-panel`,
  `.share-panel`, …): solid `var(--bg2)` (opaque for legibility) +
  `--shPop` + `--r-xl`, no border.
- **App shell**: `.sidebar` / `.rpanel` use `var(--bg)` with an
  `inset … 0 var(--brd)` whisper edge; `.content` uses `var(--bg3)`. The tone
  step is the separator.

## Do / Don't

- Do change a token to shift the whole system; do keep light + dark in sync.
- Do reuse the shared primitive (e.g. `.doc-item`) — restyle the primitive,
  not one instance.
- Don't add `border:1px solid var(--brd)` to box a surface — use tint + depth.
- Don't put translucency behind body text.
- Don't introduce ad-hoc hex values or one-off shadows; extend the scale.

## Coverage

The system is applied product-wide: app shell (sidebar, rpanel, corpus/wiki,
entity pages, chat/compile, composer), shared chrome
(cards/buttons/inputs/modals/popovers), the public landing (`.lp-*`), and
pricing (`.pg-*`). The landing topbar and hero terminal keep an intentional
frosted-glass treatment (decorative product visual over the network canvas),
now expressed through `--gl` / `--glBlur` rather than ad-hoc rgba.
