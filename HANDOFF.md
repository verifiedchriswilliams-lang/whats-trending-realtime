# TrendingInRealTime.com — Claude Code Handoff

This document is the first-session brief for Claude Code. Read CLAUDE.md for the full
product spec and architecture. This file covers: what's drifted since last active development,
what needs immediate attention, and how to work in this repo with Claude Code.

---

## Quick Start (Claude Code, Session 1)

```bash
cd ~/Projects/whats-trending-realtime
python3 trending_dashboard.py        # runs on http://localhost:8080
```

Production: https://www.trendinginrealtime.com
GitHub: github.com/verifiedchriswilliams-lang/whats-trending-realtime
Railway: auto-deploys on push to `main`

**Git is fully available from Mac terminal** — Claude Code can `git push` directly.
(Unlike the previous Cowork VM workflow, there is NO need for the
`git pull --rebase origin main && git push` workaround from a separate terminal.
Claude Code runs on the Mac and has full git access.)

---

## Code vs. Documentation Drift (as of Sept 2026 handoff)

The last active development session was ~3 months ago. The following items in the
actual code differ from what CLAUDE.md says — these are ground truth from the file.

### News Sources: 18, not 15

Three sources were added to `SOURCES[]` and `SCRAPE_SOURCES{}` that are not yet
documented in CLAUDE.md:

| ID | Name | RSS | Lean | Tier |
|---|---|---|---|---|
| cbsnews | CBS News | cbsnews.com/latest/rss/main (direct) | Center-Left | 2 |
| washexam | Washington Examiner | Google News RSS (site:washingtonexaminer.com) | Right | 2 |
| freepress | The Free Press | thefp.com/feed (direct) | Center-Right | 2 |

Both `cbsnews` and `washexam` are in `SCRAPE_SOURCES` (homepage scraping enabled).
`freepress` is NOT in `SCRAPE_SOURCES` — RSS only, no homepage cross-verification.

Source count is now **18 news RSS + 8 supplemental = 26 total** (not 23 as shown on
the loading screen and in CLAUDE.md).

### Memeorandum is the "reddit_posts" source

`fetch_memeorandum()` scrapes memeorandum.com and stores results in the `reddit_posts`
key of `data_store`. The function reuses `_REDDIT_CACHE`. This is confusing but
intentional — it was renamed in the data store before the reddit slot was repurposed.
Memeorandum is still active in the pipeline and renders in the Social Velocity sidebar.

---

## Immediate Cleanup Items (do these first)

### 🔴 Security: Hardcoded Facebook API token in production code

The Facebook tab was removed from the UI, but the backend code was NOT cleaned up.
Two places in `trending_dashboard.py` contain a hardcoded Facebook app token:

- Line ~806: inside `fetch_facebook_engagement()` — function is never called but still present
- Line ~1713: inside `@app.route('/debug/fb')` — a debug route that is publicly accessible

**Action required:**
1. Delete `fetch_facebook_engagement()` entirely (lines ~761–850)
2. Delete the `/debug/fb` route entirely (lines ~1707–1724)
3. Delete the `/debug/memo` route (lines ~1725–1760) — diagnostic, no longer needed
4. Confirm `fetch_facebook_engagement` is not called anywhere in `refresh_data()`

### 🟡 Loading screen source count is wrong

The loading overlay says "Scanning 23 sources" but actual count is 26.
Search for `Scanning 23 sources` and update to `Scanning 26 sources`.

### 🟡 CLAUDE.md source count and tables are out of date

Update CLAUDE.md:
- Project purpose: "18 major news sources" (not 15)
- Architecture stack: feedparser now ingests 18 news sources (not 15)
- Data sources section: add CBS News, Washington Examiner, Free Press to the Tier 2 table
- Supplemental sources total: 18 + 8 = 26 total
- Per-source QA table: add rows for cbsnews, washexam, freepress

---

## Staleness Checklist (3 months since last session)

These should be verified on first session — some may have broken since last active dev.

### RSS Feeds to Verify
Run a quick `feedparser.parse(url)` on each to confirm they're still returning entries:

| Source | Feed URL | Risk |
|---|---|---|
| The Free Press | thefp.com/feed | New — hasn't been QA'd |
| Washington Examiner | Google News RSS | Google News RSS format can change |
| Daily Wire | dailywire.com/feeds/rss.xml | Has changed URLs before |
| Fox News | feeds.foxnews.com/foxnews/latest | History of feed changes |
| NBC News | feeds.nbcnews.com/nbcnews/public/news | Occasionally returns empty |
| Breitbart | breitbart.com/feed | Has had certificate issues |

### API Endpoints to Verify
- **Bluesky** `app.bsky.unspecced.getTrendingTopics` — "unspecced" means Bluesky can
  change or remove it without notice. If it returns 0 topics or errors, check the
  AT Protocol changelog or try `app.bsky.unspecced.getTrends` as fallback.
- **Twitter/X trends** — `getdaytrends.com` and `trends24.in` both block cloud IPs
  intermittently. If both fail, graceful "unavailable" message shows. Low priority.
- **Google Trends RSS** — historically stable; verify it still returns 25 entries.
- **Drudge scraper** — Drudge has changed markup before; verify links are being parsed.

### Railway / Infrastructure
- Confirm the Railway deployment is still running and not on a billing hold
- Check if Python 3.13 is still the Railway auto-detected version (do NOT add runtime.txt)
- Verify `www.trendinginrealtime.com` resolves correctly (GoDaddy CNAME → Railway)
- Check Railway logs for any recurring errors (timeout patterns, DNS failures, etc.)

### Dependencies
Current `requirements.txt` (minimal, no pinned versions beyond floor):
```
feedparser>=6.0.0
flask>=3.0.0
requests>=2.31.0
beautifulsoup4>=4.12.0
gunicorn>=21.0.0
```
Run `pip list --outdated` locally to spot any packages with significant version jumps.
No action needed unless something broke — Railway pins the environment at deploy time.

---

## Architecture Reminder (the important bits)

**Single file:** The entire app — Flask server, data pipeline, HTML/CSS/JS — lives in
`trending_dashboard.py` (~2,650 lines). There is no template directory, no static folder.
The HTML is a raw string embedded in the Python file.

**No database.** All state is in-memory. Every Railway restart = cold start, ~30 min
for first data cycle to complete. The `loading: True` flag controls the splash screen.

**Refresh cycle:** `refresh_data()` runs every 30 minutes via a background thread.
Call `/debug/refresh` (GET) to force a synchronous refresh and see any exceptions.

**Auth:** A `_SESSION_TOKEN` is generated at startup and injected into the HTML. All
`/api/data` calls require this token in the `X-Session-Token` header. This is a
lightweight anti-scraping measure, not real auth. No user login exists.

**Clustering constants to know:**
```python
SIMILARITY_THRESHOLD = 0.28   # greedy assignment threshold
MERGE_THRESHOLD = 0.20        # post-pass centroid merge threshold
MAX_VALID_SCRAPE_POS = 80     # cap for scrape_confirmed flag
INJECT_LIMIT = 10             # synthetic injection position cap
```

---

## Routes

| Route | Purpose |
|---|---|
| `/` | Main dashboard (HTML) |
| `/bluetrends` | Blue Trends page direct link (server-injects `_INIT_VIEW="bt"`) |
| `/privacy` | Required for Meta app (keep, do not delete) |
| `/robots.txt` | Standard robots |
| `/api/data` | JSON data feed (requires X-Session-Token header) |
| `/api/refresh` | POST — trigger async refresh |
| `/debug/refresh` | GET — synchronous refresh + error dump (keep for debugging) |
| `/debug/fb` | ⚠️ DELETE — dead Facebook debug route with hardcoded token |
| `/debug/memo` | 🟡 DELETE — old Memeorandum diagnostic, no longer needed |

---

## What's Working Well (no changes needed)

- TF-IDF clustering with post-merge pass — stable, clusters are accurate
- Bluesky + Liberal Reddit Blue Trends page — working, showing all 4 subreddits
- Synthetic article injection across 10+ sources — consistently ~47 articles/cycle
- Heat score formula — well-calibrated
- DW alignment score with prefix matching — accurate
- Velocity sparklines (Jaccard) — working correctly
- Junk injection filter — recently fixed for hyphen/em-dash "Top Stories" pattern
- Mobile bottom nav — working on screens ≤900px

---

## Suggested First Session Priorities

1. **Security cleanup** — remove dead Facebook code and hardcoded token (30 min)
2. **Verify live sources** — hit `/debug/refresh` on production, check logs for failures
3. **Update loading screen + CLAUDE.md** — fix source count from 23 → 26
4. **QA new sources** — check CBS News, Washington Examiner, Free Press are returning
   articles and scraping correctly; add to per-source QA table in CLAUDE.md
5. **Assess new feature priorities** — review the backlog in CLAUDE.md and decide
   what the next development phase looks like
