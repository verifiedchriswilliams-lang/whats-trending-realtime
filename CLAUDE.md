# TrendingInRealTime.com — Editorial Intelligence Dashboard

## Project Purpose

A real-time editorial intelligence tool for the Daily Wire's editorial team. It aggregates RSS feeds from 15 major news sources every 30 minutes, clusters stories by specific topic (not generic keywords), and surfaces a Daily Wire Coverage Alignment score — showing editors which top trending stories they are and aren't covering.

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
- feedparser for RSS ingestion (15 sources, concurrent via ThreadPoolExecutor)
- requests + BeautifulSoup4 for homepage scraping (13 sources)
- Google Trends via official public RSS feed (no API key, no rate limits)
- Facebook Graph API for article engagement data (app token required — see Environment)
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

The key advantage: two articles must share a **pattern of words**, not just one, to exceed the threshold. Single shared words rarely cross it.

**Constants to tune:**
- `SIMILARITY_THRESHOLD = 0.28` — raise to tighten clusters (fewer false merges), lower to loosen (catches more related stories)
- `STOP_WORDS` — high-frequency political/news words that would cause false merges if left in the TF-IDF vocabulary. Currently includes: trump, president, american, united, states, says, told, report, new, first, could, would, one, year, people, government, country, also, last, week, two, day, three, days, ago, news, just, back, make, time, according, say, still, us, war, world, think, like, big, old, former, just, top, high, state, federal, national, second, city, million, billion, big, great, major, leading, meet, talks, deal, amid, amid, call, push, move, take, help, plan, after, amid, despite, over, under, house, senate, congress, parliament, lawmakers, republican, democrat, gop, bipartisan, party, bill, vote, law, act, policy, administration, officials, white

**Credible source filter:** Only counts a source toward `source_count` if the article is either scrape-confirmed (appeared on homepage) OR less than 4 hours old.

**Scrape position cap (`MAX_VALID_SCRAPE_POS = 80`):** An article is only marked `scrape_confirmed=True` if its matched scrape position is ≤ 80. JS-rendered sites like Fox News cannot be scraped by BeautifulSoup — instead of returning headlines, the scraper picks up static sidebar/footer anchor links at positions 90–150+. Without this cap these false matches would inflate heat scores as though the stories were editorial homepage picks. All legitimate sources confirm within positions 1–75. This prevents stale Google News RSS articles (surfaced by relevance, not recency) from inflating source counts for stories outlets have moved on from.

### Homepage Scraping (Cross-Verification)
`scrape_homepage(sid, url)` fetches each source's actual homepage and extracts all `<h1>/<h2>/<h3>` text plus prominent anchor link text. Runs concurrently with RSS fetch (20-worker ThreadPoolExecutor).

Articles are matched against scraped headlines using:
1. Exact normalized substring match (title in scraped or scraped in title)
2. Word-overlap ≥ 60% for titles with 4+ words

Matched articles are marked `scrape_confirmed=True`. In the expanded article view:
- `★` = RSS hero (feed position 0 or 1)
- `✓` = scrape confirmed (appeared on homepage)
- `★✓` = double-confirmed (both RSS position AND scraped homepage)

**Source card ordering:** Editorial picks (scrape_position set) appear first, then RSS chronological. For Daily Wire, `topStoryTextContainer` h3s are targeted first to capture editorial Top Stories in correct order.

### Velocity Sparklines
Each trending topic's heat trajectory is tracked across refreshes using **Jaccard source-set matching** — a cluster is considered "the same story" across cycles if the set of source IDs covering it overlaps by ≥ 33% with a previously seen cluster.

This replaced a naive approach that keyed history by cluster label text, which broke every cycle because TF-IDF cluster labels change as new articles arrive.

`_heat_history = {}` stores up to 4 readings per frozenset(source_ids). The `spark()` JS function draws a real multi-point curve from this array.

### Daily Wire Alignment Score
Checks what % of the top 10 trending topics Daily Wire is covering. Checks ALL keywords from ALL cluster articles vs DW's RSS (not just the cluster label). Results shown as A/B/C/D grade + per-topic ✓/✗ breakdown.

---

## Data Sources (15 total)

### Tier 1 — Editorial/Homepage Feeds
| ID | Name | RSS Feed | Lean |
|---|---|---|---|
| foxnews | Fox News | Google News RSS (site:foxnews.com) | Right |
| cnn | CNN | Google News RSS (site:cnn.com) | Left |
| nytimes | New York Times | nyt/HomePage | Left |
| dailymail | Daily Mail | news/index | Center-Right |
| nypost | NY Post | nypost.com/feed | Right |
| ap | AP News | Google News RSS (site:apnews.com) | Center |
| reuters | Reuters | Google News RSS (site:reuters.com) | Center |
| nbcnews | NBC News | nbcnews/public/news | Left |
| dailywire | Daily Wire | dailywire.com/rss | Right |

**Note on Fox News:** Previously used `feeds.foxnews.com/foxnews/national` which pulled the crime beat rather than homepage editorial stories. Switched to Google News RSS to surface Fox's most prominent editorial coverage, matching their actual homepage.

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

---

## UI Features

### Dashboard tab — Top Trending Topics
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

### Side by Side tab
- Left column: top 10 trending topics by heat score (source count + signal)
- Right column: top 10 Daily Wire articles (editorial picks first, then RSS)
- Green **✓ DW** badge on left when Daily Wire is covering that trending topic. Hover shows DW article title.
- No red gap badge — absence of the green check is signal enough
- DW articles show **Top Story** badge for editorial picks (scrape_position ≤ 5)

### Last Hour tab
- All articles published in the last 60 minutes across all 15 outlets, chronological (newest first)
- Two sections: **Just Published** (< 15 min old) with pulsing dot indicator, and **Earlier This Hour**
- **⚡ X sources** signal badge when the article's story is already clustering on the Dashboard (shows how many outlets are covering it)
- Political lean color on the source eyebrow (FOX NEWS, CNN, etc.)
- Live count badge on the tab updates every refresh cycle
- Auto-refreshes with the main data pipeline

### Social Velocity sidebar
- **Drudge** tab: top headline links scraped from Drudge Report
- **Twitter** tab: US trending topics. Primary source: getdaytrends.com (server-rendered). Fallback: trends24.in. Both may be intermittent from cloud IPs.
- **Facebook** tab: top articles by engagement (reactions + shares + comments) via Facebook Graph API. Skips Google News proxy sources (CNN/AP/Reuters/Fox) since their URLs are google.com redirects. Candidates sorted oldest-first so articles have had time to accumulate shares. Threshold: ≥ 10 total engagement. Cache: 60 minutes. Rate-limit backoff: 2 hours.

### Google Trends US sidebar
- Shows top 25 US search trends via official Google Trends RSS feed
- `https://trends.google.com/trends/trendingsearches/daily/rss?geo=US`
- Cached 2 hours, 4-hour backoff on failure
- "X min ago" / "Xh ago" label shows cache age

### Live Source Feed (Source Headlines grid)
- All 15 sources displayed with their top 8 headlines
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
| Fox News | ⚠️ Moderate | ❌ JS-rendered | Google News RSS gives engagement-ranked content, not editorial order. Fox homepage is React-rendered — BeautifulSoup scraper can't see headlines. MAX_VALID_SCRAPE_POS=80 blocks false-positive footer link matches (pos 90-150). |
| CNN | ✅ Good | ✅ Good | Google News RSS + scrape positions 24-75. Ordering may not exactly match CNN's editorial priority (#1 story, but real CNN articles. |
| NY Times | ✅ Excellent | ✅ Excellent | Direct homepage RSS feed + tight scrape positions 11-44. Best source setup. |
| Daily Mail | ✅ Good | ⚠️ Partial | Only ~20% of RSS articles scrape-confirmed because /news/index.rss is the news section but Daily Mail homepage is dominated by lifestyle/celebrity. Expected behavior. |
| NY Post | ✅ Good | ✅ Good | Direct RSS + scrape positions 7-90. |
| AP News | ✅ Good | ✅ Good | Google News RSS + scrape positions 32-111. May miss some AP top stories that Google doesn't surface. |
| Reuters | ⚠️ Moderate | ❌ Blocked | Reuters homepage blocks scraping. Google News RSS articles unverified — pass on age alone. |
| NBC News | ✅ Excellent | ✅ Excellent | Direct RSS + very tight scrape positions 2-13. Best scraper performance. |
| Daily Wire | ✅ Excellent | ✅ Excellent | Direct RSS + topStoryTextContainer targeting captures actual editorial Top Stories (positions 1-5). |
| Breitbart | ✅ Good | ✅ Good | Direct RSS + scrape positions 1-51. |
| Sky News | ✅ Good | ✅ Good | Direct RSS (home feed) + scrape positions 16-66. |
| The Hill | ✅ Good | ❌ JS-rendered | Switched to homenews/feed/ (news-only). Homepage is JS-rendered, so 0 scrape confirmations expected. |
| Washington Times | ✅ Excellent | ✅ Excellent | Direct RSS + scrape positions 4-37. |
| Fox Business | ✅ Good | ❌ JS-rendered | Switched to Google News RSS. Homepage is JS-rendered like Fox News — 0 scrape confirmations expected. |
| Townhall | ✅ Good | ✅ Good | Direct RSS (tipsheet) + scrape positions 2-26. |

### Other Known Issues
- **Reuters RSS:** Their feed URL may periodically break as Reuters migrates infrastructure.
- **Clustering edge cases:** Very fast-breaking stories (first 10 minutes) may not cluster correctly until multiple sources pick them up. TF-IDF needs a minimum article count to form meaningful vectors.
- **Twitter/X trends:** getdaytrends.com and trends24.in may block cloud server IPs intermittently. Shows "unavailable" gracefully when both fail.
- **Facebook Graph API:** App is currently in Development mode ("no use cases") which may impose tighter rate limits. Rate limit errors (#4) trigger a 2-hour backoff. Token is hardcoded — should be moved to Railway env var. If the app is promoted to Live mode at developers.facebook.com, rate limits increase significantly.
- **SIMILARITY_THRESHOLD tuning:** 0.28 is the current setting. After a full day of news cycles, this may need adjustment — raise if unrelated stories are still merging, lower if related stories are splitting into separate clusters.

---

## Phase 2 Roadmap

### Completed
- [x] **Scraped page position boosting** — `scrape_position` recorded per article. Positions 1–3 = editorial spotlight (+15/outlet), 4–8 = standard hero (+20/outlet).
- [x] **Google Stitch design refresh** — full structural rewrite with fixed sidebar, table layout, sparklines, source chips.
- [x] **Side by Side tab** — trending topics vs Daily Wire editorial picks, side by side.
- [x] **Last Hour tab** — all articles from last 60 min, newest first, with signal badges and Just Published pulsing indicator.
- [x] **Facebook engagement signal** — Graph API with app token, top articles by reactions+shares+comments. Oldest-first candidate sorting so articles have had time to accumulate shares.
- [x] **Possessive stripping + ambient reference filter** — cleaner clustering (legacy from keyword-seed era, some logic still relevant).
- [x] **Fox News feed fix** — switched from crime-beat RSS to Google News editorial alignment.
- [x] **TF-IDF cosine similarity clustering** — replaced keyword-seed approach entirely. No more single-word false merges. `SIMILARITY_THRESHOLD = 0.28`.
- [x] **Velocity sparklines (Jaccard matching)** — `_heat_history` keyed by frozenset(source_ids) with ≥33% Jaccard overlap for story identity across refreshes. Real 4-point spark curve.
- [x] **Stale source credibility filter** — sources only counted if article is <4h old OR scrape-confirmed. Prevents stale Google News articles from inflating source chips.
- [x] **Tooltips** — all UI badges have hover explanations: Breaking, age, Lead (lists outlets), ★/✓ marks, ✓ DW badge, delta.
- [x] **Source name homepage links** — source names in Live Source Feed link to each outlet's homepage.
- [x] **Duplicate subtitle removal** — trending rows no longer repeat the headline in a gray subtitle below the bold title.
- [x] **Header cleanup** — removed non-functional notification and account placeholder icon buttons.

### Backlog
- [ ] **Drudge Report scraper** — no RSS feed, requires HTML parsing; would be high signal
- [ ] **Auth layer** — password protect for Daily Wire editorial team use
- [ ] **Email digest** — daily 8am summary of top 10 trending + DW alignment score
- [ ] **Story staleness** — fade out / gray out stories older than 4 hours from trending list
- [ ] **Drudge siren** — visual alert when a story is Drudge's top link
- [ ] **foxbusiness scrape** — add to SCRAPE_SOURCES (currently missing from scrape config)
- [ ] **Facebook token rotation** — move FB_TOKEN out of source code into Railway env var
- [ ] **Facebook Live mode** — promote app at developers.facebook.com to increase rate limits

---

## Environment

- **Production URL:** www.trendinginrealtime.com (GoDaddy CNAME → fl8w2a92.up.railway.app)
- **DNS:** GoDaddy CNAME `www` → `fl8w2a92.up.railway.app` + apex forward → www. TXT `_railway-verify.www` → `railway-verify=c920a03...` for Railway verification. No Cloudflare.
- **GitHub repo:** github.com/verifiedchriswilliams-lang/whats-trending-realtime
- **Railway project:** auto-deploys on push to `main`
- **Python:** 3.13 (Railway auto-detected — do NOT add runtime.txt, it breaks the build)
- **PORT:** read from `os.environ.get('PORT', 8080)` — Railway sets this automatically
- **Facebook Graph API token:** App ID `1491126469205088`, hardcoded as `APP_ID|APP_SECRET` in `fetch_facebook_engagement()`. TODO: move to Railway environment variable.

---

## Editorial Context

The dashboard is designed for a 5-minute morning scan by Daily Wire editors. Priority order for reading:
1. Top 3 trending topics (highest heat score = most cross-source coverage)
2. Any "● DW Gap" badges on topics 1–10
3. Daily Wire Alignment grade — if C or D, editors need story assignments
4. Last Hour tab — catch anything breaking in the last 60 minutes that hasn't clustered yet
5. Google Trends sidebar — catches search-driven stories RSS may miss
6. Side by Side tab — quick visual scan of trending vs DW editorial priorities
