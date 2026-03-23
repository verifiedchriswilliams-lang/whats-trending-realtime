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
<title>WhatsTrendingInRealTime.com</title>
<style>
:root{--linen:#F4F0E8;--linen-d:#EAE4D6;--linen-dd:#D6CCBA;--white:#FFF;--navy:#1A2744;--ink:#111827;--ink-m:#374151;--ink-l:#6B7280;--red:#C41230;--green:#14532D;--border:#CEC6B2;--border-l:#E2DAC8;--sh:rgba(26,39,68,.07)}
*{margin:0;padding:0;box-sizing:border-box}html{scroll-behavior:smooth}
body{background:var(--linen);color:var(--ink);font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;font-size:14px;line-height:1.5;min-height:100vh}
#ov{position:fixed;inset:0;background:var(--navy);display:flex;flex-direction:column;align-items:center;justify-content:center;z-index:9999;transition:opacity .5s}
#ov.h{opacity:0;pointer-events:none}
.sp{width:40px;height:40px;border:3px solid rgba(255,255,255,.15);border-top-color:#fff;border-radius:50%;animation:sp .85s linear infinite;margin-bottom:16px}
@keyframes sp{to{transform:rotate(360deg)}}
.lt{font-family:Georgia,serif;font-size:20px;color:#fff;margin-bottom:6px}.ls{font-size:13px;color:rgba(255,255,255,.45)}
.mast{background:var(--navy);border-bottom:3px solid var(--red);padding:0 24px;display:flex;align-items:center;justify-content:space-between;position:sticky;top:0;z-index:100;min-height:54px;gap:16px}
.ml{display:flex;align-items:center;gap:12px}
.mf{background:var(--red);color:#fff;font-size:10px;font-weight:800;letter-spacing:1.5px;text-transform:uppercase;padding:3px 9px;border-radius:2px}
.mn{font-family:Georgia,serif;font-size:18px;font-weight:700;color:#fff}
.mt2{font-size:9px;color:rgba(255,255,255,.4);text-transform:uppercase;letter-spacing:1.2px;margin-top:2px}
.mr{display:flex;align-items:center;gap:12px;flex-wrap:wrap}
.lp{display:flex;align-items:center;gap:5px;border:1px solid rgba(239,68,68,.4);padding:3px 9px;border-radius:3px;font-size:11px;font-weight:700;color:#f87171}
.lp::before{content:'';width:6px;height:6px;border-radius:50%;background:#f87171;animation:lp 2s infinite}
@keyframes lp{0%,100%{opacity:1}50%{opacity:.25}}
.mm{font-size:11px;color:rgba(255,255,255,.45)}
.sp2{font-size:11px;font-weight:600;color:rgba(255,255,255,.7);background:rgba(255,255,255,.1);border:1px solid rgba(255,255,255,.2);padding:3px 9px;border-radius:3px}
.rb{background:transparent;border:1px solid rgba(255,255,255,.25);color:rgba(255,255,255,.75);padding:5px 13px;border-radius:3px;cursor:pointer;font-size:11px;font-weight:600;transition:all .15s;white-space:nowrap}
.rb:hover{background:var(--red);border-color:var(--red);color:#fff}
.eb{background:var(--linen-d);border-bottom:1px solid var(--border);padding:5px 24px;display:flex;align-items:center;justify-content:space-between;font-family:Georgia,serif;font-style:italic;font-size:12px;color:var(--ink-l)}
.main{display:grid;grid-template-columns:1fr 264px;grid-template-areas:"topics trends" "sources sources";max-width:1700px;margin:0 auto;padding:12px 16px}
.card{background:var(--white);border:1px solid var(--border);border-radius:2px;box-shadow:0 1px 4px var(--sh);overflow:hidden;margin:8px}
.ch{padding:10px 16px;border-bottom:2px solid var(--navy);display:flex;align-items:center;gap:8px;background:var(--white)}
.ch h2{font-family:Georgia,serif;font-size:12px;font-weight:700;text-transform:uppercase;letter-spacing:.8px;color:var(--navy)}
.chr{margin-left:auto;font-size:11px;color:var(--ink-l);font-style:italic}
#tc{grid-area:topics}
.tr{border-bottom:1px solid var(--border-l)}.tr:last-child{border-bottom:none}
.tm{display:flex;align-items:center;gap:10px;padding:10px 16px;cursor:pointer;transition:background .1s}
.tm:hover{background:var(--linen)}
.rk{font-family:Georgia,serif;font-size:16px;font-weight:700;color:var(--ink-l);width:24px;text-align:right;flex-shrink:0}
.rk.h{color:var(--red)}
.tb{flex:1;min-width:0}
.tk{font-family:Georgia,serif;font-size:15px;font-weight:700;color:var(--ink);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.th2{font-size:12px;color:var(--ink-m);font-style:italic;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;margin-top:2px}
.tmr{display:flex;align-items:center;gap:7px;margin-top:5px}
.sds{display:flex;gap:3px}.sd{width:8px;height:8px;border-radius:50%;flex-shrink:0}
.ct{font-size:11px;color:var(--ink-l)}
.hw{display:flex;align-items:center;gap:6px;flex-shrink:0}
.hbg{width:54px;height:4px;background:var(--linen-dd);border-radius:2px}
.hfl{height:4px;background:var(--red);border-radius:2px}
.hn{font-family:Georgia,serif;font-size:11px;font-weight:700;color:var(--red);width:26px;text-align:right}
.ei{font-size:10px;color:var(--ink-l);flex-shrink:0}
.hbadge{font-size:9px;font-weight:800;letter-spacing:.8px;text-transform:uppercase;background:var(--navy);color:#fff;padding:2px 6px;border-radius:2px;flex-shrink:0}
.dwgap{font-size:9px;font-weight:800;letter-spacing:.6px;text-transform:uppercase;background:#C41230;color:#fff;padding:2px 6px;border-radius:2px;flex-shrink:0;animation:lp 2s infinite}
.hero-art{background:rgba(26,39,68,.04);border-left:3px solid var(--navy)}
.ta{display:none;background:var(--linen);border-top:1px solid var(--border-l)}
.ta.o{display:block}
.tar{padding:7px 16px 7px 50px;border-bottom:1px solid var(--border-l);font-size:12px}
.tar:last-child{border-bottom:none}
.tas{font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.5px;color:var(--ink-l);margin-bottom:2px}
.tar a{color:var(--navy);text-decoration:none}.tar a:hover{color:var(--red);text-decoration:underline}
/* BREAKING badge */
.brk{font-size:9px;font-weight:900;letter-spacing:1px;text-transform:uppercase;background:#C41230;color:#fff;padding:2px 6px;border-radius:2px;flex-shrink:0;animation:lp 1.5s infinite}
.age-badge{font-size:9px;font-weight:700;color:var(--ink-l);background:var(--linen-d);border:1px solid var(--border);padding:1px 5px;border-radius:2px;flex-shrink:0}
/* Signals sidebar — tabbed */
#gcard{grid-area:trends}
.stabs{display:flex;border-bottom:2px solid var(--navy);background:var(--white)}
.stab{flex:1;padding:7px 4px;font-size:10px;font-weight:800;text-transform:uppercase;letter-spacing:.6px;color:var(--ink-l);text-align:center;cursor:pointer;border:none;background:none;transition:all .15s;border-bottom:2px solid transparent;margin-bottom:-2px}
.stab.active{color:var(--navy);border-bottom-color:var(--red)}
.stab:hover:not(.active){color:var(--ink)}
.spanel{display:none}.spanel.active{display:block}
.gi{display:flex;align-items:center;gap:8px;padding:7px 14px;border-bottom:1px solid var(--border-l);font-size:13px}
.gi:last-child{border-bottom:none}
.grank{font-family:Georgia,serif;font-size:12px;font-weight:700;color:var(--red);width:18px;flex-shrink:0}
.gterm{flex:1;color:var(--ink)}
.gbw{width:34px;flex-shrink:0}.gbb{height:3px;background:var(--linen-dd);border-radius:2px}.gbf{height:3px;background:#1D4ED8;border-radius:2px}
/* Drudge links */
.di{padding:7px 14px;border-bottom:1px solid var(--border-l);font-size:12px;line-height:1.4}
.di:last-child{border-bottom:none}
.di a{font-family:Georgia,serif;color:var(--navy);text-decoration:none}.di a:hover{color:var(--red);text-decoration:underline}
#ss{grid-area:sources}
.sg{display:grid;grid-template-columns:repeat(auto-fill,minmax(285px,1fr));gap:10px;padding:12px}
.sc{background:var(--white);border:1px solid var(--border);border-radius:2px;overflow:hidden;box-shadow:0 1px 3px var(--sh)}
.sch{padding:8px 12px;border-bottom:2px solid;display:flex;align-items:center;justify-content:space-between;gap:8px}
.snw{display:flex;align-items:center;gap:7px}
.sdl{width:10px;height:10px;border-radius:50%;flex-shrink:0}
.sn{font-size:11px;font-weight:800;color:var(--ink);text-transform:uppercase;letter-spacing:.6px}
.lc{font-size:10px;font-weight:600;padding:2px 6px;border-radius:2px}
.st{padding:7px 12px;border-bottom:1px solid var(--border-l);font-size:12px;line-height:1.45}
.st:last-child{border-bottom:none}
.st a{font-family:Georgia,serif;color:var(--ink);text-decoration:none}.st a:hover{color:var(--red);text-decoration:underline}
.se{padding:14px 12px;font-size:12px;color:var(--ink-l);font-style:italic}
#ac{grid-area:align}
.ab{display:flex;align-items:flex-start;gap:24px;padding:16px 20px;flex-wrap:wrap}
.sr2{width:106px;height:106px;border-radius:50%;display:flex;flex-direction:column;align-items:center;justify-content:center;border:4px solid;flex-shrink:0}
.sp3{font-family:Georgia,serif;font-size:26px;font-weight:800}
.sg2{font-family:Georgia,serif;font-size:17px;font-weight:700;margin-top:-2px}
.sl{font-size:10px;color:var(--ink-l);text-transform:uppercase;letter-spacing:.8px;margin-top:2px}
.ad{flex:1;min-width:0}
.as2{font-family:Georgia,serif;font-size:14px;color:var(--ink-m);margin-bottom:12px}
.as2 strong{color:var(--ink)}
.ag{display:grid;grid-template-columns:repeat(auto-fill,minmax(210px,1fr));gap:5px}
.ar{display:flex;align-items:center;gap:7px;padding:5px 10px;border-radius:2px;background:var(--linen);border:1px solid var(--border-l);font-size:12px}
.ac2{color:var(--green);font-size:14px;flex-shrink:0}.ax{color:var(--red);font-size:14px;flex-shrink:0}
.an{flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:var(--ink)}
.adw{font-size:10px;color:var(--red);margin-top:1px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-style:italic}
@media(max-width:900px){.main{grid-template-columns:1fr;grid-template-areas:"topics" "trends" "sources" "align"}}
</style></head><body>
<div id="ov"><div class="sp"></div><div class="lt">WhatsTrendingInRealTime.com</div><div class="ls">Scanning 15 sources + Google Trends US — ~15 seconds</div></div>
<header class="mast">
  <div class="ml"><span class="mf">Editorial</span><div><div class="mn">WhatsTrendingInRealTime.com</div><div class="mt2">Intelligence Dashboard · 15 Sources</div></div></div>
  <div class="mr"><span class="lp">LIVE</span><span class="sp2" id="sc2">Loading...</span><span class="mm" id="lu">—</span><span class="mm" id="cd"></span><button class="rb" onclick="fr()">↻ Refresh Now</button></div>
</header>
<div class="eb"><span id="ed">Loading...</span><span id="es">—</span></div>
<div class="main">
  <div class="card" id="tc"><div class="ch"><span>🔥</span><h2>Top Trending Topics</h2><span class="chr">Ranked by cross-source heat score · Click to expand</span></div><div id="tl"><div style="padding:20px;text-align:center;color:var(--ink-l)">Loading...</div></div></div>
  <div class="card" id="gcard">
    <div class="ch"><span>📡</span><h2>Signals</h2><span class="chr">Live social trends</span></div>
    <div class="stabs">
      <button class="stab active" onclick="switchTab('rd')">📋 Reddit</button>
      <button class="stab" onclick="switchTab('tw')">𝕏 Twitter</button>
      <button class="stab" onclick="switchTab('dr')">🔦 Drudge</button>
    </div>
    <div id="sp-rd" class="spanel active"><div id="rl"><div style="padding:14px;text-align:center;color:var(--ink-l);font-size:12px">Loading...</div></div></div>
    <div id="sp-tw" class="spanel"><div id="tl2"><div style="padding:14px;text-align:center;color:var(--ink-l);font-size:12px">Loading...</div></div></div>
    <div id="sp-dr" class="spanel"><div id="dl"><div style="padding:14px;text-align:center;color:var(--ink-l);font-size:12px">Loading...</div></div></div>
  </div>
  <div class="card" id="ss"><div class="ch"><span>📰</span><h2>Source Headlines</h2><span class="chr">Fox · NYT · CNN · Daily Mail · NY Post · AP · Reuters · Breitbart · Sky · NBC · Hill · DW · WashTimes · FoxBiz · Townhall</span></div><div class="sg" id="sg"></div></div>
</div>
<script>
const SO=['foxnews','nypost','dailywire','breitbart','washtimes','townhall','ap','reuters','thehill','skynews','cnn','nytimes','nbcnews','dailymail','foxbusiness'];
let _n=Date.now()+30*60*1000,_lastTs=null;
function e(s){return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;')}
function ta(iso){if(!iso)return'—';const d=Math.floor((Date.now()-new Date(iso))/1000);if(d<60)return d+'s ago';if(d<3600)return Math.floor(d/60)+'m ago';return Math.floor(d/3600)+'h ago'}
function fc(ms){if(ms<=0)return'Refreshing...';const m=Math.floor(ms/60000),s=Math.floor((ms%60000)/1000);return'Next refresh: '+m+':'+String(s).padStart(2,'0')}
function rT(topics){
  const el=document.getElementById('tl');
  if(!topics||!topics.length){el.innerHTML='<div style="padding:20px;text-align:center;color:var(--ink-l)">No trending topics yet.</div>';return}
  const mx=topics[0].heat_score||1;
  el.innerHTML=topics.map((t,i)=>{
    const pct=Math.round((t.heat_score/mx)*100),hot=i<3;
    const heroSrcs=new Set(t.hero_sources||[]);
    const dots=(t.sources||[]).map(s=>{
      const isHero=heroSrcs.has(s);
      return '<span class="sd" style="background:'+((window._L||{})[s]||'#6B7280')+';'+(isHero?'width:11px;height:11px;outline:2px solid var(--navy);outline-offset:1px;':'')+'" title="'+e(s)+(isHero?' — LEAD STORY':'')+'"></span>';
    }).join('');
    const heroBadge=heroSrcs.size>0?'<span class="hbadge">Lead at '+heroSrcs.size+' outlet'+(heroSrcs.size>1?'s':'')+'</span>':'';
    const brkBadge=t.is_breaking?'<span class="brk">Breaking</span>':'';
    const ageMin=t.age_minutes;
    const ageBadge=(!t.is_breaking&&ageMin!=null)?'<span class="age-badge">'+(ageMin<60?ageMin+'m':Math.floor(ageMin/60)+'h')+'</span>':'';
    const d=t.delta;
    const deltaBadge=d===null||d===undefined?'':d>0?'<span style="font-size:10px;font-weight:700;color:#15803D;flex-shrink:0">▲'+d+'</span>':d<0?'<span style="font-size:10px;font-weight:700;color:#C41230;flex-shrink:0">▼'+Math.abs(d)+'</span>':'<span style="font-size:10px;color:#6B7280;flex-shrink:0">—</span>';
    const arts=(t.articles||[]).map(a=>{
      const isHeroArt=a.feed_position===0||a.feed_position===1;
      const isScrapeConfirmed=a.scrape_confirmed===true;
      const heroMark=isHeroArt&&isScrapeConfirmed?' ★✓':isHeroArt?' ★':isScrapeConfirmed?' ✓':'';
      const age=a.pub_ts?'<span style="color:var(--ink-l);font-size:10px;margin-left:6px;font-style:normal">'+ta(a.pub_ts)+'</span>':'';
      return '<div class="tar'+(isHeroArt||isScrapeConfirmed?' hero-art':'')+'"><div class="tas">'+e(a.source_id)+heroMark+age+'</div><a href="'+e(a.link)+'" target="_blank">'+e(a.title)+'</a></div>';
    }).join('');
    return '<div class="tr"><div class="tm" onclick="tg('+i+')"><span class="rk'+(hot?' h':'')+'">'+( i+1)+'</span><div class="tb"><div class="tk" style="display:flex;align-items:center;gap:7px;">'+e(t.keyword)+brkBadge+ageBadge+heroBadge+'</div><div class="th2">'+e(t.topic)+'</div><div class="tmr"><div class="sds">'+dots+'</div><span class="ct">'+t.source_count+' sources · '+t.article_count+' stories</span></div></div><div class="hw">'+deltaBadge+'<div class="hbg"><div class="hfl" style="width:'+pct+'%"></div></div><span class="hn">'+t.heat_score+'</span></div><span class="ei" id="ei'+i+'">▸</span></div><div class="ta" id="ta'+i+'">'+arts+'</div></div>';
  }).join('');
}
function tg(i){document.getElementById('ta'+i).classList.toggle('o');const ic=document.getElementById('ei'+i);ic.textContent=ic.textContent==='▸'?'▾':'▸'}
let _activeTab='rd';
function switchTab(tab){
  _activeTab=tab;
  document.querySelectorAll('.stab').forEach((b,i)=>{b.classList.toggle('active',['rd','tw','dr'][i]===tab)});
  document.querySelectorAll('.spanel').forEach((p,i)=>{p.classList.toggle('active',['sp-rd','sp-tw','sp-dr'][i]==='sp-'+tab)});
}
function rG(posts){
  const el=document.getElementById('rl');
  if(!posts||!posts.length){el.innerHTML='<div style="padding:14px;text-align:center;color:var(--ink-l);font-size:12px">r/Conservative unavailable</div>';return}
  el.innerHTML=posts.map((p,i)=>{
    const score=p.score>999?(p.score/1000).toFixed(1)+'k':p.score;
    return '<div class="di"><a href="'+e(p.link)+'" target="_blank">'+e(p.title)+'</a><div style="font-size:10px;color:var(--ink-l);margin-top:2px">▲'+score+' · '+p.comments+' comments</div></div>';
  }).join('');
}
function rTw(trends){
  const el=document.getElementById('tl2');
  if(!trends||!trends.length){el.innerHTML='<div style="padding:14px;text-align:center;color:var(--ink-l);font-size:12px">Twitter/X trends unavailable</div>';return}
  el.innerHTML=trends.slice(0,25).map((t,i)=>'<div class="gi"><span class="grank">'+(i+1)+'</span><span class="gterm">'+e(t)+'</span><div class="gbw"><div class="gbb"><div class="gbf" style="width:'+Math.round(((25-i)/25)*100)+'%;background:#1DA1F2"></div></div></div></div>').join('');
}
function rDr(links){
  const el=document.getElementById('dl');
  if(!links||!links.length){el.innerHTML='<div style="padding:14px;text-align:center;color:var(--ink-l);font-size:12px">Drudge unavailable</div>';return}
  el.innerHTML=links.map((l,i)=>'<div class="di"><a href="'+e(l.link)+'" target="_blank">'+e(l.title)+'</a></div>').join('');
}
function rS(srcs){
  if(!srcs)return;
  window._L={};Object.entries(srcs).forEach(([id,s])=>window._L[id]=s.lean_color);
  const ord=[...SO.filter(id=>srcs[id]),...Object.keys(srcs).filter(id=>!SO.includes(id))];
  document.getElementById('sg').innerHTML=ord.map(sid=>{
    const s=srcs[sid];if(!s)return'';
    const arts=s.articles||[];
    return '<div class="sc"><div class="sch" style="border-color:'+e(s.lean_color)+'"><div class="snw"><span class="sdl" style="background:'+e(s.lean_color)+'"></span><span class="sn">'+e(s.name)+'</span></div><span class="lc" style="background:'+e(s.lean_color)+'18;color:'+e(s.lean_color)+'">'+e(s.lean_label)+'</span></div>'+(arts.length?arts.map(a=>'<div class="st"><a href="'+e(a.link)+'" target="_blank">'+e(a.title)+'</a></div>').join(''):'<div class="se">⚠ Feed unavailable</div>')+'</div>';
  }).join('');
}
function rA(al){
  const el=document.getElementById('al');
  if(!al){el.innerHTML='<div style="padding:20px;text-align:center;color:var(--ink-l)">Daily Wire RSS not loading.</div>';return}
  const gc={A:'#14532D',B:'#15803D',C:'#92400E',D:'#C41230'}[al.grade]||'#374151';
  const rows=(al.details||[]).map(d=>'<div class="ar"><span class="'+(d.covered?'ac2':'ax')+'">'+(d.covered?'✓':'✗')+'</span><div style="flex:1;min-width:0"><div class="an">'+e(d.topic)+'</div>'+(d.dw_article?'<div class="adw">↳ '+e(d.dw_article)+'</div>':'')+'</div></div>').join('');
  el.innerHTML='<div class="ab"><div class="sr2" style="border-color:'+gc+';color:'+gc+'"><span class="sp3">'+al.score+'%</span><span class="sg2">'+al.grade+'</span><span class="sl">Coverage</span></div><div class="ad"><div class="as2">Daily Wire covered <strong>'+al.covered+' of '+al.total+'</strong> top trending topics today.'+(al.score<60?' <span style="color:var(--red)">↑ '+(al.total-al.covered)+' stories need coverage.</span>':' <span style="color:var(--green)">Strong alignment.</span>')+'</div><div class="ag">'+rows+'</div></div></div>';
}
async function ld(){
  try{
    const d=await(await fetch('/api/data')).json();
    if(d.loading){setTimeout(ld,3000);return}
    document.getElementById('ov').classList.add('h');
    document.getElementById('sc2').textContent=(d.sources_live||0)+' sources live';
    document.getElementById('lu').textContent=d.last_updated?'Updated '+ta(d.last_updated):'';
    const now=new Date();
    document.getElementById('ed').textContent=now.toLocaleDateString('en-US',{weekday:'long',year:'numeric',month:'long',day:'numeric'});
    document.getElementById('es').textContent=(d.sources_live||0)+' of 15 sources reporting';
    // Sync countdown to server's actual refresh schedule
    if(d.last_updated){
      const serverNext=new Date(d.last_updated).getTime()+30*60*1000;
      if(serverNext>Date.now()) _n=serverNext;
    }
    // Only re-render if data actually changed
    if(d.last_updated!==_lastTs){
      _lastTs=d.last_updated;
      rT(d.trending_topics);rG(d.reddit_posts);
      rTw(d.twitter_trends);rDr(d.drudge_links);
      rS(d.sources);
    }
  }catch(ex){setTimeout(ld,5000)}
}
async function fr(){
  document.getElementById('ov').classList.remove('h');
  try{await fetch('/api/refresh',{method:'POST'})}catch(ex){}
  _n=Date.now()+30*60*1000;_lastTs=null;setTimeout(ld,3000);
}
// Countdown timer + auto-trigger refresh when server schedule fires
setInterval(()=>{const r=_n-Date.now();document.getElementById('cd').textContent=fc(r);if(r<=0){_n=Date.now()+30*60*1000;ld()}},1000);
// Poll for new data every 2 minutes so UI picks up server refreshes promptly
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
