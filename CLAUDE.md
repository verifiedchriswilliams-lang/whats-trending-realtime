# WhatsTrendingInRealTime.com — Editorial Intelligence Dashboard

## Project Purpose

A real-time editorial intelligence tool for the Daily Wire's editorial team. It aggregates RSS feeds from 15 major news sources every 30 minutes, clusters stories by specific topic (not generic keywords), and surfaces a Daily Wire Coverage Alignment score — showing editors which top trending stories they are and aren't covering.

**Target audience:** Conservative Americans 25–65. The editorial philosophy is "Daily Mail for American conservatives without the tabloid streak" — credibility of NYT/WaPo with a conservative perspective.

---

## Architecture

Single-file Python Flask app (`trending_dashboard.py`) deployed on Railway. No database — all state is in-memory. The HTML dashboard is embedded as a raw string in the Python file.

```
trending_dashboard.py   ← entire app (Flask server + data pipeline + HTML/CSS/JS)
requirements.txt        ← feedparser, flask, pytrends, gunicorn
Procfile                ← web: python trending_dashboard.py
CLAUDE.md               ← this file
```

**Stack:**
- Python 3.13 (Railway auto-detected)
- Flask for HTTP serving
- feedparser for RSS ingestion (15 sources, concurrent via ThreadPoolExecutor)
- pytrends for Google Trends US (unofficial API, rate-limited — cached 2h)
- gunicorn for production serving (via Procfile)
- Railway for hosting, GitHub for version control

---

## Key Algorithms

### Heat Score
`heat_score = (source_count × 12) + article_count + (hero_count × 20)`

- `source_count` = number of distinct outlets covering this story
- `article_count` = total articles in the cluster
- `hero_count` = number of outlets where this story was their #1 or #2 feed item (lead/hero position)

### Story Clustering (IMPORTANT — do not revert this logic)
Stories are clustered by **specific keywords only** — words appearing in more than 10% of all articles are filtered out as "generic connective tissue" (e.g. "trump", "president", "american"). This is intentional. Without this filter, a single mega-cluster forms around common words, making the tool useless for editorial signal.

The threshold: `max_freq = max(4, len(flat) * 0.10)`

A story clusters around a keyword if:
- The keyword appears in ≤10% of all articles AND
- At least 2 sources cover it OR 3+ articles mention it

### Daily Wire Alignment Score
Checks what % of the top 10 trending topics Daily Wire is covering. Each topic is checked against DW's RSS articles using keyword matching. Results shown as A/B/C/D grade + per-topic ✓/✗ breakdown.

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

**Per-source limit: 12 articles** (top of feed = above the fold signal)

---

## UI Features

### Top Trending Topics panel
- Ranked by heat score (highest first)
- **"Lead at X outlets"** navy badge: story was the #1/#2 article at that many outlets
- **"● DW Gap"** pulsing red badge: story is in top 10 but Daily Wire isn't covering it
- Source dots: colored by political lean, larger with outline ring = hero/lead position
- Click any row to expand and see all individual article headlines per outlet
- ★ marker on articles that were position 0 or 1 in their feed

### Google Trends US sidebar
- Shows top 25 US search trends
- Cached for 2 hours (pytrends gets rate-limited by Google)
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

### Deploying
```bash
git add -A
git commit -m "your message"
git pull --rebase origin main && git push
# Railway auto-deploys on push to main
```

### Making changes via Claude (Cowork)
The Cowork mount at `/sessions/.../mnt/whats-trending-realtime/` maps to `~/Projects/whats-trending-realtime/` on the Mac. **File overwrites do NOT sync back to Mac** — only new file creation works. The workaround is to commit from the VM, then `git pull --rebase && git push` from the Mac terminal, which pulls the committed changes down.

---

## Known Issues & Phase 2 Roadmap

### Known Issues
- **Google Trends rate-limiting:** pytrends uses Google's unofficial API and gets 429'd quickly. Mitigated with 2-hour cache. Long-term fix: use SerpAPI or a different trends provider.
- **Reuters RSS:** Their feed URL may periodically break as Reuters migrates infrastructure.
- **Clustering edge cases:** Very fast-breaking stories (first 10 minutes) may not cluster correctly until multiple sources pick them up.

### Phase 2 Features
- [ ] **Homepage scraping** for Fox News, Daily Wire, Breitbart — scrape actual HTML to detect pinned/featured stories not in RSS order
- [ ] **Drudge Report scraper** — no RSS feed, requires HTML parsing
- [ ] **Social signals** — Twitter/X trending topics, Reddit r/Conservative and r/politics
- [ ] **Custom domain** — WhatsTrendingInRealTime.com via Railway custom domain + DNS CNAME
- [ ] **Auth layer** — password protect for Daily Wire editorial team use
- [ ] **Email digest** — daily 8am summary of top 10 trending + DW alignment score
- [ ] **Story staleness** — fade out stories older than 2 hours from the trending list
- [ ] **Drudge siren** — visual alert when a story is Drudge's top link

---

## Environment

- **Production URL:** web-production-456b3.up.railway.app (temporary — pending custom domain)
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
