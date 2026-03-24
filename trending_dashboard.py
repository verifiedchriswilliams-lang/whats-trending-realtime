#!/usr/bin/env python3
"""
TrendingInRealTime.com — Editorial Intelligence Dashboard  v2
Newspaper theme. Clustering fix. 15 sources incl. NYT.
"""

import json, time, threading, re, sys, os, webbrowser, math
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
    {"id":"foxnews",    "name":"Fox News",          "rss":"https://news.google.com/rss/search?q=site:foxnews.com&ceid=US:en&hl=en-US&gl=US", "lean":"right", "tier":1},
    {"id":"cnn",        "name":"CNN",               "rss":"https://news.google.com/rss/search?q=site:cnn.com&ceid=US:en&hl=en-US&gl=US", "lean":"left", "tier":1},
    {"id":"nytimes",    "name":"New York Times",    "rss":"https://rss.nytimes.com/services/xml/rss/nyt/HomePage.xml","lean":"left",         "tier":1},
    {"id":"dailymail",  "name":"Daily Mail",        "rss":"https://www.dailymail.co.uk/news/index.rss",               "lean":"center-right", "tier":1},
    {"id":"nypost",     "name":"NY Post",           "rss":"https://nypost.com/feed/",                                 "lean":"right",        "tier":1},
    {"id":"ap",         "name":"AP News",           "rss":"https://news.google.com/rss/search?q=site:apnews.com&ceid=US:en&hl=en-US&gl=US", "lean":"center", "tier":1},
    {"id":"reuters",    "name":"Reuters",           "rss":"https://news.google.com/rss/search?q=site:reuters.com&ceid=US:en&hl=en-US&gl=US", "lean":"center", "tier":1},
    {"id":"nbcnews",    "name":"NBC News",          "rss":"https://feeds.nbcnews.com/nbcnews/public/news",            "lean":"left",         "tier":1},
    {"id":"dailywire",  "name":"Daily Wire",        "rss":"https://www.dailywire.com/feeds/rss.xml",                  "lean":"right",        "tier":1},
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
    # --- Quantity/degree adverbs — appear in unrelated headlines, make garbage seeds ---
    'nearly','roughly','almost','barely','about','approximately','least','most',
    'more','less','once','twice','again','ever','never','always','often',
    # --- Common headline verbs/adjectives that bleed across unrelated stories ---
    'says','said','told','tell','tells','calls','called','warn','warns','warned',
    'claim','claims','claimed','deny','denies','denied','admit','admits','admitted',
    'open','opens','opened','close','closes','closed','hold','holds','held',
    'face','faces','faced','push','pushes','pushed','pull','pulls','pulled',
    'cut','cuts','raise','raises','raised','drop','drops','dropped',
    'win','wins','won','lose','loses','lost','lead','leads','led',
    'start','starts','started','stop','stops','stopped','end','ends','ended',
    'start','begin','begins','began','continue','continues','continued',
    'grow','grows','grew','rise','rises','rose','fall','falls','fell',
    'sign','signs','signed','launch','launches','launched','pass','passes','passed',
    'block','blocks','blocked','reject','rejects','rejected','approve','approves',
    'leave','leaves','left','return','returns','returned','move','moves','moved',
    'bring','brings','brought','send','sends','sent','show','shows','showed',
    'report','reports','reported','reveal','reveals','revealed','confirm','confirms',
    'hit','hits','strike','strikes','struck','target','targets','targeted',
    'top','major','key','big','huge','massive','large','giant','record','historic',
    'former','future','potential','possible','likely','unlikely','expected',
    'second','third','fourth','fifth','sixth','seventh','eighth','ninth','tenth',
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
    # --- US political bodies — too broad, appear in unrelated stories ---
    'congress','senate','house','parliament','legislature','lawmakers','lawmaker',
    'republican','republicans','democrat','democrats','gop','bipartisan',
    # --- Generic human/social nouns — appear in every story type, never a useful seed ---
    'family','families','woman','women','man','men','child','children','kid','kids',
    'couple','couples','life','lives','girl','girls','boy','boys','teen','teens',
    'student','students','parent','parents','friend','friends','neighbor','neighbors',
    'victim','victims','survivor','survivors','resident','residents','citizen','citizens',
    'thing','things','part','parts','way','ways','place','places','area',
    'work','working','worker','workers','job','jobs',
    'company','companies','business','businesses','market','markets',
    'court','courts','judge','judges','law','laws','legal',
}

data_store = {"last_updated":None,"sources":{},"trending_topics":[],"twitter_trends":[],"drudge_links":[],"facebook_posts":[],"sources_live":0,"loading":True}
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
        for i, e in enumerate(feed.entries[:20]):
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
    """Scrape a news source homepage and return headlines in editorial order.
    Returns a list of (normalized_headline, page_position) tuples (1-based).
    Position 1 = highest editorial placement on the page.

    For Daily Wire: explicitly targets the editorial 'Top Stories' section
    (div[class*=topStoryTextContainer] h3) so those 5 curated picks come first
    (positions 1-5), before the generic h2/h3 scan fills in the rest.
    This fixes the RSS-vs-editorial mismatch where old stories can stay #1
    on the site even after newer articles have pushed them down the feed.

    Empty list returned on failure — scraping degrades gracefully."""
    if not HAS_SCRAPE:
        return []
    try:
        r = requests.get(url, timeout=10, headers={
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml',
        })
        r.raise_for_status()
        soup = BeautifulSoup(r.text, 'html.parser')
        ordered = []  # ordered list of normalized headline strings (de-duped)
        seen = set()

        def add(text):
            norm = text.strip().lower()
            if 20 <= len(norm) <= 250 and norm not in seen:
                seen.add(norm)
                ordered.append(norm)

        # --- Daily Wire: target editorial Top Stories section FIRST ---
        # The Top Stories widget uses divs with class containing 'topStoryTextContainer'
        # containing h3 elements — these are editor-curated picks, not RSS chronology.
        if sid == 'dailywire':
            for div in soup.find_all('div', class_=lambda c: c and 'topStoryTextContainer' in c):
                h3 = div.find('h3')
                if h3:
                    add(h3.get_text(separator=' ', strip=True))

        # --- All sources: h1/h2/h3 in document order ---
        for tag in soup.find_all(['h1', 'h2', 'h3']):
            add(tag.get_text(separator=' ', strip=True))

        # --- Prominent anchor text (fallback for JS-heavy or non-semantic sites) ---
        for tag in soup.find_all('a', href=True):
            add(tag.get_text(separator=' ', strip=True))

        # Return as (text, position) — position is 1-based editorial rank
        return [(text, pos + 1) for pos, text in enumerate(ordered)]

    except Exception as ex:
        print(f"  scrape {sid}: {ex}")
        return []

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
    """Scrape US Twitter/X trending topics.
    Primary: getdaytrends.com (server-side rendered, reliable on cloud IPs)
    Fallback: trends24.in
    """
    global _TWITTER_CACHE
    now = time.time()
    if _TWITTER_CACHE["data"] and now - _TWITTER_CACHE["fetched_at"] < 1800:
        return _TWITTER_CACHE["data"]
    if not HAS_SCRAPE:
        return _TWITTER_CACHE["data"]

    hdrs = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
    }

    def _parse_getdaytrends(html):
        soup = BeautifulSoup(html, 'html.parser')
        trends, seen = [], set()
        # getdaytrends.com: trend names are in <p class="trend-name"> or <span class="trend-name">
        for el in soup.select('.trend-name, [class*="trend"] p, [class*="trending"] span'):
            text = el.get_text(strip=True)
            if not text or len(text) < 2 or len(text) > 80: continue
            if text.lower() in _SITE_NAV_TERMS or text.lower() in seen: continue
            seen.add(text.lower())
            trends.append(text)
        return trends[:25]

    def _parse_trends24(html):
        soup = BeautifulSoup(html, 'html.parser')
        trends, seen = [], set()
        for card in soup.select('.trend-card, [class*="trend-card"]'):
            for li in card.select('ol li a, li a'):
                text = li.get_text(strip=True)
                if not text or len(text) < 2 or len(text) > 80: continue
                if text.lower() in _SITE_NAV_TERMS or text.lower() in seen: continue
                seen.add(text.lower())
                trends.append(text)
            if len(trends) >= 25: break
        # Fallback: any <a> with a hash-like short label inside a list
        if not trends:
            for a in soup.select('li a'):
                text = a.get_text(strip=True)
                if not text or len(text) < 2 or len(text) > 80: continue
                if text.lower() in _SITE_NAV_TERMS or text.lower() in seen: continue
                seen.add(text.lower())
                trends.append(text)
                if len(trends) >= 25: break
        return trends[:25]

    sources = [
        ("https://getdaytrends.com/united-states/", _parse_getdaytrends),
        ("https://trends24.in/united-states/",      _parse_trends24),
    ]
    for url, parser in sources:
        try:
            r = requests.get(url, timeout=15, headers=hdrs)
            r.raise_for_status()
            trends = parser(r.text)
            if trends:
                _TWITTER_CACHE = {"data": trends, "fetched_at": now}
                print(f"  Twitter/X trends: {len(trends)} trends from {url}")
                return trends
            else:
                print(f"  Twitter/X: 0 trends parsed from {url}, trying next source")
        except Exception as ex:
            print(f"  Twitter trends error ({url}): {ex}")

    print("  Twitter/X: all sources failed")
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
            headers={'User-Agent': 'TrendingInRealTime/1.0 (editorial dashboard)'},
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


_FB_CACHE = {"data": [], "fetched_at": 0, "backoff_until": 0}

def fetch_facebook_engagement(all_arts):
    """Fetch Facebook engagement (reactions + shares + comments) for article URLs
    via the public Facebook Graph API URL endpoint — no API key required.
    Best signal for which stories are catching fire with the conservative Facebook audience.

    Skips Google News proxy sources (cnn, ap, reuters) since their URLs are redirects.
    Fetches engagement for direct article URLs from all other sources concurrently.
    Falls back to cached data on error with a 1-hour backoff."""
    global _FB_CACHE
    now = time.time()
    if now < _FB_CACHE.get("backoff_until", 0):
        return _FB_CACHE["data"]
    if _FB_CACHE["data"] and now - _FB_CACHE["fetched_at"] < 3600:
        return _FB_CACHE["data"]
    if not HAS_SCRAPE:
        return _FB_CACHE["data"]

    # Skip Google News proxy sources — their URLs are google.com redirects
    SKIP_SOURCES = {"cnn", "ap", "reuters", "foxnews"}
    candidates = []
    for sid, arts in all_arts.items():
        if sid in SKIP_SOURCES:
            continue
        for art in arts[:10]:
            url = art.get("link", "")
            if url and url.startswith("http") and "google.com" not in url:
                candidates.append({
                    "url":    url,
                    "title":  art.get("title", ""),
                    "source": sid,
                })

    if not candidates:
        print("  Facebook: no candidates (all sources skipped or no URLs)")
        return _FB_CACHE.get("data", [])

    FB_TOKEN = "1491126469205088|cd10efe58b5e4ee341710581b704bec7"
    first_error = []  # capture first error message for diagnostics

    def fetch_one(item):
        try:
            r = requests.get(
                f"https://graph.facebook.com/v19.0/?id={item['url']}&fields=engagement&access_token={FB_TOKEN}",
                timeout=8,
                headers={"User-Agent": "TrendingInRealTime.com/2.0 (editorial dashboard)"},
            )
            data = r.json()
            if "error" in data:
                if not first_error:
                    first_error.append(data["error"])
                return None
            eng = data.get("engagement", {})
            total = (eng.get("reaction_count", 0) +
                     eng.get("share_count", 0) +
                     eng.get("comment_count", 0))
            if total > 0:
                return {**item,
                        "fb_total":     total,
                        "fb_reactions": eng.get("reaction_count", 0),
                        "fb_shares":    eng.get("share_count", 0),
                        "fb_comments":  eng.get("comment_count", 0)}
        except Exception as ex:
            if not first_error:
                first_error.append({"message": str(ex)})
        return None

    try:
        results = []
        sample = candidates[:15]
        with ThreadPoolExecutor(max_workers=12) as ex:
            futures = [ex.submit(fetch_one, item) for item in sample]
            for f in as_completed(futures):
                r = f.result()
                if r:
                    results.append(r)

        if first_error:
            print(f"  Facebook API error: {first_error[0]}")

        if not results and first_error:
            err_code = first_error[0].get("code", 0)
            err_type = first_error[0].get("type", "")
            err_msg  = first_error[0].get("message", "")
            print(f"  Facebook: no results — {err_type}: {err_msg}")
            # Rate limit (#4): back off 2 hours instead of retrying every cycle
            if err_code == 4:
                display = "App rate limit reached. Your Facebook app may be in Development mode — switch it to Live mode at developers.facebook.com to increase limits."
                _FB_CACHE["backoff_until"] = now + 7200
            else:
                display = f"{err_type}: {err_msg}"
            _FB_CACHE["data"] = [{"__unavailable": True, "reason": display}]
            _FB_CACHE["fetched_at"] = now
            return _FB_CACHE["data"]

        results.sort(key=lambda x: x["fb_total"], reverse=True)
        top = results[:20]
        _FB_CACHE = {"data": top, "fetched_at": now, "backoff_until": 0}
        print(f"  Facebook: {len(top)} articles with engagement (checked {len(sample)}, {len(candidates)} candidates)")
        return top
    except Exception as ex:
        print(f"  Facebook engagement error: {ex}")
        _FB_CACHE["backoff_until"] = now + 3600
        return _FB_CACHE.get("data", [])


# ── TF-IDF COSINE SIMILARITY CLUSTERING ──────────────────────────────────────
# Replaces the single-keyword seed approach.
# Each article title is vectorized via TF-IDF (sparse dict, no numpy needed).
# Articles are greedily assigned to the nearest cluster above SIMILARITY_THRESHOLD.
# This prevents "congress", "season", "poll" false merges because two articles
# must share a PATTERN of words — not just one — to exceed the threshold.

SIMILARITY_THRESHOLD = 0.28   # Tune: higher = tighter clusters, fewer false merges

def _tfidf_tokenize(title):
    """Tokenize a headline for TF-IDF clustering (reuses STOP_WORDS)."""
    words = re.findall(r"[A-Za-z']+", title.lower())
    words = [w[:-2] if w.endswith("'s") else w.rstrip("'") for w in words]
    return [w for w in words if w not in STOP_WORDS and len(w) > 3]

def _build_tfidf(tokenized_docs):
    """Build L2-normalised TF-IDF sparse vectors (list of dicts) for all docs."""
    N = len(tokenized_docs)
    df = defaultdict(int)
    for tokens in tokenized_docs:
        for t in set(tokens):
            df[t] += 1
    vecs = []
    for tokens in tokenized_docs:
        tf = defaultdict(int)
        for t in tokens:
            tf[t] += 1
        vec = {w: cnt * math.log((N + 1) / (df[w] + 1))
               for w, cnt in tf.items()}
        norm = math.sqrt(sum(v * v for v in vec.values()))
        vecs.append({w: v / norm for w, v in vec.items()} if norm > 0 else {})
    return vecs

def _cosine(v1, v2):
    """Cosine similarity between two L2-normalised sparse dicts."""
    if len(v1) > len(v2):
        v1, v2 = v2, v1
    return sum(v * v2.get(w, 0.0) for w, v in v1.items())

def _update_centroid(centroid, new_vec, n):
    """Online centroid update: running mean, re-normalised."""
    merged = {}
    for w in set(list(centroid.keys()) + list(new_vec.keys())):
        merged[w] = centroid.get(w, 0.0) * (n - 1) / n + new_vec.get(w, 0.0) / n
    norm = math.sqrt(sum(v * v for v in merged.values()))
    return {w: v / norm for w, v in merged.items()} if norm > 0 else merged

# ─────────────────────────────────────────────────────────────────────────────

def extract_keywords(title):
    words = re.findall(r"[A-Za-z']+", title.lower())
    # Strip possessives: "trump's" → "trump", "iran's" → "iran"
    words = [w[:-2] if w.endswith("'s") else w.rstrip("'") for w in words]
    filtered = [w for w in words if w not in STOP_WORDS and len(w)>3]
    proper = [p.lower() for p in re.findall(r'\b[A-Z][a-z]{2,}\b', title) if p.lower() not in STOP_WORDS and len(p)>3]
    seen,result = set(),[]
    for w in filtered+proper:
        if w not in seen: seen.add(w); result.append(w)
    return result

# Preferred source order for choosing the most readable cluster headline label.
# AP/Reuters/NYT give clean, neutral, descriptive headlines.
_LABEL_SRC_PREF = ["ap","reuters","nytimes","nbcnews","cnn","foxnews","thehill",
                   "skynews","washtimes","nypost","foxbusiness","dailywire",
                   "breitbart","townhall","dailymail"]

def best_label(kw, articles):
    """Return the most representative real headline from the cluster.

    Picks the article with the highest keyword overlap with other cluster
    articles, breaking ties by preferring authoritative sources (AP, Reuters,
    NYT) that tend to write clean, descriptive headlines.  Strips common
    Google News source suffixes like '- Reuters' or '- CNN'.
    """
    if not articles:
        return kw.title()

    art_kws = [(a, set(extract_keywords(a["title"])) - {kw}) for a in articles]

    best_art, best_score = None, -1
    for i, (art, kws) in enumerate(art_kws):
        # How many OTHER articles share at least one secondary keyword with this one?
        overlap = sum(1 for j, (_, okws) in enumerate(art_kws)
                      if i != j and kws & okws)
        # Break ties by source preference (lower index = better)
        src = art.get("source_id", "")
        src_rank = _LABEL_SRC_PREF.index(src) if src in _LABEL_SRC_PREF else 99
        score = overlap * 100 - src_rank
        if score > best_score:
            best_score = score
            best_art = art

    title = (best_art or articles[0])["title"]
    # Strip trailing "- Source Name" appended by Google News RSS
    title = re.sub(r'\s*[-–]\s*(Reuters|AP News|CNN|Fox News|NBC News|The Hill'
                   r'|Washington Times|Breitbart|Townhall|Sky News'
                   r'|Daily Wire|NY Post|Daily Mail|Fox Business)\s*$',
                   '', title, flags=re.IGNORECASE).strip()
    return title

def cluster_topics(all_arts):
    # Flatten articles
    flat = []
    for sid, arts in all_arts.items():
        for art in arts:
            flat.append({**art, "source_id": sid})
    if not flat:
        return []

    # ── TF-IDF cosine similarity clustering ──────────────────────────────────
    # Build sparse TF-IDF vectors for every article title, then greedily assign
    # each article to the nearest existing cluster (if cosine ≥ threshold) or
    # start a new cluster.  Each article belongs to exactly one cluster.
    tokenized = [_tfidf_tokenize(art["title"]) for art in flat]
    tfidf_vecs = _build_tfidf(tokenized)

    raw_clusters = []   # list of lists of indices into flat[]
    centroids    = []   # centroid vec (sparse dict) per cluster

    for i, vec in enumerate(tfidf_vecs):
        if not vec:
            continue
        best_ci, best_sim = -1, SIMILARITY_THRESHOLD
        for ci, centroid in enumerate(centroids):
            sim = _cosine(vec, centroid)
            if sim > best_sim:
                best_sim = sim
                best_ci = ci
        if best_ci >= 0:
            raw_clusters[best_ci].append(i)
            centroids[best_ci] = _update_centroid(
                centroids[best_ci], vec, len(raw_clusters[best_ci]))
        else:
            raw_clusters.append([i])
            centroids.append(dict(vec))

    clusters = []
    tier1 = {s["id"] for s in SOURCES if s["tier"]==1}

    for idxs in raw_clusters:
        cl_arts = [flat[i] for i in idxs]
        cl_srcs = set(a["source_id"] for a in cl_arts)

        # Require at least 2 distinct sources
        if len(cl_srcs) < 2:
            continue

        t1 = [a for a in cl_arts if a["source_id"] in tier1]
        label = best_label("", cl_arts)
        src_count = len(cl_srcs)

        # --- Position-weighted hero scoring ---
        # RSS hero: feed position 0 or 1 (top of feed)
        # Scrape hero: article confirmed on homepage at position ≤ 8
        # Editorial spotlight: scrape position ≤ 3 (top of page / editorial "Top Stories" section)
        # Double-confirmed: RSS hero AND scraped (both signals agree)
        hero_set = set()
        double_confirmed = 0
        editorial_spotlight_set = set()  # scrape position 1-3 = editors are actively leading with this

        seen_double = set()
        for a in cl_arts:
            sid_a = a["source_id"]
            is_rss_hero    = a.get("feed_position", 99) <= 1
            scrape_pos     = a.get("scrape_position")          # None if not matched
            is_scrape_hero = scrape_pos is not None and scrape_pos <= 8
            is_editorial   = scrape_pos is not None and scrape_pos <= 3

            if is_rss_hero or is_scrape_hero:
                hero_set.add(sid_a)
            if is_editorial:
                editorial_spotlight_set.add(sid_a)
            # Double-confirmed: RSS hero + any scrape hit (count once per source)
            if is_rss_hero and a.get("scrape_confirmed") and sid_a not in seen_double:
                double_confirmed += 1
                seen_double.add(sid_a)

        hero_sources = list(hero_set | editorial_spotlight_set)
        hero_count   = len(hero_set)
        editorial_spotlight = len(editorial_spotlight_set)

        # Heat formula:
        #   base:               source_count × 12
        #   breadth:            + article_count
        #   hero placement:     + hero_count × 20   (RSS top-2 OR scrape pos 1-8)
        #   double-confirmed:   + double_confirmed × 10  (RSS hero AND scraped)
        #   editorial spotlight:+ editorial_spotlight × 15  (scrape pos 1-3; editors chose it)
        heat = (src_count * 12 + len(cl_arts)
                + (hero_count * 20)
                + (double_confirmed * 10)
                + (editorial_spotlight * 15))

        # Story age: derived from the most recently published article in the cluster
        now_utc = datetime.now(timezone.utc)
        pub_times = [datetime.fromisoformat(a["pub_ts"]) for a in cl_arts if a.get("pub_ts")]
        if pub_times:
            newest = max(pub_times)
            age_minutes = int((now_utc - newest).total_seconds() / 60)
        else:
            age_minutes = None
        is_breaking = age_minutes is not None and age_minutes < 90

        clusters.append({"keyword": label, "topic": label,
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
        scraped_pages = {}  # sid → list of (normalized_headline, position) tuples
        for f in as_completed(scrape_futures):
            sid = scrape_futures[f]
            scraped_pages[sid] = f.result()
            if scraped_pages[sid]:
                print(f"  🔎 scraped {sid}: {len(scraped_pages[sid])} headlines (top: {scraped_pages[sid][0][0][:50] if scraped_pages[sid] else '—'})")

    # Cross-verify: match articles against scraped homepage, recording editorial position.
    # scrape_position 1–3 = editorial spotlight (top of page / Top Stories section)
    # scrape_position 4–8 = standard hero placement
    # scrape_position 9+  = present on page but below the fold
    if scraped_pages:
        for sid, arts in all_arts.items():
            sc_list = scraped_pages.get(sid, [])
            if not sc_list:
                continue
            # Build position lookup: normalized_text → page_position
            sc_pos = {text: pos for text, pos in sc_list}
            sc_texts = list(sc_pos.keys())
            for art in arts:
                norm = art["title"].lower()
                matched_pos = None
                for h in sc_texts:
                    if (norm in h or h in norm or
                            (len(norm.split()) >= 4 and
                             len(set(norm.split()) & set(h.split())) / max(len(norm.split()), 1) >= 0.6)):
                        matched_pos = sc_pos[h]
                        break
                if matched_pos is not None:
                    art["scrape_confirmed"] = True
                    art["scrape_position"] = matched_pos
                else:
                    art["scrape_confirmed"] = False

    print("  Fetching Drudge + Twitter/X + Facebook engagement...")
    drudge_links    = fetch_drudge()
    twitter_trends  = fetch_twitter_trends()
    facebook_posts  = fetch_facebook_engagement(all_arts)
    print(f"  {'✓' if drudge_links else '✗'} Drudge: {len(drudge_links)} links")
    print(f"  {'✓' if twitter_trends else '✗'} Twitter/X: {len(twitter_trends)} trends")
    print(f"  {'✓' if facebook_posts else '✗'} Facebook: {len(facebook_posts)} articles with engagement")
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
        raw = all_arts.get(sid, [])
        # Sort so editorially-prominent articles (scrape_position set) float to the top,
        # ordered by their homepage position. Unmatched RSS articles follow in feed order.
        # This ensures the source card matches what editors are actually leading with on their
        # homepage, not just the newest-published articles from the RSS feed.
        editorial = sorted([a for a in raw if a.get("scrape_position")], key=lambda a: a["scrape_position"])
        rss_only  = [a for a in raw if not a.get("scrape_position")]
        display   = (editorial + rss_only)[:10]
        srcs[sid]={**s,"lean_label":li["label"],"lean_color":li["color"],"articles":display,"status":"ok" if sid in all_arts else "error"}
    with data_lock:
        data_store.update({"last_updated":datetime.utcnow().isoformat()+"Z","sources":srcs,"trending_topics":topics,
                           "twitter_trends":twitter_trends,"drudge_links":drudge_links,"facebook_posts":facebook_posts,
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
<title>Editorial Intelligence — TrendingInRealTime.com</title>
<link rel="icon" type="image/svg+xml" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'><rect width='32' height='32' rx='6' fill='%23BA032A'/><polyline points='4,24 10,16 16,20 22,10 28,6' fill='none' stroke='white' stroke-width='3' stroke-linecap='round' stroke-linejoin='round'/><circle cx='28' cy='6' r='2.5' fill='white'/></svg>">
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
.main{margin-left:256px;margin-top:64px;padding:20px 20px 24px;min-height:calc(100vh - 64px)}
.cgrid{display:grid;grid-template-columns:minmax(0,1fr) 280px;gap:20px;align-items:start}

/* SECTION HEADER */
.sec-hdr{display:flex;justify-content:space-between;align-items:flex-end;margin-bottom:16px}
.sec-title{font-family:'Newsreader',Georgia,serif;font-size:30px;font-weight:700;color:var(--navy-d);line-height:1.1}
.sec-sub{font-size:13px;color:var(--ink-l);margin-top:4px}
.bdg{padding:3px 8px;background:var(--surface-high);border-radius:2px;font-size:9px;font-weight:800;letter-spacing:.5px;font-family:'Inter',sans-serif;color:var(--ink-m)}

/* TRENDING TABLE */
.tbl-wrap{background:var(--surface-top);padding:2px;border-radius:3px;overflow-x:auto;margin-bottom:28px}
.tbl-inner{background:var(--surface-0);border-radius:3px;overflow:visible;box-shadow:0 1px 4px var(--sh)}
.topics-tbl{width:100%;border-collapse:collapse;table-layout:fixed}
.topics-tbl thead th{padding:10px 16px;font-size:9px;font-weight:800;color:var(--ink-l);text-transform:uppercase;letter-spacing:1.5px;background:var(--surface-low);border-bottom:1px solid var(--surface-high);text-align:left;font-family:'Inter',sans-serif}
.topics-tbl thead th.tc{text-align:center}
.topics-tbl thead th.tr2{text-align:right}
.th-r{width:56px}.th-s{width:108px}.th-v{width:112px}.th-g{width:80px}
.topics-tbl td{overflow:hidden}
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

/* SIDE BY SIDE PAGE */
.sbs-page{margin-left:256px;margin-top:64px;padding:28px 28px 40px;min-height:calc(100vh - 64px);display:none}
.sbs-hdr{margin-bottom:22px;padding-bottom:16px;border-bottom:2px solid var(--surface-top);display:flex;align-items:baseline;gap:16px}
.sbs-hdr h2{font-family:'Newsreader',Georgia,serif;font-size:26px;font-weight:700;color:var(--navy-d);margin:0}
.sbs-hdr p{font-size:12px;color:var(--ink-l);margin:0}
.sbs-grid{display:grid;grid-template-columns:1fr 1px 1fr;gap:0;align-items:start}
.sbs-divider{background:var(--surface-top);align-self:stretch;margin:0 28px}
.sbs-col-hd{padding-bottom:10px;border-bottom:2px solid var(--navy);margin-bottom:2px}
.sbs-col-title{font-family:'Newsreader',Georgia,serif;font-size:17px;font-weight:700;color:var(--navy-d);display:block}
.sbs-col-sub{font-size:10px;color:var(--ink-l);text-transform:uppercase;letter-spacing:.6px;display:block;margin-top:3px}
.sbs-row{display:flex;align-items:flex-start;gap:14px;padding:11px 0;border-bottom:1px solid var(--surface-low)}
.sbs-row:last-child{border-bottom:none}
.sbs-rank{font-family:'Newsreader',Georgia,serif;font-size:22px;font-weight:700;color:var(--red);min-width:30px;line-height:1.1;flex-shrink:0}
.sbs-body{}
.sbs-hl{font-family:'Newsreader',Georgia,serif;font-size:14px;color:var(--ink);line-height:1.45}
.sbs-hl a{color:var(--ink);text-decoration:none}
.sbs-hl a:hover{color:var(--red);text-decoration:underline}
.sbs-meta{font-size:11px;color:var(--ink-l);margin-top:4px;display:flex;align-items:center;gap:6px;flex-wrap:wrap}
.sbs-badge{display:inline-flex;align-items:center;font-size:9px;font-weight:700;padding:2px 6px;border-radius:2px;letter-spacing:.3px}
.sbs-dw-yes{background:rgba(21,128,61,.1);color:#15803D}
.sbs-top{background:var(--surface-top);color:var(--navy-d)}
</style></head><body>

<div id="ov"><div class="spin"></div><div class="ov-ttl">TrendingInRealTime.com</div><div class="ov-sub">Scanning 15 sources · Building intelligence report…</div></div>

<header class="topbar">
  <div class="tb-left">
    <span class="tb-brand">Editorial Intelligence</span>
    <nav class="tb-nav">
      <a href="#" class="tnav act" onclick="switchPage('dash');return false">Dashboard</a>
      <a href="#" class="tnav" onclick="switchPage('sbs');return false">Side by Side</a>
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
                <th class="th-v" title="Story trajectory since last refresh. Rising curve = gaining coverage across sources. Flat = no change. Falling = losing momentum.">Velocity</th>
                <th class="th-g tr2" title="Heat Score = weighted coverage strength. Formula: (sources × 12) + articles + (lead outlets × 20) + (double-confirmed × 10). Higher = more editors are leading with this story.">Signal</th>
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
          <button class="stab" onclick="switchTab('fb')"><span class="ms" style="font-size:14px">thumb_up</span>Facebook</button>
        </div>
        <div id="sp-dr" class="spanel active"><div id="dl"><div style="padding:16px;text-align:center;color:var(--ink-l);font-size:12px">Loading…</div></div></div>
        <div id="sp-tw" class="spanel"><div id="tl2"><div style="padding:16px;text-align:center;color:var(--ink-l);font-size:12px">Loading…</div></div></div>
        <div id="sp-fb" class="spanel"><div id="fl"><div style="padding:16px;text-align:center;color:var(--ink-l);font-size:12px">Loading…</div></div></div>
      </div>
    </aside>
  </div>
</main>

<div class="sbs-page" id="sbs-page">
  <div class="sbs-hdr">
    <h2>Side by Side</h2>
    <p>Cross-source trending vs. Daily Wire editorial picks</p>
  </div>
  <div class="sbs-grid">
    <div>
      <div class="sbs-col-hd">
        <span class="sbs-col-title">What's Trending</span>
        <span class="sbs-col-sub">Top 10 by cross-source heat score</span>
      </div>
      <div id="sbs-left"><div style="padding:20px;color:var(--ink-l);font-size:13px">Loading…</div></div>
    </div>
    <div class="sbs-divider"></div>
    <div>
      <div class="sbs-col-hd">
        <span class="sbs-col-title">Daily Wire Top Stories</span>
        <span class="sbs-col-sub">Editorial picks · refreshed each cycle</span>
      </div>
      <div id="sbs-right"><div style="padding:20px;color:var(--ink-l);font-size:13px">Loading…</div></div>
    </div>
  </div>
</div>

<button class="fab" onclick="fr()" title="Refresh data"><span class="ms" style="font-size:24px">refresh</span></button>

<script>
const SO=['foxnews','nypost','dailywire','breitbart','washtimes','townhall','ap','reuters','thehill','skynews','cnn','nytimes','nbcnews','dailymail','foxbusiness'];
const SA={foxnews:'FOX',cnn:'CNN',nytimes:'NYT',dailymail:'DM',nypost:'NYP',ap:'AP',reuters:'REU',nbcnews:'NBC',dailywire:'DW',breitbart:'BB',skynews:'SKY',thehill:'HILL',washtimes:'WT',foxbusiness:'FOXB',townhall:'TH'};
let _n=Date.now()+30*60*1000,_lastTs=null,_lastData=null,_page='dash';
function switchPage(pg){
  _page=pg;
  const isDash=pg==='dash';
  document.querySelector('.main').style.display=isDash?'block':'none';
  document.getElementById('sbs-page').style.display=isDash?'none':'block';
  document.querySelectorAll('.tnav').forEach((a,i)=>a.classList.toggle('act',['dash','sbs'][i]===pg));
  if(pg==='sbs'&&_lastData)renderSBS(_lastData);
}
function renderSBS(d){
  const topics=(d.trending_topics||[]).slice(0,10);
  const dwArts=((d.sources||{}).dailywire||{}).articles||[];
  const rk=i=>(i<9?'0':'')+(i+1);
  document.getElementById('sbs-left').innerHTML=topics.length?topics.map((t,i)=>{
    const dwOn=(t.sources||[]).includes('dailywire')||t.dw_covered;
    const badge=dwOn?'<span class="sbs-badge sbs-dw-yes" title="Daily Wire is covering this story">\u2713 DW</span>':'';
    return '<div class="sbs-row"><span class="sbs-rank">'+rk(i)+'</span><div class="sbs-body"><div class="sbs-hl">'+e(t.topic||t.keyword)+'</div><div class="sbs-meta"><span>'+t.source_count+' source'+(t.source_count!==1?'s':'')+'</span><span>Signal '+t.heat_score+'</span>'+badge+'</div></div></div>';
  }).join(''):'<div style="padding:20px;color:var(--ink-l);font-size:13px">No trending data yet.</div>';
  document.getElementById('sbs-right').innerHTML=dwArts.length?dwArts.slice(0,10).map((a,i)=>{
    const isTop=a.scrape_position&&a.scrape_position<=5;
    const age=a.pub_ts?'<span>'+ta(a.pub_ts)+'</span>':'';
    return '<div class="sbs-row"><span class="sbs-rank">'+rk(i)+'</span><div class="sbs-body"><div class="sbs-hl"><a href="'+e(a.link)+'" target="_blank">'+e(a.title)+'</a></div><div class="sbs-meta">'+(isTop?'<span class="sbs-badge sbs-top">Top Story</span>':'')+age+'</div></div></div>';
  }).join(''):'<div style="padding:20px;color:var(--ink-l);font-size:13px">Daily Wire articles loading…</div>';
}
function e(s){return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;')}
function ta(iso){if(!iso)return'';const d=Math.floor((Date.now()-new Date(iso))/1000);if(d<60)return d+'s ago';if(d<3600)return Math.floor(d/60)+'m ago';return Math.floor(d/3600)+'h ago'}
function fc(ms){if(ms<=0)return'Refreshing…';const m=Math.floor(ms/60000),s=Math.floor((ms%60000)/1000);return m+':'+String(s).padStart(2,'0')+' Refresh'}
function spark(delta,heat){
  const w=88,h=32;
  if(delta===null||delta===undefined){
    return '<span title="First data point — no previous refresh to compare against yet."><svg width="'+w+'" height="'+h+'" viewBox="0 0 '+w+' '+h+'"><path d="M0 16 L'+w+' 16" stroke="#c5c6ce" stroke-width="1.5" fill="none"/></svg></span>';
  }
  if(delta>0){
    const rise=Math.min(delta/(heat||1)*160,24);
    const p='M0 '+(h-4)+' L22 '+(h-4-rise*.25)+' L44 '+(h-4-rise*.55)+' L66 '+(h-4-rise*.82)+' L'+w+' '+Math.max(4,h-4-rise);
    return '<span title="Gaining momentum — heat score rose +'+delta+' points since last refresh. More sources picked this up or promoted it above the fold."><svg width="'+w+'" height="'+h+'" viewBox="0 0 '+w+' '+h+'"><path d="'+p+'" stroke="#BA032A" stroke-width="2.5" fill="none" stroke-linecap="round" stroke-linejoin="round"/></svg></span>';
  }
  const drop=Math.min(Math.abs(delta)/(heat||1)*160,24);
  const p='M0 4 L22 '+(4+drop*.25)+' L44 '+(4+drop*.55)+' L66 '+(4+drop*.82)+' L'+w+' '+Math.min(h-4,4+drop);
  return '<span title="Losing momentum — heat score fell '+Math.abs(delta)+' points since last refresh. Sources are moving on or deprioritising this story."><svg width="'+w+'" height="'+h+'" viewBox="0 0 '+w+' '+h+'"><path d="'+p+'" stroke="#c5c6ce" stroke-width="1.5" fill="none" stroke-linecap="round" stroke-linejoin="round"/></svg></span>';
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
    const brkBadge=t.is_breaking?'<span class="tag brk" title="Published within the last 90 minutes">Breaking</span>':'';
    const am=t.age_minutes;
    const ageBadge=(!t.is_breaking&&am!=null)?'<span class="tag age" title="Most recent article in this cluster was published '+(am<60?am+' minutes':Math.floor(am/60)+' hour'+(Math.floor(am/60)>1?'s':''))+' ago">'+(am<60?am+'m':Math.floor(am/60)+'h')+'</span>':'';
    const leadSrcs=(t.hero_sources||[]).join(', ');
    const leadBadge=heroSrcs.size>0?'<span class="tag lead" title="This story is the top headline at '+heroSrcs.size+(heroSrcs.size>1?' outlets':' outlet')+(leadSrcs?': '+leadSrcs:'')+'">Lead at '+heroSrcs.size+(heroSrcs.size>1?' outlets':' outlet')+'</span>':'';
    const d=t.delta;
    const dh=d===null||d===undefined?'':d>0?'<span class="sig-d" style="color:#15803D" title="Heat score rose +'+d+' points since last refresh (30 min ago)">\u25b2'+d+'</span>':d<0?'<span class="sig-d" style="color:#BA032A" title="Heat score fell '+Math.abs(d)+' points since last refresh (30 min ago)">\u25bc'+Math.abs(d)+'</span>':'<span class="sig-d" style="color:#9CA3AF" title="No change since last refresh">\u2014</span>';
    const arts=(t.articles||[]).map(a=>{
      const isH=a.feed_position===0||a.feed_position===1,isS=a.scrape_confirmed===true;
      const markTitle=isH&&isS?' title="\u2605\u2713 Double-confirmed: top 2 in RSS feed AND found on homepage"':isH?' title="\u2605 RSS hero: appeared in top 2 positions in this outlet\'s feed"':isS?' title="\u2713 Scrape confirmed: found on outlet\'s live homepage"':'';
      const mark=isH&&isS?' <span'+markTitle+'>\u2605\u2713</span>':isH?' <span'+markTitle+'>\u2605</span>':isS?' <span'+markTitle+'>\u2713</span>':'';
      const age=a.pub_ts?' <span style="color:var(--ink-l);font-size:10px">'+ta(a.pub_ts)+'</span>':'';
      return '<div class="a-row'+(isH||isS?' a-hero':'')+'"><div class="a-src">'+e(a.source_id)+mark+age+'</div><a href="'+e(a.link)+'" target="_blank" onclick="event.stopPropagation()">'+e(a.title)+'</a></div>';
    }).join('');
    const rn=(i<9?'0':'')+(i+1);
    return '<tr class="t-row" onclick="tg('+i+')">'
      +'<td><span class="rn '+(hot?'rn-h':'rn-n')+'">'+rn+'</span></td>'
      +'<td><div class="t-hl">'+e(t.keyword)+'</div><div class="t-tags">'+brkBadge+ageBadge+leadBadge+'</div></td>'
      +'<td><div class="chips">'+chips+'</div></td>'
      +'<td>'+spark(t.delta,t.heat_score)+'</td>'
      +'<td><span class="sig-n" title="Heat Score '+t.heat_score+': ('+((t.sources||[]).length)+' sources \xd7 12) + articles + (lead outlets \xd7 20) + (double-confirmed \xd7 10)">'+t.heat_score+'</span>'+dh+'<span class="ei-c" id="ei'+i+'">\u25b8</span></td>'
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
  document.querySelectorAll('.stab').forEach((b,i)=>{b.classList.toggle('active',['dr','tw','fb'][i]===tab)});
  document.querySelectorAll('.spanel').forEach((p,i)=>{p.classList.toggle('active',['sp-dr','sp-tw','sp-fb'][i]==='sp-'+tab)});
}
function fmtFb(n){if(n>=1000000)return(n/1000000).toFixed(1)+'M';if(n>=1000)return(n/1000).toFixed(1)+'k';return n}
function rFb(posts){
  const el=document.getElementById('fl');
  if(!posts||!posts.length){
    el.innerHTML='<div style="padding:16px;text-align:center;color:var(--ink-l);font-size:12px">No Facebook engagement data yet.<br><span style="font-size:11px;margin-top:4px;display:block">Checking article URLs against the Facebook Graph API.</span></div>';
    return;
  }
  if(posts.length===1&&posts[0].__unavailable){
    const reason=posts[0].reason?'<br><span style="font-size:10px;opacity:.7">'+e(posts[0].reason)+'</span>':'';
    el.innerHTML='<div style="padding:16px;text-align:center;color:var(--ink-l);font-size:12px">Facebook engagement unavailable.'+reason+'</div>';
    return;
  }
  const SA2={foxnews:'FOX',nypost:'NYP',dailywire:'DW',breitbart:'BB',washtimes:'WT',townhall:'TH',nytimes:'NYT',nbcnews:'NBC',dailymail:'DM',foxbusiness:'FOXB',skynews:'SKY',thehill:'HILL'};
  el.innerHTML=posts.map(p=>{
    const src=SA2[p.source]||(p.source||'').slice(0,4).toUpperCase();
    const tot=fmtFb(p.fb_total||0);
    const rx=fmtFb(p.fb_reactions||0);
    const sh=fmtFb(p.fb_shares||0);
    const cm=fmtFb(p.fb_comments||0);
    return '<div class="si"><a href="'+e(p.url)+'" target="_blank">'+e(p.title)+'</a>'
      +'<div class="si-m" title="'+tot+' total \u00b7 '+rx+' reactions \u00b7 '+sh+' shares \u00b7 '+cm+' comments">'
      +'<span style="background:#1877F2;color:#fff;border-radius:3px;padding:1px 5px;font-size:10px;font-weight:700;margin-right:5px">'+e(src)+'</span>'
      +'\uD83D\uDC4D\uFE0F '+rx+' \u00b7 \u{1F501} '+sh+' \u00b7 \u{1F4AC} '+cm
      +'</div></div>';
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
    _lastData=d;
    if(d.last_updated!==_lastTs){
      _lastTs=d.last_updated;
      rT(d.trending_topics);rFb(d.facebook_posts);rTw(d.twitter_trends);rDr(d.drudge_links);rS(d.sources);
      if(_page==='sbs')renderSBS(d);
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
    print("\n"+"="*60+"\n  TrendingInRealTime.com — Editorial Dashboard v2\n"+"="*60)
    print(f"\n  URL: http://localhost:{PORT}  |  {len(SOURCES)} sources  |  Ctrl+C to stop\n")
    threading.Thread(target=bg_loop,args=(1800,),daemon=True).start()
    if IS_LOCAL:
        threading.Timer(2.0,lambda:webbrowser.open(f'http://localhost:{PORT}')).start()
    app.run(host='0.0.0.0',port=PORT,debug=False,threaded=True,use_reloader=False)
