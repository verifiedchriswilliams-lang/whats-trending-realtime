#!/usr/bin/env python3
"""
WhatsTrendingInRealTime.com — Editorial Intelligence Dashboard  v2
Newspaper theme. Clustering fix. 15 sources incl. NYT.
"""

import json, time, threading, re, sys, os, webbrowser
from datetime import datetime
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed

def pip_install(pkg):
    print(f"  Installing {pkg}...")
    os.system(f'"{sys.executable}" -m pip install {pkg} --quiet --break-system-packages 2>/dev/null || "{sys.executable}" -m pip install {pkg} --quiet 2>/dev/null')

try: import feedparser
except ImportError: pip_install('feedparser'); import feedparser

try: from flask import Flask, jsonify
except ImportError: pip_install('flask'); from flask import Flask, jsonify

try:
    from pytrends.request import TrendReq; HAS_PYTRENDS = True
except ImportError:
    pip_install('pytrends')
    try: from pytrends.request import TrendReq; HAS_PYTRENDS = True
    except: HAS_PYTRENDS = False; print("  pytrends unavailable.")

SOURCES = [
    {"id":"foxnews",    "name":"Fox News",          "rss":"https://feeds.foxnews.com/foxnews/latest",                  "lean":"right",        "tier":1},
    {"id":"cnn",        "name":"CNN",               "rss":"https://rss.cnn.com/rss/cnn_topstories.rss",               "lean":"left",         "tier":1},
    {"id":"nytimes",    "name":"New York Times",    "rss":"https://rss.nytimes.com/services/xml/rss/nyt/HomePage.xml","lean":"left",         "tier":1},
    {"id":"dailymail",  "name":"Daily Mail",        "rss":"https://www.dailymail.co.uk/news/index.rss",               "lean":"center-right", "tier":1},
    {"id":"nypost",     "name":"NY Post",           "rss":"https://nypost.com/feed/",                                 "lean":"right",        "tier":1},
    {"id":"ap",         "name":"AP News",           "rss":"https://feeds.apnews.com/apnews/topnews",                  "lean":"center",       "tier":1},
    {"id":"reuters",    "name":"Reuters",           "rss":"https://feeds.reuters.com/reuters/topNews",                "lean":"center",       "tier":1},
    {"id":"nbcnews",    "name":"NBC News",          "rss":"https://feeds.nbcnews.com/nbcnews/public/news",            "lean":"left",         "tier":1},
    {"id":"dailywire",  "name":"Daily Wire",        "rss":"https://www.dailywire.com/rss.xml",                        "lean":"right",        "tier":1},
    {"id":"breitbart",  "name":"Breitbart",         "rss":"https://feeds.feedburner.com/breitbart",                   "lean":"right",        "tier":2},
    {"id":"skynews",    "name":"Sky News",          "rss":"https://feeds.skynews.com/feeds/rss/home.xml",             "lean":"center",       "tier":2},
    {"id":"thehill",    "name":"The Hill",          "rss":"https://thehill.com/rss/syndication/all-news",             "lean":"center",       "tier":2},
    {"id":"washtimes",  "name":"Washington Times",  "rss":"https://www.washingtontimes.com/rss/headlines/news/",      "lean":"right",        "tier":2},
    {"id":"foxbusiness","name":"Fox Business",      "rss":"https://feeds.foxbusiness.com/foxbusiness/latest",         "lean":"right",        "tier":2},
    {"id":"townhall",   "name":"Townhall",          "rss":"https://townhall.com/rss",                                 "lean":"right",        "tier":2},
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
    'death','dead','died','dies','kill','kills','killed','killing','killer',
    'shot','shots','shooting','crash','crashes','fire','fires','blast','explosion',
    'bomb','bombing','attack','attacks','murder','murders','murdered',
    'arrest','arrests','arrested','charge','charges','charged',
    'police','officer','officers','court','trial','guilty','verdict','sentence','sentenced',
    'body','bodies','hospital','victim','victims','suspect','suspects',
    'found','missing','search','rescue','emergency','tragedy','tragic',
    'recall','accident','incident',
}

data_store = {"last_updated":None,"sources":{},"trending_topics":[],"google_trends":[],"alignment_score":None,"sources_live":0,"loading":True}
data_lock = threading.Lock()

def fetch_source(source):
    try:
        feed = feedparser.parse(source["rss"])
        if feed.bozo and not feed.entries: return source["id"], []
        arts = []
        for e in feed.entries[:20]:
            t = e.get("title","").strip()
            if not t or len(t)<10: continue
            arts.append({"title":t,"link":e.get("link","#"),"summary":re.sub(r'<[^>]+>','',e.get("summary",""))[:200],"published":e.get("published","")})
        return source["id"], arts
    except: return source["id"], []

def fetch_google_trends():
    if not HAS_PYTRENDS: return []
    try:
        pt = TrendReq(hl='en-US',tz=300,timeout=(15,30),requests_args={'headers':{'User-Agent':'Mozilla/5.0'}})
        return pt.trending_searches(pn='united_states')[0].tolist()[:25]
    except Exception as e:
        print(f"  Google Trends error: {e}"); return []

def extract_keywords(title):
    words = re.findall(r"[A-Za-z']+", title.lower())
    filtered = [w for w in words if w not in STOP_WORDS and len(w)>3]
    proper = [p.lower() for p in re.findall(r'\b[A-Z][a-z]{2,}\b', title) if p.lower() not in STOP_WORDS and len(p)>3]
    seen,result = set(),[]
    for w in filtered+proper:
        if w not in seen: seen.add(w); result.append(w)
    return result

def cluster_topics(all_arts):
    kw_idx = defaultdict(list)
    for sid, arts in all_arts.items():
        for art in arts:
            for kw in extract_keywords(art["title"]):
                kw_idx[kw].append((sid, art))
    kw_src = {kw:len(set(s for s,_ in a)) for kw,a in kw_idx.items()}
    hot = {kw:c for kw,c in kw_src.items() if c>=2} or {kw:c for kw,c in kw_src.items() if len(kw_idx[kw])>=3}
    sorted_kws = sorted(hot.items(), key=lambda x:(-x[1],-len(kw_idx[x[0]])))
    used, clusters = set(), []
    tier1 = {s["id"] for s in SOURCES if s["tier"]==1}
    for kw, src_count in sorted_kws[:40]:
        cl_arts, cl_srcs = [], set()
        for sid, art in kw_idx[kw]:
            k = (sid, art["title"])
            if k not in used:
                cl_arts.append({**art,"source_id":sid}); cl_srcs.add(sid); used.add(k)
        if len(cl_arts)<2: continue
        t1 = [a for a in cl_arts if a["source_id"] in tier1]
        best = (t1 or cl_arts)[0]
        clusters.append({"keyword":kw.title(),"topic":best["title"],"articles":cl_arts[:10],
                         "sources":list(cl_srcs),"source_count":len(cl_srcs),
                         "article_count":len(cl_arts),"heat_score":src_count*12+len(cl_arts)})
    clusters.sort(key=lambda x:-x["heat_score"])
    return clusters[:20]

def compute_alignment(all_arts, topics):
    dw = all_arts.get("dailywire",[])
    if not dw or not topics: return None
    dw_kws = set()
    for a in dw: dw_kws.update(extract_keywords(a["title"]))
    top10, covered, details = topics[:10], 0, []
    for t in top10:
        kw = t["keyword"].lower()
        ok = kw in dw_kws or any(kw in a["title"].lower() for a in dw)
        covered += int(ok)
        match = next((a["title"] for a in dw if kw in a["title"].lower()), None)
        details.append({"topic":t["keyword"],"covered":ok,"dw_article":match,"heat_score":t["heat_score"]})
    score = round(covered/len(top10)*100) if top10 else 0
    grade = "A" if score>=80 else "B" if score>=60 else "C" if score>=40 else "D"
    return {"score":score,"grade":grade,"covered":covered,"total":len(top10),"details":details}

def refresh_data():
    ts = datetime.now().strftime('%H:%M:%S')
    print(f"\n[{ts}] Fetching {len(SOURCES)} sources + Google Trends...")
    all_arts = {}
    with ThreadPoolExecutor(max_workers=12) as ex:
        for sid, arts in [f.result() for f in as_completed({ex.submit(fetch_source,s):s for s in SOURCES})]:
            if arts: all_arts[sid]=arts; print(f"  ✓ {sid}: {len(arts)}")
            else: print(f"  ✗ {sid}: no data")
    print("  Fetching Google Trends...")
    gt = fetch_google_trends()
    print(f"  {'✓' if gt else '✗'} Google Trends: {len(gt) if gt else 'unavailable'}")
    topics = cluster_topics(all_arts)
    print(f"  → {len(topics)} trending topics")
    align = compute_alignment(all_arts, topics)
    if align: print(f"  → DW alignment: {align['score']}% ({align['grade']})")
    srcs = {}
    for s in SOURCES:
        sid = s["id"]; li = LEAN.get(s["lean"],{"label":s["lean"],"color":"#374151"})
        srcs[sid]={**s,"lean_label":li["label"],"lean_color":li["color"],"articles":all_arts.get(sid,[])[:8],"status":"ok" if sid in all_arts else "error"}
    with data_lock:
        data_store.update({"last_updated":datetime.now().isoformat(),"sources":srcs,"trending_topics":topics,
                           "google_trends":gt,"alignment_score":align,"sources_live":len(all_arts),"loading":False})
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
.main{display:grid;grid-template-columns:1fr 264px;grid-template-areas:"topics trends" "sources sources" "align align";max-width:1700px;margin:0 auto;padding:12px 16px}
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
.ta{display:none;background:var(--linen);border-top:1px solid var(--border-l)}
.ta.o{display:block}
.tar{padding:7px 16px 7px 50px;border-bottom:1px solid var(--border-l);font-size:12px}
.tar:last-child{border-bottom:none}
.tas{font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.5px;color:var(--ink-l);margin-bottom:2px}
.tar a{color:var(--navy);text-decoration:none}.tar a:hover{color:var(--red);text-decoration:underline}
#gcard{grid-area:trends}
.gi{display:flex;align-items:center;gap:8px;padding:7px 14px;border-bottom:1px solid var(--border-l);font-size:13px}
.gi:last-child{border-bottom:none}
.grank{font-family:Georgia,serif;font-size:12px;font-weight:700;color:var(--red);width:18px;flex-shrink:0}
.gterm{flex:1;color:var(--ink)}
.gbw{width:34px;flex-shrink:0}.gbb{height:3px;background:var(--linen-dd);border-radius:2px}.gbf{height:3px;background:#1D4ED8;border-radius:2px}
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
  <div class="card" id="gcard"><div class="ch"><span>📈</span><h2>Google Trends US</h2><span class="chr">Right now</span></div><div id="gl"><div style="padding:16px;text-align:center;color:var(--ink-l)">Loading...</div></div></div>
  <div class="card" id="ss"><div class="ch"><span>📰</span><h2>Source Headlines</h2><span class="chr">Fox · NYT · CNN · Daily Mail · NY Post · AP · Reuters · Breitbart · Sky · NBC · Hill · DW · WashTimes · FoxBiz · Townhall</span></div><div class="sg" id="sg"></div></div>
  <div class="card" id="ac"><div class="ch"><span>🎯</span><h2>Daily Wire Coverage Alignment</h2><span class="chr">Are you covering what's trending?</span></div><div id="al"><div style="padding:20px;text-align:center;color:var(--ink-l)">Loading...</div></div></div>
</div>
<script>
const SO=['foxnews','nypost','dailywire','breitbart','washtimes','townhall','ap','reuters','thehill','skynews','cnn','nytimes','nbcnews','dailymail','foxbusiness'];
let _n=Date.now()+30*60*1000;
function e(s){return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;')}
function ta(iso){if(!iso)return'—';const d=Math.floor((Date.now()-new Date(iso))/1000);if(d<60)return d+'s ago';if(d<3600)return Math.floor(d/60)+'m ago';return Math.floor(d/3600)+'h ago'}
function fc(ms){if(ms<=0)return'Refreshing...';const m=Math.floor(ms/60000),s=Math.floor((ms%60000)/1000);return'Next refresh: '+m+':'+String(s).padStart(2,'0')}
function rT(topics){
  const el=document.getElementById('tl');
  if(!topics||!topics.length){el.innerHTML='<div style="padding:20px;text-align:center;color:var(--ink-l)">No trending topics yet.</div>';return}
  const mx=topics[0].heat_score||1;
  el.innerHTML=topics.map((t,i)=>{
    const pct=Math.round((t.heat_score/mx)*100),hot=i<3;
    const dots=(t.sources||[]).map(s=>'<span class="sd" style="background:'+((window._L||{})[s]||'#6B7280')+'" title="'+e(s)+'"></span>').join('');
    const arts=(t.articles||[]).map(a=>'<div class="tar"><div class="tas">'+e(a.source_id)+'</div><a href="'+e(a.link)+'" target="_blank">'+e(a.title)+'</a></div>').join('');
    return '<div class="tr"><div class="tm" onclick="tg('+i+')"><span class="rk'+(hot?' h':'')+'">'+( i+1)+'</span><div class="tb"><div class="tk">'+e(t.keyword)+'</div><div class="th2">'+e(t.topic)+'</div><div class="tmr"><div class="sds">'+dots+'</div><span class="ct">'+t.source_count+' sources · '+t.article_count+' stories</span></div></div><div class="hw"><div class="hbg"><div class="hfl" style="width:'+pct+'%"></div></div><span class="hn">'+t.heat_score+'</span></div><span class="ei" id="ei'+i+'">▸</span></div><div class="ta" id="ta'+i+'">'+arts+'</div></div>';
  }).join('');
}
function tg(i){document.getElementById('ta'+i).classList.toggle('o');const ic=document.getElementById('ei'+i);ic.textContent=ic.textContent==='▸'?'▾':'▸'}
function rG(gt){
  const el=document.getElementById('gl');
  if(!gt||!gt.length){el.innerHTML='<div style="padding:14px;text-align:center;color:var(--ink-l);font-size:12px">Google Trends unavailable<br><i style="font-size:11px">Rate-limited. Try again later.</i></div>';return}
  el.innerHTML=gt.slice(0,25).map((t,i)=>'<div class="gi"><span class="grank">'+(i+1)+'</span><span class="gterm">'+e(t)+'</span><div class="gbw"><div class="gbb"><div class="gbf" style="width:'+Math.round(((25-i)/25)*100)+'%"></div></div></div></div>').join('');
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
    rT(d.trending_topics);rG(d.google_trends);rS(d.sources);rA(d.alignment_score);
  }catch(ex){setTimeout(ld,5000)}
}
async function fr(){
  document.getElementById('ov').classList.remove('h');
  try{await fetch('/api/refresh',{method:'POST'})}catch(ex){}
  _n=Date.now()+30*60*1000;setTimeout(ld,3000);
}
setInterval(()=>{const r=_n-Date.now();document.getElementById('cd').textContent=fc(r);if(r<=0){_n=Date.now()+30*60*1000;ld()}},1000);
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
