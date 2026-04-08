#!/usr/bin/env python3
"""
TrendingInRealTime.com — Editorial Intelligence Dashboard  v2
Newspaper theme. Clustering fix. 15 sources incl. NYT.
"""

import json, time, threading, re, sys, os, webbrowser, math, secrets
from datetime import datetime, timezone, timedelta
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed

def pip_install(pkg):
    print(f"  Installing {pkg}...")
    os.system(f'"{sys.executable}" -m pip install {pkg} --quiet --break-system-packages 2>/dev/null || "{sys.executable}" -m pip install {pkg} --quiet 2>/dev/null')

try: import feedparser
except ImportError: pip_install('feedparser'); import feedparser

try: from flask import Flask, jsonify, request
except ImportError: pip_install('flask'); from flask import Flask, jsonify, request

try: import requests; from bs4 import BeautifulSoup; HAS_SCRAPE = True
except ImportError:
    pip_install('requests'); pip_install('beautifulsoup4')
    try: import requests; from bs4 import BeautifulSoup; HAS_SCRAPE = True
    except: HAS_SCRAPE = False; print("  requests/bs4 unavailable — scraping disabled.")

# Session token — set once at startup, embedded in main page, required for /api/data
_SESSION_TOKEN = secrets.token_hex(16)

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
    "cbsnews":    "https://www.cbsnews.com",
    "washexam":   "https://www.washingtonexaminer.com",
}

SOURCES = [
    # Tier 1 — editorial homepage / top-story feeds where available
    {"id":"foxnews",    "name":"Fox News",          "rss":"https://feeds.foxnews.com/foxnews/latest", "lean":"right", "tier":1, "rss_limit":50},
    {"id":"cnn",        "name":"CNN",               "rss":"https://news.google.com/rss/search?q=site:cnn.com&ceid=US:en&hl=en-US&gl=US",  "lean":"left", "tier":1},
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
    {"id":"thehill",    "name":"The Hill",          "rss":"https://thehill.com/homenews/feed/",                        "lean":"center",       "tier":2},
    {"id":"washtimes",  "name":"Washington Times",  "rss":"https://www.washingtontimes.com/rss/headlines/news/",      "lean":"right",        "tier":2},
    {"id":"foxbusiness","name":"Fox Business",      "rss":"https://news.google.com/rss/search?q=site:foxbusiness.com&ceid=US:en&hl=en-US&gl=US", "lean":"right", "tier":2},
    {"id":"townhall",   "name":"Townhall",          "rss":"https://townhall.com/rss/tipsheet",                        "lean":"right",        "tier":2},
    # Tier 3 — new additions
    {"id":"cbsnews",    "name":"CBS News",          "rss":"https://www.cbsnews.com/latest/rss/main",                  "lean":"center-left",  "tier":2},
    {"id":"washexam",   "name":"Washington Examiner","rss":"https://news.google.com/rss/search?q=site:washingtonexaminer.com&ceid=US:en&hl=en-US&gl=US", "lean":"right", "tier":2},
    {"id":"freepress",  "name":"The Free Press",    "rss":"https://www.thefp.com/feed",                               "lean":"center-right", "tier":2},
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

data_store = {"last_updated":None,"sources":{},"trending_topics":[],"twitter_trends":[],"drudge_links":[],"reddit_posts":[],"bluesky_trends":[],"liberal_reddit":[],"last_hour":[],"sources_live":0,"loading":True}
data_lock = threading.Lock()

# Heat history for velocity sparklines.
# Keyed by frozenset of source IDs (stable across refreshes even when headline changes).
# Each entry stores the last 4 heat scores so the sparkline draws a real curve.
_heat_history = {}  # frozenset(source_ids) → [heat1, heat2, heat3, heat4]

# Google Trends cache — only re-fetch every 2 hours, back off 4h on failure
_gt_cache = {"data": [], "fetched_at": 0, "next_retry": 0}

# Blue Trends caches — 30-minute TTL, same cadence as main refresh
_BLUESKY_CACHE    = {"data": [], "fetched_at": 0}
_LIB_REDDIT_CACHE = {"data": [], "fetched_at": 0}

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
        # Use requests (with 15s timeout) to fetch raw RSS bytes, then hand to feedparser.
        # feedparser.parse(url) uses urllib with no timeout — one slow/hung feed blocks
        # the entire ThreadPoolExecutor and freezes the refresh cycle indefinitely.
        if HAS_SCRAPE:
            try:
                resp = requests.get(source["rss"], timeout=15, headers=_RSS_HEADERS)
                raw = resp.content
            except Exception as e:
                print(f"  {source['id']} RSS fetch error: {e}")
                return source["id"], []
            feed = feedparser.parse(raw)
        else:
            feed = feedparser.parse(source["rss"], request_headers=_RSS_HEADERS)
        if feed.bozo and not feed.entries: return source["id"], []
        arts = []
        cutoff = datetime.now(timezone.utc) - timedelta(hours=48)
        rss_limit = source.get("rss_limit", 20)
        for i, e in enumerate(feed.entries[:rss_limit]):
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
    Returns a 3-tuple: (headlines, url_map, orig_map) where:
      headlines = [(normalized_headline, page_position), ...] (1-based position)
      url_map   = {normalized_headline: article_url} (populated for all sources)
      orig_map  = {normalized_headline: original_case_title} (for synthetic injection)
    Position 1 = highest editorial placement on the page.

    Source-specific targeted scrapers run FIRST to lock in the correct editorial
    order for positions 1-N. The generic h1/h2/h3 scan fills in the rest.

    Synthetic injection in refresh_data() uses url_map to create articles for
    scraped editorial picks that have no matching RSS article (e.g. Fox pinned
    hero stories, CNN with a sparse RSS pool). URL capture now runs for all sources.

    Empty tuple returned on failure — scraping degrades gracefully."""
    if not HAS_SCRAPE:
        return [], {}, {}
    try:
        r = requests.get(url, timeout=10, headers={
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml',
        })
        r.raise_for_status()
        soup = BeautifulSoup(r.text, 'html.parser')

        # Derive this source's base URL for resolving relative hrefs
        _proto_end = url.find('://')
        _host_end  = url.find('/', _proto_end + 3) if _proto_end >= 0 else -1
        _site_base = url[:_host_end] if _host_end > 0 else url.rstrip('/')

        ordered      = []  # ordered list of normalized headline strings (de-duped)
        ordered_orig = []  # parallel list preserving original case
        seen    = set()
        url_map = {}  # norm → absolute article URL (all sources, where capturable)

        def add(text, href=None):
            norm = text.strip().lower()
            if 20 <= len(norm) <= 250 and norm not in seen:
                seen.add(norm)
                ordered.append(norm)
                ordered_orig.append(text.strip())
                if href:
                    if href.startswith('/'):
                        href = _site_base + href
                    if href.startswith('http'):
                        url_map[norm] = href

        def _nearest_href(tag):
            """Find the article href nearest to a headline tag.
            Checks parent <a> first (most common pattern), then the first <a>
            found in the containing article/div (for sites where <a> wraps both
            image and headline at the card level)."""
            parent_a = tag.find_parent('a', href=True)
            if parent_a:
                return parent_a['href']
            container = tag.find_parent(['article', 'div'])
            if container:
                a_tag = container.find('a', href=True)
                if a_tag:
                    return a_tag['href']
            return None

        # ── Source-specific targeted scrapers ─────────────────────────────────
        # These run BEFORE the generic h1/h2/h3 scan so editorial sections get
        # the lowest (best) position numbers in the ordered list.
        # Each targeted block captures both headline text AND article URLs.

        # --- Daily Wire: editorial 'Top Stories' widget (topStoryTextContainer h3) ---
        if sid == 'dailywire':
            for div in soup.find_all('div', class_=lambda c: c and 'topStoryTextContainer' in c):
                h3 = div.find('h3')
                if h3:
                    add(h3.get_text(separator=' ', strip=True), _nearest_href(h3))

        # --- Fox News: div.big-top (hero) + div.thumbs-2-7 (editorial grid) ---
        # Fox is server-side rendered — BeautifulSoup can parse the full layout.
        # These sections lock in positions 1-10 as Fox's actual editorial picks.
        if sid == 'foxnews':
            big_top = soup.find('div', class_='big-top')
            if big_top:
                for h in big_top.find_all(['h1', 'h2', 'h3']):
                    add(h.get_text(separator=' ', strip=True), _nearest_href(h))
            thumbs = soup.find('div', class_='thumbs-2-7')
            if thumbs:
                for h in thumbs.find_all(['h1', 'h2', 'h3']):
                    add(h.get_text(separator=' ', strip=True), _nearest_href(h))
            for div in soup.find_all('div', class_=lambda c: c and 'collection-article' in c):
                for h in div.find_all(['h2', 'h3']):
                    add(h.get_text(separator=' ', strip=True), _nearest_href(h))

        # --- CNN: article cards and lead-story containers ---
        # CNN's homepage uses container_lead-plus-headlines for the hero section
        # and individual <article> elements for story cards (SSR content).
        if sid == 'cnn':
            for div in soup.find_all('div', class_=lambda c: c and 'container_lead' in c):
                for h in div.find_all(['h2', 'h3']):
                    add(h.get_text(separator=' ', strip=True), _nearest_href(h))
            for article in soup.find_all('article'):
                h = article.find(['h2', 'h3'])
                if h:
                    add(h.get_text(separator=' ', strip=True), _nearest_href(h))

        # --- NBC News: article elements (SSR story cards, tight positions 2-13) ---
        if sid == 'nbcnews':
            for article in soup.find_all('article'):
                h = article.find(['h2', 'h3'])
                if h:
                    add(h.get_text(separator=' ', strip=True), _nearest_href(h))

        # --- NY Post: featured hero area + story cards ---
        if sid == 'nypost':
            for div in soup.find_all(['div', 'section'],
                                      class_=lambda c: c and any(x in str(c) for x in
                                      ['featured-area', 'top-story', 'story-layout--hero', 'primary-stories'])):
                for h in div.find_all(['h1', 'h2', 'h3']):
                    add(h.get_text(separator=' ', strip=True), _nearest_href(h))
            for article in soup.find_all('article', class_=lambda c: c and 'story' in str(c)):
                h = article.find(['h2', 'h3'])
                if h:
                    add(h.get_text(separator=' ', strip=True), _nearest_href(h))

        # --- Breitbart: hero story + story listing grid ---
        if sid == 'breitbart':
            for div in soup.find_all(['div', 'section'],
                                      class_=lambda c: c and any(x in str(c) for x in
                                      ['top-story', 'hero', 'primary-stories', 'main-column'])):
                for h in div.find_all(['h1', 'h2', 'h3']):
                    add(h.get_text(separator=' ', strip=True), _nearest_href(h))
            for article in soup.find_all('article'):
                h = article.find(['h1', 'h2', 'h3'])
                if h:
                    add(h.get_text(separator=' ', strip=True), _nearest_href(h))

        # --- NY Times: article elements (homepage RSS already editorial-ordered,
        #     but targeted scraping improves URL capture for synthetic injection) ---
        if sid == 'nytimes':
            for article in soup.find_all('article'):
                h = article.find(['h1', 'h2', 'h3'])
                if h:
                    add(h.get_text(separator=' ', strip=True), _nearest_href(h))

        # --- Sky News: article list items ---
        if sid == 'skynews':
            for article in soup.find_all(['article', 'li'],
                                          class_=lambda c: c and 'sdc-article' in str(c)):
                h = article.find(['h3', 'h2'])
                if h:
                    add(h.get_text(separator=' ', strip=True), _nearest_href(h))

        # ── Generic scan: all sources — h1/h2/h3 in document order ───────────
        # URL capture now runs here too (not just Fox), so all scraped headings
        # have associated article URLs available for synthetic injection.
        for tag in soup.find_all(['h1', 'h2', 'h3']):
            add(tag.get_text(separator=' ', strip=True), _nearest_href(tag))

        # --- Prominent anchor text (fallback for JS-heavy / non-semantic sites) ---
        for tag in soup.find_all('a', href=True):
            add(tag.get_text(separator=' ', strip=True))

        headlines = [(text, pos + 1) for pos, text in enumerate(ordered)]
        orig_map  = {norm: orig for norm, orig in zip(ordered, ordered_orig)}
        return headlines, url_map, orig_map

    except Exception as ex:
        print(f"  scrape {sid}: {ex}")
        return [], {}, {}

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


def fetch_memeorandum():
    """Scrape Memeorandum (memeorandum.com) for top political stories.
    Memeorandum is a political news aggregator that surfaces stories getting
    the most cross-blog/cross-media attention — a strong editorial signal.
    Simple static HTML, no API key, no auth required."""
    global _REDDIT_CACHE  # reusing cache slot; renamed in data_store as 'reddit_posts'
    now = time.time()
    if _REDDIT_CACHE["data"] and now - _REDDIT_CACHE["fetched_at"] < 1800:
        return _REDDIT_CACHE["data"]
    if not HAS_SCRAPE:
        return _REDDIT_CACHE["data"]
    try:
        r = requests.get(
            "https://www.memeorandum.com/",
            timeout=12,
            headers={
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml',
                'Accept-Language': 'en-US,en;q=0.9',
            }
        )
        r.raise_for_status()
        soup = BeautifulSoup(r.text, 'html.parser')
        stories = []
        seen = set()
        # Memeorandum structure (confirmed via browser inspection March 2026):
        #   div.item
        #     div.ii
        #       strong.L1/.L2/.L3/.L4  ← prominence tier
        #         a href="..."          ← main story headline
        #     div (no class)            ← "Discussion: Site A and Site B"
        for item in soup.find_all('div', class_='item'):
            ii = item.find('div', class_='ii')
            if not ii:
                continue
            strong = ii.find('strong')
            if not strong:
                continue
            a = strong.find('a', href=True)
            if not a:
                continue
            title = a.get_text(strip=True)
            link  = a.get('href', '#')
            if not title or title in seen or len(title) < 15:
                continue
            seen.add(title)
            # Count discussants: sibling divs containing "Discussion:" text
            discussants = 0
            for sibling in item.find_all('div'):
                if 'Discussion:' in sibling.get_text():
                    discussants = len(sibling.find_all('a', href=True))
                    break
            stories.append({"title": title, "link": link, "discussants": discussants})
            if len(stories) >= 20:
                break
        if stories:
            _REDDIT_CACHE = {"data": stories, "fetched_at": now}
            print(f"  Memeorandum: {len(stories)} stories")
        else:
            print("  Memeorandum: no stories parsed")
        return _REDDIT_CACHE["data"]
    except Exception as ex:
        print(f"  Memeorandum fetch error: {ex}")
        return _REDDIT_CACHE["data"]


def fetch_bluesky_trends():
    """Fetch trending topics from Bluesky via their public AT Protocol API.
    No API key required — uses the same endpoint the official Bluesky app uses.
    Returns list of dicts: {topic, displayName, postCount}
    Cache: 30 minutes."""
    global _BLUESKY_CACHE
    now = time.time()
    if _BLUESKY_CACHE["data"] and now - _BLUESKY_CACHE["fetched_at"] < 1800:
        return _BLUESKY_CACHE["data"]
    if not HAS_SCRAPE:
        return _BLUESKY_CACHE["data"]
    try:
        r = requests.get(
            "https://public.api.bsky.app/xrpc/app.bsky.unspecced.getTrendingTopics",
            params={"limit": 25},
            timeout=12,
            headers={"User-Agent": "TrendingInRealTime/1.0 (editorial research tool)"},
        )
        r.raise_for_status()
        data = r.json()
        topics = []
        for t in data.get("topics", []):
            name = t.get("displayName") or t.get("topic", "")
            tag  = t.get("topic", "")
            cnt  = t.get("postCount", 0)
            if not name:
                continue
            topics.append({"displayName": name, "topic": tag, "postCount": cnt})
        _BLUESKY_CACHE = {"data": topics, "fetched_at": now}
        print(f"  Bluesky trends: {len(topics)} topics")
        return topics
    except Exception as ex:
        print(f"  Bluesky trends error: {ex}")
        return _BLUESKY_CACHE["data"]


def fetch_liberal_reddit():
    """Fetch hot posts from liberal subreddits via Reddit's public RSS feeds.
    Uses feedparser (same library as all 15 news sources) — no OAuth, no API key.
    Subreddits: politics, progressive, liberal, democrats.
    Returns list of dicts: {title, url, subreddit, permalink}
    Cache: 30 minutes."""
    global _LIB_REDDIT_CACHE
    now = time.time()
    if _LIB_REDDIT_CACHE["data"] and now - _LIB_REDDIT_CACHE["fetched_at"] < 1800:
        return _LIB_REDDIT_CACHE["data"]
    if not HAS_SCRAPE:
        return _LIB_REDDIT_CACHE["data"]

    SUBREDDITS = ["politics", "progressive", "liberal", "democrats"]
    hdrs = {
        "User-Agent": "TrendingInRealTime/1.0 (editorial research bot; contact cwilliams@dwventures.com)",
        "Accept": "application/rss+xml, application/xml, text/xml, */*",
    }
    # Collect up to 8 posts per subreddit, then interleave so all 4 subs are represented
    per_sub = {sub: [] for sub in SUBREDDITS}
    seen_titles = set()
    for sub in SUBREDDITS:
        try:
            resp = requests.get(
                f"https://www.reddit.com/r/{sub}/hot.rss",
                params={"limit": 25},
                timeout=15,
                headers=hdrs,
            )
            resp.raise_for_status()
            feed = feedparser.parse(resp.content)
            for entry in feed.entries[:25]:
                if len(per_sub[sub]) >= 8:
                    break
                title = (entry.get("title") or "").strip()
                if not title or len(title) < 10:
                    continue
                # Reddit RSS wraps titles like: "r/politics: Some headline" — strip prefix
                if title.lower().startswith(f"r/{sub}:"):
                    title = title[len(f"r/{sub}:"):].strip()
                if not title or len(title) < 10:
                    continue
                title_key = title[:50].lower()
                if title_key in seen_titles:
                    continue
                seen_titles.add(title_key)
                link = entry.get("link", "")
                # RSS link is the reddit thread; try to get external article URL from summary
                summary = entry.get("summary", "")
                # Extract first href from summary HTML as the article URL if it's external
                import re as _re
                ext_urls = _re.findall(r'href="(https?://(?!www\.reddit\.com)[^"]+)"', summary)
                article_url = ext_urls[0] if ext_urls else link
                per_sub[sub].append({
                    "title":     title,
                    "url":       article_url,
                    "subreddit": sub,
                    "permalink": link,
                })
        except Exception as ex:
            print(f"  Liberal Reddit RSS ({sub}) error: {ex}")

    # Round-robin interleave so all subreddits appear throughout the list
    all_posts = []
    max_len = max((len(v) for v in per_sub.values()), default=0)
    for i in range(max_len):
        for sub in SUBREDDITS:
            if i < len(per_sub[sub]):
                all_posts.append(per_sub[sub][i])

    result = all_posts[:32]
    if result:
        _LIB_REDDIT_CACHE = {"data": result, "fetched_at": now}
        print(f"  Liberal Reddit RSS: {len(result)} posts across {len(SUBREDDITS)} subreddits")
    else:
        print("  Liberal Reddit RSS: no posts retrieved")
    return _LIB_REDDIT_CACHE["data"]


_FB_CACHE = {"data": [], "fetched_at": 0, "backoff_until": 0}

def fetch_facebook_engagement(all_arts):
    """Fetch Facebook engagement (reactions + shares + comments) for article URLs
    via the public Facebook Graph API URL endpoint — no API key required.
    Best signal for which stories are catching fire with the conservative Facebook audience.

    Skips Google News proxy sources (cnn, ap, reuters) since their URLs are google.com redirects.
    Fox News was previously skipped for the same reason but switched to a direct RSS feed.
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

    # Skip Google News proxy sources — their URLs are google.com redirects.
    # Reuters still uses Google News RSS (direct feed unavailable), so skip it.
    # CNN, AP, Fox News removed after switching to direct feeds (direct article URLs).
    SKIP_SOURCES = {"reuters"}
    candidates = []
    for sid, arts in all_arts.items():
        if sid in SKIP_SOURCES:
            continue
        for art in arts[:20]:
            url = art.get("link", "")
            if url and url.startswith("http") and "google.com" not in url:
                candidates.append({
                    "url":    url,
                    "title":  art.get("title", ""),
                    "source": sid,
                    "pub_ts": art.get("pub_ts", ""),
                })

    if not candidates:
        print("  Facebook: no candidates (all sources skipped or no URLs)")
        return _FB_CACHE.get("data", [])

    # Sort oldest-first so we check articles that have had the most time to
    # accumulate Facebook shares. Very recent articles (< 30 min) have near-zero
    # engagement and cause the entire sample to return empty.
    candidates.sort(key=lambda x: x.get("pub_ts") or "")

    FB_TOKEN = "1491126469205088|cd10efe58b5e4ee341710581b704bec7"
    first_error = []  # capture first error message for diagnostics
    first_response = []  # log first raw API response for diagnostics

    def fetch_one(item):
        try:
            r = requests.get(
                f"https://graph.facebook.com/v21.0/?id={item['url']}&fields=engagement&access_token={FB_TOKEN}",
                timeout=8,
                headers={"User-Agent": "TrendingInRealTime.com/2.0 (editorial dashboard)"},
            )
            data = r.json()
            # Log the first raw response so Railway logs show what's actually coming back
            if not first_response:
                first_response.append({"url": item['url'], "status": r.status_code, "data": data})
            if "error" in data:
                if not first_error:
                    first_error.append(data["error"])
                return None
            eng = data.get("engagement", {})
            total = (eng.get("reaction_count", 0) +
                     eng.get("share_count", 0) +
                     eng.get("comment_count", 0))
            if total >= 10:
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
        sample = candidates[:8]  # 10 calls/hour limit — stay well under with 8/cycle
        with ThreadPoolExecutor(max_workers=12) as ex:
            futures = [ex.submit(fetch_one, item) for item in sample]
            for f in as_completed(futures):
                r = f.result()
                if r:
                    results.append(r)

        if first_response:
            fr = first_response[0]
            print(f"  Facebook API first response [{fr['status']}] url={fr['url'][:60]} data={str(fr['data'])[:200]}")
        if first_error:
            print(f"  Facebook API error: {first_error[0]}")

        if not results and first_error:
            err_code = first_error[0].get("code", 0)
            err_type = first_error[0].get("type", "")
            err_msg  = first_error[0].get("message", "")
            print(f"  Facebook: no results — {err_type}: {err_msg}")
            # Rate limits: back off to avoid hammering the API
            if err_code == 4:
                display = "App rate limit reached."
                _FB_CACHE["backoff_until"] = now + 7200  # 2-hour backoff for app-level limit
            elif err_code == 613:
                display = "Rate limited (10 calls/hour). Will retry next hour."
                _FB_CACHE["backoff_until"] = now + 3600  # 1-hour backoff for per-hour limit
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

# Maximum scrape position to count as scrape-confirmed.
# Pages like Fox News (JS-rendered) return anchor links from sidebars/footers at positions
# 90–150+, which are NOT real editorial picks. Capping at 80 blocks these false positives
# while keeping all legitimate scrape hits (even long pages like CNN rarely exceed pos 75
# for meaningful above-the-fold content).
MAX_VALID_SCRAPE_POS = 80

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

# ── Story category classification ──────────────────────────────────────────
_INTL_KW = {
    'china','chinese','beijing','russia','russian','moscow','ukraine','ukrainian',
    'kyiv','iran','iranian','tehran','israel','israeli','gaza','palestine','palestinian',
    'europe','european','nato','britain','british','england','london','france','french',
    'paris','germany','german','berlin','canada','canadian','ottawa','mexico','mexican',
    'india','indian','pakistan','pakistani','afghanistan','afghan','korea','korean',
    'japan','japanese','taiwan','taiwanese','australia','australian','new zealand',
    'middle east','africa','african','latin america','eu ','european union','brussels',
    'kremlin','zelensky','netanyahu','modi','trudeau','macron','xi jinping','xi ',
    'ceasefire','cease-fire','foreign minister','diplomatic','embassy','sanctions',
    'g7','g20','imf','world bank','united nations','un security','interpol',
    'south china sea','black sea','red sea','strait of hormuz',
}
_SPORTS_KW = {
    'nfl','nba','mlb','nhl','nascar','fifa','mls','pga tour','ufc','mma','ncaa','espn',
    'super bowl','world cup','championship','playoffs','playoff','nfl draft','nba draft',
    'quarterback','pitcher','linebacker','goalie','touchdown','home run','slam dunk',
    'hat trick','overtime','halftime','inning','free throw','field goal',
    'stadium','arena','roster','free agency','trade deadline','signing bonus',
    'lakers','cowboys','patriots','eagles','chiefs','49ers','yankees','celtics',
    'lebron','mahomes','brady','curry','durant','jalen hurts','burrow',
    'olympics','olympic games','march madness','final four','world series',
    'wimbledon','us open','masters tournament','pga tour','tour de france',
    'formula 1','formula one','grand prix','soccer','basketball','baseball',
    'football game','hockey','tennis match','golf tournament',
}
_ENT_KW = {
    'hollywood','celebrity','celebrities','movie','film','box office',
    'tv show','television show','streaming','netflix','disney+','hulu','hbo max','prime video',
    'album','concert','tour','grammy','oscar','emmy','golden globe','tony award',
    'actor','actress','singer','rapper','musician','pop star',
    'trailer','movie premiere','episode','season finale','cast','director','producer',
    'kardashian','taylor swift','beyonce','drake','rihanna','kanye','spotify',
    'billboard','tiktok','viral video','influencer','reality tv','reality show',
    'red carpet','award show','music video','chart-topping','box-office',
    'superhero','marvel','dc comics','animated film','documentary film',
}
_BIZ_KW = {
    'stock market','stock price','shares','dow jones','nasdaq','s&p 500','wall street',
    'federal reserve','fed rate','interest rate','inflation','recession','gdp','economy',
    'economic growth','earnings report','quarterly earnings','revenue','profit','loss',
    'bankruptcy','merger','acquisition','ipo','hedge fund','private equity','venture capital',
    'bitcoin','cryptocurrency','crypto','ethereum','blockchain',
    'oil price','gas price','energy price','commodity','trade deficit','trade war',
    'tariff','tariffs','jobs report','unemployment rate','labor market','wage growth',
    'treasury','national debt','debt ceiling','federal budget','fiscal','monetary policy',
    'small business','corporation','ceo','executive','investor','investment',
    'housing market','mortgage rate','real estate market','retail sales',
}
_CRIME_KW = {
    'murder','homicide','killing','killed','shooting','gunshot','stabbing','stabbed',
    'robbery','robbed','theft','stolen','burglar','burglary','arson',
    'arrest','arrested','charged','indicted','convicted','sentenced','verdict','guilty','acquitted',
    'trial','defendant','suspect','fugitive','manhunt','wanted','on the run',
    'hostage','kidnap','kidnapping','abduction','abducted',
    'assault','sexual assault','rape','trafficking','human trafficking',
    'drug bust','drug trafficking','cartel','gang violence','organized crime',
    'serial killer','mass shooting','death toll','crime scene',
    'fbi investigation','doj investigation','grand jury','plea deal',
    'prison','jail','inmate','parole','probation','execution','death row',
    'police shooting','officer involved','bodycam','use of force',
}
_TECH_KW = {
    'artificial intelligence','ai model','machine learning','chatgpt','openai','anthropic',
    'google deepmind','large language model','llm','generative ai','ai-generated',
    'silicon valley','tech company','startup','venture capital','tech giant',
    'apple inc','microsoft','amazon','meta platforms','alphabet','nvidia','amd',
    'semiconductor','chip shortage','data center','cloud computing','aws','azure',
    'data breach','hacked','cybersecurity','cyber attack','ransomware','phishing',
    'social media platform','algorithm change','content moderation',
    'self-driving','autonomous vehicle','electric vehicle','spacex','rocket launch',
    'quantum computing','robotics','drone','surveillance tech','facial recognition',
    'elon musk','mark zuckerberg','sam altman','sundar pichai','satya nadella',
    'app store','smartphone','iphone','android','software update','operating system',
}
_HEALTH_KW = {
    'vaccine','vaccination','covid','pandemic','outbreak','epidemic','disease',
    'virus','bacteria','infection','contagious','quarantine','public health',
    'cancer','tumor','clinical trial','fda approval','drug approval','fda approves',
    'hospital','healthcare','health insurance','medicare','medicaid','aca',
    'surgery','diagnosis','treatment','therapy','prescription drug','opioid',
    'overdose','drug overdose','mental health','suicide rate','depression','anxiety',
    'cdc','nih','who ','world health','surgeon general',
    'obesity','diabetes','heart disease','alzheimer','dementia','rare disease',
    'medical research','scientists find','study finds','health warning',
    'birth rate','fertility','abortion','reproductive','planned parenthood',
}

# Priority order for ties — more specific categories beat broader ones
_CAT_PRIORITY = ['international','crime','sports','entertainment','business','technology','health','national']

def classify_category(titles):
    """Classify article titles into 1-2 categories (list). Returns ['national'] as default."""
    combined = ' ' + ' '.join(titles).lower() + ' '
    scores = {
        'international': sum(1 for kw in _INTL_KW   if kw in combined),
        'sports':        sum(1 for kw in _SPORTS_KW  if kw in combined),
        'entertainment': sum(1 for kw in _ENT_KW     if kw in combined),
        'business':      sum(1 for kw in _BIZ_KW     if kw in combined),
        'crime':         sum(1 for kw in _CRIME_KW   if kw in combined),
        'technology':    sum(1 for kw in _TECH_KW    if kw in combined),
        'health':        sum(1 for kw in _HEALTH_KW  if kw in combined),
    }
    best_score = max(scores.values())
    if best_score == 0:
        return ['national']
    # Collect all categories that hit the best score, in priority order, cap at 2
    winners = [cat for cat in _CAT_PRIORITY if scores.get(cat, 0) == best_score]
    return winners[:2] if winners else ['national']

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

    now_utc = datetime.now(timezone.utc)

    for idxs in raw_clusters:
        cl_arts = [flat[i] for i in idxs]

        # Only count a source if its article is either:
        #   (a) published within the last 4 hours — still actively in the news cycle, OR
        #   (b) scrape-confirmed — verified on the source's live homepage right now
        # This prevents stale Google News RSS articles (e.g. a 6h-old CNN piece that
        # Google still surfaces) from making it look like a source is currently covering
        # a story it has already moved on from.
        def is_credible(a):
            if a.get("scrape_confirmed"):
                return True
            pts = a.get("pub_ts")
            if pts:
                try:
                    age = (now_utc - datetime.fromisoformat(pts)).total_seconds() / 60
                    return age <= 240  # 4 hours
                except Exception:
                    pass
            return True  # no timestamp — give benefit of the doubt

        cl_srcs = set(a["source_id"] for a in cl_arts if is_credible(a))

        # Require at least 2 credible sources
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
                         "age_minutes": age_minutes, "is_breaking": is_breaking,
                         "category": classify_category([a["title"] for a in cl_arts])})

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
        # 1. Exact keyword intersection
        shared = cluster_kws & dw_kws
        if shared: return True, shared
        # 2. Prefix-aware match: catches olympic/olympics, transgender/trans, etc.
        #    Two keywords match if they share a common 5-char prefix (lightweight stemming).
        for ck in cluster_kws:
            if len(ck) < 5: continue
            pfx = ck[:5]
            for dk in dw_kws:
                if len(dk) >= 5 and dk[:5] == pfx:
                    return True, {ck}
        # 3. Substring fallback: cluster keyword appears inside a DW article title
        for a in dw:
            title_lower = a["title"].lower()
            for kw in cluster_kws:
                if len(kw) > 4 and kw in title_lower:
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
        scraped_pages    = {}  # sid → [(normalized_headline, position), ...]
        scraped_url_maps = {}  # sid → {norm_headline: article_url} (Fox editorial only)
        scraped_orig_maps= {}  # sid → {norm_headline: original_case_title}
        for f in as_completed(scrape_futures):
            sid = scrape_futures[f]
            result = f.result()
            # scrape_homepage() now returns (headlines, url_map, orig_map) 3-tuple
            if isinstance(result, tuple) and len(result) == 3:
                headlines, url_map, orig_map = result
            else:
                headlines, url_map, orig_map = result, {}, {}
            scraped_pages[sid] = headlines
            if url_map:    scraped_url_maps[sid] = url_map
            if orig_map:   scraped_orig_maps[sid] = orig_map
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
                    art["scrape_position"] = matched_pos
                    # Only mark confirmed if the position is within the valid editorial
                    # zone. JS-rendered sites (Fox News, Fox Business) return sidebar/footer
                    # anchor links at positions 90–150+ — these are NOT editorial picks.
                    art["scrape_confirmed"] = matched_pos <= MAX_VALID_SCRAPE_POS
                else:
                    art["scrape_confirmed"] = False

    # ── Synthetic editorial injection — all scraped sources ──────────────────
    # For any source where the RSS pool is missing editorial top stories
    # (chronological feeds, pinned hero stories, small pool), inject synthetic
    # articles for scraped editorial picks at positions 1–INJECT_LIMIT that have
    # no matching RSS article.
    #
    # Injected articles are scrape_confirmed=True, feed_position=0 (hero), and
    # flagged synthetic=True. They flow through clustering + heat scoring normally.
    #
    # URL quality gate: must be from the source's own domain AND have article-depth
    # path (≥ 2 path segments) to filter out section pages and nav links.
    #
    # Sources excluded from injection:
    #   dailymail — homepage dominated by celebrity/lifestyle, not top news
    #   reuters   — homepage blocked (0 scrape data), auto-skipped by url_map check
    #   thehill   — JS-rendered homepage (403), auto-skipped
    #   foxbusiness — JS-rendered homepage, auto-skipped
    INJECT_LIMIT    = 10
    SKIP_INJECT     = {'dailymail'}   # sources whose homepage mix makes injection unreliable

    # Junk filter for synthetic injection — blocks nav elements, promos, and ads
    # that pass the URL quality gate (depth ≥ 2) but aren't actual news headlines.
    _JUNK_TITLE_RE = re.compile(
        r'\d+\s*%\s*off'           # "60% Off"
        r'|vip\s+membership'       # "VIP Memberships"
        r'|^listen\s+to\b'         # "Listen to Sky News podcasts"
        r'|podcast'                # any podcast reference
        r'|newsletter'             # newsletter signups
        r'|site\s+information'     # "Site Information Navigation"
        r'|navigation$'            # ends with "Navigation"
        r'|–\s+top\s+stories$'     # "Source Name – Top Stories"
        r'|subscribe\b'            # subscribe prompts
        r'|sign\s+up\b'            # sign up prompts
        r'|^new!\s'                # "NEW! ..." promos
        r'|^new\s+live\b'          # "NEW Live sports talk show..."
        r'|get\s+today.s\s+top\s+stories'  # WashTimes newsletter promo
        r'|every\s+day\s+at\s+\d'  # "Every Day at 2PM" schedule promos
        r'|listen\s+to\s+the\s+front',  # "Listen to The Front" podcast promo
        re.IGNORECASE
    )
    _JUNK_PATH_RE = re.compile(
        r'/podcast|/subscribe|/newsletter|/membership|/about|/contact'
        r'|/privacy|/terms|/rss|/feeds|/apps|/store',
        re.IGNORECASE
    )

    def _is_junk_injection(title, href):
        if _JUNK_TITLE_RE.search(title):
            return True
        path = href.split('?')[0] if '?' in href else href
        if _JUNK_PATH_RE.search(path):
            return True
        return False

    total_injected = 0
    for inject_sid, inject_homepage_url in SCRAPE_SOURCES.items():
        if inject_sid in SKIP_INJECT:
            continue
        sc_list  = scraped_pages.get(inject_sid, [])
        iurl_map = scraped_url_maps.get(inject_sid, {})
        iorig_map= scraped_orig_maps.get(inject_sid, {})
        if not sc_list or not iurl_map:
            continue   # no scrape data or no URLs captured → nothing to inject

        # Derive source domain for URL validation (e.g. 'www.foxnews.com')
        _p = inject_homepage_url.find('://')
        _q = inject_homepage_url.find('/', _p + 3) if _p >= 0 else -1
        site_netloc = inject_homepage_url[_p+3:_q] if _q > 0 else inject_homepage_url[_p+3:]

        arts = all_arts.get(inject_sid, [])
        sc_texts = [text for text, _pos in sc_list]

        # Build set of scraped norms already matched to an RSS article
        already_matched = set()
        for art in arts:
            norm = art['title'].lower()
            for h in sc_texts:
                if (norm in h or h in norm or
                        (len(norm.split()) >= 4 and
                         len(set(norm.split()) & set(h.split())) / max(len(norm.split()), 1) >= 0.6)):
                    already_matched.add(h)
                    break

        injected = 0
        for h_norm, pos in sc_list:
            if pos > INJECT_LIMIT:
                break
            if h_norm in already_matched:
                continue
            href = iurl_map.get(h_norm)
            if not href:
                continue
            orig_title = iorig_map.get(h_norm, h_norm.title())
            # Skip nav elements, promos, ads, and podcast/newsletter links
            if _is_junk_injection(orig_title, href):
                continue
            # Must be from this source's own domain
            _hp = href.find('://')
            _hq = href.find('/', _hp + 3) if _hp >= 0 else -1
            href_netloc = href[_hp+3:_hq] if _hq > 0 else href[_hp+3:]
            if site_netloc not in href_netloc:
                continue
            # Must look like an article (path depth ≥ 2 segments)
            _path_start = href.find('/', _hp + 3) if _hp >= 0 else 0
            _path = href[_path_start:].split('?')[0] if _path_start else ''
            path_parts = [p for p in _path.split('/') if p]
            if len(path_parts) < 2:
                continue
            synthetic = {
                "title":            orig_title,
                "link":             href,
                "summary":          "",
                "published":        "",
                "pub_ts":           None,
                "feed_position":    0,
                "scrape_confirmed": True,
                "scrape_position":  pos,
                "synthetic":        True,
            }
            if inject_sid not in all_arts:
                all_arts[inject_sid] = []
            all_arts[inject_sid].append(synthetic)
            already_matched.add(h_norm)
            injected += 1
            print(f"  💉 {inject_sid} pos={pos}: {orig_title[:65]}")
        if injected:
            total_injected += injected
            print(f"  {inject_sid}: {injected} synthetic editorial articles injected")
    if total_injected:
        print(f"  Total synthetic injections: {total_injected} across all sources")

    print("  Fetching Drudge + Twitter/X + Memeorandum + Bluesky + Liberal Reddit...")
    drudge_links    = fetch_drudge()
    twitter_trends  = fetch_twitter_trends()
    reddit_posts    = fetch_memeorandum()
    bluesky_trends  = fetch_bluesky_trends()
    liberal_reddit  = fetch_liberal_reddit()
    print(f"  {'✓' if drudge_links else '✗'} Drudge: {len(drudge_links)} links")
    print(f"  {'✓' if twitter_trends else '✗'} Twitter/X: {len(twitter_trends)} trends")
    print(f"  {'✓' if reddit_posts else '✗'} Memeorandum: {len(reddit_posts)} stories")
    print(f"  {'✓' if bluesky_trends else '✗'} Bluesky: {len(bluesky_trends)} trends")
    print(f"  {'✓' if liberal_reddit else '✗'} Liberal Reddit: {len(liberal_reddit)} posts")
    topics = cluster_topics(all_arts)
    print(f"  → {len(topics)} trending topics")

    # Velocity sparklines: match clusters across refreshes by source-set Jaccard similarity.
    # Headlines change each cycle (TF-IDF picks a different representative each time),
    # so keying by headline text almost never matches. Source sets are stable — the same
    # story is covered by the same outlets across refreshes even if wording differs.
    global _heat_history
    new_history = {}
    for t in topics:
        cur_srcs = frozenset(t.get("sources", []))
        # Find the previous cluster with highest source overlap (Jaccard ≥ 0.33)
        best_key, best_sim = None, 0.0
        for key in _heat_history:
            inter = len(cur_srcs & key)
            union = len(cur_srcs | key)
            sim = inter / union if union > 0 else 0.0
            if sim > best_sim:
                best_sim, best_key = sim, key
        history = _heat_history[best_key] if best_key and best_sim >= 0.33 else []
        t["delta"] = (t["heat_score"] - history[-1]) if history else None
        t["heat_history"] = (history + [t["heat_score"]])[-4:]  # keep last 4 readings
        new_history[cur_srcs] = t["heat_history"]
    _heat_history = new_history

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
        for art in display:
            if "category" not in art:
                art["category"] = classify_category([art.get("title", "")])
        homepage = SCRAPE_SOURCES.get(sid, "")
        srcs[sid]={**s,"lean_label":li["label"],"lean_color":li["color"],"articles":display,"status":"ok" if sid in all_arts else "error","homepage":homepage}
    # ── Last Hour feed ────────────────────────────────────────────────────────
    # Collect every article published in the last 60 minutes across all sources,
    # sorted newest-first. Annotate with cluster_sources so the UI can show a
    # "X outlets" cross-signal badge when a breaking story is already clustering.
    lh_now = datetime.now(timezone.utc)
    lh_cutoff = lh_now - timedelta(hours=1)
    # Build title → cluster source count lookup from trending topics
    title_to_cluster_srcs = {}
    for t in topics:
        n = len(t.get("sources", []))
        for a in t.get("articles", []):
            title_to_cluster_srcs[a.get("title", "")] = n
    last_hour = []
    for s in SOURCES:
        sid = s["id"]
        li = LEAN.get(s.get("lean","center"), {"label":"Center","color":"#374151"})
        for art in all_arts.get(sid, []):
            pts = art.get("pub_ts")
            if not pts:
                continue
            try:
                pub = datetime.fromisoformat(pts)
                if pub < lh_cutoff:
                    continue
                age_min = max(0, int((lh_now - pub).total_seconds() / 60))
                last_hour.append({
                    "source_id":   sid,
                    "source_name": s["name"],
                    "lean_color":  li["color"],
                    "lean_label":  li["label"],
                    "title":       art.get("title", ""),
                    "link":        art.get("link", ""),
                    "pub_ts":      pts,
                    "age_minutes": age_min,
                    "cluster_sources": title_to_cluster_srcs.get(art.get("title",""), 0),
                    "category":    classify_category([art.get("title", "")]),
                })
            except Exception:
                continue
    last_hour.sort(key=lambda x: x["pub_ts"], reverse=True)

    with data_lock:
        data_store.update({"last_updated":datetime.now(timezone.utc).isoformat().replace('+00:00','Z'),"sources":srcs,"trending_topics":topics,
                           "twitter_trends":twitter_trends,"drudge_links":drudge_links,"reddit_posts":reddit_posts,"bluesky_trends":bluesky_trends,"liberal_reddit":liberal_reddit,
                           "last_hour":last_hour,"sources_live":len(all_arts),"loading":False})
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Done. {len(all_arts)}/{len(SOURCES)} live.\n")

def bg_loop(interval=1800):
    while True:
        try: refresh_data()
        except Exception as e: print(f"  Error: {e}"); data_store["loading"]=False
        time.sleep(interval)

app = Flask(__name__)

@app.route('/')
def index():
    from flask import make_response
    # Inject session token as a JS variable so it survives corporate proxies (Zscaler etc.)
    page = HTML.replace('/*__API_KEY__*/', f'const _API_KEY="{_SESSION_TOKEN}";', 1)
    resp = make_response(page, 200)
    resp.headers['Content-Type'] = 'text/html; charset=utf-8'
    return resp

@app.route('/bluetrends')
def bluetrends():
    from flask import make_response
    # Serve the main app with ?view=bt so JS auto-switches to Blue Trends on load
    page = HTML.replace('/*__API_KEY__*/', f'const _API_KEY="{_SESSION_TOKEN}";', 1)
    page = page.replace('let _n=Date.now()', 'const _INIT_VIEW="bt";let _n=Date.now()', 1)
    resp = make_response(page, 200)
    resp.headers['Content-Type'] = 'text/html; charset=utf-8'
    return resp

@app.route('/privacy')
def privacy():
    return ("""<!DOCTYPE html>
<html><head><title>Privacy Policy — TrendingInRealTime.com</title>
<style>body{font-family:sans-serif;max-width:800px;margin:60px auto;padding:0 24px;color:#333;line-height:1.7}
h1{font-size:24px;margin-bottom:8px}h2{font-size:18px;margin-top:32px}</style></head>
<body>
<h1>Privacy Policy</h1>
<p><strong>Last updated: March 31, 2026</strong></p>
<p>TrendingInRealTime.com is an internal editorial intelligence dashboard operated by Daily Wire Ventures.
This application is not a public-facing consumer product and is accessible only to authorized Daily Wire editorial staff.</p>
<h2>Data Collection</h2>
<p>This application does not collect, store, or share any personal data from users.
No user accounts are created. No personal information is transmitted to third parties.</p>
<h2>Facebook API Usage</h2>
<p>This application uses the Facebook Graph API solely to retrieve publicly available engagement
metrics (share counts, reactions) on published news article URLs. No user data, profile information,
or private content is accessed. All data retrieved is publicly available information.</p>
<h2>Cookies</h2>
<p>This application uses a single session cookie for internal authentication purposes only.
No tracking or advertising cookies are used.</p>
<h2>Contact</h2>
<p>For questions about this privacy policy, contact: cwilliams@dwventures.com</p>
</body></html>""", 200, {'Content-Type': 'text/html; charset=utf-8'})

@app.route('/robots.txt')
def robots():
    return ("User-agent: *\nDisallow: /api/\nDisallow: /debug/\n", 200, {'Content-Type': 'text/plain'})

@app.route('/api/data')
def api_data():
    if request.headers.get('X-Dashboard-Key') != _SESSION_TOKEN:
        ip = request.headers.get('X-Forwarded-For', request.remote_addr)
        ua = request.headers.get('User-Agent', 'unknown')
        print(f"403 BLOCKED | IP: {ip} | UA: {ua}", flush=True)
        return ('Forbidden', 403)
    with data_lock:
        ts = data_store.get('last_updated') or ''
        etag = f'"{hash(ts)}"'
        if request.headers.get('If-None-Match') == etag:
            return ('', 304)
        resp = jsonify(data_store)
        resp.headers['ETag'] = etag
        resp.headers['Cache-Control'] = 'no-store'
        return resp

@app.route('/api/refresh', methods=['POST'])
def api_refresh():
    threading.Thread(target=refresh_data,daemon=True).start()
    return jsonify({"status":"ok"})

@app.route('/debug/refresh')
def debug_refresh():
    """Run refresh_data() synchronously and return any exception. Diagnoses startup crashes."""
    import traceback
    try:
        refresh_data()
        with data_lock:
            return jsonify({"status": "ok", "sources_live": data_store.get("sources_live"), "last_updated": data_store.get("last_updated")})
    except Exception as ex:
        return jsonify({"error": str(ex), "traceback": traceback.format_exc()})

@app.route('/debug/fb')
def debug_fb():
    """Diagnostic endpoint: makes ONE live Facebook Graph API call and returns raw response.
    Useful for confirming API connectivity and permissions from Railway. DELETE after fix."""
    if not HAS_SCRAPE:
        return jsonify({"error": "requests not available"})
    FB_TOKEN = "1491126469205088|cd10efe58b5e4ee341710581b704bec7"
    test_url = "https://nypost.com/2025/01/15/us-news/trump-cabinet-picks/"
    try:
        r = requests.get(
            f"https://graph.facebook.com/v21.0/?id={test_url}&fields=engagement&access_token={FB_TOKEN}",
            timeout=10,
            headers={"User-Agent": "TrendingInRealTime.com/2.0 (editorial dashboard)"},
        )
        return jsonify({"status": r.status_code, "url_tested": test_url, "response": r.json()})
    except Exception as ex:
        return jsonify({"error": str(ex)})

@app.route('/debug/memo')
def debug_memo():
    """Diagnostic: fetch Memeorandum with correct selectors (div.item > div.ii > strong > a)."""
    if not HAS_SCRAPE:
        return jsonify({"error": "requests not available"})
    try:
        r = requests.get("https://www.memeorandum.com/", timeout=12, headers={
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
        })
        soup = BeautifulSoup(r.text, 'html.parser')
        stories = []
        for item in soup.find_all('div', class_='item')[:5]:
            ii = item.find('div', class_='ii')
            if not ii: continue
            strong = ii.find('strong')
            if not strong: continue
            a = strong.find('a', href=True)
            if a:
                stories.append({"title": a.get_text(strip=True), "link": a.get('href')})
        return jsonify({"status": r.status_code, "items_found": len(soup.find_all('div', class_='item')), "sample": stories})
    except Exception as ex:
        return jsonify({"error": str(ex)})

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

.live-dot{width:7px;height:7px;border-radius:50%;background:var(--red);animation:lp 2s infinite;box-shadow:0 0 8px rgba(186,3,42,.6)}
@keyframes lp{0%,100%{opacity:1}50%{opacity:.2}}
.sb-live{display:flex;align-items:center;gap:8px;padding:8px 10px;margin-bottom:12px;background:rgba(186,3,42,.06);border-radius:4px;border:1px solid rgba(186,3,42,.12)}
.sb-live-pill{display:flex;align-items:center;gap:5px}
.sb-live-txt{font-size:9px;font-weight:800;letter-spacing:2px;color:var(--red);text-transform:uppercase}
.sb-live-time{font-size:10px;color:var(--ink-l);font-variant-numeric:tabular-nums;margin-left:auto}

/* LEFT SIDEBAR */
.sidebar{position:fixed;top:0;left:0;bottom:0;width:256px;z-index:90;display:flex;flex-direction:column;padding:16px;background:#f2f4f6;border-right:1px solid var(--surface-top);overflow-y:auto}
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
.main{margin-left:256px;margin-top:0;padding:20px 20px 24px;min-height:100vh}
.cgrid{display:grid;grid-template-columns:minmax(0,1fr) 360px;gap:20px;align-items:start}

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
.rn-cat{display:flex;flex-direction:column;align-items:center;margin-top:4px;gap:2px}
.t-hl{font-family:'Newsreader',Georgia,serif;font-size:16px;font-weight:700;line-height:1.35;color:var(--ink);margin-bottom:6px}
.t-st{font-size:11px;color:var(--ink-m);margin-bottom:8px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;font-family:'Inter',sans-serif}
.t-tags{display:flex;align-items:center;gap:5px;flex-wrap:wrap}
.tag{padding:2px 7px;background:var(--surface-high);border-radius:2px;font-size:9px;font-weight:700;text-transform:uppercase;letter-spacing:.4px;font-family:'Inter',sans-serif;color:var(--ink-m)}
.tag.brk{background:rgba(186,3,42,.1);color:var(--red);animation:lp 1.5s infinite}
.tag.age{background:var(--surface-low);color:var(--ink-l);border:1px solid var(--surface-high)}
.tag.lead{background:var(--navy);color:#fff}
.tag.cat{border-radius:2px;font-size:9px;font-weight:700;text-transform:uppercase;letter-spacing:.4px}
.tag.cat-natl{background:#EFF6FF;color:#1D4ED8}
.tag.cat-intl{background:#F0FDFA;color:#0F766E}
.tag.cat-sport{background:#F0FDF4;color:#15803D}
.tag.cat-ent{background:#FFF7ED;color:#C2410C}
.tag.cat-biz{background:#F5F3FF;color:#6D28D9}
.tag.cat-crime{background:#FEF2F2;color:#991B1B}
.tag.cat-tech{background:#EEF2FF;color:#4338CA}
.tag.cat-health{background:#FDF2F8;color:#BE185D}
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

/* ── Responsive breakpoints ────────────────────────────────────────────── */
/* ── Mobile top header + hamburger drawer ──────────────────────────────── */
.mob-hdr{display:none;position:fixed;top:0;left:0;right:0;height:48px;z-index:300;
  background:#fff;border-bottom:2px solid var(--surface-top);
  align-items:center;justify-content:space-between;padding:0 16px 0 14px}
.mob-hdr-brand{display:flex;align-items:center;gap:9px}
.mob-hdr-icon{width:30px;height:30px;border-radius:2px;background:var(--navy);
  display:flex;align-items:center;justify-content:center;flex-shrink:0}
.mob-hdr-title{font-family:'Newsreader',Georgia,serif;font-size:15px;font-weight:700;color:var(--navy-d)}
.mob-hdr-right{display:flex;align-items:center;gap:10px}
.mob-live-pill{display:flex;align-items:center;gap:4px}
.mob-live-txt{font-size:8px;font-weight:800;letter-spacing:1.5px;color:var(--red);text-transform:uppercase}
.mob-cd{font-size:10px;color:var(--ink-l);font-variant-numeric:tabular-nums}
.mob-hbg{background:none;border:none;cursor:pointer;padding:4px;color:var(--navy-d);
  display:flex;align-items:center;justify-content:center;border-radius:4px}
.mob-hbg .ms{font-size:26px}
/* Drawer overlay */
.mob-overlay{display:none;position:fixed;inset:0;z-index:290;background:rgba(0,0,0,.35)}
.mob-overlay.open{display:block}
/* Drawer panel */
.mob-drawer{position:fixed;top:48px;right:-260px;bottom:0;width:240px;z-index:295;
  background:#fff;border-left:1px solid var(--surface-top);
  display:flex;flex-direction:column;padding:12px;
  box-shadow:-4px 0 20px rgba(0,0,0,.15);
  transition:right .22s cubic-bezier(.4,0,.2,1);overflow-y:auto}
.mob-drawer.open{right:0}
.mob-drawer .sb-lnk{font-size:14px;padding:11px 14px;border-radius:4px}
.mob-drawer-live{display:flex;align-items:center;gap:8px;padding:8px 10px;
  margin-bottom:12px;background:rgba(186,3,42,.06);border-radius:4px;
  border:1px solid rgba(186,3,42,.12)}

/* ── All ≤900px mobile overrides in one block ──────────────────────────── */
@media(max-width:900px){
  .mob-hdr{display:flex}
  .sidebar{display:none}
  /* Main pages: remove sidebar offset, add top padding for mob-hdr */
  .main{margin-left:0;padding-top:56px;padding-bottom:76px}
  .lh-page{margin-left:0!important;padding-top:56px!important;padding-bottom:76px!important}
  .sbs-page{margin-left:0!important;padding:56px 16px 76px!important}
  .cgrid{grid-template-columns:1fr}
  .fab{display:none}
  .mob-nav{display:flex}
  /* Side by Side: stack columns vertically */
  .sbs-hdr{flex-direction:column!important;align-items:flex-start!important;gap:4px!important}
  .sbs-hdr h2{font-size:22px!important}
  .sbs-grid{display:block!important;grid-template-columns:unset!important}
  .sbs-divider{display:none!important}
  .sbs-grid>div+div+div{margin-top:28px!important;padding-top:20px!important;border-top:2px solid var(--surface-top)!important}
}

/* ── sec-hdr: stack on mobile, hide decorative date/badge ─────────────── */
@media(max-width:600px){
  .sec-hdr{flex-direction:column;align-items:flex-start;gap:6px}
  .sec-hdr > div:last-child{display:none}
}

/* ── Responsive trending table (mobile card layout) ───────────────────── */
@media(max-width:600px){
  .topics-tbl,.topics-tbl tbody{display:block;width:100%}
  .topics-tbl thead{display:none}
  .topics-tbl tbody tr.t-row{
    display:grid;
    grid-template-columns:44px 1fr auto;
    grid-template-rows:auto auto;
    padding:10px 8px;cursor:pointer;
    border-bottom:1px solid var(--surface-top);background:inherit}
  .topics-tbl tbody tr.t-row td{display:block;overflow:visible;padding:0}
  .topics-tbl tbody tr.t-row td:nth-child(1){grid-column:1;grid-row:1/3;padding-top:2px}
  .topics-tbl tbody tr.t-row td:nth-child(2){grid-column:2;grid-row:1}
  .topics-tbl tbody tr.t-row td:nth-child(3){grid-column:2;grid-row:2;padding-top:5px}
  .topics-tbl tbody tr.t-row td:nth-child(4){display:none}
  .topics-tbl tbody tr.t-row td:nth-child(5){grid-column:3;grid-row:1/3;padding-left:10px;text-align:right;padding-top:2px}
  .topics-tbl tbody tr.x-row{display:block;width:100%}
  .topics-tbl tbody tr.x-row td{display:block;padding:0 8px 12px 52px!important}
  .t-hl{font-size:15px}
  .sig-n{font-size:18px}
  .rn{font-size:20px!important}
}

/* ── Mobile bottom navigation bar ─────────────────────────────────────── */
.mob-nav{display:none;position:fixed;bottom:0;left:0;right:0;z-index:200;
  background:#fff;border-top:2px solid var(--surface-top);
  padding-bottom:env(safe-area-inset-bottom,0px);height:60px}
.mob-nav-item{display:flex;flex-direction:column;align-items:center;justify-content:center;
  flex:1;height:100%;font-size:8.5px;font-weight:700;letter-spacing:.03em;
  color:var(--ink-l);text-decoration:none;gap:1px;transition:color .15s;
  text-transform:uppercase;padding:4px 2px 0;position:relative}
.mob-nav-item .ms{font-size:21px;line-height:1}
.mob-nav-item.active{color:var(--red)}
.mob-lh-badge{display:none;position:absolute;top:4px;right:calc(50% - 18px);
  background:var(--red);color:#fff;border-radius:8px;font-size:8px;
  font-weight:800;padding:1px 4px;line-height:1.4}
/* ── Last Hour tab ─────────────────────────────────────────────────────── */
.lh-page{margin-left:256px;margin-top:0;padding:28px 28px 40px;min-height:100vh;display:none;max-width:900px}
.lh-hdr{margin-bottom:22px;padding-bottom:16px;border-bottom:2px solid var(--surface-top);display:flex;align-items:baseline;gap:16px}
.lh-hdr h2{font-family:'Newsreader',Georgia,serif;font-size:26px;font-weight:700;color:var(--navy-d);margin:0}
.lh-hdr p{font-size:12px;color:var(--ink-l);margin:0}
.lh-count{font-size:11px;font-weight:700;background:var(--red);color:#fff;border-radius:10px;padding:2px 7px;margin-left:4px;vertical-align:middle}
.lh-item{padding:11px 0;border-bottom:1px solid var(--surface-low);display:flex;flex-direction:column;gap:4px}
.lh-item:last-child{border-bottom:none}
.lh-eyebrow{display:flex;align-items:center;gap:8px;font-size:10px;font-weight:800;text-transform:uppercase;letter-spacing:.08em}
.lh-src{padding:2px 6px;border-radius:3px;color:#fff;font-size:9px;font-weight:800;letter-spacing:.04em}
.lh-time{font-size:10px;color:var(--ink-l)}
.lh-hl{font-family:'Newsreader',Georgia,serif;font-size:15px;line-height:1.45;color:var(--ink)}
.lh-hl a{color:inherit;text-decoration:none}
.lh-hl a:hover{color:var(--red)}
.lh-fresh{display:inline-flex;align-items:center;gap:4px;font-size:9px;font-weight:800;color:var(--red);text-transform:uppercase;letter-spacing:.06em}
.lh-fresh-dot{width:6px;height:6px;border-radius:50%;background:var(--red);animation:pulse 1.4s infinite}
.lh-signal{display:inline-flex;align-items:center;font-size:9px;font-weight:700;background:var(--navy);color:#fff;border-radius:3px;padding:2px 6px;letter-spacing:.04em}
.lh-empty{padding:40px 0;text-align:center;color:var(--ink-l);font-size:13px}
.lh-section-hdr{font-size:9px;font-weight:800;text-transform:uppercase;letter-spacing:.1em;color:var(--ink-l);padding:14px 0 4px;border-top:2px solid var(--surface-top);margin-top:4px}
.lh-section-hdr:first-child{border-top:none;padding-top:0}
@media(max-width:1024px){.lh-page{margin-left:0}}

/* SIDE BY SIDE PAGE */
.sbs-page{margin-left:256px;margin-top:0;padding:28px 28px 40px;min-height:100vh;display:none}
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

/* BLUE TRENDS PAGE */
.bt-page{margin-left:256px;margin-top:0;padding:28px 28px 40px;min-height:100vh;display:none}
.bt-hdr{margin-bottom:22px;padding-bottom:16px;border-bottom:2px solid var(--surface-top);display:flex;align-items:baseline;gap:16px}
.bt-hdr h2{font-family:'Newsreader',Georgia,serif;font-size:26px;font-weight:700;color:var(--navy-d);margin:0}
.bt-hdr p{font-size:12px;color:var(--ink-l);margin:0}
.bt-grid{display:grid;grid-template-columns:1fr 1px 1fr;gap:0;align-items:start}
.bt-divider{background:var(--surface-top);align-self:stretch;margin:0 28px}
.bt-col{}
.bt-col-hd{display:flex;align-items:flex-start;gap:10px;padding-bottom:10px;border-bottom:2px solid var(--navy);margin-bottom:2px}
.bt-col-icon{flex-shrink:0;margin-top:2px}
.bt-col-title{font-family:'Newsreader',Georgia,serif;font-size:17px;font-weight:700;color:var(--navy-d);display:block}
.bt-col-sub{font-size:10px;color:var(--ink-l);text-transform:uppercase;letter-spacing:.6px;display:block;margin-top:3px}
.bt-item{padding:10px 0;border-bottom:1px solid var(--surface-low);display:flex;align-items:flex-start;gap:12px}
.bt-item:last-child{border-bottom:none}
.bt-rank{font-family:'Newsreader',Georgia,serif;font-size:20px;font-weight:700;color:#1d9bf0;min-width:28px;flex-shrink:0;line-height:1.2}
.bt-body{}
.bt-title{font-family:'Newsreader',Georgia,serif;font-size:14px;color:var(--ink);line-height:1.4}
.bt-title a{color:var(--ink);text-decoration:none}
.bt-title a:hover{color:#1d9bf0;text-decoration:underline}
.bt-meta{font-size:11px;color:var(--ink-l);margin-top:4px;display:flex;align-items:center;gap:6px;flex-wrap:wrap}
.bt-sub-badge{font-size:9px;font-weight:700;padding:2px 6px;border-radius:2px;letter-spacing:.3px;background:#ff450018;color:#cc3700}
.bt-loading{padding:20px;color:var(--ink-l);font-size:13px}
@media(max-width:1024px){.bt-page{margin-left:0}}
@media(max-width:900px){
  .bt-page{margin-left:0!important;padding:56px 16px 76px!important}
  .bt-hdr{flex-direction:column!important;align-items:flex-start!important;gap:4px!important}
  .bt-hdr h2{font-size:22px!important}
  .bt-grid{display:block!important;grid-template-columns:unset!important}
  .bt-divider{display:none}
  .bt-col{margin-bottom:28px}
}
</style></head><body>

<div id="ov"><div class="spin"></div><div class="ov-ttl">TrendingInRealTime.com</div><div class="ov-sub">Scanning 15 sources · Building intelligence report…</div></div>

<!-- Mobile top header bar -->
<div class="mob-hdr" id="mob-hdr">
  <div class="mob-hdr-brand">
    <div class="mob-hdr-icon"><span class="ms" style="color:#fff;font-size:17px">psychology</span></div>
    <span class="mob-hdr-title">Intelligence Ops</span>
  </div>
  <div class="mob-hdr-right">
    <div class="mob-live-pill"><span class="live-dot"></span><span class="mob-live-txt">Live</span></div>
    <span class="mob-cd" id="cd-mob"></span>
    <button class="mob-hbg" onclick="toggleDrawer()" aria-label="Open navigation">
      <span class="ms" id="mob-hbg-icon">menu</span>
    </button>
  </div>
</div>

<!-- Drawer backdrop -->
<div class="mob-overlay" id="mob-overlay" onclick="closeDrawer()"></div>

<!-- Mobile nav drawer (slides in from right) -->
<div class="mob-drawer" id="mob-drawer">
  <nav class="sb-nav" style="gap:4px">
    <a href="#" class="sb-lnk act" id="drw-topics" onclick="switchPage('dash');closeDrawer();return false">
      <span class="ms">local_fire_department</span><span>Topic Intelligence</span>
    </a>
    <a href="#" class="sb-lnk" id="drw-live" onclick="switchPage('dash','live-feed-section');closeDrawer();return false">
      <span class="ms">newspaper</span><span>Live Source Feed</span>
    </a>
    <a href="#" class="sb-lnk" id="drw-social" onclick="switchPage('dash','social-velocity-section');closeDrawer();return false">
      <span class="ms">trending_up</span><span>Social Velocity</span>
    </a>
    <a href="#" class="sb-lnk" id="drw-sbs" onclick="switchPage('sbs');closeDrawer();return false">
      <span class="ms">compare_arrows</span><span>Side by Side</span>
    </a>
    <a href="#" class="sb-lnk" id="drw-lh" onclick="switchPage('lh');closeDrawer();return false">
      <span class="ms">schedule</span>
      <span style="display:flex;align-items:center;gap:6px">Last Hour<span class="lh-count" id="lh-badge-drw" style="display:none">0</span></span>
    </a>
    <a href="#" class="sb-lnk" id="drw-bt" onclick="switchPage('bt');closeDrawer();return false" style="margin-top:4px;border-top:1px solid var(--surface-high);padding-top:10px">
      <span class="ms" style="color:#1d9bf0">sentiment_very_dissatisfied</span>
      <span style="color:#1d9bf0;font-weight:600">Blue Trends</span>
    </a>
  </nav>
</div>

<aside class="sidebar">
  <div class="sb-brand">
    <div class="sb-icon"><span class="ms" style="color:#fff;font-size:22px">psychology</span></div>
    <div><div class="sb-title">Intelligence Ops</div><div class="sb-sub">Global Newsroom</div></div>
  </div>
  <div class="sb-live">
    <div class="sb-live-pill"><span class="live-dot"></span><span class="sb-live-txt">Live</span></div>
    <span class="sb-live-time" id="cd"></span>
  </div>
  <nav class="sb-nav">
    <a href="#" class="sb-lnk act" id="nav-topics" onclick="switchPage('dash');return false">
      <span class="ms">local_fire_department</span><span>Topic Intelligence</span>
    </a>
    <a href="#" class="sb-lnk" id="nav-live" onclick="switchPage('dash','live-feed-section');return false">
      <span class="ms">newspaper</span><span>Live Source Feed</span>
    </a>
    <a href="#" class="sb-lnk" id="nav-social" onclick="switchPage('dash','social-velocity-section');return false">
      <span class="ms">trending_up</span><span>Social Velocity</span>
    </a>
    <a href="#" class="sb-lnk" id="nav-sbs" onclick="switchPage('sbs');return false">
      <span class="ms">compare_arrows</span><span>Side by Side</span>
    </a>
    <a href="#" class="sb-lnk" id="nav-lh" onclick="switchPage('lh');return false">
      <span class="ms">schedule</span>
      <span style="display:flex;align-items:center;gap:6px">Last Hour<span class="lh-count" id="lh-badge" style="display:none">0</span></span>
    </a>
    <a href="#" class="sb-lnk" id="nav-bt" onclick="switchPage('bt');return false" style="margin-top:4px;border-top:1px solid var(--surface-high);padding-top:10px">
      <span class="ms" style="color:#1d9bf0">sentiment_very_dissatisfied</span>
      <span style="color:#1d9bf0;font-weight:600">Blue Trends</span>
    </a>
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
      <div class="feed-hdr" id="live-feed-section">
        <h3>Live Source Feed</h3>
        <div class="feed-div"></div>
        <span style="font-size:11px;color:var(--ink-l);white-space:nowrap" id="es">—</span>
      </div>
      <div class="src-grid" id="sg"></div>
    </section>
    <aside>
      <div class="panel" id="social-velocity-section">
        <div class="panel-hd"><span class="ms" style="color:var(--red)">trending_up</span><h3>Social Velocity</h3></div>
        <div class="stabs">
          <button class="stab active" onclick="switchTab('dr')"><span class="ms" style="font-size:14px">campaign</span>Drudge</button>
          <button class="stab" onclick="switchTab('tw')"><span class="ms" style="font-size:14px">tag</span>Twitter</button>
          <button class="stab" onclick="switchTab('re')"><span class="ms" style="font-size:14px">hub</span>Memo</button>
        </div>
        <div id="sp-dr" class="spanel active"><div id="dl"><div style="padding:16px;text-align:center;color:var(--ink-l);font-size:12px">Loading…</div></div></div>
        <div id="sp-tw" class="spanel"><div id="tl2"><div style="padding:16px;text-align:center;color:var(--ink-l);font-size:12px">Loading…</div></div></div>
        <div id="sp-re" class="spanel"><div id="rl"><div style="padding:16px;text-align:center;color:var(--ink-l);font-size:12px">Loading…</div></div></div>
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

<div class="lh-page" id="lh-page">
  <div class="lh-hdr">
    <h2>Last Hour</h2>
    <p>Every article published across all 15 outlets in the past 60 minutes · newest first</p>
  </div>
  <div id="lh-feed"><div class="lh-empty">Loading…</div></div>
</div>

<div class="bt-page" id="bt-page">
  <div class="bt-hdr">
    <h2>Blue Trends</h2>
    <p>What's generating engagement on the left — Bluesky trending topics &amp; top liberal Reddit posts</p>
  </div>
  <div class="bt-grid">
    <div class="bt-col">
      <div class="bt-col-hd">
        <span class="bt-col-icon" style="color:#1d9bf0"><svg width="18" height="18" viewBox="0 0 360 320" fill="currentColor"><path d="M180 142c-15-47-61-82-110-82C31 60 0 93 0 133c0 74 76 116 180 187 104-71 180-113 180-187 0-40-31-73-70-73-49 0-95 35-110 82z"/></svg></span>
        <div><div class="bt-col-title">Bluesky Trending</div><div class="bt-col-sub">Top topics right now on Bluesky</div></div>
      </div>
      <div id="bt-bsky"><div class="bt-loading">Loading…</div></div>
    </div>
    <div class="bt-divider"></div>
    <div class="bt-col">
      <div class="bt-col-hd">
        <span class="bt-col-icon" style="color:#ff4500"><svg width="18" height="18" viewBox="0 0 20 20" fill="currentColor"><circle cx="10" cy="10" r="10"/><path fill="#fff" d="M16.67 10a1.46 1.46 0 0 0-2.47-1 7.12 7.12 0 0 0-3.85-1.23l.65-3.08 2.13.45a1 1 0 1 0 .42-.83l-2.38-.5a.25.25 0 0 0-.3.19l-.73 3.44a7.14 7.14 0 0 0-3.89 1.23 1.46 1.46 0 1 0-1.61 2.39 2.87 2.87 0 0 0 0 .44c0 2.24 2.61 4.06 5.83 4.06s5.83-1.82 5.83-4.06a2.87 2.87 0 0 0 0-.44 1.46 1.46 0 0 0 .27-.06zM7.5 11a1 1 0 1 1 1 1 1 1 0 0 1-1-1zm5.57 2.65a3.53 3.53 0 0 1-2 .46 3.53 3.53 0 0 1-2-.46.25.25 0 0 1 .35-.35 3.08 3.08 0 0 0 1.68.37 3.08 3.08 0 0 0 1.68-.37.25.25 0 0 1 .35.35zm-.07-1.65a1 1 0 1 1 1-1 1 1 0 0 1-1 1z"/></svg></span>
        <div><div class="bt-col-title">Liberal Reddit Hot</div><div class="bt-col-sub">r/politics · r/progressive · r/liberal · r/democrats</div></div>
      </div>
      <div id="bt-reddit"><div class="bt-loading">Loading…</div></div>
    </div>
  </div>
</div>

<!-- Mobile bottom navigation — visible on screens ≤900px -->
<nav class="mob-nav">
  <a href="#" class="mob-nav-item active" id="mob-topics" onclick="switchPage('dash');return false">
    <span class="ms">local_fire_department</span><span>Topics</span>
  </a>
  <a href="#" class="mob-nav-item" id="mob-live" onclick="switchPage('dash','live-feed-section');return false">
    <span class="ms">newspaper</span><span>Sources</span>
  </a>
  <a href="#" class="mob-nav-item" id="mob-social" onclick="switchPage('dash','social-velocity-section');return false">
    <span class="ms">trending_up</span><span>Social</span>
  </a>
  <a href="#" class="mob-nav-item" id="mob-sbs" onclick="switchPage('sbs');return false">
    <span class="ms">compare_arrows</span><span>Side by Side</span>
  </a>
  <a href="#" class="mob-nav-item" id="mob-lh" onclick="switchPage('lh');return false">
    <span class="ms">schedule</span><span>Last Hour</span>
    <span class="mob-lh-badge" id="mob-lh-badge">0</span>
  </a>
</nav>

<button class="fab" onclick="fr()" title="Refresh data"><span class="ms" style="font-size:24px">refresh</span></button>

<script>
const SO=['nytimes','foxnews','dailywire','dailymail','ap','thehill','washtimes','reuters','nbcnews','cnn','townhall','skynews','foxbusiness','nypost','breitbart','cbsnews','washexam','freepress'];
const SA={foxnews:'FOX',cnn:'CNN',nytimes:'NYT',dailymail:'DM',nypost:'NYP',ap:'AP',reuters:'REU',nbcnews:'NBC',dailywire:'DW',breitbart:'BB',skynews:'SKY',thehill:'HILL',washtimes:'WT',foxbusiness:'FOXB',townhall:'TH',cbsnews:'CBS',washexam:'EXAM',freepress:'FP'};
let _n=Date.now()+30*60*1000,_lastTs=null,_lastData=null,_page='dash';
function switchPage(pg, scrollTo){
  _page=pg;
  document.querySelector('.main').style.display=pg==='dash'?'block':'none';
  document.getElementById('sbs-page').style.display=pg==='sbs'?'block':'none';
  document.getElementById('lh-page').style.display=pg==='lh'?'block':'none';
  document.getElementById('bt-page').style.display=pg==='bt'?'block':'none';

  // Determine which sidebar nav item is "active" (scroll-to items map back to 'dash')
  const activeNav = scrollTo==='live-feed-section' ? 'nav-live'
                  : scrollTo==='social-velocity-section' ? 'nav-social'
                  : pg==='dash' ? 'nav-topics'
                  : pg==='sbs'  ? 'nav-sbs'
                  : pg==='lh'   ? 'nav-lh'
                  : pg==='bt'   ? 'nav-bt' : '';
  document.querySelectorAll('.sb-lnk').forEach(a=>a.classList.remove('act'));
  if(activeNav){const el=document.getElementById(activeNav);if(el)el.classList.add('act');}

  // Mobile bottom nav active state
  const activeMob = scrollTo==='live-feed-section' ? 'mob-live'
                  : scrollTo==='social-velocity-section' ? 'mob-social'
                  : pg==='dash' ? 'mob-topics'
                  : pg==='sbs'  ? 'mob-sbs'
                  : pg==='lh'   ? 'mob-lh'
                  : pg==='bt'   ? 'mob-bt' : '';
  document.querySelectorAll('.mob-nav-item').forEach(a=>a.classList.remove('active'));
  if(activeMob){const el=document.getElementById(activeMob);if(el)el.classList.add('active');}
  // Sync drawer nav active state
  const activeDrw = scrollTo==='live-feed-section' ? 'drw-live'
                  : scrollTo==='social-velocity-section' ? 'drw-social'
                  : pg==='dash' ? 'drw-topics'
                  : pg==='sbs'  ? 'drw-sbs'
                  : pg==='lh'   ? 'drw-lh'
                  : pg==='bt'   ? 'drw-bt' : '';
  document.querySelectorAll('.mob-drawer .sb-lnk').forEach(a=>a.classList.remove('act'));
  if(activeDrw){const el=document.getElementById(activeDrw);if(el)el.classList.add('act');}

  if(pg==='sbs'&&_lastData)renderSBS(_lastData);
  if(pg==='lh'&&_lastData)rLH(_lastData.last_hour||[]);
  if(pg==='bt'&&_lastData)rBT(_lastData);

  // Scroll to sub-section if requested (e.g. Live Source Feed, Social Velocity)
  if(scrollTo){
    setTimeout(()=>{
      const t=document.getElementById(scrollTo);
      if(t)t.scrollIntoView({behavior:'smooth',block:'start'});
    },50);
  } else {
    window.scrollTo({top:0,behavior:'smooth'});
  }
}
// ── Last Hour render ───────────────────────────────────────────────────────
function rLH(arts){
  const el=document.getElementById('lh-feed');
  if(!arts||!arts.length){el.innerHTML='<div class="lh-empty">No articles published in the last hour yet.<br><span style="font-size:11px;margin-top:4px;display:block">Check back after the next refresh cycle.</span></div>';return;}
  // Update badge (sidebar + mobile)
  const badge=document.getElementById('lh-badge');
  badge.textContent=arts.length;badge.style.display='';
  const mbadge=document.getElementById('mob-lh-badge');
  if(mbadge){mbadge.textContent=arts.length;mbadge.style.display='';}
  const dbadge=document.getElementById('lh-badge-drw');
  if(dbadge){dbadge.textContent=arts.length;dbadge.style.display='';}
  // Split into two buckets: just published (< 15 min) and earlier (15–60 min)
  const fresh=arts.filter(a=>a.age_minutes<15);
  const older=arts.filter(a=>a.age_minutes>=15);
  function renderItem(a){
    const freshMark=a.age_minutes<15
      ?'<span class="lh-fresh"><span class="lh-fresh-dot"></span>Just now</span> '
      :'';
    const signal=a.cluster_sources>=2
      ?'<span class="lh-signal" title="Already clustering — '+a.cluster_sources+' outlets covering this story on the Dashboard">\u26a1 '+a.cluster_sources+' outlets</span> '
      :'';
    const mins=a.age_minutes<1?'<1m ago':a.age_minutes+'m ago';
    return '<div class="lh-item">'
      +'<div class="lh-eyebrow"><span class="lh-src" style="background:'+e(a.lean_color)+'">'+e(a.source_name)+'</span>'
      +'<span class="lh-time">'+mins+'</span>'
      +catBadge(a.category)+freshMark+signal+'</div>'
      +'<div class="lh-hl"><a href="'+e(a.link)+'" target="_blank">'+e(a.title)+'</a></div>'
      +'</div>';
  }
  let html='';
  if(fresh.length){
    html+='<div class="lh-section-hdr">\u26a1 Just Published — last 15 minutes ('+fresh.length+')</div>';
    html+=fresh.map(renderItem).join('');
  }
  if(older.length){
    html+='<div class="lh-section-hdr">Earlier this hour ('+older.length+')</div>';
    html+=older.map(renderItem).join('');
  }
  el.innerHTML=html;
}
function renderSBS(d){
  const topics=(d.trending_topics||[]).slice(0,10);
  const dwArts=((d.sources||{}).dailywire||{}).articles||[];
  const rk=i=>(i<9?'0':'')+(i+1);
  document.getElementById('sbs-left').innerHTML=topics.length?topics.map((t,i)=>{
    const dwOn=(t.sources||[]).includes('dailywire')||t.dw_covered;
    const badge=dwOn?'<span class="sbs-badge sbs-dw-yes" title="Daily Wire is covering this story">\u2713 DW</span>':'';
    return '<div class="sbs-row"><span class="sbs-rank">'+rk(i)+'</span><div class="sbs-body"><div class="sbs-hl">'+e(t.topic||t.keyword)+'</div><div class="sbs-meta">'+catBadge(t.category)+'<span>'+t.source_count+' source'+(t.source_count!==1?'s':'')+'</span><span>Signal '+t.heat_score+'</span>'+badge+'</div></div></div>';
  }).join(''):'<div style="padding:20px;color:var(--ink-l);font-size:13px">No trending data yet.</div>';
  document.getElementById('sbs-right').innerHTML=dwArts.length?dwArts.slice(0,10).map((a,i)=>{
    const isTop=a.scrape_position&&a.scrape_position<=5;
    const age=a.pub_ts?'<span>'+ta(a.pub_ts)+'</span>':'';
    return '<div class="sbs-row"><span class="sbs-rank">'+rk(i)+'</span><div class="sbs-body"><div class="sbs-hl"><a href="'+e(a.link)+'" target="_blank">'+e(a.title)+'</a></div><div class="sbs-meta">'+catBadge(a.category)+(isTop?'<span class="sbs-badge sbs-top">Top Story</span>':'')+age+'</div></div></div>';
  }).join(''):'<div style="padding:20px;color:var(--ink-l);font-size:13px">Daily Wire articles loading…</div>';
}
function e(s){return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;')}
function ta(iso){if(!iso)return'';const d=Math.floor((Date.now()-new Date(iso))/1000);if(d<60)return d+'s ago';if(d<3600)return Math.floor(d/60)+'m ago';return Math.floor(d/3600)+'h ago'}
function fc(ms){if(ms<=0)return'Refreshing…';const m=Math.floor(ms/60000),s=Math.floor((ms%60000)/1000);return m+':'+String(s).padStart(2,'0')+' Refresh'}
function spark(delta,heat,history){
  const w=88,h=32,pad=4;
  // With a real history array, draw a true multi-point curve
  if(history&&history.length>=2){
    const mn=Math.min(...history),mx=Math.max(...history);
    const range=mx-mn||1;
    const pts=history.map((v,i)=>{
      const x=pad+(i/(history.length-1))*(w-pad*2);
      const y=pad+(1-(v-mn)/range)*(h-pad*2);
      return x+' '+y;
    });
    const p='M'+pts.join(' L');
    const rising=history[history.length-1]>history[0];
    const flat=history[history.length-1]===history[0];
    const color=rising?'#BA032A':flat?'#c5c6ce':'#c5c6ce';
    const sw=rising?'2.5':'1.5';
    const tip=delta===null?'First reading':delta>0?'Gaining momentum — +'+delta+' pts since last refresh':delta<0?'Losing momentum — '+delta+' pts since last refresh':'No change since last refresh';
    return '<span title="'+tip+'"><svg width="'+w+'" height="'+h+'" viewBox="0 0 '+w+' '+h+'"><path d="'+p+'" stroke="'+color+'" stroke-width="'+sw+'" fill="none" stroke-linecap="round" stroke-linejoin="round"/></svg></span>';
  }
  // Fallback: single delta point (first refresh or no history)
  if(delta===null||delta===undefined){
    return '<span title="First data point — velocity will appear after next refresh."><svg width="'+w+'" height="'+h+'" viewBox="0 0 '+w+' '+h+'"><path d="M'+pad+' '+(h/2)+' L'+(w-pad)+' '+(h/2)+'" stroke="#e2e8f0" stroke-width="1.5" fill="none"/></svg></span>';
  }
  if(delta>0){
    const rise=Math.min(delta/(heat||1)*160,24);
    const p='M0 '+(h-pad)+' L22 '+(h-pad-rise*.25)+' L44 '+(h-pad-rise*.55)+' L66 '+(h-pad-rise*.82)+' L'+w+' '+Math.max(pad,h-pad-rise);
    return '<span title="Gaining momentum — heat score rose +'+delta+' points since last refresh."><svg width="'+w+'" height="'+h+'" viewBox="0 0 '+w+' '+h+'"><path d="'+p+'" stroke="#BA032A" stroke-width="2.5" fill="none" stroke-linecap="round" stroke-linejoin="round"/></svg></span>';
  }
  const drop=Math.min(Math.abs(delta)/(heat||1)*160,24);
  const p='M0 '+pad+' L22 '+(pad+drop*.25)+' L44 '+(pad+drop*.55)+' L66 '+(pad+drop*.82)+' L'+w+' '+Math.min(h-pad,pad+drop);
  return '<span title="Losing momentum — heat score fell '+Math.abs(delta)+' points since last refresh."><svg width="'+w+'" height="'+h+'" viewBox="0 0 '+w+' '+h+'"><path d="'+p+'" stroke="#c5c6ce" stroke-width="1.5" fill="none" stroke-linecap="round" stroke-linejoin="round"/></svg></span>';
}
const _CAT_LABEL={'national':'Natl','international':'Intl','sports':'Sport','entertainment':'Ent','business':'Biz','crime':'Crime','technology':'Tech','health':'Health'};
const _CAT_CLS={'national':'cat-natl','international':'cat-intl','sports':'cat-sport','entertainment':'cat-ent','business':'cat-biz','crime':'cat-crime','technology':'cat-tech','health':'cat-health'};
function catBadge(cats){
  const arr=Array.isArray(cats)?cats:[cats||'national'];
  return arr.map(cat=>{
    const lbl=_CAT_LABEL[cat]||'Natl',cls=_CAT_CLS[cat]||'cat-natl';
    return '<span class="tag cat '+cls+'">'+lbl+'</span>';
  }).join('');
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
      +'<td><span class="rn '+(hot?'rn-h':'rn-n')+'">'+rn+'</span><div class="rn-cat">'+catBadge(t.category)+'</div></td>'
      +'<td><div class="t-hl">'+e(t.keyword)+'</div><div class="t-tags">'+brkBadge+ageBadge+leadBadge+'</div></td>'
      +'<td><div class="chips">'+chips+'</div></td>'
      +'<td>'+spark(t.delta,t.heat_score,t.heat_history)+'</td>'
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
  document.querySelectorAll('.stab').forEach((b,i)=>{b.classList.toggle('active',['dr','tw','re'][i]===tab)});
  document.querySelectorAll('.spanel').forEach((p,i)=>{p.classList.toggle('active',['sp-dr','sp-tw','sp-re'][i]==='sp-'+tab)});
}
function fmtK(n){if(n>=1000000)return(n/1000000).toFixed(1)+'M';if(n>=1000)return(n/1000).toFixed(1)+'k';return n}
function rRe(posts){
  const el=document.getElementById('rl');
  if(!posts||!posts.length){
    el.innerHTML='<div style="padding:16px;text-align:center;color:var(--ink-l);font-size:12px">Memeorandum unavailable.<br><span style="font-size:11px;margin-top:4px;display:block">Fetching top political stories…</span></div>';
    return;
  }
  el.innerHTML=posts.map((p,i)=>{
    const disc=p.discussants>0?'<span style="color:var(--ink-l);font-size:10px">\u00b7 '+p.discussants+' sources discussing</span>':'';
    return '<div class="si">'
      +'<a href="'+e(p.link)+'" target="_blank" rel="noopener">'+e(p.title)+'</a>'
      +'<div class="si-m">'
      +'<span style="background:#1a5276;color:#fff;border-radius:3px;padding:1px 5px;font-size:10px;font-weight:700;margin-right:5px">MEMO</span>'
      +disc
      +'</div></div>';
  }).join('');
}
function rTw(trends){
  const el=document.getElementById('tl2');
  if(!trends||!trends.length){el.innerHTML='<div style="padding:16px;text-align:center;color:var(--ink-l);font-size:12px">Twitter/X trends unavailable</div>';return}
  el.innerHTML=trends.slice(0,25).map((t,i)=>'<div class="tw-r"><span class="tw-rk">'+(i+1)+'</span><span class="tw-tm"><a href="https://x.com/search?q='+encodeURIComponent(t)+'&src=trend_click" target="_blank" rel="noopener" style="color:inherit;text-decoration:none;" onmouseover="this.style.textDecoration=\'underline\'" onmouseout="this.style.textDecoration=\'none\'">'+e(t)+'</a></span><div class="tw-bw"><div class="tw-bg"><div class="tw-bf" style="width:'+Math.round(((25-i)/25)*100)+'%"></div></div></div></div>').join('');
}
function rDr(links){
  const el=document.getElementById('dl');
  if(!links||!links.length){el.innerHTML='<div style="padding:16px;text-align:center;color:var(--ink-l);font-size:12px">Drudge unavailable</div>';return}
  el.innerHTML=links.map(l=>'<div class="si"><a href="'+e(l.link)+'" target="_blank">'+e(l.title)+'</a></div>').join('');
}
// ── Blue Trends render ─────────────────────────────────────────────────────
function rBT(d){
  const bskyEl=document.getElementById('bt-bsky');
  const redEl=document.getElementById('bt-reddit');
  if(!bskyEl||!redEl)return;

  // Bluesky trending topics
  const topics=(d.bluesky_trends||[]);
  // Update subtitle with actual count
  const bskySubEl=bskyEl.closest('.bt-col')&&bskyEl.closest('.bt-col').querySelector('.bt-col-sub');
  if(bskySubEl&&topics.length)bskySubEl.textContent=topics.length+' topic'+(topics.length===1?'':'s')+' trending on Bluesky right now';
  if(!topics.length){
    bskyEl.innerHTML='<div class="bt-loading">Bluesky trending data unavailable.<br><span style="font-size:11px;margin-top:4px;display:block">Will retry next refresh cycle.</span></div>';
  } else {
    bskyEl.innerHTML=topics.map((t,i)=>{
      const cnt=t.postCount?'<span>'+fmtK(t.postCount)+' posts</span>':'';
      // Link to Bluesky search — use hashtag URL if topic starts with #, else plain search
      const searchQ=t.topic||t.displayName;
      const searchUrl='https://bsky.app/search?q='+encodeURIComponent(searchQ);
      return '<div class="bt-item">'
        +'<div class="bt-rank">'+(i+1)+'</div>'
        +'<div class="bt-body">'
        +'<div class="bt-title" style="font-weight:600"><a href="'+searchUrl+'" target="_blank" rel="noopener" style="color:#1d9bf0;text-decoration:none" onmouseover="this.style.textDecoration=\'underline\'" onmouseout="this.style.textDecoration=\'none\'">'+e(t.displayName)+'</a></div>'
        +(cnt?'<div class="bt-meta">'+cnt+'</div>':'')
        +'</div></div>';
    }).join('');
  }

  // Liberal Reddit hot posts
  const posts=d.liberal_reddit||[];
  const subColors={politics:'#ff4500',progressive:'#7e22ce',liberal:'#2563eb',democrats:'#1d4ed8'};
  if(!posts.length){
    redEl.innerHTML='<div class="bt-loading">Liberal Reddit data unavailable.<br><span style="font-size:11px;margin-top:4px;display:block">Will retry next refresh cycle.</span></div>';
  } else {
    redEl.innerHTML=posts.map((p,i)=>{
      const clr=subColors[p.subreddit]||'#ff4500';
      const hasExt=p.url&&p.url!==p.permalink;
      return '<div class="bt-item">'
        +'<div class="bt-rank" style="color:#ff4500">'+(i+1)+'</div>'
        +'<div class="bt-body">'
        +'<div class="bt-title"><a href="'+e(hasExt?p.url:p.permalink)+'" target="_blank" rel="noopener">'+e(p.title)+'</a></div>'
        +'<div class="bt-meta">'
        +'<span style="background:'+clr+'18;color:'+clr+';font-size:9px;font-weight:700;padding:2px 6px;border-radius:2px;letter-spacing:.3px">r/'+e(p.subreddit)+'</span>'
        +(hasExt?'<a href="'+e(p.permalink)+'" target="_blank" rel="noopener" style="color:var(--ink-l);font-size:10px;text-decoration:none">discussion →</a>':'')
        +'</div></div></div>';
    }).join('');
  }
}

function rS(srcs){
  if(!srcs)return;
  window._L={};Object.entries(srcs).forEach(([id,s])=>window._L[id]=s.lean_color);
  const ord=[...SO.filter(id=>srcs[id]),...Object.keys(srcs).filter(id=>!SO.includes(id))];
  document.getElementById('sg').innerHTML=ord.map(sid=>{
    const s=srcs[sid];if(!s)return'';
    const arts=s.articles||[];
    return '<div class="sc" style="border-top-color:'+e(s.lean_color)+'">'
      +'<div class="sc-hd"><span class="sc-nm">'+(s.homepage?'<a href="'+e(s.homepage)+'" target="_blank" style="color:inherit;text-decoration:none;border-bottom:1px solid currentColor;padding-bottom:1px">'+e(s.name)+'</a>':e(s.name))+'</span>'
      +'<span class="sc-ln" style="background:'+e(s.lean_color)+'18;color:'+e(s.lean_color)+'">'+e(s.lean_label)+'</span></div>'
      +(arts.length?arts.map(a=>'<div class="sc-art"><a href="'+e(a.link)+'" target="_blank">'+e(a.title)+'</a></div>').join(''):'<div class="sc-empty">Feed unavailable</div>')
      +'</div>';
  }).join('');
}
/*__API_KEY__*/
let _etag='';
async function ld(){
  try{
    const hdrs={'X-Dashboard-Key':_API_KEY};
    if(_etag)hdrs['If-None-Match']=_etag;
    const res=await fetch('/api/data',{headers:hdrs});
    if(res.status===304)return;
    if(res.headers.get('ETag'))_etag=res.headers.get('ETag');
    const d=await res.json();
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
      rT(d.trending_topics);rRe(d.reddit_posts);rTw(d.twitter_trends);rDr(d.drudge_links);rS(d.sources);
      if(_page==='bt')rBT(d);
      if(_page==='sbs')renderSBS(d);
      // Always update LH badge count; re-render feed if on that tab
      const lhArts=d.last_hour||[];
      const lhBadge=document.getElementById('lh-badge');
      if(lhArts.length){lhBadge.textContent=lhArts.length;lhBadge.style.display='';}else{lhBadge.style.display='none';}
      if(_page==='lh')rLH(lhArts);
    }
  }catch(ex){setTimeout(ld,5000)}
}
async function fr(){
  document.getElementById('ov').classList.remove('h');
  try{await fetch('/api/refresh',{method:'POST'})}catch(ex){}
  _n=Date.now()+30*60*1000;_lastTs=null;setTimeout(ld,3000);
}
setInterval(()=>{
  const r=_n-Date.now(),txt=fc(r);
  document.getElementById('cd').textContent=txt;
  const cdm=document.getElementById('cd-mob');if(cdm)cdm.textContent=txt;
  if(r<=0){_n=Date.now()+30*60*1000;ld()}
},1000);

function toggleDrawer(){
  const dr=document.getElementById('mob-drawer'),ov=document.getElementById('mob-overlay'),ic=document.getElementById('mob-hbg-icon');
  const open=dr.classList.toggle('open');
  ov.classList.toggle('open',open);
  ic.textContent=open?'close':'menu';
}
function closeDrawer(){
  document.getElementById('mob-drawer').classList.remove('open');
  document.getElementById('mob-overlay').classList.remove('open');
  document.getElementById('mob-hbg-icon').textContent='menu';
}

if(typeof _INIT_VIEW!=='undefined'&&_INIT_VIEW)switchPage(_INIT_VIEW);
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
