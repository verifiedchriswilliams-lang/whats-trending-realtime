# WhatsTrendingInRealTime.com — Editorial Intelligence Dashboard

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
- gunicorn for production serving (via Procfile)
- Railway for hosting, GitHub for version control

---

## Key Algorithms

### Heat Score
`heat_score = (source_count × 12) + article_count + (hero_count × 20) + (double_confirmed × 10)`

- `source_count` = number of distinct outlets covering this story
- `article_count` = total articles in the cluster
- `hero_count` = outlets where this story was RSS position 0–1 OR appeared on scraped homepage
- `double_confirmed` = outlets where story is BOTH RSS position 0–1 AND scraped from homepage (strongest signal)

### Story Clustering (IMPORTANT — do not revert this logic)
Stories are clustered by **specific keywords only** — words appearing in more than 10% of all articles are filtered out as "generic connective tissue" (e.g. "trump", "president", "american"). This is intentional. Without this filter, a single mega-cluster forms around common words, making the tool useless for editorial signal.

The threshold: `max_freq = max(4, len(flat) * 0.10)`

A story clusters around a keyword if:
- The keyword appears in ≤10% of all articles AND
- At least 2 sources cover it OR 3+ articles mention it

### Homepage Scraping (Cross-Verification)
`scrape_homepage(sid, url)` fetches each source's actual homepage and extracts all `<h1>/<h2>/<h3>` text plus prominent anchor link text. Runs concurrently with RSS fetch (20-worker ThreadPoolExecutor).

Articles are matched against scraped headlines using:
1. Exact normalized substring match (title in scraped or scraped in title)
2. Word-overlap ≥ 60% for titles with 4+ words

Matched articles are marked `scrape_confirmed=True`. In the expanded article view:
- `★` = RSS hero (feed position 0 or 1)
- `✓` = scrape confirmed (appeared on homepage)
- `★✓` = double-confirmed (both RSS position AND scraped homepage)

### Daily Wire Alignment Score
Checks what % of the top 10 trending topics Daily Wire is covering. Checks ALL keywords from ALL cluster articles vs DW's RSS (not just the cluster label). Results shown as A/B/C/D grade + per-topic ✓/✗ breakdown.

---

## Data Sources (15 total)

### Tier 1 — Editorial/Homepage Feeds
| ID | Name | RSS Feed | Lean |
|---|---|---|---|
| foxnews | Fox News | foxnews/national | Right |
| cnn | CNN | cnn_topstories | Left |
| nytimes | New York Times | nyt/HomePage | Left |
| dailymail | Daily Mail | news/index | Center-Right |
| nypost | NY Post | nypost.com/feed | Right |
| ap | AP News | apnews/topnews | Center |
| reuters | Reuters | reuters/topNews | Center |
| nbcnews | NBC News | nbcnews/public/news | Left |
| dailywire | Daily Wire | dailywire.com/rss | Right |

### Tier 2 — Opinion/Political Feeds
| ID | Name | RSS Feed | Lean |
|---|---|---|---|
| breitbart | Breitbart | breitbart.com/feed | Right |
| skynews | Sky News | skynews/home | Center |
| thehill | The Hill | thehill/all-news | Center |
| washtimes | Washington Times | washingtontimes/news | Right |
| foxbusiness | Fox Business | foxbusiness/markets | Right |
| townhall | Townhall | townhall.com/rss | Right |

**Per-source limit:** 12 articles from RSS (top of feed = above-the-fold signal). Scraped homepage adds cross-verification layer.

---

## UI Features

### Top Trending Topics panel
- Ranked by heat score (highest first)
- **"Lead at X outlets"** navy badge: story was hero at that many outlets (RSS + scrape verified)
- **"● DW Gap"** pulsing red badge: story is in top 10 but Daily Wire isn't covering it
- Source dots: colored by political lean, larger with outline ring = hero/lead position
- Green ▲ / Red ▼ delta badge: trajectory vs previous refresh (heat score change)
- Click any row to expand and see all individual article headlines per outlet
- `★` = RSS hero, `✓` = scrape confirmed, `★✓` = double confirmed
- Article age shown inline ("14m ago", "3h ago") from parsed pub_ts

### Google Trends US sidebar
- Shows top 25 US search trends via official Google Trends RSS feed
- `https://trends.google.com/trends/trendingsearches/daily/rss?geo=US`
- Cached 2 hours, 4-hour backoff on failure
- "X min ago" / "Xh ago" label shows cache age

### Source Headlines grid
- All 15 sources displayed with their top 8 headlines
- Color-coded by political lean

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
- **Homepage scraping blocks:** Some sources (NYT, Reuters) may return 403s — scraping degrades gracefully (frozenset() returned, no crash).

---

## Phase 2 Roadmap

### Next Session (Tomorrow)
- [ ] **Scraped page position boosting** — use the ordinal position of a headline on the scraped homepage (e.g. 1st h2 vs 8th h2) as a continuous signal, not just binary present/absent. Stories in the top 3 scraped positions get a larger heat score boost than stories at position 10.
- [ ] **Google Stitch design refresh** — user will provide Stitch output; integrate new CSS/HTML design into the embedded template.

### Backlog
- [ ] **Drudge Report scraper** — no RSS feed, requires HTML parsing; would be high signal
- [ ] **Social signals** — Twitter/X trending topics, Reddit r/Conservative and r/politics
- [ ] **Auth layer** — password protect for Daily Wire editorial team use
- [ ] **Email digest** — daily 8am summary of top 10 trending + DW alignment score
- [ ] **Story staleness** — fade out / gray out stories older than 4 hours from trending list
- [ ] **Drudge siren** — visual alert when a story is Drudge's top link
- [ ] **foxbusiness scrape** — add to SCRAPE_SOURCES (currently missing from scrape config)

---

## Environment

- **Production URL:** whatstrendinginrealtime.com (Cloudflare → web-production-456b3.up.railway.app)
- **DNS:** GoDaddy nameservers → Cloudflare (lennon + lilith), CNAME proxy to Railway URL
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
4. Google Trends sidebar — catches search-driven stories RSS may miss
