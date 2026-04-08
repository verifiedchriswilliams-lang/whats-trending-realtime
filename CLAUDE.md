# TrendingInRealTime.com — Editorial Intelligence Dashboard

## Project Purpose

A real-time editorial intelligence tool for the Daily Wire's editorial team. It aggregates RSS feeds from 15 major news sources plus Bluesky, liberal Reddit subreddits, Drudge, Twitter/X trends, and Google Trends (23 sources total) every 30 minutes, clusters stories by specific topic (not generic keywords), and surfaces a Daily Wire Coverage Alignment score — showing editors which top trending stories they are and aren't covering.

**Target audience:** Conservative Americans 25–65. The editorial philosophy is "Daily Mail for American conservatives without the tabloid streak" — credibility of NYT/WaPo with a conservative perspective.

---

## Architecture

Single-file Python Flask app (`trending_dashboard.py`) deployed on Railway. No database — all state is in-memory. The HTML dashboard is embedded as a raw string in the Python file.

```
trending_dashboard.py   ← entire app (Flask server + data pipeline + HTML/CSS/JS)
requirements.txt        ← feedparser, flask, requests, beautifulsoup4, gunicorn
Procfile                ← web: python trending_dashboard.py
CLAUDE.md               ← this file
```

**Stack:**
- Python 3.13 (Railway auto-detected — do NOT add runtime.txt, it breaks the build)
- Flask for HTTP serving
- feedparser for RSS ingestion (15 news sources + 4 Reddit subreddits, concurrent via ThreadPoolExecutor)
- requests + BeautifulSoup4 for homepage scraping (13 sources)
- Google Trends via official public RSS feed (no API key, no rate limits)
- Bluesky AT Protocol public API (`app.bsky.unspecced.getTrendingTopics`, no auth required)
- Reddit RSS feeds for 4 liberal subreddits (politics, progressive, liberal, democrats) via feedparser
- gunicorn for production serving (via Procfile)
- Railway for hosting, GitHub for version control

---

## Key Algorithms

### Heat Score
`heat_score = (source_count × 12) + article_count + (hero_count × 20) + (double_confirmed × 10) + (editorial_spotlight × 15)`

- `source_count` = number of distinct outlets covering this story
- `article_count` = total articles in the cluster
- `hero_count` = outlets where this story was RSS position 0–1 OR appeared on scraped homepage (pos ≤ 8)
- `double_confirmed` = outlets where story is BOTH RSS position 0–1 AND scraped from homepage
- `editorial_spotlight` = outlets where scraped homepage position is 1–3 (editors are actively leading with this story; for Daily Wire this maps to their "Top Stories" section)

### Story Clustering — TF-IDF Cosine Similarity (IMPORTANT — do not revert this logic)

Stories are clustered using **TF-IDF cosine similarity**, not keyword seeds. This replaced the old keyword-frequency approach after it proved unable to prevent false merges (e.g. "Delta/Congress" merging unrelated stories that shared a common word).

**How it works:**
1. Each article title is tokenized and stopwords are removed (see `STOP_WORDS` set)
2. A TF-IDF sparse vector is built for all article titles in the corpus
3. Articles are greedily assigned to the nearest existing cluster centroid if cosine similarity ≥ `SIMILARITY_THRESHOLD = 0.28`
4. If no cluster exceeds the threshold, a new cluster is seeded
5. Cluster centroids are updated online (running mean) as new articles join
6. **Post-processing merge pass:** After greedy clustering, any two clusters whose centroids have cosine similarity ≥ `MERGE_THRESHOLD = 0.20` are merged. This catches false splits where the same story was seeded from two different vocabulary angles (e.g. "Oil slides after Iran ceasefire" vs "US-Iran agree to ceasefire"). Iterates until no more merges are possible.

The key advantage: two articles must share a **pattern of words**, not just one, to exceed the threshold. Single shared words rarely cross it.

**Constants to tune:**
- `SIMILARITY_THRESHOLD = 0.28` — raise to tighten clusters (fewer false merges), lower to loosen (catches more related stories)
- `MERGE_THRESHOLD = 0.20` — post-processing centroid similarity required to merge two existing clusters. Lower than SIMILARITY_THRESHOLD to catch same-story splits.
- `STOP_WORDS` — high-frequency political/news words that would cause false merges if left in the TF-IDF vocabulary. Currently includes: trump, president, american, united, states, says, told, report, new, first, could, would, one, year, people, government, country, also, last, week, two, day, three, days, ago, news, just, back, make, time, according, say, still, us, war, world, think, like, big, old, former, just, top, high, state, federal, national, second, city, million, billion, big, great, major, leading, meet, talks, deal, amid, amid, call, push, move, take, help, plan, after, amid, despite, over, under, house, senate, congress, parliament, lawmakers, republican, democrat, gop, bipartisan, party, bill, vote, law, act, policy, administration, officials, white

**Credible source filter:** Only counts a source toward `source_count` if the article is either scrape-confirmed (appeared on homepage) OR less than 4 hours old.

**Scrape position cap (`MAX_VALID_SCRAPE_POS = 80`):** An article is only marked `scrape_confirmed=True` if its matched scrape position is ≤ 80. Fox News's raw HTML (server-side rendered) is fully parseable by BeautifulSoup — but the anchor link fallback sweep picks up static sidebar/footer links at positions 90–150+. The Fox-specific targeted scraper (`div.big-top`, `div.thumbs-2-7`) ensures editorial headlines appear at positions 1-10, and the cap blocks the stale footer matches that follow. All legitimate editorial content from any source confirms within positions 1–75. This prevents stale Google News RSS articles (surfaced by relevance, not recency) from inflating source counts for stories outlets have moved on from.

### Homepage Scraping (Cross-Verification)
`scrape_homepage(sid, url)` fetches each source's actual homepage and extracts all `<h1>/<h2>/<h3>` text plus prominent anchor link text. Returns a **3-tuple**: `(headlines, url_map, orig_map)`.

- `headlines` = `[(normalized_text, position), ...]` for cross-verification matching
- `url_map` = `{normalized_text: absolute_url}` — used by synthetic injection
- `orig_map` = `{normalized_text: original_case_title}` — used to preserve casing in injected articles

Runs concurrently with RSS fetch (20-worker ThreadPoolExecutor).

Articles are matched against scraped headlines using:
1. Exact normalized substring match (title in scraped or scraped in title)
2. Word-overlap ≥ 60% for titles with 4+ words

Matched articles are marked `scrape_confirmed=True`. In the expanded article view:
- `★` = RSS hero (feed position 0 or 1)
- `✓` = scrape confirmed (appeared on homepage)
- `★✓` = double-confirmed (both RSS position AND scraped homepage)

**Source card ordering:** Editorial picks (scrape_position set) appear first, then RSS chronological. For Daily Wire, `topStoryTextContainer` h3s are targeted first to capture editorial Top Stories in correct order.

### Synthetic Article Injection
When a source's RSS pool misses editorially pinned stories (Fox's chronological feed, CNN's sparse pool, etc.), articles are injected from scraped homepage headlines that weren't matched to any RSS article.

**How it works:**
- After cross-verification, any scraped headline at position ≤ `INJECT_LIMIT = 10` that wasn't matched to an RSS article and has a captured URL is injected as a synthetic article
- Injected articles get `scrape_confirmed=True`, `scrape_position=pos`, `synthetic=True`, `pub_ts=None`
- URL quality gate: href must match the source's own domain AND have path depth ≥ 2 (filters nav/section links)
- Junk filter (`_is_junk_injection`): blocks nav headers, ads, promos, podcast/newsletter links — patterns include `% off`, `VIP membership`, `Listen to [source] podcasts`, `Site Information Navigation`, `[-–] Top Stories` (matches both hyphen and em-dash variants — e.g. "New York Times - Top Stories"), `newsletter`, `subscribe`, `Every Day at [time]`, etc.
- `SKIP_INJECT = {'dailymail'}` — Daily Mail homepage is lifestyle/celebrity-heavy; injection would surface non-news content
- Sources with no `url_map` (Reuters blocked, The Hill 403, Fox Business JS-rendered) are automatically excluded

**Typical injection counts (from March 2026 QA):** ~47 total synthetic articles per cycle across 10 sources. Fox: 9, AP: 9, NY Post: 7, WashTimes: 6, Breitbart: 4, NYT: 3, NBC: 3, CNN: 2, Townhall: 3, Sky News: 1.

### Velocity Sparklines
Each trending topic's heat trajectory is tracked across refreshes using **Jaccard source-set matching** — a cluster is considered "the same story" across cycles if the set of source IDs covering it overlaps by ≥ 33% with a previously seen cluster.

This replaced a naive approach that keyed history by cluster label text, which broke every cycle because TF-IDF cluster labels change as new articles arrive.

`_heat_history = {}` stores up to 4 readings per frozenset(source_ids). The `spark()` JS function draws a real multi-point curve from this array.

### Daily Wire Alignment Score
Checks what % of the top 10 trending topics Daily Wire is covering. Checks ALL keywords from ALL cluster articles vs DW's RSS (not just the cluster label). Results shown as A/B/C/D grade + per-topic ✓/✗ breakdown.

**Matching uses three layers (in order):**
1. **Exact keyword intersection** — shared words after stop-word filtering
2. **Prefix-aware match** — two keywords match if they share a 5-character prefix (lightweight stemming). Catches `olympic`/`olympics`, `transgender`/`trans`, and similar root-word variants where DW files under a shorter/longer form
3. **Substring fallback** — cluster keyword (>4 chars) appears as a substring anywhere in a DW article title

DW articles older than 12 hours are excluded from matching (prevents yesterday's coverage from suppressing a DW Gap badge for today's story).

---

## Data Sources (15 news RSS + 8 supplemental = 23 total)

### Tier 1 — Editorial/Homepage Feeds
| ID | Name | RSS Feed | Lean |
|---|---|---|---|
| foxnews | Fox News | feeds.foxnews.com/foxnews/latest (50 articles) | Right |
| cnn | CNN | Google News RSS (site:cnn.com) | Left |
| nytimes | New York Times | nyt/HomePage | Left |
| dailymail | Daily Mail | news/index | Center-Right |
| nypost | NY Post | nypost.com/feed | Right |
| ap | AP News | Google News RSS (site:apnews.com) | Center |
| reuters | Reuters | Google News RSS (site:reuters.com) | Center |
| nbcnews | NBC News | nbcnews/public/news | Left |
| dailywire | Daily Wire | dailywire.com/rss | Right |

**Note on Fox News:** History of feed changes: originally used `feeds.foxnews.com/foxnews/national` (crime beat only), then switched to Google News RSS (site:foxnews.com) to get engagement-ranked content. Google News RSS was dropped after QA confirmed it fails to surface Fox's editorially pinned "LIVE UPDATES" hero stories (published once, updated in-place — never refreshed to position 0 in a chronological feed). Final fix: switched back to `feeds.foxnews.com/foxnews/latest` with a 50-article pool (`rss_limit: 50` in source config) to maximize the chance of catching pinned hero stories regardless of publish age. Paired with Fox-specific targeted scraping of `div.big-top` (hero) and `div.thumbs-2-7` (editorial grid) so cross-verification correctly maps scraped editorial positions 1-10 to the right RSS articles. Fox IS server-side rendered — BeautifulSoup can parse the full editorial layout from raw HTML without JavaScript.

**Note on CNN:** Previously used `rss.cnn.com/rss/cnn_topstories.rss` — consistently returned only 2 articles from Railway (feed reliability issue). Switched to Google News RSS (site:cnn.com) which returns ~20 articles ranked by engagement/prominence.

**Note on AP News:** Previously used `feeds.apnews.com/rss/apf-topnews` — Railway DNS fails to resolve `feeds.apnews.com` (`[Errno -5] No address associated with hostname`). Switched to Google News RSS (site:apnews.com) which resolves correctly and returns ~17 engagement-ranked articles.

### Tier 2 — Opinion/Political Feeds
| ID | Name | RSS Feed | Lean |
|---|---|---|---|
| breitbart | Breitbart | breitbart.com/feed | Right |
| skynews | Sky News | skynews/home | Center |
| thehill | The Hill | thehill/homenews/feed | Center |
| washtimes | Washington Times | washingtontimes/news | Right |
| foxbusiness | Fox Business | Google News RSS (site:foxbusiness.com) | Right |
| townhall | Townhall | townhall.com/rss/tipsheet | Right |

**Per-source limit:** 20 articles from RSS. Scraped homepage adds cross-verification layer and reorders source card to show editorial picks first.

**Note on The Hill:** Previously used `thehill.com/feed/` which mixes news, opinion, and tipsheet posts in reverse-chronological order — tipsheets frequently claimed the top RSS positions (fp=0,1) over real news stories. Switched to `thehill.com/homenews/feed/` which is news-only and better reflects editorial priorities.

**Note on Fox Business:** Previously used `feeds.foxbusiness.com/foxbusiness/latest` (raw chronological) — the most-recently published articles became RSS heroes regardless of editorial prominence. Switched to Google News RSS (site:foxbusiness.com) which ranks by engagement/prominence, consistent with how we handle Fox News, CNN, AP, and Reuters.

### Supplemental Sources (Blue Trends + Social Velocity)
| Source | Method | Notes |
|---|---|---|
| Bluesky | AT Protocol API (`getTrendingTopics`, limit=25, no auth) | Returns up to ~10 curated trending topics regardless of limit — server-side cap. Cache: 30 min. |
| r/politics | Reddit RSS (`/hot.rss`) | Liberal-leaning, up to 8 posts per cycle |
| r/progressive | Reddit RSS (`/hot.rss`) | Explicitly progressive, up to 8 posts per cycle |
| r/liberal | Reddit RSS (`/hot.rss`) | Explicitly liberal, up to 8 posts per cycle |
| r/democrats | Reddit RSS (`/hot.rss`) | Explicitly Democratic, up to 8 posts per cycle |
| Drudge Report | HTML scrape | Top headline links. Cache: 30 min. |
| Twitter/X Trends | getdaytrends.com (primary) / trends24.in (fallback) | US trending topics. Both may block cloud IPs intermittently. |
| Google Trends | Official RSS (`trendingsearches/daily/rss?geo=US`) | Top 25 US search trends. Cache: 2 hours. |

**Reddit fetch strategy:** Each subreddit fetches up to 25 RSS entries, caps at 8 posts per sub, then interleaves round-robin (politics[0] → progressive[0] → liberal[0] → democrats[0] → politics[1] → …) so all four subreddits always appear in the feed. Max 32 posts total. No OAuth or API key — uses public RSS via feedparser.

---

## UI Features

### Navigation
The app uses a **fixed left sidebar** for navigation (no top nav bar). The sidebar collapses on screens ≤ 900px, replaced by a **mobile bottom nav bar** with icon+label items.

**Sidebar nav items (top to bottom):**
1. **Topic Intelligence** (`local_fire_department`) — Top Trending Topics dashboard (main view)
2. **Live Source Feed** (`newspaper`) — smooth-scrolls to the 23-source headline grid on the Dashboard page
3. **Social Velocity** (`trending_up`) — smooth-scrolls to the Drudge/Twitter sidebar on the Dashboard page
4. **Side by Side** (`compare_arrows`) — trending vs DW editorial picks comparison page
5. **Last Hour** (`schedule`) — recent articles page, with live article count badge
6. **Blue Trends** (`mood_bad`, blue) — Bluesky trending topics + Liberal Reddit hot posts. Also accessible at `/bluetrends` as a deep-link.

The **LIVE indicator + countdown to refresh** lives in the sidebar between the Intelligence Ops logo and the nav items (`.sb-live` element). There is no top header bar — content starts at the very top of the viewport.

### Dashboard — Top Trending Topics
- Ranked by heat score (highest first)
- **"Lead at X outlets"** navy badge: story was hero at that many outlets (RSS + scrape verified). Hover tooltip lists the outlets.
- **"● DW Gap"** pulsing red badge: story is in top 10 but Daily Wire isn't covering it
- Source dots: colored by political lean, larger with outline ring = hero/lead position
- Green ▲ / Red ▼ delta badge: trajectory vs previous refresh (heat score change)
- Velocity sparkline: small 4-point chart showing heat score over last 4 refreshes (Jaccard-matched)
- Click any row to expand and see all individual article headlines per outlet
- `★` = RSS hero, `✓` = scrape confirmed, `★✓` = double confirmed (all have hover tooltips)
- Article age shown inline ("14m ago", "3h ago") from parsed pub_ts. Hover for exact timestamp.
- **Breaking** orange badge: article published within last 90 minutes

### Side by Side
- Left column: top 10 trending topics by heat score (source count + signal)
- Right column: top 10 Daily Wire articles (editorial picks first, then RSS)
- Green **✓ DW** badge on left when Daily Wire is covering that trending topic. Hover shows DW article title.
- No red gap badge — absence of the green check is signal enough
- DW articles show **Top Story** badge for editorial picks (scrape_position ≤ 5)

### Last Hour
- All articles published in the last 60 minutes across all 15 outlets, chronological (newest first)
- Two sections: **Just Published** (< 15 min old) with pulsing dot indicator, and **Earlier This Hour**
- **⚡ X sources** signal badge when the article's story is already clustering on the Dashboard (shows how many outlets are covering it)
- Political lean color on the source eyebrow (FOX NEWS, CNN, etc.)
- Live count badge on the tab updates every refresh cycle
- Auto-refreshes with the main data pipeline

### Social Velocity sidebar
- **Drudge** tab: top headline links scraped from Drudge Report
- **Twitter** tab: US trending topics. Primary source: getdaytrends.com (server-rendered). Fallback: trends24.in. Both may be intermittent from cloud IPs.

**Note:** Facebook tab was removed. Meta's Graph API (`Page Public Content Access` feature) requires App Review and is incompatible with the Facebook Login app type — not feasible for public page engagement data without a full app rebuild.

### Blue Trends page (`/bluetrends`)
Two-column view showing what's generating engagement on the left side of the political spectrum.

- **Left column — Bluesky Trending:** Top topics from Bluesky's public AT Protocol API. Each topic is a clickable link to `bsky.app/search?q=...`. Subtitle dynamically shows actual count ("X topics trending on Bluesky right now") since the API typically returns ~10 curated topics regardless of the limit=25 request.
- **Right column — Liberal Reddit Hot:** Hot posts from r/politics, r/progressive, r/liberal, and r/democrats, interleaved round-robin. Posts link to the external article URL (extracted from RSS summary HTML) when available, otherwise to the Reddit thread.
- Deep-link: `trendinginrealtime.com/bluetrends` routes directly to this view via server-side injection of `_INIT_VIEW="bt"` into the HTML before serving.
- Nav icon: `mood_bad` (Material Symbols), blue (`#1d9bf0`)

### Google Trends US sidebar
- Shows top 25 US search trends via official Google Trends RSS feed
- `https://trends.google.com/trends/trendingsearches/daily/rss?geo=US`
- Cached 2 hours, 4-hour backoff on failure
- "X min ago" / "Xh ago" label shows cache age

### Live Source Feed (Source Headlines grid)
- All 15 news sources displayed with their top 8 headlines
- Color-coded by political lean
- Editorial picks (scrape-confirmed) shown first per source
- Source names link to each outlet's homepage

### Daily Wire Coverage Alignment
- Circular gauge showing % of top 10 trends covered
- Grade A/B/C/D
- Per-topic ✓/✗ breakdown with DW article title when matched

---

## Development Workflow

### Running locally
```bash
cd ~/Projects/whats-trending-realtime
python3 trending_dashboard.py
# Opens http://localhost:8080 automatically
```

### Deploying (Cowork VM → Mac → Railway)
The VM **cannot** push to GitHub directly (network restriction). Workflow:
1. Claude edits files and commits from VM
2. From Mac terminal: `git pull --rebase origin main && git push`
3. Railway auto-deploys on push to `main`

The Cowork mount at `/sessions/.../mnt/whats-trending-realtime/` maps to `~/Projects/whats-trending-realtime/` on the Mac. **File overwrites do NOT sync back to Mac** — only new file creation does. The commit+pull workaround handles this.

---

## Known Issues

### Per-Source Data Quality (from full QA regression, March 2026)

| Source | RSS Quality | Scrape Quality | Notes |
|---|---|---|---|
| Fox News | ✅ Good | ✅ Good | Direct RSS (feeds.foxnews.com/foxnews/latest, 50 articles). Fox IS server-side rendered — BeautifulSoup parses the full editorial layout. Targeted scraper hits `div.big-top` (hero) + `div.thumbs-2-7` (editorial grid) first, so positions 1-10 are Fox's actual top stories. MAX_VALID_SCRAPE_POS=80 blocks footer anchor links (pos 90-150). Synthetic injection typically ~9 articles/cycle. |
| CNN | ✅ Good | ✅ Good | Google News RSS (site:cnn.com) — ~20 articles. Switched from direct RSS which returned only 2 articles from Railway. Synthetic injection typically ~2 articles/cycle. |
| NY Times | ✅ Excellent | ✅ Excellent | Direct homepage RSS feed + tight scrape positions 11-44. Best source setup. Synthetic injection ~3 articles/cycle. |
| Daily Mail | ✅ Good | ⚠️ Partial | Only ~20% of RSS articles scrape-confirmed because /news/index.rss is the news section but Daily Mail homepage is dominated by lifestyle/celebrity. Expected behavior. Excluded from synthetic injection (SKIP_INJECT). |
| NY Post | ✅ Good | ✅ Good | Direct RSS + scrape positions 7-90. Synthetic injection ~7 articles/cycle. |
| AP News | ✅ Good | ✅ Good | Google News RSS (site:apnews.com) — ~17 articles. Switched from direct RSS which fails Railway DNS (`feeds.apnews.com` not resolving). Synthetic injection ~9 articles/cycle. |
| Reuters | ⚠️ Moderate | ❌ Blocked | Reuters homepage blocks scraping. Google News RSS articles unverified — pass on age alone. No synthetic injection (url_map empty). |
| NBC News | ✅ Excellent | ✅ Excellent | Direct RSS + very tight scrape positions 2-13. Best scraper performance. Synthetic injection ~3 articles/cycle. |
| Daily Wire | ✅ Excellent | ✅ Excellent | Direct RSS + topStoryTextContainer targeting captures actual editorial Top Stories (positions 1-5). |
| Breitbart | ✅ Good | ✅ Good | Direct RSS + scrape positions 1-51. Synthetic injection ~4 articles/cycle. |
| Sky News | ✅ Good | ✅ Good | Direct RSS (home feed) + scrape positions 16-66. Synthetic injection ~1 article/cycle. |
| The Hill | ✅ Good | ❌ JS-rendered | Switched to homenews/feed/ (news-only). Homepage is JS-rendered, so 0 scrape confirmations expected. No synthetic injection. |
| Washington Times | ✅ Excellent | ✅ Excellent | Direct RSS + scrape positions 4-37. Synthetic injection ~6 articles/cycle. |
| Fox Business | ✅ Good | ❌ JS-rendered | Google News RSS (site:foxbusiness.com). Homepage is JS-rendered — 0 scrape confirmations expected. No synthetic injection. |
| Townhall | ✅ Good | ✅ Good | Direct RSS (tipsheet) + scrape positions 2-26. Synthetic injection ~3 articles/cycle. |

### Other Known Issues
- **Reuters RSS:** Their feed URL may periodically break as Reuters migrates infrastructure.
- **Clustering edge cases:** Very fast-breaking stories (first 10 minutes) may not cluster correctly until multiple sources pick them up. TF-IDF needs a minimum article count to form meaningful vectors.
- **Post-merge threshold tuning:** `MERGE_THRESHOLD = 0.20` was chosen to catch same-story false splits. If unrelated stories start merging, raise it toward 0.25. If splits persist, lower it toward 0.15.
- **Twitter/X trends:** getdaytrends.com and trends24.in may block cloud server IPs intermittently. Shows "unavailable" gracefully when both fail.
- **Bluesky topic count:** The `getTrendingTopics` API appears to return ~10 curated topics regardless of the `limit=25` parameter — this is a server-side cap on Bluesky's end, not a code issue. The subtitle dynamically reflects the actual count returned.
- **SIMILARITY_THRESHOLD tuning:** 0.28 is the current setting. After a full day of news cycles, this may need adjustment — raise if unrelated stories are still merging, lower if related stories are splitting into separate clusters.

---

## Phase 2 Roadmap

### Completed
- [x] **Scraped page position boosting** — `scrape_position` recorded per article. Positions 1–3 = editorial spotlight (+15/outlet), 4–8 = standard hero (+20/outlet).
- [x] **Google Stitch design refresh** — full structural rewrite with fixed sidebar, table layout, sparklines, source chips.
- [x] **Side by Side tab** — trending topics vs Daily Wire editorial picks, side by side.
- [x] **Last Hour tab** — all articles from last 60 min, newest first, with signal badges and Just Published pulsing indicator.
- [x] **Possessive stripping + ambient reference filter** — cleaner clustering (legacy from keyword-seed era, some logic still relevant).
- [x] **Fox News feed fix** — switched from crime-beat `foxnews/national` → Google News RSS → `feeds.foxnews.com/foxnews/latest` (50 articles). Final fix adds Fox-specific targeted scraping of `div.big-top` + `div.thumbs-2-7` to lock editorial positions 1-10 to Fox's actual homepage order.
- [x] **TF-IDF cosine similarity clustering** — replaced keyword-seed approach entirely. No more single-word false merges. `SIMILARITY_THRESHOLD = 0.28`.
- [x] **Post-clustering merge pass** — after greedy clustering, iteratively merges cluster pairs with centroid cosine similarity ≥ `MERGE_THRESHOLD = 0.20`. Fixes false splits where the same story is covered from different vocabulary angles (e.g. oil-price vs. ceasefire-agreement framing of the same event).
- [x] **Velocity sparklines (Jaccard matching)** — `_heat_history` keyed by frozenset(source_ids) with ≥33% Jaccard overlap for story identity across refreshes. Real 4-point spark curve.
- [x] **Stale source credibility filter** — sources only counted if article is <4h old OR scrape-confirmed. Prevents stale Google News articles from inflating source chips.
- [x] **Tooltips** — all UI badges have hover explanations: Breaking, age, Lead (lists outlets), ★/✓ marks, ✓ DW badge, delta.
- [x] **Source name homepage links** — source names in Live Source Feed link to each outlet's homepage.
- [x] **Duplicate subtitle removal** — trending rows no longer repeat the headline in a gray subtitle below the bold title.
- [x] **Synthetic article injection (generalized)** — `scrape_homepage()` returns a 3-tuple `(headlines, url_map, orig_map)`. After cross-verification, unmatched scraped headlines at positions 1–10 with valid article URLs are injected as synthetic articles. Junk filter (`_is_junk_injection`) blocks nav headers, ads, promos, and podcast/newsletter links. Applied to all scraped sources except Daily Mail.
- [x] **Junk injection filter fix** — `[-–]` regex now matches both regular hyphen and em-dash in "Top Stories" pattern. Previously only matched em-dash, allowing "Source Name - Top Stories" section headers to slip through and seed false clusters.
- [x] **Targeted homepage scrapers** — source-specific CSS selectors run before the generic h1/h2/h3 scan for: Fox News (`div.big-top`, `div.thumbs-2-7`), CNN (`container_lead` divs + `<article>`), Daily Wire (`topStoryTextContainer h3`), NBC News (`<article>`), NY Post (`featured-area`/`top-story` + `article.story`), Breitbart (`top-story`/`hero` + `<article>`), NY Times (`<article>`), Sky News (`sdc-article` list items). Locks editorial positions 1–10 to the source's actual homepage order.
- [x] **AP News fix** — switched from direct RSS (Railway DNS failure) to Google News RSS.
- [x] **CNN fix** — switched from direct RSS (2 articles) to Google News RSS (~20 articles).
- [x] **Sidebar navigation** — removed top nav bar; all navigation moved to fixed left sidebar using Material Symbols icons.
- [x] **Mobile bottom nav** — fixed bottom bar visible at ≤900px; sidebar collapses. Solves disappearing navigation on mobile web.
- [x] **Topbar removal** — "Editorial Intelligence" header bar eliminated; LIVE indicator + countdown moved into sidebar above nav items (`.sb-live`). All page containers start at `top:0`, reclaiming 64px of vertical space.
- [x] **DW alignment prefix matching** — added 5-char prefix matching step between exact and substring fallback. Fixes `olympic`/`olympics`, `transgender`/`trans`, and similar root-word variants where DW's framing uses a different inflection.
- [x] **Facebook tab removed** — Meta's Graph API requires App Review for `Page Public Content Access` and is incompatible with the Facebook Login app type. Removed from Social Velocity sidebar entirely.
- [x] **Blue Trends page** — new page at `/bluetrends` (also deep-linkable as `trendinginrealtime.com/bluetrends`) showing Bluesky trending topics (left column) and Liberal Reddit hot posts from r/politics, r/progressive, r/liberal, r/democrats (right column). Nav icon: `mood_bad` (Material Symbols).
- [x] **Bluesky trending topics** — `fetch_bluesky_trends()` calls `app.bsky.unspecced.getTrendingTopics` (no auth, limit=25). Each topic links to `bsky.app/search?q=...`. Subtitle shows dynamic count. Cache: 30 min.
- [x] **Liberal Reddit hot posts** — `fetch_liberal_reddit()` fetches RSS from 4 subreddits via feedparser. Round-robin interleave ensures all 4 subs always appear (cap: 8 per sub). External article URLs extracted from RSS summary HTML when available.
- [x] **Loading screen source count** — updated from "Scanning 15 sources" to "Scanning 23 sources".

### Backlog
- [ ] **Auth layer** — password protect for Daily Wire editorial team use
- [ ] **Email digest** — daily 8am summary of top 10 trending + DW alignment score
- [ ] **Story staleness** — fade out / gray out stories older than 4 hours from trending list
- [ ] **Drudge siren** — visual alert when a story is Drudge's top link
- [ ] **foxbusiness scrape** — add to SCRAPE_SOURCES (currently missing from scrape config)

---

## Environment

- **Production URL:** www.trendinginrealtime.com (GoDaddy CNAME → fl8w2a92.up.railway.app)
- **DNS:** GoDaddy CNAME `www` → `fl8w2a92.up.railway.app` + apex forward → www. TXT `_railway-verify.www` → `railway-verify=c920a03...` for Railway verification. No Cloudflare.
- **GitHub repo:** github.com/verifiedchriswilliams-lang/whats-trending-realtime
- **Railway project:** auto-deploys on push to `main`
- **Python:** 3.13 (Railway auto-detected — do NOT add runtime.txt, it breaks the build)
- **PORT:** read from `os.environ.get('PORT', 8080)` — Railway sets this automatically

---

## Editorial Context

The dashboard is designed for a 5-minute morning scan by Daily Wire editors. Priority order for reading:
1. Top 3 trending topics (highest heat score = most cross-source coverage)
2. Any "● DW Gap" badges on topics 1–10
3. Daily Wire Alignment grade — if C or D, editors need story assignments
4. Last Hour tab — catch anything breaking in the last 60 minutes that hasn't clustered yet
5. Google Trends sidebar — catches search-driven stories RSS may miss
6. Side by Side tab — quick visual scan of trending vs DW editorial priorities
7. Blue Trends tab — what's generating engagement on the left; useful for anticipating counter-narrative stories
