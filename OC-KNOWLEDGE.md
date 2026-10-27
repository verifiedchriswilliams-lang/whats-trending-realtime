# OC-KNOWLEDGE.md

Knowledge file for Other.Chris (OC), the conversational voice agent on usernamedchris.com.
Everything here was read out of this repository. Anything marked "(inferred)" is a
reasonable reading of the code rather than something the code states outright. Anything
I could not determine is in "Questions for Chris" at the bottom instead of being guessed.

Verified against commit `bae997b` (30 September 2026). Production responded 200 when this
was written.

---

## 1. One-liner

TrendingInRealTime.com is a live news dashboard that reads 25 major American news outlets
every half hour, works out which stories they are all covering, and shows you how widely
and how prominently each story is being carried across the political spectrum.

---

## 2. The elevator pitch (spoken)

Most of us read two or three outlets and quietly assume that is the news. TrendingInRealTime
reads twenty five of them at once, every thirty minutes, and clusters the headlines into
actual stories so you can see what the whole press is running right now. Next to every story
there is a row of dots, one per outlet, grouped left, center and right, so you can see at a
glance who is carrying it and, more interestingly, who is not. The political labels are not
mine, they come straight from AllSides, and the site says so. There is no opinion anywhere
on the page. It just shows you what twenty five newsrooms decided to put in front of people
today.

---

## 3. The problem and the why

The problem the product is built around is stated in the site's own meta description, which
is the clearest statement of intent in the repo: "Most of us read two or three outlets and
assume that's the news. See what all 25 are running right now, what's genuinely major, and
what your sources skipped."

So the thing being solved is a blind spot. If you read a handful of outlets you get a picture
of the day that feels complete and is not. The dashboard's answer is breadth plus absence:
every story shows which outlets across the spectrum are carrying it, and the empty dots show
the ones that are not.

The project history also tells you what it used to be. This started life as an internal
editorial intelligence tool for The Daily Wire, built to show that newsroom which trending
stories it was and was not covering. In September 2026 it was pivoted to a general audience.
The commit "Remove Daily Wire, Side by Side, and the dead alignment code" (8 September 2026)
took out the Daily Wire source, the Coverage Alignment score and the Side by Side comparison
page. The project instructions are explicit that a home team framing must not come back.

The editorial stance is written into the project rules: there is none. Outlets are chosen for
reputation and reach, their political placement comes from a third party, and the coverage
dots are described as "the whole claim". Nothing in the interface is supposed to editorialise
beyond that.

### Why I built it (from Chris, October 2026)

I built it for editorial executives and editorial teams. The idea was that in one snapshot
you could see the velocity of the stories moving in the world, both the most published and
the most engaged, and at the same time see how those stories were being reported across
different outlets, where the bias was, where the emphasis differed depending on who was
covering it.

What I did not expect is who actually ended up using it. The producers, the podcast hosts and
the podcast producers picked it up for show prep, because it told them whether they were
talking about the most timely and topical thing. So it solved a completely different problem
from the one I built it for, and it has pivoted from there.

The move to a general audience in 2026 was partly a consequence of leaving the Daily Wire, but
it also just seemed like a more valuable tool for the public than for a newsroom. Without
having to go and visit twenty five sites, you can see what people are talking about the most,
which stories are being covered the most, where the coverage gaps are, and how the same story
gets approached differently on the left, in the center and on the right.

---

## 4. What it actually does

**First visit.** The page opens with a loading overlay that reads "TrendingInRealTime.com"
and under it "Reading 25 newsrooms, Ranking what the press is covering". The client polls the
data endpoint every three seconds until the first refresh cycle finishes, then the overlay
fades. On a cold start that wait can be a minute or two, because nothing is cached and the
whole fetch runs from scratch.

**The frame.** There is a fixed left sidebar, no top header bar. It carries the wordmark
"TrendingInRealTime" and the tagline "what the press is covering right now", a live pill with
a countdown to the next refresh, four nav items (Trending, Live Source Feed, Social Velocity,
Last Hour), a "Refresh Now" button, and two lines of status: how many sources are live out of
25, and how long ago the data updated. At 900 pixels and below the sidebar collapses to a top
bar with a Menu button that opens a drawer.

**The leading story.** The top ranked cluster opens the page as a hero, and the ranked list
below it starts at 02, because the hero is item 01. The hero carries, in order: the rank
number with the age of the newest article beneath it, an eyebrow reading "Leading story" plus
the story's category, the headline (linked to the article it was taken from), a computed lede,
a block labelled "How it is being headlined", the coverage dots with their legend, and then a
photograph with its credit, a rule, and the Velocity and Signal measurements.

The lede is computed, never written. It names up to three of the outlets leading the story
and says how recent the newest article is. For example: "Eight outlets are leading with it,
among them BBC News, CNN and NBC News. The most recent article landed six minutes ago."

The "How it is being headlined" block is the part worth understanding. The design called for
a second sentence characterising how the framing splits, and that would have been the only
unsourced opinion on a page whose entire position is that it reports what the press is
running. So instead of asserting it, the hero shows it: the same story as one left of center
outlet and one right of center outlet actually headlined it, quoted word for word, each in
its own lean colour and linked through. Framing differences are evidence on this page, not
assertion. There is a hard rule in the project instructions: every sentence in the hero is
computed from the data, and every characterisation of the coverage is a quote. No language
model lede.

**The ranked list.** Below the hero is a table with four columns: Rank, Story, Velocity,
Signal. Its subtitle reads "Priority ranked by cross-source heat score, Click any row to
expand", and there is a "Last 24 hours" badge beside the date. Each row carries the rank
number with an age chip under it, the headline, a subtitle line giving the category and the
outlets leading it ("Crime, led by CBS News, BBC News, NPR and 2 more"), the coverage dots
with a count like "8 of 25 outlets", a velocity sparkline, and the Signal number with its
change since the last refresh. Click any row and it expands to show every individual article
in the cluster, by outlet, with marks for how prominently each outlet is running it.

**The coverage dots.** This is the signature element. One dot per outlet across the whole
25 outlet roster, grouped left, then center, then right, then the outlets not carrying the
story at all, which are drawn in a muted tone. The shape alone reads as balance, and absence
is visible rather than implied. Hovering a group names the outlets in it. The legend under it
reads like "6 left, 4 center, 3 right, 12 not carrying it".

**Live Source Feed.** A grid of all 25 outlets, each card showing that outlet's current
headlines, colour coded by lean, with the outlet's name linking to its homepage. Editorial
picks (headlines confirmed on the outlet's actual homepage) are listed before the plain RSS
ones, so the card reflects what that newsroom is leading with rather than just what it
published most recently. Up to 10 headlines per outlet reach the browser.

**Last Hour.** Everything published in the last sixty minutes across all 25 outlets, newest
first, in two sections: "Just Published, last 15 minutes" with a pulsing indicator, and
"Earlier this hour". Each item carries a lightning badge reading something like "4 outlets"
when that story is already clustering on the main dashboard, which is how you catch a
breaking story crossing over from one outlet to many.

**Social Velocity.** A right hand rail listing the top 25 Twitter/X trends for the United
States, labelled "Trending on X, United States". It is explicitly an outside signal. It feeds
nothing: no heat score, no clustering, no ranking.

**Refresh.** Everything refreshes together on a thirty minute cycle, and the countdown in the
sidebar tells you when the next one lands.

---

## 5. How it works under the hood

### For a smart non-engineer

It is one Python file. Every half hour a background thread wakes up, pulls the RSS feed from
each of the 25 outlets, and at the same time fetches the actual homepage HTML for 18 of them.
The RSS tells you what an outlet published. The homepage tells you what it chose to lead with,
which is the more interesting signal and the thing most aggregators miss.

Then it has to work out which headlines are the same story. It does this with a classic
information retrieval technique called TF-IDF cosine similarity, which turns each headline
into a vector of weighted words and measures the angle between them. Similar headlines point
in similar directions. There is no AI model involved anywhere in this, and that is worth
saying plainly because people assume there is.

Once stories are clustered, each one gets a heat score built from how many distinct outlets
are carrying it and how prominently each one is running it. The clusters sort by that score,
the top twenty get rendered, and the whole thing is held in memory until the next cycle.

### Tech stack

- **Language:** Python 3.13 (Railway auto detects it; the project instructions say explicitly
  not to add a `runtime.txt` because it breaks the build)
- **Web framework:** Flask, serving both the HTML page and a JSON endpoint
- **RSS parsing:** `feedparser`
- **HTTP:** `requests`, with a 15 second timeout on every fetch
- **HTML parsing:** `BeautifulSoup4`, for homepage scraping
- **Hosting:** Railway, auto deploying on every push to `main`
- **Source control:** GitHub, `verifiedchriswilliams-lang/whats-trending-realtime`
- **Domain:** www.trendinginrealtime.com, GoDaddy CNAME pointed at Railway, apex forwards to
  www. No Cloudflare.
- **Database:** none. All state is in memory in a Python dictionary behind a lock.
- **Storage, CDN, analytics, payments, auth:** none of these exist. No cookies, no tracking,
  no accounts, no payment integration.
- **Fonts:** Instrument Sans from Google Fonts, one family, no icon font.
- **Dependencies in total:** five. `feedparser`, `flask`, `requests`, `beautifulsoup4`,
  `gunicorn`.
- **Environment variables:** exactly one, `PORT`, which Railway sets.

The whole application including the server, the data pipeline, and all the HTML, CSS and
JavaScript is 2,621 lines in `trending_dashboard.py`. The HTML is a raw Python string in that
same file. There is no template directory and no static directory, which is why the social
share image is served by its own Flask route reading a PNG out of the repo.

### AI and models

**There are none.** This is the single most counterintuitive technical fact about the project
and OC should be comfortable saying it directly. No large language model, no embeddings, no
vector store, no text to speech, no image generation, no external AI API of any kind. There
are no API keys in the application because it does not call any paid service.

The clustering that people assume is AI is TF-IDF cosine similarity, hand written in about
sixty lines using plain Python dictionaries. It does not even use numpy or scikit-learn. The
only occurrences of the words "AI", "LLM" or "OpenAI" anywhere in the file are inside a
keyword list used to tag a story as belonging to the technology category.

The hero's lede, which reads like generated prose, is template assembly: it counts the leading
outlets, looks up their names, picks one of four sentence shapes depending on how many there
are, and appends a recency clause. The one place a model would obviously have helped, writing
a sentence about how the framing differs between left and right, was deliberately left to
quotation instead, on the grounds that an unsourced editorial judgement would undercut the
whole premise.

### Data: sources, ingestion, schedule

- **25 news outlets**, balanced 10 left of center, 5 center, 10 right of center.
- Political placement comes from **AllSides**, snapshotted 2026-09-22. The snapshot date,
  the source name and the ratings URL are constants at the top of the file
  (`RATINGS_SOURCE`, `RATINGS_AS_OF`, `RATINGS_URL`), and every outlet carries its verbatim
  AllSides tier in an `allsides` field. AllSides publishes five tiers; the interface collapses
  Left plus Lean Left into "left" and Right plus Lean Right into "right" so there are three
  display buckets instead of five.
- Snapshot composition: **10 Lean Left, 5 Center, 7 Lean Right, 3 Right.** No outlet currently
  in the roster carries AllSides' full Left rating.
- AllSides rates perspective only, explicitly not accuracy or credibility, and only online US
  political content. The code comments insist that any copy citing the ratings must say so.
- **Eight of the 25 are pulled through Google News RSS** rather than the outlet's own feed:
  CNN, NPR, AP, USA Today, Politico, Reuters, WSJ and the Washington Examiner. Each of those
  was a workaround for a specific failure, documented in the comments. The Wall Street Journal
  feeds were frozen at January 2025. USA Today retired its RSS service. NPR's feed fingerprints
  the TLS handshake rather than the headers, so curl gets a 200 and Python gets a 403 with
  byte identical headers. AP's own feed host fails DNS resolution from Railway.
- **18 of the 25 also get their homepage scraped** for cross verification.
- **Refresh interval:** 1800 seconds, so every 30 minutes, on a daemon thread.
- **Concurrency:** a 20 worker thread pool runs the RSS fetches and the homepage scrapes at
  the same time.
- **Article window:** anything published more than 48 hours ago is discarded.
- **Per source cap:** 20 articles from RSS. Fox News is the single exception at 50, because
  its feed is strictly chronological and editorially pinned "LIVE UPDATES" stories never
  refresh back to the top of it.
- **Deduplication:** feeds list the same story more than once (NBC filed four duplicates and
  NY Post three in a single cycle), so repeats are dropped by normalised title, keeping the
  first appearance because that preserves the best feed position.
- **Retention:** none. Nothing is written to disk. Every Railway restart is a cold start, and
  the velocity history starts again from zero.

### Key algorithms, step by step

**1. Clustering (TF-IDF cosine similarity).**
Each headline is tokenised, stopwords are removed, and a length normalised TF-IDF sparse
vector is built across the whole corpus. Articles are greedily assigned to the nearest
existing cluster centroid if cosine similarity reaches `SIMILARITY_THRESHOLD = 0.28`,
otherwise they seed a new cluster. Centroids update as a running mean as members join.
Afterwards a merge pass repeatedly combines any two clusters whose centroids are within
`MERGE_THRESHOLD = 0.20`, which catches the same story seeded from two different vocabulary
angles.

**2. The shared term gate.**
Cosine on its own was not enough, and the site shipped the proof. One live cluster held
"I paid 30,000 pounds for an influencer degree", "Pro-Trump TV ads paid for with Customs and
Border Protection money" and a Real Housewives story about child support. Their only common
token was "paid". A headline reduces to very few tokens, so a single rare shared word can
dominate both vectors. So two articles must now also share `MIN_SHARED_TERMS = 2` content
tokens with an existing member before joining. The gate deliberately uses a different
vocabulary from the vectors: the TF-IDF stopword list runs to 616 entries and drops words of
three characters or fewer, while the gate uses an 84 word function word list, keeps words of
three or more characters, and applies crude suffix stripping so that "arrest" matches
"arrested". Measured on a live 415 article corpus, clusters containing an unrelated pair fell
from five to two, and the only two clusters that disappeared were both false merges.

**3. Heat score, and why homepage position is the interesting half.**
Chris's framing of this, which is worth having in full because it is not obvious from the
code alone: the RSS feed gives you the chronology of what an outlet published, but crawling
the homepage every thirty minutes tells you where that story sits and how it is moving. An
outlet moves a story up its own page when it is performing, when it is sticky, when it is
being shared. So tracking position over time is a way of inferring how a story is being
consumed, not just that it was reported. Both halves feed the score, and because the score
is what the velocity sparkline plots, a story climbing an outlet's homepage shows up as a
rising curve.

**3. Heat score.**
```
heat = (source_count x 12)
     + counted_articles            (at most 3 from any one outlet)
     + (hero_count x 20)           (RSS position 0 or 1, OR homepage position 1 to 8)
     + (double_confirmed x 10)     (both of the above, same outlet)
     + (editorial_spotlight x 15)  (homepage position 1 to 3)
```
Every term except the article count is per outlet, which is the point: the score is meant to
say "many newsrooms are on this", not "one newsroom filed a lot". `MAX_ARTICLES_PER_SOURCE = 3`
caps the one term that was not already per outlet, after a sample found NY Post supplying five
of six articles in one cluster.

**4. Cross verification against the homepage.**
Articles are matched to scraped homepage headlines by exact normalised substring, or by 60
percent word overlap for titles of four or more words. A match records the page position, and
only positions at or below `MAX_VALID_SCRAPE_POS = 80` count as confirmed, which blocks stale
sidebar and footer links.

**5. Synthetic article injection.**
When an outlet's RSS misses a story its editors have pinned to the homepage, that headline is
injected as a synthetic article if it sits at homepage position 10 or better, has a captured
URL on the outlet's own domain with a path depth of at least two, and survives a junk filter
that blocks navigation headers, ads, podcast and newsletter promos. The Daily Mail is excluded
because its homepage is celebrity and lifestyle heavy.

**6. Velocity.**
A cluster is treated as the same story across refreshes when its set of source IDs overlaps a
previously seen set by at least 33 percent (Jaccard similarity). Up to four heat readings are
kept per story, and the sparkline draws a real curve through them. The curve takes its colour
from its own final segment, so it always agrees with the change badge beside it.

**7. Credibility filter.**
An outlet only counts toward a story's breadth if its article is either confirmed on the
outlet's homepage or less than four hours old. This stops stale Google News results, which
surface by relevance rather than recency, from inflating a story outlets have moved on from.

**8. Categorisation.**
Keyword scoring into eight buckets: international, crime, sports, entertainment, business,
technology, health, and national as the fallback. A story can carry at most two.

### Infrastructure and deployment

Push to `main` on GitHub, Railway builds and deploys. There are no staging environments, no
CI pipeline, no tests in the repo, and no monitoring beyond Railway's own logs and the
`/debug/refresh` route, which runs a refresh synchronously and returns the traceback if
anything throws.

Routes:

| Route | Purpose |
|---|---|
| `/` | The dashboard |
| `/privacy` | Privacy policy |
| `/og-image.png` | Social share card, served from the repo |
| `/robots.txt` | Disallows `/api/` and `/debug/` |
| `/api/data` | JSON payload, requires the session token header |
| `/api/refresh` | POST, triggers an async refresh |
| `/debug/refresh` | GET, synchronous refresh with error dump |
| `/bluetrends`, `/redtrends` | Redirect to `/`, retired pages kept so old links do not break |

One thing to note honestly: `gunicorn` is listed in `requirements.txt`, but the `Procfile`
says `web: python trending_dashboard.py`, which runs Flask's own development server in
production. (inferred) That is a real but low stakes gap given the traffic profile and the
fact that all the work happens on a background thread.

### Performance, cost and scaling

The design is deliberately cheap. One process, no database, no paid APIs, five dependencies.
The cost is essentially Railway hosting and the domain.

The constraints visible in the code are mostly about politeness and resilience rather than
scale. Every outbound request has a 15 second timeout, and the comment explains why:
`feedparser.parse(url)` uses urllib with no timeout, so one hung feed would block the entire
thread pool and freeze the refresh cycle indefinitely. The Twitter trends fetch caches for
30 minutes and falls back to a second provider. The JSON endpoint uses ETags so repeat polls
get a 304 rather than the full payload. Clusters are capped at 10 articles in the payload, and
the ranked list at 20 stories, which keeps the response small.

The honest ceiling: because everything lives in memory in one process, you cannot run two
instances without them diverging, and every restart loses the velocity history.

### Security and privacy

- No user accounts, no login, no cookies, no analytics, no tracking profile. The privacy
  policy states all of this.
- `/api/data` requires an `X-Dashboard-Key` header matching a session token generated at
  startup with `secrets.token_hex(16)` and injected into the page. The code and the handoff
  doc both describe this accurately as a lightweight anti scraping measure, not real auth.
  Blocked requests are logged with IP and user agent.
- Only publicly published RSS feeds, public homepages and public trending pages are read.
  Nothing paywalled, nothing user specific. Every headline links back to the publisher.
- `.gitignore` covers `.env`, `*.env` and `config_local.py`.

---

## 6. Design and product decisions

**Measurement before assertion.** The strongest recurring pattern in the history is that
product questions get answered with live data rather than opinion, and several times the data
inverted the hypothesis. Fox News having a 50 article pool looked like a thumb on the scale;
measurement showed the 48 hour cutoff bound first and NY Post was the actual offender.
Memeorandum was suspected of being partisan; it turned out not to be in aggregate, and was cut
on sourcing instead. Thumbnails on every row were proposed and then rejected on the numbers.

**The roster rebalance is the best example.** The site had claimed a balanced 7 left, 6 center,
7 right across twenty sources. Measured against the AllSides snapshot it was actually 10 left,
4 center, 6 right, which meant the hand assigned leans had been wrong on 11 of 20 in a direction
that manufactured apparent balance. It also gave left of center stories a 10 dot coverage
ceiling against 6 for the right, a 67 percent measurement advantage. The fix was additive:
nothing was removed, five outlets were added (Bloomberg, The Dispatch, Fox Business, Daily Mail,
Washington Free Beacon) to reach 10/5/10. Epoch Times, Newsmax, OAN, The Post Millennial,
Breitbart and Townhall were considered and rejected. The Daily Mail was included on reach
grounds, which is why the stated criterion is reputation and reach rather than reputation alone.

**Things tried and removed.** Reddit powered two pages, Blue Trends and Red Trends, built to be
symmetric. They were retired because Reddit rate limited one side harder than the other on most
cycles, so the two pages could not be symmetric in fact, only in layout. Removing them also cut
the refresh cycle from about 44 seconds to about 14. Memeorandum was removed because 8 of the
20 headlines on its panel came from outside the roster, including an advocacy organisation and
a personal Substack, and a page that picks 25 outlets on reputation and third party attribution
cannot put an unvetted back door beside them. Google Trends was deleted as dead code that had
never been wired up despite being documented as a shipped feature. A Facebook integration was
removed when Meta's Graph API turned out to require App Review for the access it needed.

**Thumbnails on every row, rejected on measurement.** Only 12 of 25 feeds carry an image and
they split 3 left, 2 center, 7 right, because the eight Google News feeds strip all media and
those skew left. Twenty images would also be roughly 3.1MB per page load, hotlinked from a
dozen CDNs with no image proxy. One credited image on one story is a claim the product can
stand behind; twenty uncredited ones drawn from a supply that is 7 of 12 right of center is not.

**The palette does not editorialise.** The three lean colours hold constant lightness and
chroma and differ only in hue, so no side reads as heavier or more negative. Rising velocity is
green and falling is neutral grey, never red, because a story gaining coverage should not read
as a warning.

**The interface went through three redesigns.** Chris worked with Claude Design to get to the
current visual language, then kept refining that output through development rather than
implementing it as drawn. The design system and artboards in `docs/design/` are the artefacts
of that process, and the project notes record several places where the artboards were
deliberately not followed because measurement said otherwise.

**The name is settled.** It was "What's Trending In Real Time" first. He landed on
"Trending In Real Time" because the URL is shorter and it was available. The old name survives
in `run.sh` and in the retired `trending_dashboard_v2.py`, which are leftovers rather than a
live question.

**Deliberately simple.** One file, no database, no build step, no framework on the front end.
No icon font at all, because every icon sat beside a text label anyway and removing it dropped
a 328KB font.

---

## 7. Timeline and status

- **Before April 2026:** the project existed as an internal Daily Wire editorial intelligence
  tool. Chris built the original over a single weekend. Most of the work since has been
  subtraction rather than addition, including a set of velocity metrics and most of the social
  sources. The first commit in this repository already contains a complete 2,580 line
  application, so the repo starts partway through the story.
- **7 April 2026:** first commit in this repo. That month's work was the Blue Trends page,
  Bluesky trending topics, Reddit fetchers, and the post clustering merge pass.
- **Roughly three month gap.**
- **8 September 2026:** the big day. Seventeen commits. Removed a hardcoded Facebook token and
  the dead code around it, removed Daily Wire and the Side by Side page, rebalanced to 20
  general market sources, fixed four dead feeds, descoped the social sources, and shipped the
  Phase 1 visual redesign.
- **10 to 21 September 2026:** favicon, social metadata, a 16:9 share card, and a rewritten site
  description.
- **22 September 2026:** the AllSides rebalance to 25 outlets at 10/5/10, the Sources column
  folded into the headline, the per outlet cap on breadth, Reddit and the two trend pages
  retired, and the leading story hero introduced.
- **23 to 30 September 2026:** hero image quality, hero layout, the shared term clustering gate,
  the Social Velocity rail restored with Twitter only, and a run of hero refinements.
- **30 September 2026:** latest commit, "Reorganise the hero's evidence column".

**Status: live in production** at www.trendinginrealtime.com, responding 200. Fifty commits
total, two authors.

**Visibly in progress or planned** (from the backlog in the project instructions): evening out
the image supply by scraping og:image from article pages, a daily email digest, fading out
stories older than four hours, fixing the two homepage scrapes that return 403, stripping the
Google News publisher suffix before clustering rather than only in the display label, adding a
time term to the ranking, deleting the stale `trending_dashboard_v2.py`, normalising the dot
counts within buckets, and a public Sources and Methodology page that surfaces the AllSides
attribution in the interface rather than only in the docs.

---

## 8. Numbers and facts

Only things the code proves.

| Fact | Value |
|---|---|
| News outlets | 25 |
| Political balance | 10 left of center, 5 center, 10 right of center |
| AllSides tiers in the roster | 10 Lean Left, 5 Center, 7 Lean Right, 3 Right |
| Ratings source and date | AllSides, snapshot 2026-09-22 |
| Outlets whose homepage is also scraped | 18 |
| Outlets pulled via Google News RSS | 8 |
| Refresh interval | 30 minutes |
| Article age cutoff | 48 hours |
| Articles per outlet per cycle | 20 (Fox News 50) |
| Stories shown in the ranked list | 20, plus the hero at rank 01 |
| Articles per story in the payload | up to 10 |
| Headlines per outlet in the source grid | up to 10 |
| Story categories | 8 |
| Twitter/X trends shown | up to 25 |
| Clustering threshold | 0.28 cosine |
| Cluster merge threshold | 0.20 cosine |
| Minimum shared terms to join a cluster | 2 |
| Max articles counted per outlet toward breadth | 3 |
| Velocity history kept per story | 4 readings |
| Story identity match across refreshes | 33 percent Jaccard overlap on source IDs |
| Stopword list size | 616 entries |
| Clustering gate function word list | 84 entries |
| Python dependencies | 5 |
| Environment variables | 1 (`PORT`) |
| Application size | 2,621 lines, one file |
| Commits | 50, from 7 April 2026 to 30 September 2026 |
| Price | free, no payment code exists |
| Accounts, cookies, trackers | none |

---

## 9. Glossary

- **Heat score / Signal.** The ranking number for a story. Built from how many outlets carry
  it and how prominently each runs it. Displayed in the interface as "Signal".
- **Velocity.** The change in a story's heat score, shown as a four point sparkline plus a
  change badge for the last 30 minutes.
- **Coverage dots.** The row of one dot per outlet under each story, grouped left, center,
  right, and not covering.
- **Lean.** The three bucket political placement (left, center, right) that drives colour
  coding, collapsed from AllSides' five tiers.
- **AllSides.** The third party media bias rating organisation whose ratings the site uses
  verbatim rather than assigning leans itself.
- **Cluster.** A group of articles from different outlets judged to be the same story.
- **TF-IDF cosine similarity.** The maths used to decide whether two headlines are the same
  story. Term frequency inverse document frequency.
- **Shared term gate.** The extra rule requiring two shared content words before an article
  joins a cluster, on top of the similarity score.
- **Hero / leading story.** The top ranked cluster, rendered large at the top of the page as
  item 01.
- **Scrape confirmed.** An article that was also found on its outlet's actual homepage, not
  just in its RSS feed.
- **Editorial spotlight.** An article at homepage position 1 to 3, meaning editors are actively
  leading with it.
- **Double confirmed.** An article that is both near the top of the RSS feed and on the homepage.
- **Synthetic article injection.** Adding a story to an outlet's pool from its homepage when
  the RSS feed missed it.
- **Jaccard matching.** Treating a cluster as the same story across refreshes based on overlap
  in the set of outlets covering it.
- **Last Hour.** The page listing everything published across all outlets in the last 60 minutes.
- **Social Velocity.** The right hand rail of Twitter/X trends.
- **Breaking.** A story whose newest article is under 90 minutes old.
- **Side by Side / Coverage Alignment.** Retired Daily Wire era features. They no longer exist.
- **Blue Trends / Red Trends.** Retired Reddit powered pages. The URLs now redirect to the home
  page.

---

## 10. Likely questions and good answers

**What is TrendingInRealTime?**
It is a live news dashboard. It reads 25 major American news outlets every thirty minutes,
figures out which headlines are the same story, and ranks those stories by how widely and how
prominently the press is covering them. The thing that makes it different from a normal news
aggregator is that every story shows you which outlets across the political spectrum are
carrying it, and which are not.

**Is it free?**
Yes, completely. There is no payment code in it, no accounts, no paywall and no ads. It is just
a public web page.

**How do I use it?**
Go to trendinginrealtime.com. The leading story opens the page, the ranked list runs below it,
and you can click any row to expand it and see every individual article in that story, outlet
by outlet. There is a Last Hour view for anything that just broke, and a source grid if you
want to see what each newsroom is leading with on its own.

**Do I need to sign up?**
No. There is no login, and there is nothing to sign up for. It sets no cookies and runs no
analytics, so I genuinely do not know who visits.

**What model does it use?**
None. There is no AI in it at all, and I think that surprises people. The clustering is TF-IDF
cosine similarity, which is a classic information retrieval technique from well before the
current wave. It is about sixty lines of plain Python using dictionaries, no numpy, no
scikit-learn, no API calls. The hero's lede reads like it was written by a model but it is
template assembly: count the leaders, look up their names, pick one of four sentence shapes.

**Why no AI, given everything else you build?**
Partly because it did not need it, and partly because of what the product is claiming. The
whole position of the site is that it reports what the press is running and adds no judgement
of its own. The moment a model writes a sentence characterising how the coverage splits, that
is an unsourced opinion in the largest type on the page. So the hero quotes two real headlines
instead, one from a left of center outlet and one from a right of center outlet, and lets you
see the framing difference yourself.

**How does the ranking work?**
Each story's score starts from how many distinct outlets are carrying it, times twelve. Then it
adds the article count, then a big bonus for every outlet running it near the top of its feed
or on its homepage, a further bonus when both of those are true, and the largest per outlet
bonus when it sits in an outlet's top three homepage slots, because that means editors actively
chose to lead with it. Almost every term is per outlet on purpose. The score is meant to say
"many newsrooms are on this", not "one newsroom filed a lot".

**How do you decide two headlines are the same story?**
Two tests, and it needs to pass both. First, cosine similarity on TF-IDF vectors of the
headlines has to clear 0.28. Second, it has to share at least two meaningful words with an
existing member. The second test exists because the first one was not enough and the site
shipped the proof. One live cluster held a story about an influencer degree, a story about
political TV ads, and a Real Housewives story about child support. Their only common word was
"paid". A headline is only a handful of words once you strip out the filler, so a single rare
shared word can dominate both vectors.

**Who decides the political labels?**
Not me, and that is deliberate. Every outlet carries its verbatim rating from AllSides, along
with the date I snapshotted it. AllSides publishes five tiers and I collapse them into three
for display. It is also worth saying what AllSides actually rates, which is perspective, not
accuracy or credibility, and only online US political content.

**How do you know your source list is actually balanced?**
Because I checked it and it was not. The site used to claim seven left, six center, seven right
across twenty outlets. When I measured it against the AllSides ratings it was really ten left,
four center, six right, which meant my own hand assigned leans had been wrong on eleven of
twenty, in the direction that made it look balanced. Worse, it meant a left of center story
could light up ten dots and a right of center story only six, so the measurement itself was
tilted by about 67 percent. I fixed it by adding five outlets rather than removing any, which
got it to ten, five and ten.

**Why build this?**
I built it for editorial executives and editorial teams. The idea was that one snapshot would
show you the velocity of the stories moving in the world, the most published and the most
engaged, and at the same time show you how those stories were being reported across different
outlets, where the bias sat and where the emphasis changed depending on who was covering it.
Then it got away from me in a good way. The podcast producers and hosts started using it for
show prep, to check they were talking about the most timely thing. It ended up solving a
different problem from the one I built it for.

**Who is it for?**
Anyone who wants the whole picture without visiting twenty five sites. That is the general
version. In practice it was built for newsrooms and then found an audience with podcast
producers and hosts doing show prep. I should be straight with you though: I run no analytics
on it at all, so I genuinely cannot tell you who uses it today. It is a pet project, not a
business, and I have deliberately not instrumented it.

**What was it before?**
It was an internal editorial intelligence tool for The Daily Wire, built to show that newsroom
which trending stories it was and was not covering. In September 2026 I pivoted it to a general
audience, which meant taking out the Daily Wire source, a Coverage Alignment score and a Side
by Side comparison page. There is a rule in the project notes that the home team framing does
not come back.

**Isn't this just Google News?**
Google News shows you articles. This shows you the shape of coverage. The unit here is a story,
not a headline, and the point is the distribution: which of twenty five outlets are carrying it,
grouped by political lean, with the ones not carrying it visible as empty dots. Google News will
never show you what your sources skipped, because its job is to show you more of what you read.

**Isn't this just Memeorandum or Techmeme?**
Closest comparison, and I actually measured Memeorandum before deciding. It is a genuinely good
product. The reason I did not use it as a feed was sourcing: eight of the twenty headlines on
its panel came from outlets outside my roster, including an advocacy organisation and somebody's
personal Substack. A page that picks twenty five outlets on reputation and third party ratings
cannot put an unvetted back door next to them with nothing marking the difference.

**What are its limitations?**
A few real ones. The clustering still makes occasional bad merges on generic vocabulary, like
grouping unrelated money stories. Thirteen of the twenty five feeds strip images, so the picture
supply is lopsided, which is why only the leading story gets a photo. There is no database, so
every restart loses the velocity history. The ranking has no time term, so it measures magnitude
rather than momentum. And a couple of outlets block server side homepage scraping, so for those
I only see the RSS feed, not what they are leading with.

**What happens when a feed breaks?**
That source just reports zero articles and the dashboard carries on with the rest. The sidebar
shows how many sources are live out of twenty five, so you can see it. There is a QA script in
the repo that checks every feed and every scrape in one pass and exits non zero if anything came
back empty, so I can catch a dead feed in seconds rather than finding out from the page.

**Does it store my data?**
No. No accounts, no cookies, no analytics, no tracking of any kind. I could not tell you who
visits if I wanted to. There is one short lived token embedded in the page, and its only job is
to make it awkward to scrape the data endpoint directly.

**How fresh is the data?**
It refreshes every thirty minutes, and there is a live countdown in the sidebar so you always
know when the next one lands. Articles older than forty eight hours are thrown out entirely, and
an outlet only counts toward a story's breadth if its article is under four hours old or
confirmed on that outlet's homepage.

**What is the difference between the RSS feed and the homepage scraping?**
RSS tells you what an outlet published. The homepage tells you what it chose to lead with, and
that is the more interesting signal. For eighteen of the twenty five I fetch the actual homepage
HTML and record where each story sits on the page. A story in an outlet's top three slots scores
much higher than one buried in the feed, because a human editor made that call.

**What are the coverage dots?**
One dot per outlet across the whole roster, grouped left, then center, then right, then the ones
not carrying the story at all. The shape alone tells you whether something is being covered
across the spectrum or only on one side. The absence is the part people find most interesting,
and it is why the not covering dots are drawn rather than just omitted.

**What is the Social Velocity panel?**
The top twenty five Twitter trends for the US. It is labelled as what it is and it feeds nothing:
no score, no clustering, no ranking. I actually cut it once, after measuring that only three of
twenty five live trends were news and all three were the same story. I put it back because it is
a genuinely independent second signal next to the roster, and unlike a news aggregator it makes
no claim to be journalism.

**What is the tech stack?**
Deliberately boring. Python and Flask, one file, hosted on Railway, auto deploying from GitHub.
Five dependencies total. No database, no build step, no front end framework, no CDN, no
analytics, no paid APIs. All state lives in memory. The whole thing including the HTML, CSS and
JavaScript is about 2,600 lines.

**Why one file and no database?**
Because the data lives for thirty minutes and then gets replaced. There is nothing worth
persisting except the velocity history, and that is four numbers per story. Adding a database
would be real operational weight in exchange for very little. The honest cost is that every
restart is a cold start and the sparklines start again from empty.

**How much does it cost to run?**
Essentially hosting plus the domain. It calls no paid APIs because it uses no AI services and no
commercial data feeds, just public RSS and public web pages.

**Could it scale?**
Not as built, and that is a known tradeoff. Everything is in memory in one process, so you
cannot run two instances without them drifting apart. For what it is, a page that recomputes
every thirty minutes, one process is fine. If it needed to scale the first move is putting the
computed payload somewhere shared. (inferred)

**What is next?**
Two things I actually care about. The first is a daily email digest, so you get a snapshot of
the top stories without being inside the bubble of one perspective or one outlet, just a more
holistic view of what is actually happening. The second is more ambitious and still only an
idea: taking all the versions of a story and synthesising one aggregate account from them, the
most objective version I can get to. I do not know what that would be called or whether it
works, but it is the direction I find interesting. Beyond that the list is housekeeping: a
public methodology page, fading out stale stories, giving the ranking a time term so it rewards
momentum and not just size.

**Can I use your data?**
There is a JSON endpoint but it is gated behind a per session token and robots.txt disallows
it, so no, not as it stands. (needs Chris on whether he would want a real public API.)

**Isn't this just Ground News?**
I am not trying to compete with Ground News. This was a concept I wanted to explore for myself.
It started as a snapshot tool for a newsroom, then podcast producers started using it for show
prep, and it has pivoted from there. If you want the polished commercial product in this space,
that is not what this is.

**How long did it take to build?**
The original took me a weekend. Most of the work since has been taking things out rather than
putting them in. There were a lot more velocity metrics in the first version, and a run of
social sources, and almost all of that is gone now because it did not earn its place.

**What is the cleverest part of it?**
The velocity scoring, and it is less intuitive than it looks. I pull the RSS feeds, which give
me the chronology of what each outlet published. At the same time I crawl their actual
homepages every thirty minutes to see where a story sits and how it is moving. Outlets move
stories up their own page when they are performing, when they are sticky, when they are getting
shared. So watching that movement is a way of inferring how a story is being consumed, not just
that somebody reported it. The score captures both halves.

**Why is the leading story treated differently?**
Because the top story usually deserves more than one line. It gets the rank number, a computed
lede naming the outlets leading it, the coverage dots, a credited photograph, and two real
headlines quoted verbatim from opposite sides of the roster. It is still item 01 of the same
list, which is why the table below it starts at 02.

**Do you weight some outlets more than others?**
No, and I checked this specifically because it looked like I did. Fox News pulls fifty articles
where everyone else pulls twenty, which smells like a thumb on the scale. It is there because
its feed is strictly chronological and pinned stories never float back to the top. When I
measured it, the forty eight hour cutoff bound first so Fox contributed about twenty five
against everyone else's twenty, and every scoring term except the raw article count was already
per outlet. I capped that last one at three articles per outlet anyway, as a guardrail.

---

## 11. What OC should NOT say

- **Do not claim there is any AI, machine learning model or LLM in the product.** There is not.
  If someone assumes it, correct them.
- **Do not state audience numbers, traffic, revenue or growth.** None of that exists in the repo
  and the site runs no analytics, so there is nothing to cite.
- **Do not describe why Chris started it, or any business or strategic intent,** until he has
  answered the questions below. The repo supports what the product does, not what he wanted from
  it.
- **Do not present AllSides ratings as a judgement of accuracy, credibility or quality.** They
  rate perspective only, on online US political content. Say so if the ratings come up.
- **Do not describe retired features as current.** Reddit, Bluesky, Drudge, Memeorandum, Google
  Trends, the Blue Trends and Red Trends pages, the Daily Wire source, Coverage Alignment and the
  Side by Side page are all gone.
- **Do not cite `HANDOFF.md` as current.** It is a September 2026 handoff document describing an
  18 source roster with Bluesky, Reddit, Drudge and Memeorandum. It is history, not the present.
- **Do not discuss security specifics beyond what the privacy policy says,** and never discuss
  credentials, tokens or anything in git history.
- **Do not promise a public API, an email digest, or any backlog item as shipped.** None of them
  are.
- **Do not editorialise about any outlet,** or imply that a political lean says anything about
  quality. The whole product position depends on not doing this.
- **Do not describe `trending_dashboard_v2.py` as part of the product.** It is a stale 371 line
  predecessor that nothing imports or serves.
- **Do not quote a specific uptime, latency or reliability figure.** There is no monitoring to
  back one up.
- **Do not raise known defects or maintenance items.** There are a few open housekeeping items
  on the backlog. They are tracked and they are not interesting to a visitor. Do not volunteer
  them, and if pushed on limitations, use the honest product limitations already listed above
  instead.
- **Do not give out a contact email address,** or discuss the contact details on the privacy
  page. Point people at the site or at Chris directly.
- **Do not present the aggregate objective version of a story as planned, committed or
  underway.** It is an idea Chris finds interesting, nothing more. If it comes up, say that
  plainly. It would also be a real departure from how the product works today, which is to
  report and quote rather than synthesise, so do not imply it is a natural next step.

---

## 12. Questions for Chris

Chris answered the first round in October 2026 and those answers are folded into the document
above. What is still open:

1. **Would you want a real public API?** `/api/data` is token gated and robots.txt disallows
   it today. If the answer is no, I will make that a flat no in OC's answer rather than leaving
   the door ajar.
2. **The aggregate objective version of a story.** This is the one answer I would most like to
   sharpen before OC repeats it. Today the product's whole position is that it reports what the
   press is running and adds no judgement, and the hero deliberately quotes two real headlines
   rather than characterising the split, on the grounds that an unsourced editorial judgement
   would undercut the premise. Synthesising one objective account is the opposite move. Is the
   idea that this sits beside the current product as a separate thing, or that it replaces the
   reporting posture? OC's answer should be different depending on which.
3. **Is there a version of this you would want people to be able to sign up for?** The email
   digest implies collecting an address, which would be the first time the product holds any
   user data at all, and the privacy policy currently says it holds none.
4. **Anything from the Daily Wire period that should stay off the record?** OC currently says
   the product began as an internal tool for that newsroom, because the repo is explicit about
   it. Say the word and I will soften or remove it.
