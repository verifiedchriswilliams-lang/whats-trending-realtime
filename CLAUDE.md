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

### Story Clustering (IMPORTANT — do not revert this logic)
Stories are clustered by **specific keywords only** — words appearing in more than 10% of all articles are filtered out as "generic connective tissue" (e.g. "trump", "president", "american"). This is intentional. Without this filter, a single mega-cluster forms around common words, making the tool useless for editorial signal.

The threshold: `max_freq = max(4, len(flat) * 0.10)`

A story clusters around a keyword if:
- The keyword appears in ≤10% of all articles AND
- At least 2 sources cover it OR 3+ articles mention it

**Possessive stripping:** `extract_keywords()` strips `'s` from tokens before processing — "trump's" → "trump", "iran's" → "iran" — so possessives don't seed their own spurious clusters.

**Ambient reference filter:** Keywords spanning 5+ distinct sources with zero secondary keyword overlap are geopolitical/celebrity references (e.g. "israel" during an active war), not specific story anchors. These are rejected even if they pass the frequency filter. Requires at least 1 secondary shared keyword when seed spans 5+ sources.

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
| thehill | The Hill | thehill/all-news | Center |
| washtimes | Washington Times | washingtontimes/news | Right |
| foxbusiness | Fox Business | foxbusiness/latest | Right |
| townhall | Townhall | townhall.com/rss | Right |

**Per-source limit:** 20 articles from RSS. Scraped homepage adds cross-verification layer and reorders source card to show editorial picks first.

---

## UI Features

### Top Trending Topics panel (Dashboard tab)
- Ranked by heat score (highest first)
- **"Lead at X outlets"** navy badge: story was hero at that many outlets (RSS + scrape verified)
- **"● DW Gap"** pulsing red badge: story is in top 10 but Daily Wire isn't covering it
- Source dots: colored by political lean, larger with outline ring = hero/lead position
- Green ▲ / Red ▼ delta badge: trajectory vs previous refresh (heat score change)
- Click any row to expand and see all individual article headlines per outlet
- `★` = RSS hero, `✓` = scrape confirmed, `★✓` = double confirmed
- Article age shown inline ("14m ago", "3h ago") from parsed pub_ts

### Side by Side tab
- Left column: top 10 trending topics by heat score (source count + signal)
- Right column: top 10 Daily Wire articles (editorial picks first, then RSS)
- Green **✓ DW** badge on left when Daily Wire is covering that trending topic
- No red gap badge — absence of the green check is signal enough
- DW articles show **Top Story** badge for editorial picks (scrape_position ≤ 5)

### Social Velocity sidebar
- **Drudge** tab: top headline links scraped from Drudge Report
- **Twitter** tab: US trending topics. Primary source: getdaytrends.com (server-rendered). Fallback: trends24.in. Both may be intermittent from cloud IPs.
- **Facebook** tab: top articles by engagement (reactions + shares + comments) via Facebook Graph API. Requires app token (see Environment). Skips Google News proxy sources (CNN/AP/Reuters) since their URLs are redirects.

### Google Trends US sidebar
- Shows top 25 US search trends via official Google Trends RSS feed
- `https://trends.google.com/trends/trendingsearches/daily/rss?geo=US`
- Cached 2 hours, 4-hour backoff on failure
- "X min ago" / "Xh ago" label shows cache age

### Source Headlines grid
- All 15 sources displayed with their top 8 headlines
- Color-coded by political lean
- Editorial picks (scrape-confirmed) shown first per source

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

- **Reuters RSS:** Their feed URL may periodically break as Reuters migrates infrastructure.
- **Clustering edge cases:** Very fast-breaking stories (first 10 minutes) may not cluster correctly until multiple sources pick them up.
- **Homepage scraping blocks:** Some sources (NYT, Reuters, Fox) may return 403s or JS-render content — scraping degrades gracefully (empty list returned, no crash). Fox News homepage is JS-rendered; Google News RSS compensates for editorial alignment.
- **Twitter/X trends:** getdaytrends.com and trends24.in may block cloud server IPs intermittently. Shows "unavailable" gracefully when both fail.
- **Facebook Graph API:** Requires app-level access token. If token expires or is revoked, shows "unavailable" with explanation rather than loading spinner.

---

## Phase 2 Roadmap

### Completed
- [x] **Scraped page position boosting** — `scrape_position` recorded per article. Positions 1–3 = editorial spotlight (+15/outlet), 4–8 = standard hero (+20/outlet).
- [x] **Google Stitch design refresh** — full structural rewrite with fixed sidebar, table layout, sparklines, source chips.
- [x] **Side by Side tab** — trending topics vs Daily Wire editorial picks, side by side.
- [x] **Facebook engagement signal** — Graph API with app token, top articles by reactions+shares+comments.
- [x] **Possessive stripping + ambient reference filter** — cleaner clustering, no spurious Trump's/Israel mega-clusters.
- [x] **Fox News feed fix** — switched from crime-beat RSS to Google News editorial alignment.

### Backlog
- [ ] **Drudge Report scraper** — no RSS feed, requires HTML parsing; would be high signal
- [ ] **Auth layer** — password protect for Daily Wire editorial team use
- [ ] **Email digest** — daily 8am summary of top 10 trending + DW alignment score
- [ ] **Story staleness** — fade out / gray out stories older than 4 hours from trending list
- [ ] **Drudge siren** — visual alert when a story is Drudge's top link
- [ ] **foxbusiness scrape** — add to SCRAPE_SOURCES (currently missing from scrape config)
- [ ] **Facebook token rotation** — move FB_TOKEN out of source code into Railway env var

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
4. Google Trends sidebar — catches search-driven stories RSS may miss
5. Side by Side tab — quick visual scan of trending vs DW editorial priorities
