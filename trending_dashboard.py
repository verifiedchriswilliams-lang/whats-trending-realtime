#!/usr/bin/env python3
"""
WhatsTrendingInRealTime.com — Editorial Intelligence Dashboard
Real-time news aggregation & topic heat scoring for conservative editorial teams.

Usage:
    python trending_dashboard.py

Then open http://localhost:8080 in your browser.
Data auto-refreshes every 30 minutes. Click "Refresh Now" for an immediate update.
"""

import json
import time
import threading
import re
import sys
import os
import webbrowser
from datetime import datetime
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed


# ── Auto-install dependencies ─────────────────────────────────────────────────
def pip_install(pkg):
    print(f"  Installing {pkg}...")
    os.system(f'"{sys.executable}" -m pip install {pkg} --quiet --break-system-packages 2>/dev/null || '
              f'"{sys.executable}" -m pip install {pkg} --quiet 2>/dev/null')

try:
    import feedparser
except ImportError:
    pip_install('feedparser')
    import feedparser

try:
    from flask import Flask, jsonify, request as flask_request
except ImportError:
    pip_install('flask')
    from flask import Flask, jsonify, request as flask_request

try:
    from pytrends.request import TrendReq
    HAS_PYTRENDS = True
except ImportError:
    pip_install('pytrends')
    try:
        from pytrends.request import TrendReq
        HAS_PYTRENDS = True
    except Exception:
        HAS_PYTRENDS = False
        print("  Note: pytrends not available — Google Trends section will be skipped.")


# ── Source Configuration ──────────────────────────────────────────────────────
SOURCES = [
    # Tier 1 — flagship outlets
    {"id": "foxnews",     "name": "Fox News",           "rss": "https://feeds.foxnews.com/foxnews/latest",                    "lean": "right",        "tier": 1},
    {"id": "cnn",         "name": "CNN",                "rss": "https://rss.cnn.com/rss/cnn_topstories.rss",                  "lean": "left",         "tier": 1},
    {"id": "dailymail",   "name": "Daily Mail",         "rss": "https://www.dailymail.co.uk/news/index.rss",                  "lean": "center-right", "tier": 1},
    {"id": "nypost",      "name": "NY Post",            "rss": "https://nypost.com/feed/",                                    "lean": "right",        "tier": 1},
    {"id": "ap",          "name": "AP News",            "rss": "https://feeds.apnews.com/apnews/topnews",                     "lean": "center",       "tier": 1},
    {"id": "reuters",     "name": "Reuters",            "rss": "https://feeds.reuters.com/reuters/topNews",                   "lean": "center",       "tier": 1},
    {"id": "nbcnews",     "name": "NBC News",           "rss": "https://feeds.nbcnews.com/nbcnews/public/news",               "lean": "left",         "tier": 1},
    {"id": "dailywire",   "name": "Daily Wire",         "rss": "https://www.dailywire.com/rss.xml",                           "lean": "right",        "tier": 1},
    # Tier 2 — strong signal outlets
    {"id": "breitbart",   "name": "Breitbart",          "rss": "https://feeds.feedburner.com/breitbart",                      "lean": "right",        "tier": 2},
    {"id": "skynews",     "name": "Sky News",           "rss": "https://feeds.skynews.com/feeds/rss/home.xml",                "lean": "center",       "tier": 2},
    {"id": "thehill",     "name": "The Hill",           "rss": "https://thehill.com/rss/syndication/all-news",                "lean": "center",       "tier": 2},
    {"id": "washtimes",   "name": "Washington Times",   "rss": "https://www.washingtontimes.com/rss/headlines/news/",         "lean": "right",        "tier": 2},
    {"id": "foxbusiness", "name": "Fox Business",       "rss": "https://feeds.foxbusiness.com/foxbusiness/latest",            "lean": "right",        "tier": 2},
    {"id": "townhall",    "name": "Townhall",           "rss": "https://townhall.com/rss",                                    "lean": "right",        "tier": 2},
]

LEAN_DISPLAY = {
    "right":        {"label": "Right",      "color": "#EF4444"},
    "center-right": {"label": "Ctr-Right",  "color": "#F97316"},
    "center":       {"label": "Center",     "color": "#6B7280"},
    "left":         {"label": "Left",       "color": "#3B82F6"},
    "center-left":  {"label": "Ctr-Left",   "color": "#60A5FA"},
}

# Source display order in the grid
SOURCE_ORDER = [
    "foxnews", "nypost", "dailywire", "breitbart", "washtimes", "townhall",
    "ap", "reuters", "thehill", "skynews", "cnn", "nbcnews", "dailymail", "foxbusiness"
]

# ── Stop Words ────────────────────────────────────────────────────────────────
STOP_WORDS = {
    'the','a','an','and','or','but','in','on','at','to','for','of','with','by',
    'from','up','about','into','this','that','these','those','it','its','as',
    'what','which','who','when','where','why','how','all','both','each',
    'say','says','said','new','more','after','before','over','than','then',
    'her','his','him','she','he','they','their','them','we','us','our',
    'you','your','my','me','not','no','can','just','also','so','if','out',
    'now','one','two','has','have','had','been','were','was','are','is','be',
    'will','would','could','should','may','might','get','got','first','last',
    'next','vs','via','per','amid','against','between','during','while',
    'since','still','into','onto','upon','within','without','after','before',
    'report','reports','reported','reuters','news','breaking','watch','live',
    'video','photos','pictures','update','updates','latest','here','show',
    'shows','week','today','monday','tuesday','wednesday','thursday','friday',
    'saturday','sunday','year','years','time','day','days','month','months',
    'back','going','come','says','make','made','take','taken','give','given',
    'know','knew','think','thought','look','looks','need','needs','want',
    'wants','away','down','left','right','long','little','very','much','many',
    'such','only','same','then','than','well','even','like','just','come',
}


# ── Data Store ────────────────────────────────────────────────────────────────
data_store = {
    "last_updated": None,
    "sources": {},
    "trending_topics": [],
    "google_trends": [],
    "alignment_score": None,
    "sources_live": 0,
    "loading": True,
}
data_lock = threading.Lock()


# ── RSS Fetching ──────────────────────────────────────────────────────────────
def fetch_source(source):
    """Fetch and parse a single RSS feed. Returns (source_id, [articles])."""
    try:
        feed = feedparser.parse(source["rss"])
        if feed.bozo and not feed.entries:
            return source["id"], []
        articles = []
        for entry in feed.entries[:20]:
            title = entry.get("title", "").strip()
            if not title or len(title) < 10:
                continue
            # Clean HTML tags from summary
            summary = re.sub(r'<[^>]+>', '', entry.get("summary", ""))[:300]
            articles.append({
                "title":     title,
                "link":      entry.get("link", "#"),
                "summary":   summary.strip(),
                "published": entry.get("published", ""),
            })
        return source["id"], articles
    except Exception as e:
        return source["id"], []


# ── Google Trends ─────────────────────────────────────────────────────────────
def fetch_google_trends():
    """Fetch US Google Trends. Returns list of trending search strings."""
    if not HAS_PYTRENDS:
        return []
    try:
        pt = TrendReq(hl='en-US', tz=300, timeout=(15, 30),
                      requests_args={'headers': {'User-Agent': 'Mozilla/5.0'}})
        df = pt.trending_searches(pn='united_states')
        return df[0].tolist()[:25]
    except Exception as e:
        print(f"  Google Trends error: {e}")
        return []


# ── Topic Clustering ──────────────────────────────────────────────────────────
def extract_keywords(title):
    """Extract meaningful keywords from a news headline."""
    # Split on word boundaries, lowercase
    words = re.findall(r"[A-Za-z']+", title.lower())
    # Filter stop words and short words
    filtered = [w for w in words if w not in STOP_WORDS and len(w) > 3]
    # Also extract proper nouns (capitalized words in original)
    proper = re.findall(r'\b[A-Z][a-z]{2,}\b', title)
    proper_lower = [p.lower() for p in proper if p.lower() not in STOP_WORDS and len(p) > 3]
    # Merge, deduplicate, preserve order
    seen = set()
    result = []
    for w in filtered + proper_lower:
        if w not in seen:
            seen.add(w)
            result.append(w)
    return result


def cluster_topics(all_articles_by_source):
    """
    Cluster articles across sources by shared keywords.
    Returns a list of topic dicts sorted by heat score (desc).

    Heat score = (sources covering topic * 12) + article count
    Higher weight on source diversity — a story in 8 outlets beats a 15-article
    story all from one outlet.
    """
    # keyword -> list of (source_id, article)
    kw_index = defaultdict(list)

    for source_id, articles in all_articles_by_source.items():
        for art in articles:
            kws = extract_keywords(art["title"])
            for kw in kws:
                kw_index[kw].append((source_id, art))

    # Count distinct sources per keyword
    kw_source_count = {
        kw: len(set(s for s, _ in arts))
        for kw, arts in kw_index.items()
    }

    # Filter to keywords appearing in 2+ sources
    hot_kws = {kw: c for kw, c in kw_source_count.items() if c >= 2}

    if not hot_kws:
        # Fallback: just show most-mentioned keywords
        hot_kws = {kw: c for kw, c in kw_source_count.items() if len(kw_index[kw]) >= 3}

    # Sort keywords by source diversity, then by raw article count
    sorted_kws = sorted(
        hot_kws.items(),
        key=lambda x: (-x[1], -len(kw_index[x[0]]))
    )

    # Build topic clusters, avoiding article re-use
    used = set()
    clusters = []

    for kw, src_count in sorted_kws[:40]:
        arts = kw_index[kw]
        cluster_articles = []
        cluster_sources = set()

        for source_id, art in arts:
            art_key = (source_id, art["title"])
            if art_key not in used:
                cluster_articles.append({**art, "source_id": source_id})
                cluster_sources.add(source_id)
                used.add(art_key)

        if len(cluster_articles) < 2:
            continue

        # Pick best representative headline (prefer tier-1 sources)
        tier1_ids = {s["id"] for s in SOURCES if s["tier"] == 1}
        tier1_articles = [a for a in cluster_articles if a["source_id"] in tier1_ids]
        best = (tier1_articles or cluster_articles)[0]

        heat = src_count * 12 + len(cluster_articles)

        clusters.append({
            "keyword":      kw.title(),
            "topic":        best["title"],
            "articles":     cluster_articles[:10],
            "sources":      list(cluster_sources),
            "source_count": len(cluster_sources),
            "article_count": len(cluster_articles),
            "heat_score":   heat,
        })

    clusters.sort(key=lambda x: -x["heat_score"])
    return clusters[:20]


# ── Daily Wire Alignment ──────────────────────────────────────────────────────
def compute_alignment(all_articles_by_source, trending_topics):
    """
    Measure what % of the top trending topics Daily Wire is covering.
    Returns alignment dict or None if DW data unavailable.
    """
    dw_articles = all_articles_by_source.get("dailywire", [])
    if not dw_articles or not trending_topics:
        return None

    # Build DW keyword set
    dw_kws = set()
    for art in dw_articles:
        dw_kws.update(extract_keywords(art["title"]))

    topics_to_check = trending_topics[:10]
    covered = 0
    details = []

    for topic in topics_to_check:
        kw = topic["keyword"].lower()
        # Check if DW covers this keyword
        is_covered = (
            kw in dw_kws or
            any(kw in a["title"].lower() for a in dw_articles)
        )
        covered += int(is_covered)
        # Find the DW article that covers it (if any)
        matching_dw = next(
            (a["title"] for a in dw_articles if kw in a["title"].lower()), None
        )
        details.append({
            "topic":      topic["keyword"],
            "covered":    is_covered,
            "dw_article": matching_dw,
            "heat_score": topic["heat_score"],
        })

    score = round((covered / len(topics_to_check)) * 100) if topics_to_check else 0
    grade = "A" if score >= 80 else "B" if score >= 60 else "C" if score >= 40 else "D"

    return {
        "score":   score,
        "grade":   grade,
        "covered": covered,
        "total":   len(topics_to_check),
        "details": details,
    }


# ── Main Refresh ──────────────────────────────────────────────────────────────
def refresh_data():
    """Fetch everything and update the global data store."""
    ts = datetime.now().strftime('%H:%M:%S')
    print(f"\n[{ts}] Fetching {len(SOURCES)} sources + Google Trends...")

    all_articles = {}
    errors = []

    # Concurrent RSS fetch
    with ThreadPoolExecutor(max_workers=12) as ex:
        futures = {ex.submit(fetch_source, s): s for s in SOURCES}
        for future in as_completed(futures):
            source_id, articles = future.result()
            if articles:
                all_articles[source_id] = articles
                print(f"  ✓ {source_id}: {len(articles)} stories")
            else:
                src = futures[future]
                errors.append(src["name"])
                print(f"  ✗ {source_id}: no data")

    # Google Trends
    print(f"  Fetching Google Trends US...")
    google_trends = fetch_google_trends()
    if google_trends:
        print(f"  ✓ Google Trends: {len(google_trends)} searches")
    else:
        print(f"  ✗ Google Trends: unavailable")

    # Cluster topics
    print(f"  Clustering topics across {len(all_articles)} sources...")
    trending_topics = cluster_topics(all_articles)
    print(f"  → {len(trending_topics)} trending topics found")

    # Daily Wire alignment
    alignment = compute_alignment(all_articles, trending_topics)
    if alignment:
        print(f"  → DW alignment score: {alignment['score']}% ({alignment['grade']})")

    # Build per-source display data
    sources_display = {}
    for s in SOURCES:
        sid = s["id"]
        lean_info = LEAN_DISPLAY.get(s["lean"], {"label": s["lean"], "color": "#6B7280"})
        sources_display[sid] = {
            **s,
            "lean_label": lean_info["label"],
            "lean_color": lean_info["color"],
            "articles":   all_articles.get(sid, [])[:8],
            "status":     "ok" if sid in all_articles else "error",
        }

    with data_lock:
        data_store["last_updated"]   = datetime.now().isoformat()
        data_store["sources"]        = sources_display
        data_store["trending_topics"] = trending_topics
        data_store["google_trends"]  = google_trends
        data_store["alignment_score"] = alignment
        data_store["sources_live"]   = len(all_articles)
        data_store["loading"]        = False

    ts2 = datetime.now().strftime('%H:%M:%S')
    print(f"[{ts2}] Refresh complete. {len(all_articles)}/{len(SOURCES)} sources live.\n")


def background_refresh_loop(interval_seconds=1800):
    """Daemon thread: refresh data every interval_seconds (default 30 min)."""
    while True:
        try:
            refresh_data()
        except Exception as e:
            print(f"  Refresh thread error: {e}")
            with data_lock:
                data_store["loading"] = False
        time.sleep(interval_seconds)


# ── Flask App ─────────────────────────────────────────────────────────────────
app = Flask(__name__)

@app.route('/')
def index():
    return HTML_DASHBOARD, 200, {'Content-Type': 'text/html; charset=utf-8'}

@app.route('/api/data')
def api_data():
    with data_lock:
        return jsonify(data_store)

@app.route('/api/refresh', methods=['POST'])
def api_refresh():
    """Trigger an immediate background refresh."""
    t = threading.Thread(target=refresh_data, daemon=True)
    t.start()
    return jsonify({"status": "refresh_started"})


# ── HTML Dashboard ────────────────────────────────────────────────────────────
HTML_DASHBOARD = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>WhatsTrendingInRealTime.com — Editorial Dashboard</title>
<style>
:root {
  --navy:        #0F172A;
  --navy-light:  #1E293B;
  --navy-mid:    #334155;
  --navy-soft:   #475569;
  --accent:      #F97316;
  --accent-glow: rgba(249,115,22,0.15);
  --red:         #EF4444;
  --green:       #22C55E;
  --text:        #F1F5F9;
  --text-muted:  #94A3B8;
  --border:      #1E293B;
  --card:        #131C2E;
}
* { margin: 0; padding: 0; box-sizing: border-box; }
html { scroll-behavior: smooth; }
body {
  background: var(--navy);
  color: var(--text);
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
  font-size: 14px;
  line-height: 1.5;
  min-height: 100vh;
}

/* ── Loading Overlay ────────────────────── */
#loadingOverlay {
  position: fixed; inset: 0; background: var(--navy);
  display: flex; flex-direction: column; align-items: center;
  justify-content: center; z-index: 9999;
  transition: opacity 0.4s;
}
#loadingOverlay.hidden { opacity: 0; pointer-events: none; }
.spinner {
  width: 44px; height: 44px;
  border: 3px solid var(--navy-mid);
  border-top-color: var(--accent);
  border-radius: 50%;
  animation: spin 0.9s linear infinite;
  margin-bottom: 18px;
}
@keyframes spin { to { transform: rotate(360deg); } }
.loading-title { font-size: 20px; font-weight: 700; margin-bottom: 6px; }
.loading-sub { color: var(--text-muted); font-size: 13px; }
.loading-progress { margin-top: 24px; display: flex; flex-direction: column; gap: 4px; align-items: center; }
.loading-source { font-size: 12px; color: var(--text-muted); }

/* ── Header ─────────────────────────────── */
.header {
  background: var(--navy-light);
  border-bottom: 2px solid var(--accent);
  padding: 10px 24px;
  display: flex; align-items: center; justify-content: space-between;
  position: sticky; top: 0; z-index: 100;
  gap: 12px;
}
.logo { display: flex; align-items: center; gap: 10px; }
.logo-icon { font-size: 22px; }
.logo-name { font-size: 17px; font-weight: 800; letter-spacing: -0.5px; }
.logo-tagline { font-size: 10px; color: var(--accent); text-transform: uppercase; letter-spacing: 1.2px; margin-top: 1px; }
.header-meta { display: flex; align-items: center; gap: 14px; flex-wrap: wrap; }
.live-dot {
  display: flex; align-items: center; gap: 5px;
  background: rgba(239,68,68,0.12); border: 1px solid rgba(239,68,68,0.3);
  padding: 4px 10px; border-radius: 20px;
  font-size: 11px; font-weight: 700; color: var(--red); letter-spacing: 0.5px;
}
.live-dot::before {
  content: ''; width: 7px; height: 7px; border-radius: 50%;
  background: var(--red); animation: livepulse 2s infinite;
}
@keyframes livepulse { 0%,100%{opacity:1} 50%{opacity:0.4} }
.meta-text { font-size: 12px; color: var(--text-muted); }
.sources-count {
  font-size: 12px; font-weight: 600;
  background: var(--accent-glow); border: 1px solid rgba(249,115,22,0.3);
  padding: 3px 10px; border-radius: 20px; color: var(--accent);
}
.refresh-btn {
  background: var(--navy-mid); border: 1px solid var(--navy-soft);
  color: var(--text); padding: 6px 14px; border-radius: 6px;
  cursor: pointer; font-size: 12px; font-weight: 600;
  transition: all 0.15s; white-space: nowrap;
}
.refresh-btn:hover { background: var(--accent); border-color: var(--accent); color: white; }

/* ── Main Grid ──────────────────────────── */
.main {
  display: grid;
  grid-template-columns: 1fr 270px;
  grid-template-areas:
    "topics  trends"
    "sources sources"
    "align   align";
  gap: 14px;
  padding: 16px 20px;
  max-width: 1700px;
  margin: 0 auto;
}

/* ── Cards ──────────────────────────────── */
.card {
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 10px;
  overflow: hidden;
}
.card-hdr {
  padding: 11px 16px;
  border-bottom: 1px solid var(--border);
  display: flex; align-items: center; gap: 7px;
}
.card-hdr h2 {
  font-size: 11px; font-weight: 700;
  text-transform: uppercase; letter-spacing: 0.9px;
  color: var(--text-muted);
}
.card-hdr .hdr-right { margin-left: auto; font-size: 11px; color: var(--text-muted); }

/* ── Trending Topics ────────────────────── */
#topicsCard { grid-area: topics; }
.topic-row {
  border-bottom: 1px solid var(--border);
}
.topic-row:last-child { border-bottom: none; }
.topic-main {
  display: flex; align-items: center; gap: 10px;
  padding: 10px 14px; cursor: pointer;
  transition: background 0.12s;
}
.topic-main:hover { background: rgba(255,255,255,0.03); }
.topic-rank {
  font-size: 13px; font-weight: 700; color: var(--text-muted);
  width: 22px; text-align: right; flex-shrink: 0;
}
.topic-rank.hot { color: var(--accent); }
.topic-content { flex: 1; min-width: 0; }
.topic-kw {
  font-size: 14px; font-weight: 700;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.topic-headline {
  font-size: 12px; color: var(--text-muted);
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
  margin-top: 2px;
}
.topic-meta-row {
  display: flex; align-items: center; gap: 8px; margin-top: 5px;
}
.src-dots { display: flex; gap: 3px; }
.src-dot {
  width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0;
  cursor: default;
}
.coverage-text { font-size: 11px; color: var(--text-muted); }
.heat-wrap { display: flex; align-items: center; gap: 6px; flex-shrink: 0; }
.heat-bar-bg {
  width: 56px; height: 5px; border-radius: 3px;
  background: var(--navy-mid);
}
.heat-bar-fill {
  height: 5px; border-radius: 3px;
  background: linear-gradient(90deg, #F97316, #EF4444);
}
.heat-num { font-size: 11px; font-weight: 700; color: var(--accent); width: 26px; text-align: right; }
.topic-expand-icon { font-size: 11px; color: var(--text-muted); flex-shrink: 0; margin-left: 2px; }

/* Topic expanded articles */
.topic-articles {
  display: none;
  background: rgba(0,0,0,0.2);
  border-top: 1px solid var(--border);
}
.topic-articles.open { display: block; }
.ta-item {
  padding: 8px 14px 8px 46px;
  border-bottom: 1px solid rgba(255,255,255,0.04);
  font-size: 12px;
}
.ta-item:last-child { border-bottom: none; }
.ta-source { font-size: 10px; font-weight: 700; text-transform: uppercase; color: var(--text-muted); margin-bottom: 2px; }
.ta-item a { color: var(--text); text-decoration: none; }
.ta-item a:hover { color: var(--accent); }

/* ── Google Trends ──────────────────────── */
#trendsCard { grid-area: trends; }
.trend-item {
  display: flex; align-items: center; gap: 8px;
  padding: 7px 14px; border-bottom: 1px solid var(--border);
  font-size: 13px;
}
.trend-item:last-child { border-bottom: none; }
.trend-rank { font-size: 11px; color: var(--text-muted); width: 18px; flex-shrink: 0; }
.trend-term { flex: 1; }
.trend-bar-wrap { width: 40px; flex-shrink: 0; }
.trend-bar-bg { height: 3px; background: var(--navy-mid); border-radius: 2px; }
.trend-bar-fill { height: 3px; background: #3B82F6; border-radius: 2px; }

/* ── Sources Grid ───────────────────────── */
#sourcesSection { grid-area: sources; }
.sources-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: 12px;
  padding: 14px;
}
.source-card {
  background: rgba(0,0,0,0.15);
  border: 1px solid var(--border);
  border-radius: 8px;
  overflow: hidden;
}
.source-card-hdr {
  padding: 9px 13px;
  border-bottom: 1px solid var(--border);
  display: flex; align-items: center; justify-content: space-between;
  gap: 8px;
}
.source-name-wrap { display: flex; align-items: center; gap: 7px; }
.source-dot-lg {
  width: 10px; height: 10px; border-radius: 50%; flex-shrink: 0;
}
.source-name { font-size: 13px; font-weight: 700; }
.lean-chip {
  font-size: 10px; font-weight: 600;
  padding: 2px 7px; border-radius: 4px;
}
.source-count { font-size: 11px; color: var(--text-muted); }
.story-item {
  padding: 8px 13px;
  border-bottom: 1px solid rgba(255,255,255,0.04);
  font-size: 12px; line-height: 1.45;
}
.story-item:last-child { border-bottom: none; }
.story-item a { color: var(--text); text-decoration: none; }
.story-item a:hover { color: var(--accent); }
.source-error {
  padding: 14px 13px; font-size: 12px; color: var(--text-muted);
  font-style: italic;
}

/* ── Alignment Score ────────────────────── */
#alignCard { grid-area: align; }
.align-body {
  display: flex; align-items: flex-start; gap: 24px;
  padding: 16px 20px; flex-wrap: wrap;
}
.score-circle {
  width: 110px; height: 110px; border-radius: 50%;
  display: flex; flex-direction: column;
  align-items: center; justify-content: center;
  border: 4px solid; flex-shrink: 0;
}
.score-pct { font-size: 28px; font-weight: 800; }
.score-grade { font-size: 18px; font-weight: 700; margin-top: -2px; }
.score-label { font-size: 10px; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.8px; margin-top: 2px; }
.align-detail { flex: 1; min-width: 0; }
.align-summary { font-size: 14px; color: var(--text-muted); margin-bottom: 12px; }
.align-summary strong { color: var(--text); }
.align-topics {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: 6px;
}
.align-topic {
  display: flex; align-items: center; gap: 7px;
  padding: 5px 10px; border-radius: 5px;
  background: rgba(0,0,0,0.2); font-size: 12px;
}
.align-check { color: var(--green); font-size: 15px; flex-shrink: 0; }
.align-x     { color: var(--red);   font-size: 15px; flex-shrink: 0; }
.align-topic-name { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.align-dw-art { font-size: 10px; color: var(--accent); margin-top: 1px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

/* ── Responsive ─────────────────────────── */
@media (max-width: 900px) {
  .main { grid-template-columns: 1fr; grid-template-areas: "topics" "trends" "sources" "align"; }
}
</style>
</head>
<body>

<!-- Loading overlay -->
<div id="loadingOverlay">
  <div class="spinner"></div>
  <div class="loading-title">🔥 WhatsTrendingInRealTime.com</div>
  <div class="loading-sub">Scanning 14 sources + Google Trends US — takes ~15 seconds</div>
  <div class="loading-progress" id="loadingProgress"></div>
</div>

<!-- Header -->
<header class="header">
  <div class="logo">
    <span class="logo-icon">🔥</span>
    <div>
      <div class="logo-name">WhatsTrendingInRealTime.com</div>
      <div class="logo-tagline">Editorial Intelligence Dashboard</div>
    </div>
  </div>
  <div class="header-meta">
    <span class="live-dot">LIVE</span>
    <span class="sources-count" id="sourcesCount">Loading...</span>
    <span class="meta-text" id="lastUpdated">—</span>
    <span class="meta-text" id="countdown"></span>
    <button class="refresh-btn" onclick="forceRefresh()">↻ Refresh Now</button>
  </div>
</header>

<!-- Main content -->
<div class="main">

  <!-- Trending Topics -->
  <div class="card" id="topicsCard">
    <div class="card-hdr">
      <span>🔥</span>
      <h2>Top Trending Topics</h2>
      <span class="hdr-right">Ranked by cross-source heat score · Click to expand</span>
    </div>
    <div id="topicsList"><div style="padding:20px;text-align:center;color:var(--text-muted)">Loading...</div></div>
  </div>

  <!-- Google Trends -->
  <div class="card" id="trendsCard">
    <div class="card-hdr">
      <span>📈</span>
      <h2>Google Trends US</h2>
      <span class="hdr-right">Right now</span>
    </div>
    <div id="trendsList"><div style="padding:20px;text-align:center;color:var(--text-muted)">Loading...</div></div>
  </div>

  <!-- Sources section -->
  <div class="card" id="sourcesSection">
    <div class="card-hdr">
      <span>📰</span>
      <h2>Source Headlines</h2>
      <span class="hdr-right">Fox · CNN · Daily Mail · NY Post · AP · Reuters · Breitbart · Sky · NBC · Hill · DW · WashTimes · FoxBiz · Townhall</span>
    </div>
    <div class="sources-grid" id="sourcesGrid"></div>
  </div>

  <!-- Daily Wire Alignment -->
  <div class="card" id="alignCard">
    <div class="card-hdr">
      <span>🎯</span>
      <h2>Daily Wire Coverage Alignment</h2>
      <span class="hdr-right">Are you covering what's trending?</span>
    </div>
    <div id="alignBody"><div style="padding:20px;text-align:center;color:var(--text-muted)">Loading...</div></div>
  </div>

</div><!-- /main -->

<script>
// ── Config ──────────────────────────────────────────────────────
const SOURCE_ORDER = [
  'foxnews','nypost','dailywire','breitbart','washtimes','townhall',
  'ap','reuters','thehill','skynews','cnn','nbcnews','dailymail','foxbusiness'
];

let _nextRefresh = Date.now() + 30 * 60 * 1000;
let _loading = true;

// ── Utils ───────────────────────────────────────────────────────
function esc(s) {
  return String(s||'')
    .replace(/&/g,'&amp;').replace(/</g,'&lt;')
    .replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}
function timeAgo(isoStr) {
  if (!isoStr) return '—';
  const d = Math.floor((Date.now() - new Date(isoStr)) / 1000);
  if (d < 60) return `${d}s ago`;
  if (d < 3600) return `${Math.floor(d/60)}m ago`;
  return `${Math.floor(d/3600)}h ago`;
}
function fmtCountdown(ms) {
  if (ms <= 0) return 'Refreshing...';
  const m = Math.floor(ms / 60000);
  const s = Math.floor((ms % 60000) / 1000);
  return `Next refresh: ${m}:${String(s).padStart(2,'0')}`;
}

// ── Render: Trending Topics ─────────────────────────────────────
function renderTopics(topics) {
  const el = document.getElementById('topicsList');
  if (!topics || !topics.length) {
    el.innerHTML = '<div style="padding:20px;text-align:center;color:var(--text-muted)">No trending topics found. Try Refresh Now.</div>';
    return;
  }
  const maxHeat = topics[0].heat_score || 1;
  el.innerHTML = topics.map((t, i) => {
    const pct = Math.round((t.heat_score / maxHeat) * 100);
    const hot = i < 3;
    const dots = (t.sources||[]).map(sid => {
      const color = (window._leans||{})[sid] || '#6B7280';
      return `<span class="src-dot" style="background:${color}" title="${esc(sid)}"></span>`;
    }).join('');
    const articles = (t.articles||[]).map(a =>
      `<div class="ta-item">
        <div class="ta-source">${esc(a.source_id)}</div>
        <a href="${esc(a.link)}" target="_blank" rel="noopener">${esc(a.title)}</a>
      </div>`
    ).join('');
    return `
    <div class="topic-row">
      <div class="topic-main" onclick="toggleTopic(${i})">
        <span class="topic-rank ${hot?'hot':''}">${i+1}</span>
        <div class="topic-content">
          <div class="topic-kw">${esc(t.keyword)}</div>
          <div class="topic-headline">${esc(t.topic)}</div>
          <div class="topic-meta-row">
            <div class="src-dots">${dots}</div>
            <span class="coverage-text">${t.source_count} sources · ${t.article_count} stories</span>
          </div>
        </div>
        <div class="heat-wrap">
          <div class="heat-bar-bg"><div class="heat-bar-fill" style="width:${pct}%"></div></div>
          <span class="heat-num">${t.heat_score}</span>
        </div>
        <span class="topic-expand-icon" id="topicIcon${i}">▸</span>
      </div>
      <div class="topic-articles" id="topicArt${i}">${articles}</div>
    </div>`;
  }).join('');
}

function toggleTopic(i) {
  const el = document.getElementById(`topicArt${i}`);
  const ic = document.getElementById(`topicIcon${i}`);
  const open = el.classList.toggle('open');
  ic.textContent = open ? '▾' : '▸';
}

// ── Render: Google Trends ───────────────────────────────────────
function renderTrends(trends) {
  const el = document.getElementById('trendsList');
  if (!trends || !trends.length) {
    el.innerHTML = '<div style="padding:16px;text-align:center;color:var(--text-muted);font-size:12px">Google Trends unavailable<br><span style="font-size:11px">pytrends rate-limited. Try again later.</span></div>';
    return;
  }
  el.innerHTML = trends.slice(0,25).map((t, i) => {
    const pct = Math.round(((25 - i) / 25) * 100);
    return `<div class="trend-item">
      <span class="trend-rank">${i+1}</span>
      <span class="trend-term">${esc(t)}</span>
      <div class="trend-bar-wrap"><div class="trend-bar-bg"><div class="trend-bar-fill" style="width:${pct}%"></div></div></div>
    </div>`;
  }).join('');
}

// ── Render: Sources Grid ────────────────────────────────────────
function renderSources(sources) {
  if (!sources) return;
  // Build lean color map for dots
  window._leans = {};
  Object.entries(sources).forEach(([id, s]) => { window._leans[id] = s.lean_color; });

  const ordered = [
    ...SOURCE_ORDER.filter(id => sources[id]),
    ...Object.keys(sources).filter(id => !SOURCE_ORDER.includes(id))
  ];

  document.getElementById('sourcesGrid').innerHTML = ordered.map(sid => {
    const s = sources[sid];
    if (!s) return '';
    const arts = s.articles || [];
    return `
    <div class="source-card">
      <div class="source-card-hdr">
        <div class="source-name-wrap">
          <span class="source-dot-lg" style="background:${esc(s.lean_color)}"></span>
          <span class="source-name">${esc(s.name)}</span>
        </div>
        <span class="lean-chip" style="background:${esc(s.lean_color)}22;color:${esc(s.lean_color)}">${esc(s.lean_label)}</span>
      </div>
      ${arts.length ? arts.map(a =>
        `<div class="story-item"><a href="${esc(a.link)}" target="_blank" rel="noopener">${esc(a.title)}</a></div>`
      ).join('') : `<div class="source-error">⚠ Feed unavailable</div>`}
    </div>`;
  }).join('');
}

// ── Render: Alignment Score ─────────────────────────────────────
function renderAlignment(al) {
  const el = document.getElementById('alignBody');
  if (!al) {
    el.innerHTML = '<div style="padding:20px;text-align:center;color:var(--text-muted)">Daily Wire RSS not loading. Check feed URL.</div>';
    return;
  }
  const gradeColor = { A:'#22C55E', B:'#84CC16', C:'#F59E0B', D:'#EF4444' }[al.grade] || '#6B7280';
  const topicCards = (al.details||[]).map(d => `
    <div class="align-topic">
      <span class="${d.covered ? 'align-check' : 'align-x'}">${d.covered ? '✓' : '✗'}</span>
      <div style="flex:1;min-width:0">
        <div class="align-topic-name">${esc(d.topic)}</div>
        ${d.dw_article ? `<div class="align-dw-art">↳ ${esc(d.dw_article)}</div>` : ''}
      </div>
    </div>`).join('');
  el.innerHTML = `
  <div class="align-body">
    <div class="score-circle" style="border-color:${gradeColor};color:${gradeColor}">
      <span class="score-pct">${al.score}%</span>
      <span class="score-grade">${al.grade}</span>
      <span class="score-label">Coverage</span>
    </div>
    <div class="align-detail">
      <div class="align-summary">
        Daily Wire covered <strong>${al.covered} of ${al.total}</strong> top trending topics today.
        ${al.score < 60 ? `<span style="color:var(--red)"> ↑ ${al.total - al.covered} major stories need coverage.</span>` : '<span style="color:var(--green)"> Strong alignment.</span>'}
      </div>
      <div class="align-topics">${topicCards}</div>
    </div>
  </div>`;
}

// ── Data Loading ────────────────────────────────────────────────
async function loadData() {
  try {
    const res = await fetch('/api/data');
    const data = await res.json();

    if (data.loading) {
      setTimeout(loadData, 3000);
      return;
    }

    // Hide loading overlay with fade
    document.getElementById('loadingOverlay').classList.add('hidden');

    // Update header
    document.getElementById('sourcesCount').textContent =
      `${data.sources_live || 0} sources live`;
    document.getElementById('lastUpdated').textContent =
      data.last_updated ? `Updated ${timeAgo(data.last_updated)}` : '';

    // Render all sections
    renderTopics(data.trending_topics);
    renderTrends(data.google_trends);
    renderSources(data.sources);
    renderAlignment(data.alignment_score);

  } catch(e) {
    console.error('loadData error:', e);
    setTimeout(loadData, 5000);
  }
}

async function forceRefresh() {
  document.getElementById('loadingOverlay').classList.remove('hidden');
  try { await fetch('/api/refresh', { method: 'POST' }); } catch(e) {}
  _nextRefresh = Date.now() + 30 * 60 * 1000;
  setTimeout(loadData, 3000);
}

// Countdown timer
setInterval(() => {
  const rem = _nextRefresh - Date.now();
  document.getElementById('countdown').textContent = fmtCountdown(rem);
  if (rem <= 0) {
    _nextRefresh = Date.now() + 30 * 60 * 1000;
    loadData();
  }
}, 1000);

// Kick off
loadData();
</script>
</body>
</html>"""


# ── Entry Point ───────────────────────────────────────────────────────────────
if __name__ == '__main__':
    PORT = 8080

    print("\n" + "=" * 62)
    print("  🔥  WhatsTrendingInRealTime.com — Editorial Dashboard")
    print("=" * 62)
    print(f"\n  Dashboard URL:  http://localhost:{PORT}")
    print(f"  Sources:        {len(SOURCES)} news outlets")
    print(f"  Auto-refresh:   Every 30 minutes")
    print(f"  Google Trends:  {'Enabled' if HAS_PYTRENDS else 'Disabled (install pytrends)'}")
    print(f"\n  Initial data fetch starting in background...")
    print(f"  Dashboard will be ready in ~15 seconds.\n")
    print("  Press Ctrl+C to stop.\n")
    print("=" * 62 + "\n")

    # Start background refresh loop (30-min interval)
    refresh_thread = threading.Thread(
        target=background_refresh_loop,
        args=(1800,),
        daemon=True
    )
    refresh_thread.start()

    # Open browser after a 2-second delay
    threading.Timer(2.0, lambda: webbrowser.open(f'http://localhost:{PORT}')).start()

    # Start Flask (threaded for concurrent requests)
    app.run(host='0.0.0.0', port=PORT, debug=False, threaded=True, use_reloader=False)
