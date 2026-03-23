#!/usr/bin/env python3
"""
WhatsTrendingInRealTime.com — Editorial Intelligence Dashboard  v2
Newspaper theme. Clustering fix. 15 sources incl. NYT.
"""

import json, time, threading, re, sys, os, webbrowser
from datetime import datetime, timezone, timedelta
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed

def pip_install(pkg):
    print(f"  Installing {pkg}...")
    os.system(f'"{sys.executable}" -m pip install {pkg} --quiet --break-system-packages 2>/dev/null || "{sys.executable}" -m pip install {pkg} --quiet 2>/dev/null')

try: import feedparser
except ImportError: pip_install('feedparser'); import feedparser

try: from flask import Flask, jsonify
except ImportError: pip_install('flask'); from flask import Flask, jsonify

try: import requests; from bs4 import BeautifulSoup; HAS_SCRAPE = True
except ImportError:
    pip_install('requests'); pip_install('beautifulsoup4')
    try: import requests; from bs4 import BeautifulSoup; HAS_SCRAPE = True
    except: HAS_SCRAPE = False; print("  requests/bs4 unavailable — scraping disabled.")

# Google Trends via official public RSS (no API key, no rate limits)
TRENDS_RSS = "https://trends.google.com/trends/trendingsearches/daily/rss?geo=US"

# Per-source homepage scraping config: CSS selectors for headline extraction
SCRAPE_SOURCES = {
    "foxnews":    "https://www.foxnews.com",
    "cnn":        "https://www.cnn.com",
    "nytimes":    "https://www.nytimes.com",
    "dailymail":  "https://www.dailymail.co.uk",
    "nypost":     "https://nypost.com",
    "ap":         "https://apnews.com",
    "nbcnews":    "https://www.nbcnews.com",
    "dailywire":  "https://www.dailywire.com",
    "breitbart":  "https://www.breitbart.com",
    "thehill":    "https://thehill.com",
    "washtimes":  "https://www.washingtontimes.com",
    "townhall":   "https://townhall.com",
    "skynews":    "https://news.sky.com",
}

SOURCES = [
    # Tier 1 — editorial homepage / top-story feeds where available
    {"id":"foxnews",    "name":"Fox News",          "rss":"https://feeds.foxnews.com/foxnews/national",               "lean":"right",        "tier":1},
    {"id":"cnn",        "name":"CNN",               "rss":"https://rss.cnn.com/rss/edition.rss",                      "lean":"left",         "tier":1},
    {"id":"nytimes",    "name":"New York Times",    "rss":"https://rss.nytimes.com/services/xml/rss/nyt/HomePage.xml","lean":"left",         "tier":1},
    {"id":"dailymail",  "name":"Daily Mail",        "rss":"https://www.dailymail.co.uk/news/index.rss",               "lean":"center-right", "tier":1},
    {"id":"nypost",     "name":"NY Post",           "rss":"https://nypost.com/feed/",                                 "lean":"right",        "tier":1},
    {"id":"ap",         "name":"AP News",           "rss":"https://feeds.apnews.com/apnews/topnews",                  "lean":"center",       "tier":1},
    {"id":"reuters",    "name":"Reuters",           "rss":"https://www.reutersagency.com/feed/?best-topics=top-news&post_type=best", "lean":"center", "tier":1},
    {"id":"nbcnews",    "name":"NBC News",          "rss":"https://feeds.nbcnews.com/nbcnews/public/news",            "lean":"left",         "tier":1},
    {"id":"dailywire",  "name":"Daily Wire",        "rss":"https://www.dailywire.com/rss.xml",                        "lean":"right",        "tier":1},
    # Tier 2 — strong opinion/political feeds
    {"id":"breitbart",  "name":"Breitbart",         "rss":"https://www.breitbart.com/feed/",                          "lean":"right",        "tier":2},
    {"id":"skynews",    "name":"Sky News",          "rss":"https://feeds.skynews.com/feeds/rss/home.xml",             "lean":"center",       "tier":2},
    {"id":"thehill",    "name":"The Hill",          "rss":"https://thehill.com/feed/",                                "lean":"center",       "tier":2},
    {"id":"washtimes",  "name":"Washington Times",  "rss":"https://www.washingtontimes.com/rss/headlines/news/",      "lean":"right",        "tier":2},
    {"id":"foxbusiness","name":"Fox Business",      "rss":"https://feeds.foxbusiness.com/foxbusiness/latest",         "lean":"right",        "tier":2},
    {"id":"townhall",   "name":"Townhall",          "rss":"https://townhall.com/rss/tipsheet",                        "lean":"right",        "tier":2},
]

LEAN = {
    "right":        {"label":"Right",     "color":"#C41230"},
    "center-right": {"label":"Ctr-Right", "color":"#B45309"},
    "center":       {"label":"Center",    "color":"#374151"},
    "left":         {"label":"Left",      "color":"#1D4ED8"},
    "center-left":  {"label":"Ctr-Left",  "color":"#1D4ED8"},
}

SOURCE_ORDER = ["foxnews","nypost","dailywire","breitbart","washtimes","townhall",
                "ap","reuters","thehill","skynews","cnn","nytimes","nbcnews","dailymail","foxbusiness"]

STOP_WORDS = {
    # --- Function words ---
    'the','a','an','and','or','but','in','on','at','to','for','of','with','by','from','up',
    'about','into','this','that','these','those','it','its','as','what','which','who','when',
    'where','why','how','all','both','each','say','says','said','new','more','after','before',
    'over','than','then','her','his','him','she','he','they','their','them','we','us','our',
    'you','your','my','me','not','no','can','just','also','so','if','out','now','one','two',
    'has','have','had','been','were','was','are','is','be','will','would','could','should',
    'may','might','get','got','first','last','next','vs','via','per','amid','against','between',
    'during','while','since','still','onto','upon','within','without','report','reports',
    'reported','reuters','news','breaking','watch','live','video','photos','update','updates',
    'latest','show','shows','week','today','year','years','time','day','days','month','months',
    'back','going','come','make','made','take','taken','give','given','know','think','look',
    'need','want','away','down','long','little','very','much','many','such','only','same',
    'well','even','like',
    # --- Crime/emergency generics ---
    'death','dead','died','dies','kill','kills','killed','killing','killer',
    'shot','shots','shooting','crash','crashes','fire','fires','blast','explosion',
    'bomb','bombing','attack','attacks','murder','murders','murdered',
    'arrest','arrests','arrested','charge','charges','charged',
    'police','officer','officers','court','trial','guilty','verdict','sentence','sentenced',
    'body','bodies','hospital','victim','victims','suspect','suspects',
    'found','missing','search','rescue','emergency','tragedy','tragic',
    'recall','accident','incident',
    # --- Generic political/institutional nouns ---
    # These words span many unrelated stories and produce false clusters.
    # A good cluster seed must point to ONE specific story, not a category.
    'security','government','governments','national','federal','state','states',
    'official','officials','administration','department','departments',
    'agency','agencies','ministry','committee','commission','office',
    'organization','organizations','institution','institutions',
    'community','communities','group','groups','party','parties',
    'member','members','leader','leaders','staff','team','teams',
    'force','forces','military','troops','soldiers','army','navy',
    'service','services','program','programs','project','projects',
    'policy','policies','plan','plans','planning','strategy',
    'system','systems','network','networks','operation','operations',
    'deal','deals','agreement','agreements','talks','negotiations',
    'bill','bills','legislation','regulation','regulations','ruling',
    'case','cases','issue','issues','matter','matters','question',
    'move','moves','step','steps','measure','measures','decision',
    'fight','battle','battles','conflict','conflicts','struggle',
    'effort','efforts','attempt','attempts','push','push',
    'action','actions','response','responses','reaction','move',
    'claim','claims','statement','statements','announcement',
    'call','calls','demand','demands','request','requests',
    'power','powers','control','authority','rule','rules','order','orders',
    'right','rights','freedom','freedoms','justice','reform',
    'role','position','status','level','rate','rates','number',
    'money','funds','funding','budget','cost','costs','price','prices',
    'help','support','care','health','crisis','crises',
    'world','global','international','local','regional',
    'public','private','personal','political','social','economic',
    'major','large','small','high','low','long','short','early','late',
    'country','countries','nation','nations','people','person','home',
    'thing','things','part','parts','way','ways','place','places','area',
    'work','working','worker','workers','job','jobs',
    'company','companies','business','businesses','market','markets',
    'court','courts','judge','judges','law','laws','legal',
}

data_store = {"last_updated":None,"sources":{},"trending_topics":[],"reddit_posts":[],"twitter_trends":[],"drudge_links":[],"sources_live":0,"loading":True}
data_lock = threading.Lock()

# Previous topics for trajectory tracking (heat score deltas)
_prev_heat = {}  # keyword → heat_score from last refresh

# Google Trends cache — only re-fetch every 2 hours, back off 4h on failure
_gt_cache = {"data": [], "fetched_at": 0, "next_retry": 0}

def parse_pub_date(entry):
    """Parse publication date from a feed entry. Returns UTC datetime or None."""
    try:
        t = entry.get("published_parsed") or entry.get("updated_parsed")
        if t: return datetime(*t[:6], tzinfo=timezone.utc)
    except: pass
    return None

_RSS_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
    'Accept': 'application/rss+xml, application/xml, text/xml, */*',
}

def fetch_source(source):
    try:
        feed = feedparser.parse(source["rss"], request_headers=_RSS_HEADERS)
        if feed.bozo and not feed.entries: return source["id"], []
        arts = []
        cutoff = datetime.now(timezone.utc) - timedelta(hours=48)
        for i, e in enumerate(feed.entries[:12]):
            t = e.get("title","").strip()
            if not t or len(t)<10: continue
            # Reject articles older than 48 hours — stale stories pollute clustering
            pub = parse_pub_date(e)
            if pub and pub < cutoff:
                continue
            arts.append({"title":t,"link":e.get("link","#"),
                         "summary":re.sub(r'<[^>]+>','',e.get("summary",""))[:200],
                         "published":e.get("published",""),
                         "pub_ts": pub.isoformat() if pub else None,
                         "feed_position": i})
        return source["id"], arts
    except: return source["id"], []

def fetch_google_trends():
    """Fetch Google Trends US via official public RSS feed (no API key, no rate limits)."""
    global _gt_cache
    now = time.time()
    # Serve cache if data exists and is fresh (< 2 hours)
    if _gt_cache["data"] and now - _gt_cache["fetched_at"] < 7200:
        return _gt_cache["data"], _gt_cache["fetched_at"]
    # Back off if we failed recently (4-hour cooldown after failure)
    if now < _gt_cache["next_retry"]:
        print(f"  Google Trends: in backoff, next retry in {int((_gt_cache['next_retry']-now)/60)}m")
        return _gt_cache["data"], _gt_cache["fetched_at"]
    try:
        # feedparser alone sends no User-Agent so Google silently blocks it.
        # Fetch the raw bytes with requests first, then hand to feedparser.
        raw = None
        if HAS_SCRAPE:
            try:
                resp = requests.get(TRENDS_RSS, timeout=15, headers={
                    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
                    'Accept': 'application/rss+xml, application/xml, text/xml, */*',
                })
                print(f"  Google Trends HTTP {resp.status_code}")
                if resp.status_code == 200:
                    raw = resp.content
                else:
                    raise Exception(f"HTTP {resp.status_code}")
            except Exception as he:
                print(f"  Google Trends requests error: {he}")
        feed = feedparser.parse(raw or TRENDS_RSS)
        if feed.bozo and not feed.entries:
            raise Exception(f"RSS parse failed: {getattr(feed,'bozo_exception','unknown')}")
        result = [e.get("title","").strip() for e in feed.entries if e.get("title","").strip()][:25]
        if not result:
            raise Exception(f"RSS returned 0 entries (feed.bozo={feed.bozo})")
        _gt_cache = {"data": result, "fetched_at": now, "next_retry": 0}
        print(f"  Google Trends RSS: {len(result)} trends fetched")
        return result, now
    except Exception as ex:
        print(f"  Google Trends RSS error: {ex} — backing off 4h")
        _gt_cache["next_retry"] = now + 14400  # don't retry for 4 hours
        return _gt_cache["data"], _gt_cache["fetched_at"]


def scrape_homepage(sid, url):
    """Scrape a news source homepage to detect which headlines appear above the fold.
    Returns a frozenset of normalized (lowercased) headline strings, or empty set on failure.
    Used to cross-verify RSS hero position — if an article appears in BOTH RSS and the
    scraped homepage, it's a double-confirmed lead story."""
    if not HAS_SCRAPE:
        return frozenset()
    try:
        r = requests.get(url, timeout=10, headers={
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml',
        })
        r.raise_for_status()
        soup = BeautifulSoup(r.text, 'html.parser')
        headlines = set()
        # Grab text from h1/h2/h3 tags — main content hierarchy
        for tag in soup.find_all(['h1','h2','h3']):
            text = tag.get_text(separator=' ', strip=True)
            if 20 <= len(text) <= 250:
                headlines.add(text.lower())
        # Also grab prominent anchor text (many news sites use <a> for headlines)
        for tag in soup.find_all('a', href=True):
            text = tag.get_text(separator=' ', strip=True)
            if 20 <= len(text) <= 250:
                headlines.add(text.lower())
        return frozenset(headlines)
    except Exception as ex:
        print(f"  scrape {sid}: {ex}")
        return frozenset()

_DRUDGE_CACHE   = {"data": [], "fetched_at": 0}
_TWITTER_CACHE  = {"data": [], "fetched_at": 0}
_REDDIT_CACHE   = {"data": [], "fetched_at": 0}

def fetch_drudge():
    """Scrape Drudge Report for its top 12 headline links.
    Drudge is the single best proxy for what conservative 25-65 Americans are clicking.
    Simple static HTML — no JS required, extremely reliable scrape target."""
    global _DRUDGE_CACHE
    now = time.time()
    if _DRUDGE_CACHE["data"] and now - _DRUDGE_CACHE["fetched_at"] < 1800:
        return _DRUDGE_CACHE["data"]
    if not HAS_SCRAPE:
        return _DRUDGE_CACHE["data"]
    try:
        r = requests.get("https://www.drudgereport.com", timeout=15, headers={
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml',
            'Accept-Language': 'en-US,en;q=0.9',
        })
        r.raise_for_status()
        soup = BeautifulSoup(r.text, 'html.parser')
        links = []
        seen_texts = set()
        for a in soup.find_all('a', href=True):
            href = a.get('href', '')
            text = a.get_text(strip=True)
            # Skip navigation, drudge self-links, and short/empty text
            if not text or len(text) < 15: continue
            if 'drudgereport.com' in href: continue
            if href.startswith('mailto:'): continue
            if href.startswith('javascript:'): continue
            norm = text.lower()
            if norm in seen_texts: continue
            seen_texts.add(norm)
            links.append({"title": text, "link": href})
            if len(links) >= 12: break
        if links:
            _DRUDGE_CACHE = {"data": links, "fetched_at": now}
            print(f"  Drudge: {len(links)} links scraped")
        return _DRUDGE_CACHE["data"]
    except Exception as ex:
        print(f"  Drudge scrape error: {ex}")
        return _DRUDGE_CACHE["data"]


_SITE_NAV_TERMS = {
    'about','contact','feedback','terms','privacy','home','search','login','signup',
    'subscribe','newsletter','advertise','careers','help','faq','sitemap',
    'gumroad','youtube trending videos','x (twitter)',
}

def fetch_twitter_trends():
    """Scrape US Twitter/X trending topics from trends24.in."""
    global _TWITTER_CACHE
    now = time.time()
    if _TWITTER_CACHE["data"] and now - _TWITTER_CACHE["fetched_at"] < 1800:
        return _TWITTER_CACHE["data"]
    if not HAS_SCRAPE:
        return _TWITTER_CACHE["data"]
    try:
        r = requests.get("https://trends24.in/united-states/", timeout=15, headers={
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml',
            'Accept-Language': 'en-US,en;q=0.9',
        })
        r.raise_for_status()
        soup = BeautifulSoup(r.text, 'html.parser')
        trends = []
        seen = set()
        # Target only the first trend card (most current hour) ordered list
        for card in soup.select('.trend-card'):
            for li in card.select('ol li a, .trend-card__list li a'):
                text = li.get_text(strip=True)
                if not text or len(text) < 2: continue
                # Filter out site navigation links that bleed into the scrape
                if text.lower() in _SITE_NAV_TERMS: continue
                if text.lower() in seen: continue
                seen.add(text.lower())
                trends.append(text)
            if len(trends) >= 25: break
        if trends:
            _TWITTER_CACHE = {"data": trends[:25], "fetched_at": now}
            print(f"  Twitter/X trends: {len(trends[:25])} trends scraped")
        return _TWITTER_CACHE["data"]
    except Exception as ex:
        print(f"  Twitter trends scrape error: {ex}")
        return _TWITTER_CACHE["data"]


def fetch_reddit_trending():
    """Fetch hot posts from r/Conservative via Reddit's free public JSON API.
    Strong signal for what the conservative 25-65 audience is actively reading.
    No API key required — Reddit's public JSON endpoints are open."""
    global _REDDIT_CACHE
    now = time.time()
    if _REDDIT_CACHE["data"] and now - _REDDIT_CACHE["fetched_at"] < 1800:
        return _REDDIT_CACHE["data"]
    if not HAS_SCRAPE:
        return _REDDIT_CACHE["data"]
    try:
        r = requests.get(
            "https://www.reddit.com/r/Conservative/hot.json?limit=25",
            timeout=15,
            headers={'User-Agent': 'WhatsTrendingInRealTime/1.0 (editorial dashboard)'},
        )
        r.raise_for_status()
        data = r.json()
        posts = []
        for child in data.get("data", {}).get("children", []):
            p = child.get("data", {})
            if p.get("stickied"): continue  # skip pinned mod posts
            title = p.get("title", "").strip()
            url   = p.get("url", "#")
            score = p.get("score", 0)
            num_comments = p.get("num_comments", 0)
            if title:
                posts.append({"title": title, "link": url,
                              "score": score, "comments": num_comments})
        if posts:
            _REDDIT_CACHE = {"data": posts[:20], "fetched_at": now}
            print(f"  Reddit r/Conservative: {len(posts[:20])} posts")
        return _REDDIT_CACHE["data"]
    except Exception as ex:
        print(f"  Reddit fetch error: {ex}")
        return _REDDIT_CACHE["data"]


def extract_keywords(title):
    words = re.findall(r"[A-Za-z']+", title.lower())
    filtered = [w for w in words if w not in STOP_WORDS and len(w)>3]
    proper = [p.lower() for p in re.findall(r'\b[A-Z][a-z]{2,}\b', title) if p.lower() not in STOP_WORDS and len(p)>3]
    seen,result = set(),[]
    for w in filtered+proper:
        if w not in seen: seen.add(w); result.append(w)
    return result

def best_label(kw, articles):
    """Find the best 2-3 word proper noun label for a cluster keyword."""
    phrases = defaultdict(int)
    for art in articles:
        words = re.findall(r'\b[A-Z][a-z]{1,}\b', art["title"])
        lowers = [w.lower() for w in words]
        for i, lw in enumerate(lowers):
            if lw == kw:
                if i > 0:
                    two = f"{words[i-1]} {words[i]}"
                    phrases[two] += 1
                if i < len(words)-1:
                    two = f"{words[i]} {words[i+1]}"
                    phrases[two] += 1
                if i > 0 and i < len(words)-1:
                    three = f"{words[i-1]} {words[i]} {words[i+1]}"
                    phrases[three] += 1
    if phrases:
        return max(phrases.items(), key=lambda x: (x[1], len(x[0])))[0]
    return kw.title()

def cluster_topics(all_arts):
    # Flatten articles
    flat = []
    for sid, arts in all_arts.items():
        for art in arts:
            flat.append({**art, "source_id": sid})
    if not flat:
        return []

    # Extract keywords per article
    art_kws = [(art, set(extract_keywords(art["title"]))) for art in flat]

    # Count how many articles mention each keyword
    kw_freq = defaultdict(int)
    for _, kws in art_kws:
        for kw in kws:
            kw_freq[kw] += 1

    # KEY FIX: words appearing in >10% of all articles are "generic connective
    # tissue" (trump, biden, president, american) — not story anchors.
    # Filter them out so each cluster represents ONE specific story, not
    # "everything that mentions Trump."
    max_freq = max(4, len(flat) * 0.10)

    # Build index of specific keywords only
    spec_idx = defaultdict(list)
    for art, kws in art_kws:
        for kw in kws:
            if kw_freq[kw] <= max_freq:
                spec_idx[kw].append(art)

    # Source diversity per keyword
    kw_srcs = {kw: set(a["source_id"] for a in arts) for kw, arts in spec_idx.items()}

    # Require 2+ sources OR 3+ articles to surface a cluster
    hot = {kw for kw, srcs in kw_srcs.items()
           if len(srcs) >= 2 or len(spec_idx[kw]) >= 3}

    sorted_kws = sorted(hot, key=lambda kw: (-len(kw_srcs[kw]), -len(spec_idx[kw])))

    used, clusters = set(), []
    tier1 = {s["id"] for s in SOURCES if s["tier"]==1}

    for kw in sorted_kws[:60]:
        cl_arts, cl_srcs = [], set()
        for art in spec_idx[kw]:
            k = (art["source_id"], art["title"])
            if k not in used:
                cl_arts.append(art); cl_srcs.add(art["source_id"]); used.add(k)
        if len(cl_arts) < 2:
            continue

        # --- Cluster coherence check ---
        # Articles should share more than just the seed keyword.
        # Build a frequency map of all keywords across cluster articles.
        cl_kw_freq = defaultdict(int)
        for a in cl_arts:
            for w in extract_keywords(a["title"]):
                if w != kw: cl_kw_freq[w] += 1
        # Count secondary keywords shared by 2+ articles (beyond the seed)
        secondary_shared = sum(1 for w, cnt in cl_kw_freq.items() if cnt >= 2)
        # Weak cluster: only 1 source and no secondary shared keywords
        # → require 3+ articles before surfacing (stricter threshold)
        if secondary_shared == 0 and len(cl_srcs) < 2:
            continue
        # Very weak cluster: multiple sources but ZERO secondary shared keywords
        # → likely a false cluster like the old "Security" bug; require 3+ sources
        if secondary_shared == 0 and len(cl_srcs) < 3:
            continue

        t1 = [a for a in cl_arts if a["source_id"] in tier1]
        best = (t1 or cl_arts)[0]
        label = best_label(kw, cl_arts)
        src_count = len(cl_srcs)
        # Hero boost: count how many outlets placed this as their #1 or #2 story
        # Hero: RSS position 0-1, OR scrape-confirmed (appeared on homepage), or BOTH
        hero_set = set()
        for a in cl_arts:
            is_rss_hero    = a.get("feed_position", 99) <= 1
            is_scrape_hero = a.get("scrape_confirmed", False)
            if is_rss_hero or is_scrape_hero:
                hero_set.add(a["source_id"])
        hero_sources = list(hero_set)
        hero_count = len(hero_set)
        # Double-confirmed (both RSS position AND scraped) = extra +10 per outlet
        double_confirmed = sum(
            1 for a in cl_arts
            if a.get("feed_position", 99) <= 1 and a.get("scrape_confirmed", False)
            and cl_arts.index(a) == next((i for i,x in enumerate(cl_arts) if x is a), 0)
        )
        # Each hero placement = +20 bonus; double-confirmed = +10 extra
        heat = src_count * 12 + len(cl_arts) + (hero_count * 20) + (double_confirmed * 10)

        # Story age: derived from the most recently published article in the cluster
        now_utc = datetime.now(timezone.utc)
        pub_times = [datetime.fromisoformat(a["pub_ts"]) for a in cl_arts if a.get("pub_ts")]
        if pub_times:
            newest = max(pub_times)
            age_minutes = int((now_utc - newest).total_seconds() / 60)
        else:
            age_minutes = None
        is_breaking = age_minutes is not None and age_minutes < 90

        clusters.append({"keyword": label, "topic": best["title"],
                         "articles": cl_arts[:10], "sources": list(cl_srcs),
                         "source_count": src_count, "article_count": len(cl_arts),
                         "heat_score": heat, "hero_sources": hero_sources,
                         "age_minutes": age_minutes, "is_breaking": is_breaking})

    clusters.sort(key=lambda x: -x["heat_score"])
    return clusters[:20]

def compute_alignment(all_arts, topics):
    dw_all = all_arts.get("dailywire", [])
    # Only count DW articles published in the last 12 hours as "covering" a topic.
    # 6 hours was too tight — a 7h-old story is still same-day news for a daily
    # editorial cycle. 12 hours prevents yesterday's coverage from suppressing today's
    # DW Gap badge while still catching genuine same-day assignment opportunities.
    twelve_hours_ago = datetime.now(timezone.utc) - timedelta(hours=12)
    dw = [a for a in dw_all if a.get("pub_ts") and
          datetime.fromisoformat(a["pub_ts"]) > twelve_hours_ago]
    if not dw:
        dw = dw_all  # fall back to all articles if feed has no timestamps (weekend lull)
    dw_kws = set()
    if dw:
        for a in dw: dw_kws.update(extract_keywords(a["title"]))

    def dw_covers(topic):
        """True if Daily Wire is covering this topic cluster.
        Checks ALL keywords from ALL articles in the cluster — not just the label.
        This prevents false gaps when DW uses different framing than the cluster seed."""
        # Gather every keyword from every article in the cluster
        cluster_kws = set()
        for a in topic.get("articles", []):
            cluster_kws.update(extract_keywords(a["title"]))
        # Also check the display label parts
        for w in topic["keyword"].lower().split():
            if len(w) > 3: cluster_kws.add(w)
        # DW covers it if they share ANY specific keyword with the cluster
        shared = cluster_kws & dw_kws
        if shared: return True, shared
        # Fallback: substring match on DW article titles
        for a in dw:
            for kw in cluster_kws:
                if len(kw) > 4 and kw in a["title"].lower():
                    return True, {kw}
        return False, set()

    top10, covered, details = topics[:10], 0, []
    covered_set = set()
    for t in top10:
        ok, matched_kws = dw_covers(t)
        covered += int(ok)
        if ok: covered_set.add(t["keyword"])
        match = next((a["title"] for a in dw
                      if any(kw in a["title"].lower() for kw in matched_kws)), None) if matched_kws else None
        details.append({"topic":t["keyword"],"covered":ok,"dw_article":match,"heat_score":t["heat_score"]})
    score = round(covered/len(top10)*100) if top10 else 0
    grade = "A" if score>=80 else "B" if score>=60 else "C" if score>=40 else "D"
    # Attach coverage flag to ALL topics (not just top 10)
    for t in topics:
        ok, _ = dw_covers(t)
        t["dw_covered"] = ok
    return {"score":score,"grade":grade,"covered":covered,"total":len(top10),"details":details,"covered_set":list(covered_set)}

def refresh_data():
    ts = datetime.now().strftime('%H:%M:%S')
    print(f"\n[{ts}] Fetching {len(SOURCES)} sources + Google Trends + homepage scrapes...")
    all_arts = {}
    # Run RSS fetch + homepage scraping concurrently
    with ThreadPoolExecutor(max_workers=20) as ex:
        rss_futures  = {ex.submit(fetch_source, s): s for s in SOURCES}
        scrape_futures = {ex.submit(scrape_homepage, sid, url): sid
                         for sid, url in SCRAPE_SOURCES.items()} if HAS_SCRAPE else {}
        for f in as_completed(rss_futures):
            sid, arts = f.result()
            if arts: all_arts[sid]=arts; print(f"  ✓ {sid}: {len(arts)}")
            else: print(f"  ✗ {sid}: no data")
        scraped_headlines = {}  # sid → frozenset of normalized headline strings
        for f in as_completed(scrape_futures):
            sid = scrape_futures[f]
            scraped_headlines[sid] = f.result()
            if scraped_headlines[sid]:
                print(f"  🔎 scraped {sid}: {len(scraped_headlines[sid])} headlines")

    # Cross-verify: mark articles that appear on the scraped homepage (double-confirmed heroes)
    if scraped_headlines:
        for sid, arts in all_arts.items():
            sc_set = scraped_headlines.get(sid, frozenset())
            if not sc_set: continue
            for art in arts:
                norm = art["title"].lower()
                # Fuzzy: check if any scraped headline contains or is contained in the title
                art["scrape_confirmed"] = any(
                    norm in h or h in norm or
                    # word-overlap ≥ 60% as a looser match
                    (len(norm.split()) >= 4 and
                     len(set(norm.split()) & set(h.split())) / max(len(norm.split()),1) >= 0.6)
                    for h in sc_set
                )

    print("  Fetching Drudge + Twitter/X + Reddit...")
    drudge_links   = fetch_drudge()
    twitter_trends = fetch_twitter_trends()
    reddit_posts   = fetch_reddit_trending()
    print(f"  {'✓' if drudge_links else '✗'} Drudge: {len(drudge_links)} links")
    print(f"  {'✓' if twitter_trends else '✗'} Twitter/X: {len(twitter_trends)} trends")
    print(f"  {'✓' if reddit_posts else '✗'} Reddit r/Conservative: {len(reddit_posts)} posts")
    topics = cluster_topics(all_arts)
    print(f"  → {len(topics)} trending topics")

    # Trajectory: compare heat scores to previous refresh
    global _prev_heat
    for t in topics:
        prev = _prev_heat.get(t["keyword"])
        t["delta"] = (t["heat_score"] - prev) if prev is not None else None
    _prev_heat = {t["keyword"]: t["heat_score"] for t in topics}

    srcs = {}
    for s in SOURCES:
        sid = s["id"]; li = LEAN.get(s["lean"],{"label":s["lean"],"color":"#374151"})
        srcs[sid]={**s,"lean_label":li["label"],"lean_color":li["color"],"articles":all_arts.get(sid,[])[:8],"status":"ok" if sid in all_arts else "error"}
    with data_lock:
        data_store.update({"last_updated":datetime.utcnow().isoformat()+"Z","sources":srcs,"trending_topics":topics,
                           "reddit_posts":reddit_posts,"twitter_trends":twitter_trends,"drudge_links":drudge_links,
                           "sources_live":len(all_arts),"loading":False})
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Done. {len(all_arts)}/{len(SOURCES)} live.\n")

def bg_loop(interval=1800):
    while True:
        try: refresh_data()
        except Exception as e: print(f"  Error: {e}"); data_store["loading"]=False
        time.sleep(interval)

app = Flask(__name__)

@app.route('/')
def index(): return HTML, 200, {'Content-Type':'text/html; charset=utf-8'}

@app.route('/api/data')
def api_data():
    with data_lock: return jsonify(data_store)

@app.route('/api/refresh', methods=['POST'])
def api_refresh():
    threading.Thread(target=refresh_data,daemon=True).start()
    return jsonify({"status":"ok"})

HTML = r"""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Editorial Intelligence — WhatsTrendingInRealTime.com</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Newsreader:opsz,wght@6..72,400;6..72,600;6..72,700&family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">
<link href="https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined:opsz,wght,FILL,GRAD@20,400,0,0" rel="stylesheet">
<style>
:root{
  --navy:#1A2744;--navy-d:#0d1b37;--white:#fff;
  --ink:#191c1e;--ink-m:#45464d;--ink-l:#75777e;
  --red:#BA032A;--green:#14532D;
  --surface:#f8f9fb;--surface-low:#f2f4f6;--surface-ctr:#eceef0;
  --surface-high:#e6e8ea;--surface-top:#e0e3e5;--surface-0:#ffffff;
  --border:#c5c6ce;--sh:rgba(13,27,55,.07);
}
*{margin:0;padding:0;box-sizing:border-box}html{scroll-behavior:smooth}
body{background:var(--surface);color:var(--ink);font-family:'Inter',system-ui,sans-serif;font-size:14px;line-height:1.5;min-height:100vh}
.ms{font-family:'Material Symbols Outlined';font-style:normal;font-weight:400;font-size:20px;line-height:1;letter-spacing:normal;text-transform:none;white-space:nowrap;display:inline-block;-webkit-font-smoothing:antialiased}

/* LOADING OVERLAY */
#ov{position:fixed;inset:0;background:var(--navy);display:flex;flex-direction:column;align-items:center;justify-content:center;z-index:9999;transition:opacity .5s}
#ov.h{opacity:0;pointer-events:none}
.spin{width:40px;height:40px;border:3px solid rgba(255,255,255,.15);border-top-color:#fff;border-radius:50%;animation:sp .85s linear infinite;margin-bottom:16px}
@keyframes sp{to{transform:rotate(360deg)}}
.ov-ttl{font-family:'Newsreader',Georgia,serif;font-size:22px;color:#fff;margin-bottom:6px}
.ov-sub{font-size:12px;color:rgba(255,255,255,.45)}

/* TOP HEADER */
.topbar{position:fixed;top:0;left:0;right:0;height:64px;z-index:100;display:flex;align-items:center;justify-content:space-between;padding:0 24px;background:#f8f9fb;border-bottom:1px solid var(--surface-top)}
.tb-left{display:flex;align-items:center;gap:32px}
.tb-brand{font-family:'Newsreader',Georgia,serif;font-size:20px;font-weight:700;color:var(--navy-d);letter-spacing:-.2px;white-space:nowrap}
.tb-nav{display:flex;align-items:center;height:64px}
.tnav{display:flex;align-items:center;height:64px;padding:0 14px;font-size:12px;font-weight:500;color:var(--ink-l);text-decoration:none;border-bottom:2px solid transparent;transition:color .15s}
.tnav.act{color:var(--red);font-weight:700;border-bottom-color:var(--red)}
.tnav:hover:not(.act){color:var(--navy-d)}
.tb-right{display:flex;align-items:center;gap:10px}
.live-pill{display:flex;align-items:center;gap:6px;padding:4px 12px;background:rgba(186,3,42,.08);border-radius:2px}
.live-dot{width:7px;height:7px;border-radius:50%;background:var(--red);animation:lp 2s infinite;box-shadow:0 0 8px rgba(186,3,42,.6)}
@keyframes lp{0%,100%{opacity:1}50%{opacity:.2}}
.live-txt{font-size:9px;font-weight:800;letter-spacing:2px;color:var(--red);text-transform:uppercase}
.tb-time{font-size:10px;color:var(--ink-l);font-variant-numeric:tabular-nums}
.icon-btn{width:36px;height:36px;display:flex;align-items:center;justify-content:center;border:none;background:none;cursor:pointer;border-radius:2px;color:var(--ink-m);transition:background .15s}
.icon-btn:hover{background:var(--surface-ctr)}

/* LEFT SIDEBAR */
.sidebar{position:fixed;top:64px;left:0;bottom:0;width:256px;z-index:90;display:flex;flex-direction:column;padding:16px;background:#f2f4f6;border-right:1px solid var(--surface-top);overflow-y:auto}
.sb-brand{display:flex;align-items:center;gap:12px;padding:8px;margin-bottom:24px}
.sb-icon{width:40px;height:40px;border-radius:2px;background:var(--navy);display:flex;align-items:center;justify-content:center;flex-shrink:0}
.sb-title{font-family:'Newsreader',Georgia,serif;font-size:17px;color:var(--navy-d);line-height:1.2}
.sb-sub{font-size:9px;color:var(--ink-l);text-transform:uppercase;letter-spacing:1.5px;margin-top:1px}
.sb-nav{display:flex;flex-direction:column;gap:2px;flex:1}
.sb-lnk{display:flex;align-items:center;gap:10px;padding:8px 12px;font-size:13px;font-weight:500;color:var(--ink-m);text-decoration:none;border-radius:4px;transition:all .15s}
.sb-lnk.act{background:#fff;color:var(--navy-d);font-weight:600;box-shadow:0 1px 3px var(--sh)}
.sb-lnk:hover:not(.act){background:rgba(0,0,0,.04);color:var(--ink)}
.sb-footer{border-top:1px solid var(--surface-top);padding-top:16px;margin-top:16px;display:flex;flex-direction:column;gap:2px}
.sb-btn{display:flex;align-items:center;justify-content:center;gap:8px;padding:10px;margin-bottom:8px;background:linear-gradient(180deg,var(--navy) 0%,#000 100%);color:#fff;border:none;border-radius:2px;cursor:pointer;font-size:13px;font-weight:700;font-family:'Inter',sans-serif;box-shadow:0 2px 8px rgba(0,0,0,.25);width:100%;transition:opacity .15s}
.sb-btn:hover{opacity:.9}
.sb-meta{padding:5px 12px;font-size:11px;color:var(--ink-l);display:flex;align-items:center;gap:6px}

/* MAIN CANVAS */
.main{margin-left:256px;margin-top:64px;padding:24px;min-height:calc(100vh - 64px)}
.cgrid{display:grid;grid-template-columns:1fr 320px;gap:24px;align-items:start}

/* SECTION HEADER */
.sec-hdr{display:flex;justify-content:space-between;align-items:flex-end;margin-bottom:16px}
.sec-title{font-family:'Newsreader',Georgia,serif;font-size:30px;font-weight:700;color:var(--navy-d);line-height:1.1}
.sec-sub{font-size:13px;color:var(--ink-l);margin-top:4px}
.bdg{padding:3px 8px;background:var(--surface-high);border-radius:2px;font-size:9px;font-weight:800;letter-spacing:.5px;font-family:'Inter',sans-serif;color:var(--ink-m)}

/* TRENDING TABLE */
.tbl-wrap{background:var(--surface-top);padding:2px;border-radius:3px;overflow:hidden;margin-bottom:28px}
.tbl-inner{background:var(--surface-0);border-radius:3px;overflow:hidden;box-shadow:0 1px 4px var(--sh)}
.topics-tbl{width:100%;border-collapse:collapse}
.topics-tbl thead th{padding:10px 16px;font-size:9px;font-weight:800;color:var(--ink-l);text-transform:uppercase;letter-spacing:1.5px;background:var(--surface-low);border-bottom:1px solid var(--surface-high);text-align:left;font-family:'Inter',sans-serif}
.topics-tbl thead th.tc{text-align:center}
.topics-tbl thead th.tr2{text-align:right}
.th-r{width:64px}.th-s{width:116px}.th-v{width:120px}.th-g{width:76px}
.t-row{cursor:pointer;transition:background .1s}
.t-row:hover td{background:rgba(0,0,0,.015)}
.t-row td{padding:16px;border-bottom:1px solid var(--surface-low);vertical-align:top}
.x-row{display:none}
.x-row.open{display:table-row}
.x-row td{padding:0;border-bottom:1px solid var(--surface-high)}
.rn{font-family:'Newsreader',Georgia,serif;font-size:22px;font-weight:700;text-align:center;display:block}
.rn-h{color:var(--red)}.rn-n{color:var(--ink-l)}
.t-hl{font-family:'Newsreader',Georgia,serif;font-size:16px;font-weight:700;line-height:1.35;color:var(--ink);margin-bottom:6px}
.t-st{font-size:11px;color:var(--ink-m);margin-bottom:8px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;font-family:'Inter',sans-serif}
.t-tags{display:flex;align-items:center;gap:5px;flex-wrap:wrap}
.tag{padding:2px 7px;background:var(--surface-high);border-radius:2px;font-size:9px;font-weight:700;text-transform:uppercase;letter-spacing:.4px;font-family:'Inter',sans-serif;color:var(--ink-m)}
.tag.brk{background:rgba(186,3,42,.1);color:var(--red);animation:lp 1.5s infinite}
.tag.age{background:var(--surface-low);color:var(--ink-l);border:1px solid var(--surface-high)}
.tag.lead{background:var(--navy);color:#fff}
.chips{display:flex;gap:3px;flex-wrap:wrap}
.chip{width:26px;height:22px;border-radius:2px;display:flex;align-items:center;justify-content:center;font-size:7px;font-weight:800;color:#fff;font-family:'Inter',sans-serif;flex-shrink:0}
.chip.hero{outline:2px solid var(--navy);outline-offset:1px}
.sig-n{font-family:'Newsreader',Georgia,serif;font-size:22px;font-weight:700;text-align:right;color:var(--ink);display:block}
.sig-d{font-size:10px;font-weight:700;text-align:right;font-family:'Inter',sans-serif;display:block;margin-top:1px}
.ei-c{font-size:10px;color:var(--ink-l);display:block;text-align:right;margin-top:3px}
.x-inner{padding:8px 16px 8px 80px;background:var(--surface-low)}
.a-row{padding:6px 0;border-bottom:1px solid var(--surface-high);font-size:12px}
.a-row:last-child{border-bottom:none}
.a-src{font-size:9px;font-weight:700;text-transform:uppercase;letter-spacing:.5px;color:var(--ink-l);font-family:'Inter',sans-serif;margin-bottom:2px}
.a-row a{font-family:'Newsreader',Georgia,serif;color:var(--navy-d);text-decoration:none}
.a-row a:hover{color:var(--red);text-decoration:underline}
.a-hero{border-left:3px solid var(--navy);padding-left:8px;margin-left:-8px;background:rgba(13,27,55,.03)}

/* LIVE SOURCE FEED */
.feed-hdr{display:flex;align-items:center;gap:12px;margin-bottom:14px}
.feed-hdr h3{font-family:'Newsreader',Georgia,serif;font-size:20px;font-weight:700;color:var(--ink);white-space:nowrap}
.feed-div{height:1px;flex:1;background:var(--surface-high)}
.src-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:10px}
.sc{background:var(--surface-0);border:1px solid var(--surface-high);border-top:3px solid;border-radius:3px;overflow:hidden}
.sc-hd{padding:8px 12px;border-bottom:1px solid var(--surface-low);display:flex;align-items:center;justify-content:space-between}
.sc-nm{font-size:10px;font-weight:800;text-transform:uppercase;letter-spacing:.8px;font-family:'Inter',sans-serif;color:var(--ink)}
.sc-ln{font-size:8px;font-weight:700;padding:2px 6px;border-radius:2px;font-family:'Inter',sans-serif}
.sc-art{padding:7px 12px;border-bottom:1px solid var(--surface-low);font-size:12px;line-height:1.45}
.sc-art:last-child{border-bottom:none}
.sc-art a{font-family:'Newsreader',Georgia,serif;color:var(--ink);text-decoration:none}
.sc-art a:hover{color:var(--red);text-decoration:underline}
.sc-empty{padding:16px 12px;font-size:12px;color:var(--ink-l);font-style:italic;font-family:'Newsreader',Georgia,serif}

/* RIGHT PANEL */
.panel{background:var(--surface-ctr);border:1px solid rgba(0,0,0,.05);border-radius:3px;overflow:hidden}
.panel-hd{padding:14px 16px;border-bottom:1px solid var(--surface-high);display:flex;align-items:center;gap:8px}
.panel-hd h3{font-family:'Newsreader',Georgia,serif;font-size:18px;font-weight:700}
.stabs{display:flex;border-bottom:2px solid var(--navy);background:var(--surface-0)}
.stab{flex:1;padding:9px 4px;font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.7px;color:var(--ink-l);text-align:center;cursor:pointer;border:none;background:none;transition:all .15s;border-bottom:3px solid transparent;margin-bottom:-2px;font-family:'Inter',sans-serif;display:flex;align-items:center;justify-content:center;gap:4px}
.stab.active{color:var(--navy-d);border-bottom-color:var(--red)}
.stab:hover:not(.active){color:var(--ink);background:rgba(0,0,0,.03)}
.spanel{display:none}.spanel.active{display:block}
.si{padding:10px 14px;border-bottom:1px solid var(--surface-high)}
.si:last-child{border-bottom:none}
.si a{font-family:'Newsreader',Georgia,serif;color:var(--navy-d);text-decoration:none;font-size:13px;line-height:1.4;display:block}
.si a:hover{color:var(--red);text-decoration:underline}
.si-m{font-size:10px;color:var(--ink-l);margin-top:3px;font-family:'Inter',sans-serif}
.tw-r{display:flex;align-items:center;gap:10px;padding:8px 14px;border-bottom:1px solid var(--surface-high)}
.tw-r:last-child{border-bottom:none}
.tw-rk{font-family:'Newsreader',Georgia,serif;font-size:13px;font-weight:700;color:var(--red);width:20px;flex-shrink:0}
.tw-tm{flex:1;font-family:'Inter',sans-serif;font-size:12px;color:var(--ink)}
.tw-bw{width:32px;flex-shrink:0}
.tw-bg{height:3px;background:var(--surface-high);border-radius:2px}
.tw-bf{height:3px;border-radius:2px;background:#1DA1F2}

/* FAB */
.fab{position:fixed;bottom:24px;right:24px;z-index:80;width:56px;height:56px;border-radius:3px;background:linear-gradient(180deg,var(--navy) 0%,#000 100%);color:#fff;border:none;cursor:pointer;display:flex;align-items:center;justify-content:center;box-shadow:0 4px 16px rgba(0,0,0,.3);transition:transform .15s}
.fab:hover{transform:scale(1.05)}

@media(max-width:1024px){.sidebar{display:none}.main{margin-left:0}}
@media(max-width:900px){.cgrid{grid-template-columns:1fr}.tb-nav{display:none}}
</style></head><body>

<div id="ov"><div class="spin"></div><div class="ov-ttl">WhatsTrendingInRealTime.com</div><div class="ov-sub">Scanning 15 sources · Building intelligence report…</div></div>

<header class="topbar">
  <div class="tb-left">
    <span class="tb-brand">Editorial Intelligence</span>
    <nav class="tb-nav">
      <a href="#" class="tnav act">Dashboard</a>
      <a href="#" class="tnav">Analytics</a>
      <a href="#" class="tnav">Reports</a>
      <a href="#" class="tnav">Archives</a>
    </nav>
  </div>
  <div class="tb-right">
    <div class="live-pill"><span class="live-dot"></span><span class="live-txt">Live</span></div>
    <span class="tb-time" id="cd"></span>
    <button class="icon-btn" title="Notifications"><span class="ms">notifications</span></button>
    <button class="icon-btn" title="Account"><span class="ms">account_circle</span></button>
  </div>
</header>

<aside class="sidebar">
  <div class="sb-brand">
    <div class="sb-icon"><span class="ms" style="color:#fff;font-size:22px">psychology</span></div>
    <div><div class="sb-title">Intelligence Ops</div><div class="sb-sub">Global Newsroom</div></div>
  </div>
  <nav class="sb-nav">
    <a href="#" class="sb-lnk act"><span class="ms">local_fire_department</span><span>Topic Intelligence</span></a>
    <a href="#" class="sb-lnk"><span class="ms">article</span><span>Source Analysis</span></a>
    <a href="#" class="sb-lnk"><span class="ms">speed</span><span>Social Velocity</span></a>
    <a href="#" class="sb-lnk"><span class="ms">settings</span><span>Settings</span></a>
  </nav>
  <div class="sb-footer">
    <button class="sb-btn" onclick="fr()"><span class="ms" style="font-size:16px">refresh</span>Refresh Now</button>
    <div class="sb-meta"><span class="ms" style="font-size:16px">sensors</span><span id="sc2">Loading…</span></div>
    <div class="sb-meta"><span class="ms" style="font-size:16px">schedule</span><span id="lu">—</span></div>
  </div>
</aside>

<main class="main">
  <div class="cgrid">
    <section>
      <div class="sec-hdr">
        <div>
          <h2 class="sec-title">Top Trending Topics</h2>
          <p class="sec-sub">Priority ranked by cross-source heat score · Click any row to expand</p>
        </div>
        <div style="display:flex;align-items:center;gap:10px">
          <span id="ed" style="font-size:11px;color:var(--ink-l);font-family:'Newsreader',Georgia,serif;font-style:italic"></span>
          <span class="bdg">24H RANGE</span>
        </div>
      </div>
      <div class="tbl-wrap">
        <div class="tbl-inner">
          <table class="topics-tbl">
            <thead>
              <tr>
                <th class="th-r tc">Rank</th>
                <th>Headline Intelligence</th>
                <th class="th-s">Sources</th>
                <th class="th-v">Velocity</th>
                <th class="th-g tr2">Signal</th>
              </tr>
            </thead>
            <tbody id="tl"><tr><td colspan="5" style="padding:32px;text-align:center;color:var(--ink-l)">Loading intelligence…</td></tr></tbody>
          </table>
        </div>
      </div>
      <div class="feed-hdr">
        <h3>Live Source Feed</h3>
        <div class="feed-div"></div>
        <span style="font-size:11px;color:var(--ink-l);white-space:nowrap" id="es">—</span>
      </div>
      <div class="src-grid" id="sg"></div>
    </section>
    <aside>
      <div class="panel">
        <div class="panel-hd"><span class="ms" style="color:var(--red)">trending_up</span><h3>Social Velocity</h3></div>
        <div class="stabs">
          <button class="stab active" onclick="switchTab('dr')"><span class="ms" style="font-size:14px">campaign</span>Drudge</button>
          <button class="stab" onclick="switchTab('tw')"><span class="ms" style="font-size:14px">tag</span>Twitter</button>
          <button class="stab" onclick="switchTab('rd')"><span class="ms" style="font-size:14px">forum</span>Reddit</button>
        </div>
        <div id="sp-dr" class="spanel active"><div id="dl"><div style="padding:16px;text-align:center;color:var(--ink-l);font-size:12px">Loading…</div></div></div>
        <div id="sp-tw" class="spanel"><div id="tl2"><div style="padding:16px;text-align:center;color:var(--ink-l);font-size:12px">Loading…</div></div></div>
        <div id="sp-rd" class="spanel"><div id="rl"><div style="padding:16px;text-align:center;color:var(--ink-l);font-size:12px">Loading…</div></div></div>
      </div>
    </aside>
  </div>
</main>

<button class="fab" onclick="fr()" title="Refresh data"><span class="ms" style="font-size:24px">refresh</span></button>

<script>
const SO=['foxnews','nypost','dailywire','breitbart','washtimes','townhall','ap','reuters','thehill','skynews','cnn','nytimes','nbcnews','dailymail','foxbusiness'];
const SA={foxnews:'FOX',cnn:'CNN',nytimes:'NYT',dailymail:'DM',nypost:'NYP',ap:'AP',reuters:'REU',nbcnews:'NBC',dailywire:'DW',breitbart:'BB',skynews:'SKY',thehill:'HILL',washtimes:'WT',foxbusiness:'FOXB',townhall:'TH'};
let _n=Date.now()+30*60*1000,_lastTs=null;
function e(s){return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;')}
function ta(iso){if(!iso)return'';const d=Math.floor((Date.now()-new Date(iso))/1000);if(d<60)return d+'s ago';if(d<3600)return Math.floor(d/60)+'m ago';return Math.floor(d/3600)+'h ago'}
function fc(ms){if(ms<=0)return'Refreshing…';const m=Math.floor(ms/60000),s=Math.floor((ms%60000)/1000);return m+':'+String(s).padStart(2,'0')+' Refresh'}
function spark(delta,heat){
  const w=88,h=32;
  if(delta===null||delta===undefined){
    return '<svg width="'+w+'" height="'+h+'" viewBox="0 0 '+w+' '+h+'"><path d="M0 16 L'+w+' 16" stroke="#c5c6ce" stroke-width="1.5" fill="none"/></svg>';
  }
  if(delta>0){
    const rise=Math.min(delta/(heat||1)*160,24);
    const p='M0 '+(h-4)+' L22 '+(h-4-rise*.25)+' L44 '+(h-4-rise*.55)+' L66 '+(h-4-rise*.82)+' L'+w+' '+Math.max(4,h-4-rise);
    return '<svg width="'+w+'" height="'+h+'" viewBox="0 0 '+w+' '+h+'"><path d="'+p+'" stroke="#BA032A" stroke-width="2.5" fill="none" stroke-linecap="round" stroke-linejoin="round"/></svg>';
  }
  const drop=Math.min(Math.abs(delta)/(heat||1)*160,24);
  const p='M0 4 L22 '+(4+drop*.25)+' L44 '+(4+drop*.55)+' L66 '+(4+drop*.82)+' L'+w+' '+Math.min(h-4,4+drop);
  return '<svg width="'+w+'" height="'+h+'" viewBox="0 0 '+w+' '+h+'"><path d="'+p+'" stroke="#c5c6ce" stroke-width="1.5" fill="none" stroke-linecap="round" stroke-linejoin="round"/></svg>';
}
function rT(topics){
  const tb=document.getElementById('tl');
  if(!topics||!topics.length){tb.innerHTML='<tr><td colspan="5" style="padding:32px;text-align:center;color:var(--ink-l)">No trending topics yet.</td></tr>';return}
  tb.innerHTML=topics.map((t,i)=>{
    const hot=i<3,heroSrcs=new Set(t.hero_sources||[]);
    const chips=(t.sources||[]).map(s=>{
      const isH=heroSrcs.has(s),col=(window._L||{})[s]||'#6B7280',abbr=SA[s]||(s.slice(0,3).toUpperCase());
      return '<div class="chip'+(isH?' hero':'')+'" style="background:'+col+'" title="'+e(s)+(isH?' \u2014 Lead':'')+'">'+e(abbr)+'</div>';
    }).join('');
    const brkBadge=t.is_breaking?'<span class="tag brk">Breaking</span>':'';
    const am=t.age_minutes;
    const ageBadge=(!t.is_breaking&&am!=null)?'<span class="tag age">'+(am<60?am+'m':Math.floor(am/60)+'h')+'</span>':'';
    const leadBadge=heroSrcs.size>0?'<span class="tag lead">Lead at '+heroSrcs.size+(heroSrcs.size>1?' outlets':' outlet')+'</span>':'';
    const d=t.delta;
    const dh=d===null||d===undefined?'':d>0?'<span class="sig-d" style="color:#15803D">\u25b2'+d+'</span>':d<0?'<span class="sig-d" style="color:#BA032A">\u25bc'+Math.abs(d)+'</span>':'<span class="sig-d" style="color:#9CA3AF">\u2014</span>';
    const arts=(t.articles||[]).map(a=>{
      const isH=a.feed_position===0||a.feed_position===1,isS=a.scrape_confirmed===true;
      const mark=isH&&isS?' \u2605\u2713':isH?' \u2605':isS?' \u2713':'';
      const age=a.pub_ts?' <span style="color:var(--ink-l);font-size:10px">'+ta(a.pub_ts)+'</span>':'';
      return '<div class="a-row'+(isH||isS?' a-hero':'')+'"><div class="a-src">'+e(a.source_id)+mark+age+'</div><a href="'+e(a.link)+'" target="_blank" onclick="event.stopPropagation()">'+e(a.title)+'</a></div>';
    }).join('');
    const rn=(i<9?'0':'')+(i+1);
    return '<tr class="t-row" onclick="tg('+i+')">'
      +'<td><span class="rn '+(hot?'rn-h':'rn-n')+'">'+rn+'</span></td>'
      +'<td><div class="t-hl">'+e(t.keyword)+'</div><div class="t-st">'+e(t.topic)+'</div><div class="t-tags">'+brkBadge+ageBadge+leadBadge+'</div></td>'
      +'<td><div class="chips">'+chips+'</div></td>'
      +'<td>'+spark(t.delta,t.heat_score)+'</td>'
      +'<td><span class="sig-n">'+t.heat_score+'</span>'+dh+'<span class="ei-c" id="ei'+i+'">\u25b8</span></td>'
      +'</tr>'
      +'<tr id="ta'+i+'" class="x-row"><td colspan="5"><div class="x-inner">'+arts+'</div></td></tr>';
  }).join('');
}
function tg(i){
  const row=document.getElementById('ta'+i),icon=document.getElementById('ei'+i);
  icon.textContent=row.classList.toggle('open')?'\u25be':'\u25b8';
}
let _activeTab='dr';
function switchTab(tab){
  _activeTab=tab;
  document.querySelectorAll('.stab').forEach((b,i)=>{b.classList.toggle('active',['dr','tw','rd'][i]===tab)});
  document.querySelectorAll('.spanel').forEach((p,i)=>{p.classList.toggle('active',['sp-dr','sp-tw','sp-rd'][i]==='sp-'+tab)});
}
function rG(posts){
  const el=document.getElementById('rl');
  if(!posts||!posts.length){el.innerHTML='<div style="padding:16px;text-align:center;color:var(--ink-l);font-size:12px">r/Conservative unavailable</div>';return}
  el.innerHTML=posts.map(p=>{
    const sc=p.score>999?(p.score/1000).toFixed(1)+'k':p.score;
    return '<div class="si"><a href="'+e(p.link)+'" target="_blank">'+e(p.title)+'</a><div class="si-m">\u25b2'+sc+' \u00b7 '+p.comments+' comments</div></div>';
  }).join('');
}
function rTw(trends){
  const el=document.getElementById('tl2');
  if(!trends||!trends.length){el.innerHTML='<div style="padding:16px;text-align:center;color:var(--ink-l);font-size:12px">Twitter/X trends unavailable</div>';return}
  el.innerHTML=trends.slice(0,25).map((t,i)=>'<div class="tw-r"><span class="tw-rk">'+(i+1)+'</span><span class="tw-tm">'+e(t)+'</span><div class="tw-bw"><div class="tw-bg"><div class="tw-bf" style="width:'+Math.round(((25-i)/25)*100)+'%"></div></div></div></div>').join('');
}
function rDr(links){
  const el=document.getElementById('dl');
  if(!links||!links.length){el.innerHTML='<div style="padding:16px;text-align:center;color:var(--ink-l);font-size:12px">Drudge unavailable</div>';return}
  el.innerHTML=links.map(l=>'<div class="si"><a href="'+e(l.link)+'" target="_blank">'+e(l.title)+'</a></div>').join('');
}
function rS(srcs){
  if(!srcs)return;
  window._L={};Object.entries(srcs).forEach(([id,s])=>window._L[id]=s.lean_color);
  const ord=[...SO.filter(id=>srcs[id]),...Object.keys(srcs).filter(id=>!SO.includes(id))];
  document.getElementById('sg').innerHTML=ord.map(sid=>{
    const s=srcs[sid];if(!s)return'';
    const arts=s.articles||[];
    return '<div class="sc" style="border-top-color:'+e(s.lean_color)+'">'
      +'<div class="sc-hd"><span class="sc-nm">'+e(s.name)+'</span>'
      +'<span class="sc-ln" style="background:'+e(s.lean_color)+'18;color:'+e(s.lean_color)+'">'+e(s.lean_label)+'</span></div>'
      +(arts.length?arts.map(a=>'<div class="sc-art"><a href="'+e(a.link)+'" target="_blank">'+e(a.title)+'</a></div>').join(''):'<div class="sc-empty">Feed unavailable</div>')
      +'</div>';
  }).join('');
}
async function ld(){
  try{
    const d=await(await fetch('/api/data')).json();
    if(d.loading){setTimeout(ld,3000);return}
    document.getElementById('ov').classList.add('h');
    document.getElementById('sc2').textContent=(d.sources_live||0)+' sources live';
    document.getElementById('lu').textContent=d.last_updated?'Updated '+ta(d.last_updated):'—';
    const now=new Date();
    document.getElementById('ed').textContent=now.toLocaleDateString('en-US',{weekday:'long',year:'numeric',month:'long',day:'numeric'});
    document.getElementById('es').textContent=(d.sources_live||0)+' of 15 reporting';
    if(d.last_updated){const sn=new Date(d.last_updated).getTime()+30*60*1000;if(sn>Date.now())_n=sn;}
    if(d.last_updated!==_lastTs){
      _lastTs=d.last_updated;
      rT(d.trending_topics);rG(d.reddit_posts);rTw(d.twitter_trends);rDr(d.drudge_links);rS(d.sources);
    }
  }catch(ex){setTimeout(ld,5000)}
}
async function fr(){
  document.getElementById('ov').classList.remove('h');
  try{await fetch('/api/refresh',{method:'POST'})}catch(ex){}
  _n=Date.now()+30*60*1000;_lastTs=null;setTimeout(ld,3000);
}
setInterval(()=>{const r=_n-Date.now();document.getElementById('cd').textContent=fc(r);if(r<=0){_n=Date.now()+30*60*1000;ld()}},1000);
setInterval(ld,2*60*1000);
ld();
</script></body></html>"""


if __name__=='__main__':
    PORT=int(os.environ.get('PORT',8080))
    IS_LOCAL=PORT==8080
    print("\n"+"="*60+"\n  WhatsTrendingInRealTime.com — Editorial Dashboard v2\n"+"="*60)
    print(f"\n  URL: http://localhost:{PORT}  |  {len(SOURCES)} sources  |  Ctrl+C to stop\n")
    threading.Thread(target=bg_loop,args=(1800,),daemon=True).start()
    if IS_LOCAL:
        threading.Timer(2.0,lambda:webbrowser.open(f'http://localhost:{PORT}')).start()
    app.run(host='0.0.0.0',port=PORT,debug=False,threaded=True,use_reloader=False)
