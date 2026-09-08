#!/usr/bin/env python3
"""Diagnose the 403s on thehill / washtimes / skynews homepage scrapes.

scrape_homepage() sends only a User-Agent and a truncated Accept header. Modern
bot detection (Cloudflare, Akamai) fingerprints exactly that shape. This tries
progressively more browser-like header sets against each blocked host and reports
the first that gets a 200, so we know what to change rather than guessing.

    python3 scripts/probe_403.py

Run it from the Mac — it needs real network access.
"""
import sys, time
import requests

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36")

# What the app sends today.
CURRENT = {
    "User-Agent": UA,
    "Accept": "text/html,application/xhtml+xml",
}

# Full Accept string a real Chrome sends.
FULL_ACCEPT = {
    "User-Agent": UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,"
              "image/webp,image/apng,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

# Everything above plus the Sec-Fetch-* navigation hints Chrome sends on a top-level load.
BROWSER_LIKE = {
    **FULL_ACCEPT,
    "Accept-Encoding": "gzip, deflate, br",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Upgrade-Insecure-Requests": "1",
    "Connection": "keep-alive",
    "Cache-Control": "max-age=0",
}

# Same as BROWSER_LIKE but arriving "from" a search engine, which some walls treat differently.
WITH_REFERER = {**BROWSER_LIKE, "Referer": "https://www.google.com/"}

PROFILES = [
    ("current (what the app sends)", CURRENT),
    ("full Accept + Accept-Language", FULL_ACCEPT),
    ("browser-like (Sec-Fetch-*)",    BROWSER_LIKE),
    ("browser-like + Referer",        WITH_REFERER),
]

TARGETS = {
    "thehill":   "https://thehill.com",
    "washtimes": "https://www.washingtontimes.com",
    "skynews":   "https://news.sky.com",
    # Controls: these scrape fine today. If a profile breaks them, it is not safe to adopt.
    "foxnews":   "https://www.foxnews.com",
    "nypost":    "https://nypost.com",
}


def main():
    print(f"{'HOST':<12}{'PROFILE':<32}{'CODE':>5}{'BYTES':>9}{'SEC':>6}")
    print("-" * 66)
    winners = {}
    for host, url in TARGETS.items():
        for label, headers in PROFILES:
            t = time.time()
            try:
                # A session picks up cookies set by the first challenge response.
                with requests.Session() as sess:
                    r = sess.get(url, headers=headers, timeout=15)
                code, n = r.status_code, len(r.content)
            except Exception as ex:
                print(f"{host:<12}{label:<32}{'ERR':>5}{'-':>9}{time.time()-t:>6.1f}  {ex}")
                continue
            print(f"{host:<12}{label:<32}{code:>5}{n:>9}{time.time()-t:>6.1f}")
            if code == 200 and host not in winners:
                winners[host] = label
            time.sleep(1.5)  # be polite; avoid tripping rate limits mid-probe
        print()

    print("=" * 66)
    for host in TARGETS:
        w = winners.get(host)
        print(f"  {host:<12} {'FIRST 200: ' + w if w else 'no profile succeeded'}")
    blocked = [h for h in ("thehill", "washtimes", "skynews") if h not in winners]
    if blocked:
        print(f"\n  Still blocked: {', '.join(blocked)} — likely needs a real browser"
              f"\n  (JS challenge), not just headers.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
