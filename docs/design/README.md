# 2030 redesign — design source of truth

- `DESIGNSYSTEM.md` — tokens, type scale, material, motion, data-display and content
  rules. Authored in Claude Design; the canonical implementation is
  `Trending in Real Time v3.dc.html` in that project, which is **not** reachable from a
  Claude Code session (`claude.ai/design/p/...` is not an Artifact URL and 403s).
- `artboards/` — PNG exports: full page, hero, topics list, source roster.

## Status: not yet implemented

Nothing in `trending_dashboard.py` has been changed for this redesign. These are
recommendations under review, not a work order.

## The artboards predate the 8 Sept 2026 descope

They were produced against the morning's state of the app, so several things in them no
longer match the code. Reconcile before building:

| Artboard shows | Code today |
|---|---|
| Bluesky in supplemental + a "Bluesky trending" column on Blue Trends | Bluesky removed |
| Drudge Report in supplemental | Drudge removed |
| "Reddit, four communities" | Eight — four liberal, four conservative |
| "8 supplemental feeds" (footer) | 10 |
| Blue Trends only | Blue **and** Red Trends, deliberately symmetric |

## Claims in the artboard copy that the code does not currently support

- **"Nothing is weighted by outlet."** Fox News carries `rss_limit: 50` against 20 for
  every other source, so it contributes more articles to the pool. `_LABEL_SRC_PREF`
  also ranks outlets, though only to choose display label text. Either change the code
  or soften the copy.
- **"Leanings are third-party ratings."** They are not. Every lean value was assigned by
  hand in `SOURCES`. This needs a real citation (AllSides, Ad Fontes) or a rewrite.
  Shipping a false attribution is worse than shipping none.

## Lean buckets reconcile cleanly

The design uses three buckets where the code has five tiers, and they map exactly:

- **Left (7)** = `left` + `center-left` — CNN, NYT, WaPo, NBC, NPR, CBS, Politico
- **Center (6)** = `center` — AP, Reuters, BBC, The Hill, Axios, USA Today
- **Right (7)** = `right` + `center-right` — Fox, WSJ, NY Post, Washington Times,
  Washington Examiner, National Review, The Free Press

Note that `center-left` and `left` currently share the same hex (`#1D4ED8`), so those two
tiers are already indistinguishable in the UI.
