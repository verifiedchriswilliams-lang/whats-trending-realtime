# TrendingInRealTime.com — Real-Time News Dashboard

## Project Purpose

A real-time news dashboard for a general audience. It aggregates RSS feeds from 25 major
news outlets — balanced 10 right / 5 center / 10 left on AllSides ratings — plus
Twitter/X trends and Memeorandum (27 sources total) every 30 minutes, clusters stories by specific topic (not generic keywords), and
ranks them by how widely and prominently they are being covered.

**Target audience:** General market, mass consumption. The goal is that a reader can open
the page and see, at a glance, what is happening in the world right now and which stories
are gaining coverage across the press.

**Editorial stance:** None. Sources are chosen for reputation and reach, and balanced
across the political spectrum using AllSides ratings rather than our own judgement. The
coverage dots are the whole claim: they show, per story, which outlets on each side are
carrying it and which are not. Nothing in the UI should editorialise beyond that.

> **History (Sept 2026 pivot):** This was previously an internal Daily Wire editorial
> intelligence tool built to show that newsroom which trending stories it was and was not
> covering. The Daily Wire source, the Coverage Alignment score, and the Side by Side
> comparison page were removed in that pivot. Do not reintroduce a home-team framing.

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
- feedparser for RSS ingestion (25 news sources, concurrent via ThreadPoolExecutor)
- requests + BeautifulSoup4 for homepage scraping (18 sources in `SCRAPE_SOURCES`)
- Memeorandum political aggregator via HTML scrape (surfaces stories driving pundit conversation)
- gunicorn for production serving (via Procfile)
- Railway for hosting, GitHub for version control

---

## Key Algorithms

### Heat Score
`heat_score = (source_count × 12) + counted_articles + (hero_count × 20) + (double_confirmed × 10) + (editorial_spotlight × 15)`

- `source_count` = number of distinct outlets covering this story
- `counted_articles` = articles in the cluster, counting at most
  **`MAX_ARTICLES_PER_SOURCE = 3`** from any one outlet. The raw total is still
  reported as `article_count` for display. Without the cap, an outlet that files five
  stories on one game or trial carries the cluster by itself — sampled Sept 2026, NY Post
  supplied 5 of 6 articles in one cluster and 4 of 8 in another. Breadth is meant to say
  "many newsrooms are on this", so six articles from three outlets (heat 42) must outscore
  six from one outlet plus a straggler (heat 28). Every other term was already per-outlet.
- `hero_count` = outlets where this story was RSS position 0–1 OR appeared on scraped homepage (pos ≤ 8)
- `double_confirmed` = outlets where story is BOTH RSS position 0–1 AND scraped from homepage
- `editorial_spotlight` = outlets where scraped homepage position is 1–3 (editors are actively leading with this story)

### Story Clustering — TF-IDF Cosine Similarity (IMPORTANT — do not revert this logic)

Stories are clustered using **TF-IDF cosine similarity**, not keyword seeds. This replaced the old keyword-frequency approach after it proved unable to prevent false merges (e.g. "Delta/Congress" merging unrelated stories that shared a common word).

**How it works:**
1. Each article title is tokenized and stopwords are removed (see `STOP_WORDS` set)
2. A TF-IDF sparse vector is built for all article titles in the corpus
3. Articles are greedily assigned to the nearest existing cluster centroid if cosine similarity ≥ `SIMILARITY_THRESHOLD = 0.28`
4. If no cluster exceeds the threshold, a new cluster is seeded
5. Cluster centroids are updated online (running mean) as new articles join
6. **Post-processing merge pass:** After greedy clustering, any two clusters whose centroids have cosine similarity ≥ `MERGE_THRESHOLD = 0.20` are merged. This catches false splits where the same story was seeded from two different vocabulary angles (e.g. "Oil slides after Iran ceasefire" vs "US-Iran agree to ceasefire"). Iterates until no more merges are possible.

The key advantage: two articles must share a **pattern of words**, not just one, to exceed the threshold. Single shared words rarely cross it.

**Constants to tune:**
- `SIMILARITY_THRESHOLD = 0.28` — raise to tighten clusters (fewer false merges), lower to loosen (catches more related stories)
- `MERGE_THRESHOLD = 0.20` — post-processing centroid similarity required to merge two existing clusters. Lower than SIMILARITY_THRESHOLD to catch same-story splits.
- `STOP_WORDS` — high-frequency political/news words that would cause false merges if left in the TF-IDF vocabulary. Currently includes: trump, president, american, united, states, says, told, report, new, first, could, would, one, year, people, government, country, also, last, week, two, day, three, days, ago, news, just, back, make, time, according, say, still, us, war, world, think, like, big, old, former, just, top, high, state, federal, national, second, city, million, billion, big, great, major, leading, meet, talks, deal, amid, amid, call, push, move, take, help, plan, after, amid, despite, over, under, house, senate, congress, parliament, lawmakers, republican, democrat, gop, bipartisan, party, bill, vote, law, act, policy, administration, officials, white

**Credible source filter:** Only counts a source toward `source_count` if the article is either scrape-confirmed (appeared on homepage) OR less than 4 hours old.

**Scrape position cap (`MAX_VALID_SCRAPE_POS = 80`):** An article is only marked `scrape_confirmed=True` if its matched scrape position is ≤ 80. Fox News's raw HTML (server-side rendered) is fully parseable by BeautifulSoup — but the anchor link fallback sweep picks up static sidebar/footer links at positions 90–150+. The Fox-specific targeted scraper (`div.big-top`, `div.thumbs-2-7`) ensures editorial headlines appear at positions 1-10, and the cap blocks the stale footer matches that follow. All legitimate editorial content from any source confirms within positions 1–75. This prevents stale Google News RSS articles (surfaced by relevance, not recency) from inflating source counts for stories outlets have moved on from.

### Homepage Scraping (Cross-Verification)
`scrape_homepage(sid, url)` fetches each source's actual homepage and extracts all `<h1>/<h2>/<h3>` text plus prominent anchor link text. Returns a **3-tuple**: `(headlines, url_map, orig_map)`.

- `headlines` = `[(normalized_text, position), ...]` for cross-verification matching
- `url_map` = `{normalized_text: absolute_url}` — used by synthetic injection
- `orig_map` = `{normalized_text: original_case_title}` — used to preserve casing in injected articles

Runs concurrently with RSS fetch (20-worker ThreadPoolExecutor).

Articles are matched against scraped headlines using:
1. Exact normalized substring match (title in scraped or scraped in title)
2. Word-overlap ≥ 60% for titles with 4+ words

Matched articles are marked `scrape_confirmed=True`. In the expanded article view:
- `★` = RSS hero (feed position 0 or 1)
- `✓` = scrape confirmed (appeared on homepage)
- `★✓` = double-confirmed (both RSS position AND scraped homepage)

**Source card ordering:** Editorial picks (scrape_position set) appear first, then RSS chronological.

### Synthetic Article Injection
When a source's RSS pool misses editorially pinned stories (Fox's chronological feed, CNN's sparse pool, etc.), articles are injected from scraped homepage headlines that weren't matched to any RSS article.

**How it works:**
- After cross-verification, any scraped headline at position ≤ `INJECT_LIMIT = 10` that wasn't matched to an RSS article and has a captured URL is injected as a synthetic article
- Injected articles get `scrape_confirmed=True`, `scrape_position=pos`, `synthetic=True`, `pub_ts=None`
- URL quality gate: href must match the source's own domain AND have path depth ≥ 2 (filters nav/section links)
- Junk filter (`_is_junk_injection`): blocks nav headers, ads, promos, podcast/newsletter links — patterns include `% off`, `VIP membership`, `Listen to [source] podcasts`, `Site Information Navigation`, `[-–] Top Stories` (matches both hyphen and em-dash variants — e.g. "New York Times - Top Stories"), `newsletter`, `subscribe`, `Every Day at [time]`, etc.
- `SKIP_INJECT = {'dailymail'}` — Daily Mail homepage is lifestyle/celebrity-heavy; injection would surface non-news content
- Sources with no `url_map` (Reuters blocked, The Hill 403, Fox Business JS-rendered) are automatically excluded

**Typical injection counts (from March 2026 QA):** ~47 total synthetic articles per cycle across 10 sources. Fox: 9, AP: 9, NY Post: 7, WashTimes: 6, Breitbart: 4, NYT: 3, NBC: 3, CNN: 2, Townhall: 3, Sky News: 1.

### Velocity Sparklines
Each trending topic's heat trajectory is tracked across refreshes using **Jaccard source-set matching** — a cluster is considered "the same story" across cycles if the set of source IDs covering it overlaps by ≥ 33% with a previously seen cluster.

This replaced a naive approach that keyed history by cluster label text, which broke every cycle because TF-IDF cluster labels change as new articles arrive.

`_heat_history = {}` stores up to 4 readings per frozenset(source_ids). The `spark()` JS function draws a real multi-point curve from this array.


---

## Data Sources (25 news RSS + 2 supplemental = 27 total)

Sources are chosen for reputation and reach, and balanced across the political spectrum:
**10 left of center / 5 center / 10 right of center.** `lean` is the three-bucket value
that drives the colour coding throughout the UI.

### Bias ratings — AllSides

The roster's political placement is **not our judgement**. Every outlet carries the
verbatim [AllSides](https://www.allsides.com/media-bias/media-bias-ratings) rating in the
`allsides` field, snapshotted **2026-09-22** (`RATINGS_SOURCE`, `RATINGS_AS_OF`,
`RATINGS_URL` at the top of `trending_dashboard.py`). AllSides publishes five tiers; we
collapse Left + Lean Left into `left` and Right + Lean Right into `right` for display, so
the UI has three buckets instead of five.

Snapshot composition: **10 Lean Left · 5 Center · 7 Lean Right · 3 Right.** No outlet in
the roster currently carries AllSides' full Left rating.

AllSides rates **perspective only** — explicitly *not* accuracy, credibility or quality —
and only online US political content. Any UI copy that cites the ratings must say so.

**How we got to 10/5/10 (Sept 2026):** applying the AllSides snapshot to the previous
twenty-source roster showed it was actually **10 left / 4 center / 6 right**, not the
7/6/7 we had claimed — our own hand-assigned leans had been wrong on 11 of 20, in a
direction that manufactured apparent balance. That also gave left-of-center stories a
10-dot coverage ceiling against 6 for the right, a 67% measurement advantage. The fix was
**additive**: nothing was removed, five outlets were added (Bloomberg, The Dispatch, Fox
Business, Daily Mail, Washington Free Beacon) to reach 10/5/10.

Considered and rejected for the right-hand additions: Epoch Times, Newsmax, OAN, The
Post Millennial, Breitbart and Townhall. Daily Mail was included on **reach** grounds —
it is a large outlet with a real newsroom and reporting staff — which is why the
selection criterion is reputation *and* reach, not reputation alone.

### News Outlets

| ID | Name | RSS Feed | AllSides | Bucket | Tier |
|---|---|---|---|---|---|
| cnn | CNN | Google News RSS (site:cnn.com) | Lean Left | left | 1 |
| nytimes | New York Times | rss.nytimes.com nyt/HomePage | Lean Left | left | 1 |
| wapo | Washington Post | feeds.washingtonpost.com/rss/national | Lean Left | left | 1 |
| nbcnews | NBC News | feeds.nbcnews.com nbcnews/public/news | Lean Left | left | 1 |
| cbsnews | CBS News | cbsnews.com/latest/rss/main | Lean Left | left | 2 |
| npr | NPR | Google News RSS (site:npr.org) | Lean Left | left | 1 |
| ap | AP News | Google News RSS (site:apnews.com) | Lean Left | left | 1 |
| axios | Axios | api.axios.com/feed | Lean Left | left | 2 |
| usatoday | USA Today | Google News RSS (site:usatoday.com) | Lean Left | left | 2 |
| politico | Politico | Google News RSS (site:politico.com) | Lean Left | left | 2 |
| reuters | Reuters | Google News RSS (site:reuters.com) | Center | center | 1 |
| bbc | BBC News | feeds.bbci.co.uk/news/rss.xml | Center | center | 1 |
| thehill | The Hill | thehill.com/homenews/feed | Center | center | 2 |
| wsj | Wall Street Journal | Google News RSS (site:wsj.com) | Center | center | 1 |
| bloomberg | Bloomberg | feeds.bloomberg.com/politics/news.rss | Center | center | 1 |
| washtimes | Washington Times | washingtontimes.com/rss/headlines/news | Lean Right | right | 2 |
| washexam | Washington Examiner | Google News RSS (site:washingtonexaminer.com) | Lean Right | right | 2 |
| natreview | National Review | nationalreview.com/feed | Lean Right | right | 2 |
| freepress | The Free Press | thefp.com/feed | Lean Right | right | 2 |
| dispatch | The Dispatch | thedispatch.com/feed | Lean Right | right | 2 |
| foxbusiness | Fox Business | moxie.foxbusiness.com/google-publisher/latest.xml | Lean Right | right | 2 |
| dailymail | Daily Mail | dailymail.co.uk/ushome/index.rss | Lean Right | right | 2 |
| foxnews | Fox News | feeds.foxnews.com/foxnews/latest (50 articles) | Right | right | 1 |
| nypost | NY Post | nypost.com/feed | Right | right | 1 |
| freebeacon | Washington Free Beacon | freebeacon.com/feed | Right | right | 2 |

**Per-source limit:** 20 articles from RSS (Fox News: 50, via `rss_limit`).

**The five added in the 10/5/10 pass** (all verified live 22 Sept 2026, all **direct**
feeds — no new Google News dependencies): Bloomberg Politics (20 items), Fox Business
(25/18 fresh), The Dispatch (10), Daily Mail US (135/25 fresh), Washington Free Beacon
(20/8 fresh).

**Fox Business and Daily Mail were previously removed and are now back.** Fox Business
was dropped as a "vertical duplicate of Fox News" and Daily Mail as a tabloid; both were
restored on the AllSides evidence that the roster was short of right-of-center outlets,
and Daily Mail specifically on reach. Daily Mail stays in `SKIP_INJECT` — its homepage is
celebrity/lifestyle-heavy, so synthetic injection would surface non-news.

**Removed in the earlier Sept 2026 rebalance and still out:** Daily Wire (audience pivot),
Breitbart and Townhall (opinion/aggregation rather than original reporting), Sky News
(UK-centric; homepage scrape also 403s).

**Feed URLs corrected during verification:**
- **WSJ** — every `feeds.a.dj.com` feed is frozen at 27 Jan 2025, so the 48h cutoff
  discarded all of it. Now Google News RSS.
- **USA Today** — `rssfeeds.usatoday.com` 301s every path to the homepage; the RSS
  service is retired. Now Google News RSS.
- **Politico** — `politics-news.xml` is 404. `politics.xml` is live but carries only
  ~2 items inside the 48h window. Now Google News RSS for volume.
- **NPR** — `feeds.npr.org` fingerprints the **TLS handshake**, not headers: curl gets
  200, python-requests gets 403 with byte-identical headers. No header change fixes it
  and Railway runs the same stack. Now Google News RSS.

**Eight of twenty-five sources use Google News RSS** (cnn, ap, reuters, washexam, wsj,
npr, usatoday, politico). That makes the unstripped `" - Publisher"` suffix a clustering
problem — see the note below.

**Note on Google News RSS sources:** titles arrive with a
`" - Publisher"` suffix. `best_label()` strips it from the *display label only* — the raw
title still carries the suffix into TF-IDF, so publisher names pollute the clustering
vocabulary for those sources. Known issue, not yet fixed.

**Note on Fox News:** History of feed changes: originally `foxnews/national` (crime beat),
then Google News RSS, now `feeds.foxnews.com/foxnews/latest` with a 50-article pool to
catch editorially pinned "LIVE UPDATES" hero stories that never refresh to position 0 in a
chronological feed. Paired with Fox-specific targeted scraping of `div.big-top` and
`div.thumbs-2-7`. Fox IS server-side rendered — BeautifulSoup parses the full layout.
The 50-article pool is the one place an outlet gets a bigger pool than the rest. It
compensates for a chronological feed and does not weight Fox in the ranking: the 48h
cutoff binds first (Fox contributes ~25 against everyone else's ~20), `source_count`,
hero and spotlight credit are per-outlet, and since Sept 2026 `MAX_ARTICLES_PER_SOURCE`
caps the one term a deeper pool could reach.

**Note on CNN and AP:** Both use Google News RSS. CNN's direct feed returned only 2
articles from Railway; AP's `feeds.apnews.com` fails Railway DNS.

### Supplemental Sources

| Source | Method | Feeds | Notes |
|---|---|---|---|
| Twitter/X Trends | getdaytrends.com (primary) / trends24.in (fallback) | Social Velocity | getdaytrends currently parses 0 — the fallback is carrying it. |
| Memeorandum | HTML scrape (`div.item > div.ii > strong > a`) | Social Velocity | `data_store['memeorandum']`, `_MEMO_CACHE`, 30 min. Both were named `reddit_posts`/`_REDDIT_CACHE` until the Reddit pages were retired. |

**Removed Sept 2026:** Bluesky, Drudge Report, Truth Social — and, later the same month,
Reddit entirely (see below).
- **Drudge** is a single hand-curated, historically right-leaning feed — a poor fit for a
  politically balanced product.
- **Truth Social** returns a 403 Cloudflare challenge to server requests, so its panel
  could never render.
- **Bluesky** went with them: once Truth Social was gone it had no counterpart.
- **Reddit** (all eight subreddits, and the Blue Trends and Red Trends pages it fed) came
  out at the end of the month. Reddit 429s public RSS aggressively from datacentre IPs:
  even throttled to one request every two seconds with a retry, a typical cycle returned
  one or two of the four liberal subs and two of the four conservative ones. The two pages
  could not be honestly symmetric when one side routinely carried more posts than the
  other for reasons that had nothing to do with engagement. `/bluetrends` and `/redtrends`
  now 301 to `/`. The coverage dots already carry the left/center/right claim, per story,
  from sources that answer reliably. **Do not reintroduce a social panel that can only be
  populated some of the time.**

**On Memeorandum's balance:** sampled live (Sept 2026), its front page carried NYT (42
links) alongside Washington Examiner (35) and Newsmax (27), Fox News (18) alongside The
New Republic (18); classified links ran 149 left / 118 right. It is algorithmic rather
than curated — it tracks what political writers are linking to and clusters commentary
from both sides under each story — which is why it stays balanced without being balanced
by hand. Caveat: it tracks *political punditry* specifically, so it skews toward what the
commentariat is fixated on rather than general news. That is a genre skew, not a partisan
one.


---

## Design system (2030 redesign)

Source of truth: `docs/design/DESIGNSYSTEM.md`, with artboards in `docs/design/artboards/`.
**Phase 1 is implemented** — the visual language, applied to the existing layout. Phases 2
and 3 (structural, and new capability) are not started.

**Phase 1, shipped:**
- **One typeface.** Instrument Sans replaces Newsreader and Inter. No serif, no mono.
- **No icon font.** Material Symbols is gone — 25 icon spans removed, and with them a
  328KB font and its ligature fragility. Every icon sat beside a text label already. Do
  not reintroduce icons where a word will do.
- **OKLCH token palette** on `:root`. Legacy token names (`--surface`, `--ink-m`, …) are
  kept as aliases pointing at the new tokens, so existing rules inherit the palette
  without being rewritten. Write new rules against the new names: `--bg`, `--sf`, `--ink`,
  `--ink2`, `--ink3`, `--ll`, `--lc`, `--lr`, `--lo`, `--acc`, `--hair`, `--lift`.
- **Lean colours hold constant lightness and chroma**, varying only hue. Previously
  `right` (`#C41230`) was visibly darker and heavier than `left` (`#1D4ED8`), and
  `center-left` shared `left`'s exact hex, so those two tiers were indistinguishable. The
  palette no longer editorialises. If you add a lean tier, match L and C and change only H.
- **No ALL-CAPS micro-labels.** 14 `text-transform:uppercase` rules removed; 9–10px caps
  became 13px sentence case. Category labels are full words, not `Natl`/`Biz`.
- **Tabular numerals** on `body`, so the Signal column stops jittering between refreshes.
- **Rising velocity is green** (`--acc`), not red — a story gaining coverage should not
  read as a warning. Falling stays neutral grey. Never red.
- **No gradient fills**, and category badges no longer use eight saturated pill colours.

**Also shipped (design's data display):**
- **Coverage dots replace the lettered source chips.** One dot per outlet across the whole
  roster, grouped left → center → right → not covering, so the shape alone reads as
  balance and absence is visible. Each group is a single element painted with a repeating
  radial gradient (`.cdots`, 9px tile), so a 25-outlet row is four spans, not twenty-five.
  Hovering a group names its outlets. `leanMaps()` must run before `rT()` — it builds the
  roster the dots are drawn from, and when it ran inside `rS()` the first paint drew none.
- **Category and lead outlets moved to one subtitle line** ("National · led by AP News,
  NPR, NBC News and 5 more"), replacing the stacked category pill and the heavy dark
  "Lead at N outlets" badge. Capped at three names, as the artboard shows.
- **The Sources column is gone; the dots sit under the subtitle** (Sept 2026). The row now
  reads as one argument — headline, who is leading it, then how broadly it is carried —
  instead of asking the eye to pair a sentence with a separate column. It also gives the
  headline the retired column's 236px, so titles wrap less. The dot tile is the `--dt`
  token on `.cdots` (9px desktop, 7px ≤600px) and group widths are `calc(var(--n) *
  var(--dt))`, so the whole row scales without any group wrapping — a wrapped group
  destroys the single-shape reading. `.cdn` ("7 of 25 outlets") carries the label the
  column header used to.
- **Age lives under the rank number** (`.t-when`), not in the headline cell. Rank and age
  are both one-glance scalars — how big, how new — so they share the left gutter. Breaking
  is the *same* chip in red with the pulse, never the wider word "Breaking": the gutter is
  76px and the word does not fit it. The word stays in the tooltip.

**Fixed: mobile rendered every expanded row permanently.** `.topics-tbl tbody tr.x-row`
in the ≤600px block set `display:block` unconditionally, out-specifying `.x-row{display:none}`,
so all 20 stories rendered their full article lists inline with no way to collapse them.
The mobile page was ~68,000px tall. It is now gated on `.open` like the desktop rule, and
the page is ~13,800px. If you touch that media query, keep the `.open` gate.

**Naming (Sept 2026).** The app says what it is, in the same words everywhere: the
sidebar is **TrendingInRealTime / "what the press is covering right now"**, matching the
`<title>` and the share card. It previously read "Intelligence Ops / Global Newsroom",
with "Topic Intelligence" in the nav and "Headline Intelligence" as a column header —
Daily Wire–era naming for an internal newsroom tool, aimed at an audience that no longer
exists. The nav item is **Trending** and the column is **Story**. This is the same rule
Phase 1 applied to `Natl`/`Biz`: a general reader should not have to decode a label. Do
not reintroduce "intelligence" as product vocabulary.

**Identity and social metadata (Sept 2026):**
- **Favicon** is the identity mark — eight circles on a ring, five solid and three at 30%,
  empty centre, white on `#1A2231`, as an inline SVG data URI. It replaced a maroon
  `#BA032A` line-graph icon whose colour was the accent Phase 1 retired. Circles are
  r=3.4 rather than the UI's 2.6 so the ring still reads at 16px.
- **`<title>`** is "TrendingInRealTime.com — what the press is covering right now". The
  previous "Editorial Intelligence" title was Daily Wire–era naming.
- **Open Graph and Twitter card tags** were absent entirely, so any shared link rendered
  a bare preview. `/og-image.png` serves `docs/social/og-image.png` (1200×675) from the
  repo, since the app has no static directory.
- The card's coverage dots total exactly 25 — six left, three center, five right carrying
  a story, eleven not — and the headline reads "Twenty-five outlets." Keep both in step
  with the roster if you re-render: the dots are the product's claim
  about itself, and a card that disagrees with the roster undercuts it.

**The leading-story hero (Sept 2026).** The top-ranked cluster opens the page and the
table starts at 02 — rank numbers stay true to the ranking rather than restarting.

The artboard's lede is two sentences: *"Nine outlets led with it in the last ninety
minutes. Framing splits on consumer cost versus manufacturing capacity; the underlying
facts hold across the spread."* The first is computable. **The second is an editorial
judgement**, and it would be the only unsourced claim on a page whose entire position is
that it reports what the press is running. So the hero computes the first sentence and
*shows* the second: the same story as one left-of-center and one right-of-center outlet
actually headlined it, quoted verbatim, each in its own lean colour and linked to the
article. Framing differences are evidence here, not assertion.

Two rules for anything added to the hero later. **Every sentence is computed from the
data, and every characterisation of the coverage is a quote.** No LLM lede. And
**presence is read from `t.sources`, never from the article sample** — the payload caps
clusters at 10 articles, so "no outlet right of center is carrying this" is only ever
printed when the full source list says so. Inferring absence from the sample would put a
false claim in the largest type on the page.

**Images: the hero only, always credited (Sept 2026).** `entry_image()` collects *every*
candidate an entry offers — `media_content`, `media_thumbnail`, image enclosures, the
first `<img>` in the summary — and picks the largest. The hero shows one, from whichever
carrying outlet is running the story hardest and has a picture. `.hero-fig` removes
itself `onerror`, so a blocked hotlink is a missing image rather than a broken icon, and
also `onload` when the image would have to be upscaled past 1.25×: a soft hero is worse
than none. Requests go out `referrerpolicy="no-referrer"` (verified loading from foxnews,
nbcnews, foxbusiness, bbc, dailymail, natreview and axios CDNs).

**Taking the first candidate shipped a visibly pixelated hero.** Feeds advertise whatever
size suits their own page: **BBC serves 240×135** and the **Daily Mail 154×115**, both as
the first thing in the entry. Blown up to hero width that is a 4× upscale. Three rules
now apply, in `_IMG_UPGRADES` and the picker:

- **Rewrite the size token** where the CDN takes one — BBC `/ace/standard/240/` → `/1024/`
  (240×135 → 1024×576), wp.com `?fit=`, `?w=`, Axios `/320x320/`. Do **not** do this to
  Fox: `a57.foxnews.com` serves only the renditions it lists and a rewritten size 404s.
- **Ask WordPress CDNs for a width when none is given.** NY Post handed back the untouched
  master: **7430×4953, 3.9MB**. With `?w=1600` it is 1600×1066 at 263KB.
- **An undeclared width must not lose to a declared tiny one.** The Daily Mail ships a
  154×115 `<media:thumbnail>` beside a full-size `<media:content>` carrying no dimensions,
  so an unknown width scores as 900 rather than 0.
- **Skip video URLs.** NBC files `prodamdnewsencoding.akamaized.net` inside
  `<media:content>`; it is an `<img>` that can never load.

**The frame is 16:9, not the artboard's 21:9, and the crop is biased upward.** Measured
across the twelve feeds that carry images, five are exactly 16:9 and three are 3:2 —
**nothing is wider than 16:9**. A 21:9 frame therefore cropped every photograph, 43% of
the height on a 16:9 source, and a centred vertical crop takes the top of the head first.
`object-position:50% 30%` handles the residual crop on 3:2 and 1:1 sources, because news
photographs put faces above the middle. This is not face detection; do not describe it as
such.

**The hero is two columns, gated on a container query.** Argument on the left (headline,
lede, the two quoted headlines), evidence on the right (image, coverage dots, Signal).
That is 463px tall against 914px for the full-width version, so the leading story and the
top of the ranked list share the first screen, and the Signal sits with the dots it
belongs with instead of below the fold.

It keys off `@container hero-col`, not the viewport, because the main column is squeezed
between a 256px sidebar and a 360px aside — at a 1100px viewport a percentage second
column resolved to a **161px image**. Stacked single-column is the default, so a browser
without container query support gets that rather than a broken grid, and the phone layout
leads with the photograph.

**Two traps in that CSS, both of which shipped a sideways-scrolling page before they were
caught.** The second column has a hard **264px floor** because the 25-dot row cannot
shrink or wrap — a wrapped group destroys the shape the dots exist to show — and 25 tiles
at 10px plus three 4px gaps is 262px. And **a container query adds no specificity**: the
`--dt:10px` inside `@container` lost to an equal-specificity `--dt:13px` further down the
sheet, putting a 337px row in a 292px column. Size the hero tile once, outside the query.

**Thumbnails on every row were measured and rejected**, and the measurement is the reason:

- **12 of 25 feeds carry an image, and they split 3 left / 2 center / 7 right.** The eight
  Google News feeds strip all media and skew left (CNN, AP, NPR, USA Today, Politico);
  Bloomberg, CBS and the Washington Post carry none either.
- Per cluster it evens out only partly: **18 of 20** stories have an image available and
  the pick lands **5 left / 6 center / 7 right** against a 10/5/10 roster.
- **~158KB average** (Fox 309KB, NY Post 346KB, BBC 6KB) — twenty of them is **~3.1MB**
  per page load, hotlinked from a dozen CDNs with no image proxy and no static directory.
- The two clusters with no image at all were all-left-and-center coverage, so the gap is
  structural, not incidental.

A photo is the most salient thing on a row, and one outlet's picture becomes the face of
a story twenty newsrooms are covering. One credited image on one story is a claim the
product can stand behind; twenty uncredited ones drawn from a supply that is 7/12 right
of center is not. **If you revisit this, fix the supply first** (og:image scraping for
the feeds that strip media) rather than shipping the skew.

**Deferred to Phase 2** (structural): the topics list is still a `<table>`, so rows cannot
take the hover-raised plane; there is no Coverage gap section; and the fixed sidebar
remains where the design has a single scrolling column.

## UI Features

### Navigation
The app uses a **fixed left sidebar** for navigation (no top nav bar). The sidebar collapses on screens ≤ 900px, replaced by a **mobile bottom nav bar** with icon+label items.

**Sidebar nav items (top to bottom):**
1. **Trending** — Top Trending Topics dashboard (main view)
2. **Live Source Feed** (`newspaper`) — smooth-scrolls to the source headline grid on the Dashboard page
3. **Social Velocity** (`trending_up`) — smooth-scrolls to the Twitter/Memeorandum sidebar on the Dashboard page
4. **Last Hour** (`schedule`) — recent articles page, with live article count badge

Blue Trends and Red Trends were items 5 and 6 until Sept 2026. Any nav item that splits
the page by political side has to be symmetric in both structure *and* data quality; those
two could not be, because Reddit rate-limited one side harder than the other on most
cycles. The dashboard's own coverage dots carry that signal instead.

The **LIVE indicator + countdown to refresh** lives in the sidebar between the wordmark and the nav items (`.sb-live` element). There is no top header bar on desktop — content starts at the very top of the viewport. On a phone the same countdown sits in `.mob-hdr` and shows the timer alone (`fc(ms, bare=true)`); the sidebar's longer "29:16 Refresh" form does not fit beside an 18-character wordmark, a live pill and the Menu button at 390px.

### Dashboard — Top Trending Topics
- Ranked by heat score (highest first)
- **"Lead at X outlets"** navy badge: story was hero at that many outlets (RSS + scrape verified). Hover tooltip lists the outlets.
- Source dots: colored by political lean, larger with outline ring = hero/lead position
- Green ▲ / Red ▼ delta badge: trajectory vs previous refresh (heat score change)
- Velocity sparkline: small 4-point chart showing heat score over last 4 refreshes (Jaccard-matched)
- Click any row to expand and see all individual article headlines per outlet
- `★` = RSS hero, `✓` = scrape confirmed, `★✓` = double confirmed (all have hover tooltips)
- Article age shown inline ("14m ago", "3h ago") from parsed pub_ts. Hover for exact timestamp.
- **Breaking** orange badge: article published within last 90 minutes


### Last Hour
- All articles published in the last 60 minutes across all 25 outlets, chronological (newest first)
- Two sections: **Just Published** (< 15 min old) with pulsing dot indicator, and **Earlier This Hour**
- **⚡ X sources** signal badge when the article's story is already clustering on the Dashboard (shows how many outlets are covering it)
- Political lean color on the source eyebrow (FOX NEWS, CNN, etc.)
- Live count badge on the tab updates every refresh cycle
- Auto-refreshes with the main data pipeline

### Social Velocity sidebar
- **Twitter** tab: US trending topics. Primary source: getdaytrends.com (server-rendered). Fallback: trends24.in. Both may be intermittent from cloud IPs.

**Note:** Facebook tab was removed. Meta's Graph API (`Page Public Content Access` feature) requires App Review and is incompatible with the Facebook Login app type — not feasible for public page engagement data without a full app rebuild.

### Live Source Feed (Source Headlines grid)
- All 25 news sources displayed with their top 8 headlines
- Color-coded by political lean
- Editorial picks (scrape-confirmed) shown first per source
- Source names link to each outlet's homepage


---

## Development Workflow

### Running locally
```bash
cd ~/Projects/whats-trending-realtime
python3 trending_dashboard.py
# Opens http://localhost:8080 automatically
```

### Verifying live sources
```bash
python3 scripts/qa_sources.py            # RSS + scrapes + supplemental APIs
python3 scripts/qa_sources.py --rss      # RSS feeds only
python3 scripts/qa_sources.py --scrape   # homepage scrapes only
python3 scripts/qa_sources.py --supp     # supplemental APIs only
python3 scripts/qa_sources.py --prod     # live Railway deployment health
```

`--prod` is the exception to the network requirement below: it only talks to
www.trendinginrealtime.com, so it works anywhere that host is reachable. It hits
`/debug/refresh` (forces a synchronous refresh, no session token needed) and reports
`sources_live` out of 25 plus `last_updated` — the fastest way to answer "is Railway
still serving, and is it serving real data?" Allow up to ~2 minutes; it runs a full
fetch cycle.
Prints article/headline counts per source and exits non-zero if any source came back
empty. Run this after any feed change and before a deploy — it catches a dead feed in
seconds, whereas the dashboard silently renders a source with zero articles.

**Requires real network access.** Sandboxed environments (Claude Code on the web, CI
containers on an allowlist proxy) block the outbound hosts and every source reports
FAIL. Run it on the Mac, or hit `/debug/refresh` on production instead.

### Deploying (Mac → Railway)
Claude Code runs on the Mac with full git access — commit and `git push` directly.
Railway auto-deploys on push to `main`. The old Cowork VM workaround
(`git pull --rebase origin main && git push` from a separate terminal) is obsolete.

---

## Known Issues

### Per-Source Data Quality (full QA, 22 Sept 2026 — all 25 feeds + 18 scrapes)

Article counts are from one live refresh; scrape figures are `headlines/urls` from
`scripts/qa_sources.py --scrape`. **Five scrapes returned 403 in the sandbox** (nytimes,
ap, thehill, washtimes, bloomberg) — a bare `curl` from the same container is also 403ed
by nytimes and apnews, which both scrape fine from Railway, so treat sandbox 403s as
datacentre-IP blocks and confirm on production with `--prod`.

| Source | RSS | Scrape | Notes |
|---|---|---|---|
| Fox News | ✅ 25 | ✅ 238/186 | `feeds.foxnews.com/foxnews/latest`, 50-article pool. Targeted scraper hits `div.big-top` + `div.thumbs-2-7` first, so positions 1-10 are Fox's actual top stories. `MAX_VALID_SCRAPE_POS=80` blocks footer anchors (pos 90-150). |
| NY Times | ✅ 20 | ⚠️ 403 here | Direct homepage RSS. Scrape is the best in the roster from a residential/Railway IP (tight positions 11-44); 403s from this sandbox. |
| Washington Post | ✅ 16 | ➖ | `feeds.washingtonpost.com/rss/national`. Homepage read-timeouts server-side, so RSS-only. |
| NBC News | ✅ 17 | ✅ 104/63 | Direct RSS + very tight scrape positions 2-13. Best scraper performance. |
| CBS News | ✅ 20 | ⚠️ 89/2 | Direct RSS. Scrape parses headlines but captures almost no article URLs, so injection is effectively off. |
| NPR | ✅ 20 | ✅ 89/49 | Google News RSS — `feeds.npr.org` fingerprints the TLS handshake, not headers. |
| AP News | ✅ 16 | ⚠️ 403 here | Google News RSS (`feeds.apnews.com` fails Railway DNS). Scrape works from Railway (~9 injections/cycle), 403s here. |
| CNN | ✅ 20 | ⚠️ 223/2 | Google News RSS (~20 articles vs 2 from the direct feed). Scrape finds headlines but few URLs. |
| Axios | ✅ 20 | ➖ | `api.axios.com/feed`. Homepage 403s server-side, so RSS-only. |
| USA Today | ✅ 20 | ⚠️ 55/0 | Google News RSS (the direct RSS service is retired). Scrape returns no URLs — injection disabled. |
| Politico | ✅ 20 | ➖ | Google News RSS. Homepage 403s server-side, so RSS-only. |
| Reuters | ✅ 20 | ➖ | Google News RSS. Homepage blocks scraping; articles pass on age alone. |
| BBC News | ✅ 20 | ✅ 126/40 | Direct RSS + working scrape. |
| The Hill | ✅ 15 | ❌ 403 | `homenews/feed`. Homepage 403s to servers everywhere, not just here. See `scripts/probe_403.py`. |
| Wall Street Journal | ✅ 20 | ➖ | Google News RSS — every `feeds.a.dj.com` feed is frozen at 27 Jan 2025. Paywalled homepage 401s. |
| Bloomberg | ✅ 20 | ⚠️ 403 here | Added Sept 2026. `feeds.bloomberg.com/politics/news.rss`. Scrape 403s in the sandbox; unconfirmed on Railway. |
| Washington Times | ⚠️ 0 here | ❌ 403 | **Sandbox-only block:** RSS and homepage both 403 from this container, but production reported **25/25 sources live** right after this deploy, so Railway's IP is fine. Still worth a Google News RSS fallback — it has failed from Railway before. |
| Washington Examiner | ✅ 6 | ✅ 128/90 | Google News RSS — a thin pool on this cycle. Scrape is strong. |
| National Review | ✅ 13 | ➖ | Direct RSS. Homepage 403s server-side, so RSS-only. |
| The Free Press | ✅ 15 | ➖ | `thefp.com/feed`. Not in `SCRAPE_SOURCES`. |
| The Dispatch | ✅ 10 | ✅ 130/58 | Added Sept 2026. Small but consistently fresh feed. |
| Fox Business | ✅ 18 | ✅ 166/153 | Added back Sept 2026 on the direct `moxie.foxbusiness.com` feed. Earlier note that it was JS-rendered is wrong — it scrapes cleanly. |
| Daily Mail | ✅ 20 | ✅ 471/94 | Added back Sept 2026 (US edition feed). In `SKIP_INJECT` — homepage is celebrity/lifestyle-heavy. |
| NY Post | ✅ 20 | ✅ 257/204 | Direct RSS + scrape positions 7-90. |
| Washington Free Beacon | ✅ 8 | ⚠️ 59/1 | Added Sept 2026. Small feed; scrape captures headlines but only one URL. |

### Other Known Issues
- **Multi-line regex replacements in this file are dangerous.** A `re.sub` over
  `best_label()`'s Google News suffix block once consumed one line too many and deleted
  its `return title`, so every cluster label silently became `None`. It passed a syntax
  check and an app-boot check, and only live QA with real clusters caught it. After any
  multi-line edit to a function, run a refresh and confirm `trending_topics[].topic` is
  populated.
- **Rotate the Facebook token.** The removed code embedded app token `1491126469205088|…` in the repo and served it from the public `/debug/fb` endpoint. Deleting the code does **not** invalidate the token, and it remains in git history. Rotate/revoke it in the Meta app dashboard.
- **Reuters RSS:** Their feed URL may periodically break as Reuters migrates infrastructure.
- **Clustering edge cases:** Very fast-breaking stories (first 10 minutes) may not cluster correctly until multiple sources pick them up. TF-IDF needs a minimum article count to form meaningful vectors.
- **Post-merge threshold tuning:** `MERGE_THRESHOLD = 0.20` was chosen to catch same-story false splits. If unrelated stories start merging, raise it toward 0.25. If splits persist, lower it toward 0.15.
- **Twitter/X trends:** getdaytrends.com and trends24.in may block cloud server IPs intermittently. Shows "unavailable" gracefully when both fail.
- **SIMILARITY_THRESHOLD tuning:** 0.28 is the current setting. After a full day of news cycles, this may need adjustment — raise if unrelated stories are still merging, lower if related stories are splitting into separate clusters.

---

## Phase 2 Roadmap

### Completed
- [x] **Hero lead image (Sept 2026)** — `entry_image()` extracts an article image from RSS; the hero shows one, credited to the outlet it came from, and drops the figure entirely when the image fails or none exists. Thumbnails on every row were measured and rejected: the supply is 3 left / 2 center / 7 right, ~3.1MB for twenty, and 2 of 20 stories have no image at all.
- [x] **Leading-story hero (Sept 2026)** — top cluster opens the page; table starts at 02. Computed lede (leaders + recency) plus one left-of-center and one right-of-center headline quoted verbatim, so the framing split is shown rather than characterised. No LLM, no unsourced claim. `rHero()`, `.hero-*`, and `dotSplit()` shared with the coverage dots so the legend and the dots cannot disagree.
- [x] **Per-outlet cap on the breadth term (Sept 2026)** — `MAX_ARTICLES_PER_SOURCE = 3`. Heat's article term counts at most three articles from any one outlet, so no single newsroom's output can stand in for coverage across newsrooms. Investigated because Fox's `rss_limit: 50` looked like a thumb on the scale; measurement showed Fox was not the problem (the 48h cutoff binds first) and NY Post was, at 5 of 6 articles in one cluster. Affected 0 of 20 clusters on the cycle it shipped — it is a guardrail, not a re-ranking.
- [x] **Reddit and the two trend pages retired (Sept 2026)** — deleted `_fetch_reddit_set()`, both subreddit lists, the `.bt-*` CSS, the `rdPosts()`/`rBT()`/`rRT()` renderers, the two nav items in all three surfaces and the `liberal_reddit`/`conservative_reddit` store keys. `/bluetrends` and `/redtrends` 301 to `/`. Reddit 429d one side harder than the other most cycles, so the two pages could not be symmetric in fact, only in layout. Also cut ~30s off every refresh (44s → 14s): the `_REDDIT_DELAY` throttle was the single slowest thing in the pipeline. The Memeorandum slot took the chance to stop being called `reddit_posts` — it is `data_store['memeorandum']` / `_MEMO_CACHE` now.
- [x] **25-source 10/5/10 rebalance with AllSides attribution (Sept 2026)** — added Bloomberg, The Dispatch, Fox Business, Daily Mail and Washington Free Beacon, all on direct feeds; nothing removed. Every outlet now carries its verbatim AllSides rating (`allsides`) plus `RATINGS_SOURCE`/`RATINGS_AS_OF`/`RATINGS_URL`, and `LEAN` collapsed from five hand-assigned tiers to three display buckets. Fixed a 67% measurement advantage for left-of-center stories (a 10-dot ceiling against 6).
- [x] **Facebook dead-code + token removal** — deleted `fetch_facebook_engagement()` (never called by `refresh_data()`), the `/debug/fb` route, and the `/debug/memo` route. All three embedded a hardcoded Facebook app token in publicly deployed code; `/debug/fb` also exposed it via an unauthenticated endpoint. See "Rotate the Facebook token" below.
- [x] **Google Trends removed** — `fetch_google_trends()`, `_gt_cache` and `TRENDS_RSS` deleted. The function was never called by `refresh_data()`, never written to `data_store`, and never rendered, despite earlier revisions of this file describing a "Google Trends US sidebar" as a shipped feature. There is no Google Trends signal in the app; do not cite one.
- [x] **Live source QA script** — `scripts/qa_sources.py` checks all 25 RSS feeds, 18 homepage scrapes, and every supplemental API in one pass; exits non-zero if any source is empty.
- [x] **Scraped page position boosting** — `scrape_position` recorded per article. Positions 1–3 = editorial spotlight (+15/outlet), 4–8 = standard hero (+20/outlet).
- [x] **Google Stitch design refresh** — full structural rewrite with fixed sidebar, table layout, sparklines, source chips.
- [x] **Last Hour tab** — all articles from last 60 min, newest first, with signal badges and Just Published pulsing indicator.
- [x] **Possessive stripping + ambient reference filter** — cleaner clustering (legacy from keyword-seed era, some logic still relevant).
- [x] **Fox News feed fix** — switched from crime-beat `foxnews/national` → Google News RSS → `feeds.foxnews.com/foxnews/latest` (50 articles). Final fix adds Fox-specific targeted scraping of `div.big-top` + `div.thumbs-2-7` to lock editorial positions 1-10 to Fox's actual homepage order.
- [x] **TF-IDF cosine similarity clustering** — replaced keyword-seed approach entirely. No more single-word false merges. `SIMILARITY_THRESHOLD = 0.28`.
- [x] **Post-clustering merge pass** — after greedy clustering, iteratively merges cluster pairs with centroid cosine similarity ≥ `MERGE_THRESHOLD = 0.20`. Fixes false splits where the same story is covered from different vocabulary angles (e.g. oil-price vs. ceasefire-agreement framing of the same event).
- [x] **Velocity sparklines (Jaccard matching)** — `_heat_history` keyed by frozenset(source_ids) with ≥33% Jaccard overlap for story identity across refreshes. Real 4-point spark curve.
- [x] **Stale source credibility filter** — sources only counted if article is <4h old OR scrape-confirmed. Prevents stale Google News articles from inflating source chips.
- [x] **Tooltips** — all UI badges have hover explanations: Breaking, age, Lead (lists outlets), ★/✓ marks, ✓ DW badge, delta.
- [x] **Source name homepage links** — source names in Live Source Feed link to each outlet's homepage.
- [x] **Duplicate subtitle removal** — trending rows no longer repeat the headline in a gray subtitle below the bold title.
- [x] **Synthetic article injection (generalized)** — `scrape_homepage()` returns a 3-tuple `(headlines, url_map, orig_map)`. After cross-verification, unmatched scraped headlines at positions 1–10 with valid article URLs are injected as synthetic articles. Junk filter (`_is_junk_injection`) blocks nav headers, ads, promos, and podcast/newsletter links. Applied to all scraped sources except Daily Mail.
- [x] **Junk injection filter fix** — `[-–]` regex now matches both regular hyphen and em-dash in "Top Stories" pattern. Previously only matched em-dash, allowing "Source Name - Top Stories" section headers to slip through and seed false clusters.
- [x] **Targeted homepage scrapers** — source-specific CSS selectors run before the generic h1/h2/h3 scan for: Fox News (`div.big-top`, `div.thumbs-2-7`), CNN (`container_lead` divs + `<article>`), NBC News (`<article>`), NY Post (`featured-area`/`top-story` + `article.story`), NY Times (`<article>`). Locks editorial positions 1–10 to the source's actual homepage order.
- [x] **AP News fix** — switched from direct RSS (Railway DNS failure) to Google News RSS.
- [x] **CNN fix** — switched from direct RSS (2 articles) to Google News RSS (~20 articles).
- [x] **Sidebar navigation** — removed top nav bar; all navigation moved to fixed left sidebar using Material Symbols icons.
- [x] **Mobile bottom nav** — fixed bottom bar visible at ≤900px; sidebar collapses. Solves disappearing navigation on mobile web.
- [x] **Topbar removal** — "Editorial Intelligence" header bar eliminated; LIVE indicator + countdown moved into sidebar above nav items (`.sb-live`). All page containers start at `top:0`, reclaiming 64px of vertical space.
- [x] **DW alignment prefix matching** — added 5-char prefix matching step between exact and substring fallback. Fixes `olympic`/`olympics`, `transgender`/`trans`, and similar root-word variants where DW's framing uses a different inflection.
- [x] **Facebook tab removed** — Meta's Graph API requires App Review for `Page Public Content Access` and is incompatible with the Facebook Login app type. Removed from Social Velocity sidebar entirely.
- [x] **Loading screen source count** — now "Scanning 27 sources" (25 news RSS + Twitter/X + Memeorandum).
- [x] **General-market pivot (Sept 2026)** — removed Daily Wire, `compute_alignment()` (dead code), the Side by Side page and its nav in all three surfaces, and the DW framing from `/privacy`.
- [x] **20-source rebalance** — dropped Daily Mail, Breitbart, Townhall, Fox Business, Sky News; added WaPo, WSJ, BBC, NPR, Axios, USA Today, Politico, National Review. Its claimed 7 right / 6 center / 7 left turned out to be 10/4/6 once measured against AllSides — superseded by the 25-source pass above.

### Backlog
- [ ] **Even out the image supply** — 13 of 25 feeds strip media, so the available photos run 3 left / 2 center / 7 right. `og:image` from each article page would close it, at the cost of one request per article per cycle against sites that already 403 us. Needed before thumbnails could go in the list at all.
- [ ] **Email digest** — daily 8am summary of the top 10 trending stories
- [ ] **Story staleness** — fade out / gray out stories older than 4 hours from trending list
- [ ] **Fix the 403 scrapes** — run `scripts/probe_403.py`; The Hill and Washington Times are blocked, and Washington Times' RSS is blocked too (a Google News fallback is the likely fix)
- [ ] **Strip Google News suffixes before TF-IDF** — currently stripped only in `best_label()`, so publisher names pollute the clustering vocabulary for the eight Google News sources
- [ ] **Velocity in ranking** — heat score has no time term; ranking is magnitude only, and the Jaccard source-set matcher loses history exactly when a story is growing fastest. Deferred by product decision, revisit later.
- [ ] **Delete `trending_dashboard_v2.py`** — stale 15-source predecessor of the current single-file app. Not imported, not served, not referenced by `Procfile`. Dead weight that confuses source-count audits.
- [ ] **Display normalization within buckets** — coverage dots now span an uneven roster (10/5/10), so "9 of 10 left · 3 of 5 center · 4 of 10 right" reads more honestly than raw dot counts
- [ ] **Sources / Methodology page** — surface the AllSides attribution, the snapshot date, and the "perspective only, not accuracy" disclaimer in the UI, not just in this file
- [ ] **Fix `run.sh`** — installs `pytrends` (unused — nothing in the app imports it) and does not install `requests`, `beautifulsoup4`, or `gunicorn`. It should just be `pip install -r requirements.txt`.

---

## Environment

- **Production URL:** www.trendinginrealtime.com (GoDaddy CNAME → fl8w2a92.up.railway.app)
- **DNS:** GoDaddy CNAME `www` → `fl8w2a92.up.railway.app` + apex forward → www. TXT `_railway-verify.www` → `railway-verify=c920a03...` for Railway verification. No Cloudflare.
- **GitHub repo:** github.com/verifiedchriswilliams-lang/whats-trending-realtime
- **Railway project:** auto-deploys on push to `main`
- **Python:** 3.13 (Railway auto-detected — do NOT add runtime.txt, it breaks the build)
- **PORT:** read from `os.environ.get('PORT', 8080)` — Railway sets this automatically

---

## Editorial Context

The dashboard is built for a fast scan. Suggested reading order:
1. Top trending topics (highest heat score = broadest, most prominent coverage)
2. Velocity sparkline and the ▲/▼ delta — which stories are gaining or losing coverage
3. Last Hour tab — anything breaking in the last 60 minutes that hasn't clustered yet
4. Social Velocity sidebar (Twitter / Memeorandum) — stories RSS may miss