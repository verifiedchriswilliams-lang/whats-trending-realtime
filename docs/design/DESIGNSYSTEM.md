# Design System — TrendingInRealTime.com

Reference for the 2030 redesign. Source of truth for tokens, type, material and layout.
The canonical implementation is `Trending in Real Time v3.dc.html` in the design project.

**Design intent:** premium, calm, intelligent, inevitable. Apple's design language after
another decade of refinement. Clarity, negative space, precise typography, restrained
hierarchy. Not futuristic decoration — the advanced quality comes from material behavior
and proportion, never from glow, neon, or sci-fi ornament.

---

## Non-negotiables

1. **No borders, no cards, no chrome.** Hierarchy comes from whitespace, scale and
   luminance. A container appears only on interaction. There is exactly one persistent
   rule on the page: the header hairline.
2. **No mono type, no ALL-CAPS micro-labels.** Those read as dashboard, not editorial.
   Small labels are the same sans at 13px in muted ink, sentence case.
3. **Political leaning is shown, never judged.** Left/center/right share identical
   lightness and chroma, differing only in hue. No red-for-bad. Falling velocity is
   neutral gray, not red.
4. **Numerals are tabular.** `font-variant-numeric: tabular-nums` on the root.
5. **Nothing below 15px sits lighter than L 0.53** on the light ground (4.5:1 floor).

---

## Color

Two complete palettes. Every color is a custom property on the root with an inline
fallback, so a theme swap touches one object. Light is the default.

### Light (default)

| Token | Value | Use |
|---|---|---|
| `--bg` | `oklch(0.972 0.004 85)` | Page ground |
| `--sf` | `oklch(1 0 0)` | Lifted surface (hover, image slots) |
| `--ink` | `oklch(0.22 0.008 70)` | Headlines, primary text |
| `--ink2` | `oklch(0.44 0.008 70)` | Body, secondary |
| `--ink3` | `oklch(0.53 0.007 70)` | Labels, meta, timestamps — contrast floor |
| `--ll` | `oklch(0.62 0.075 255)` | Left of center |
| `--lc` | `oklch(0.66 0.012 90)` | Center |
| `--lr` | `oklch(0.62 0.075 35)` | Right of center |
| `--lo` | `oklch(0.89 0.004 80)` | Not covering |
| `--acc` | `oklch(0.55 0.11 158)` | Live, rising velocity |
| `--sheen` | `oklch(1 0 0 / 0.9)` | Ambient diffusion |
| `--bar` | `oklch(0.972 0.004 85 / 0.72)` | Header ground |
| `--hair` | `oklch(0.2 0.01 70 / 0.09)` | Header hairline |
| `--lift` | `inset 0 1px 0 oklch(1 0 0 / .8), 0 14px 44px oklch(0.3 0.01 70 / .07)` | Raised plane |

### Dark

| Token | Value |
|---|---|
| `--bg` | `oklch(0.155 0.006 250)` |
| `--sf` | `oklch(0.205 0.008 252)` |
| `--ink` | `oklch(0.97 0.002 250)` |
| `--ink2` | `oklch(0.78 0.005 250)` |
| `--ink3` | `oklch(0.645 0.008 250)` |
| `--ll` | `oklch(0.70 0.09 255)` |
| `--lc` | `oklch(0.74 0.015 250)` |
| `--lr` | `oklch(0.74 0.09 45)` |
| `--lo` | `oklch(0.32 0.006 250)` |
| `--acc` | `oklch(0.78 0.13 158)` |
| `--sheen` | `oklch(0.34 0.035 258 / 0.5)` |
| `--bar` | `oklch(0.155 0.006 250 / 0.72)` |
| `--hair` | `oklch(1 0 0 / 0.09)` |
| `--lift` | `inset 0 1px 0 oklch(1 0 0 / .07), 0 30px 80px oklch(0 0 0 / .45)` |

The three lean hues hold constant lightness and chroma within a theme. If you add a
lean tier, match L and C and change only H.

---

## Typography

**Instrument Sans** (Google Fonts, weights 400/500/600). One family, no exceptions.

| Role | Size | Weight | Tracking | Leading |
|---|---|---|---|---|
| Hero headline | `clamp(44px, 7.6vw, 96px)` | 400 | `-0.045em` | 0.94 |
| Hero lede | `clamp(16.5px, 1.55vw, 20.5px)` | 400 | — | 1.6 |
| Section heading | `clamp(25px, 2.8vw, 36px)` | 400 | `-0.038em` | — |
| Sub-section heading | `clamp(22px, 2.2vw, 27px)` | 400 | `-0.032em` | — |
| Story headline (row) | 18px | 500 | `-0.022em` | 1.35 |
| Body / list item | 15.5–16px | 400 | `-0.012em` | 1.5 |
| Label, meta, timestamp | 13–13.5px | 400 | — | 1.5 |
| Large numeral | `clamp(34px, 3.8vw, 50px)` | 400 | `-0.045em` | 1 |

Display type gets *lighter* as it gets larger — 400 at 96px, 500 at 18px. Weight and
negative tracking scale together; that relationship is what makes large type read as
expensive rather than loud.

---

## Space and rhythm

- Container: `max-width: 1200px`, padding `clamp(22px, 5vw, 64px)`.
- Section padding: `clamp(44px, 7.5vh, 96px)` vertical. Hero opens at
  `clamp(72px, 13vh, 152px)`.
- Density unit `--u` (7 / 9 / 12px for compact / balanced / airy) drives row padding
  and list gaps only. Every consumer needs an inline fallback: `calc(var(--u, 9px) * 2.6)`.

  **`--u` is a design-time control, not a shipped setting.** In the design canvas it is
  driven by the density prop and surfaces in the Tweaks panel as Compact / Balanced /
  Airy, so spacing can be judged without re-editing the file. **In production it is baked
  at 9px and the prop is deleted.** Density toggles on a reading surface go almost
  entirely unused, and the few readers who touch one land in a layout nobody designed.
  It reaches only four places — row padding, the legend margin, the feed gap and the
  last-hour gap — which is not enough of the system to justify a control. If a reader
  setting is ever wanted here, the useful one is text size, not spacing.
- Sibling groups use flex/grid with `gap`. Never margin-spaced inline siblings.
- Everything below the fixed-format layer is fluid: `minmax(0, 1fr)` tracks,
  `repeat(auto-fit, minmax(Npx, 1fr))` grids, wrap enabled, no fixed heights on text.

---

## Material

Depth is luminance and one hairline of reflected light — never a drawn border.

**Raised plane (row hover, image slot, thumbnail):**
```
background: var(--sf);
box-shadow: var(--lift);
border-radius: 20–28px;
transition: background .38s cubic-bezier(.22,.61,.36,1),
            box-shadow .38s cubic-bezier(.22,.61,.36,1);
```
Rows carry no container at rest. They gain one on hover, using negative horizontal
margin equal to their padding so the surface extends past the text column.

**Ambient diffusion:** a single large soft radial of `--sheen`, positioned off-center,
on a `position: relative` parent with `overflow: hidden`. One per view, behind the hero.
Never a gradient background, never a blob.

**Radii:** 20px thumbnails, 28px interactive rows, `clamp(22px, 3vw, 38px)` hero image.
Soft and generous. No sharp rectangles, no pill-shaped cards.

Forbidden: visible borders, glassmorphism panels, heavy or tight shadows, bevels,
gradient fills, glow.

---

## Motion

Easing is `cubic-bezier(.22,.61,.36,1)` for response, `cubic-bezier(.16,.84,.44,1)`
for entrance. Response 340–380ms; entrance 800ms–1s.

- **Entrance:** hero elements rise 16px and fade, staggered 70ms apart. Runs once.
  Use `animation-fill-mode: backwards`, never `both` — an animation that fails must
  leave the element at its natural style, not stranded at zero opacity.
- **Expansion:** 380ms unfold, 7px translate.
- **Live indicator:** 3.6s opacity breathe, nothing else.
- **Sparkline:** draws once via `stroke-dasharray` on load.

The page is fully at rest within two seconds. Nothing loops except the live dot.

---

## Data display

**Coverage dots — the core device.** One dot per outlet, grouped left / center / right,
filled where the outlet is carrying the story and faint (`--lo`) where it is not. Built
with a repeating radial gradient so a group is one element:

```
width: <count × 9>px; height: 9px; color: var(--ll);
background-image: radial-gradient(circle at 4.5px 4.5px, currentColor 2.1px, transparent 2.3px);
background-size: 9px 9px;
```
9px tile in lists, 13px in the hero. Group order is always left → center → right →
not covering, so shape alone reads as balance. Group widths must total the real roster.

**Velocity meter.** A 4-point polyline (34×14) plus the signed delta, mirroring the
backend's four stored heat readings, roughly two hours. Rising uses `--acc`; falling
uses `--ink3`. Never red.

**Signal.** Right-aligned numeral in `--ink2`, no bar, no badge. The dots already
carry magnitude.

---

## Content rules

- Leanings are third-party ratings. Say so wherever they appear, and say they are not a
  judgment of accuracy. This line is load-bearing, not boilerplate.
- Absence is data: name the outlets *not* carrying a story ("Silent", "Not carried by").
- The full source roster (currently 20: 7 left, 6 center, 7 right) lives at the bottom
  of the page, after the reader has seen the work. Scope claims up top link down to it
  rather than restating it.
- Supplemental feeds are labeled as velocity-only and stated to be outside the ranking.
- No emoji. No icons where a word will do. No exclamation.

---

## Identity

**Mark:** eight equal circles on an invisible ring, five solid and three at 28% opacity.
One circle per outlet, filled where covering. Empty center — the emptiness is the point.
Navy `#1A2231` on light, `#F2F4F8` on dark. No wordmark in the header; the mark stands
alone. Favicon is the same geometry as an inline SVG data URI.

---

## Verified defects to avoid

Real failures caught during this build. Worth reading before changing layout code.

1. `box-sizing: border-box` plus `padding-top` on a fixed-height bar collapses its
   content box to zero. Use `margin-top`.
2. Absolutely positioned ambient layers with negative horizontal insets cause page-wide
   horizontal scroll. Clip them: `overflow: hidden` on the positioned parent.
3. Custom properties must be declared on the root element *and* carry inline fallbacks
   at every use. A dropped declaration fails silently to the fallback.
4. Measuring element positions synchronously at mount reads all zeros — layout has not
   happened. Defer to `requestAnimationFrame`.
5. Scroll-driven style values proved unreliable in this stack. The header is static by
   decision: a wayfinding label that can name the wrong section is worse than none.
