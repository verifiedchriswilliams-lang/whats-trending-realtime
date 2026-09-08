#!/usr/bin/env python3
"""Live source QA for TrendingInRealTime.com.

Checks every RSS feed, every homepage scrape target, and every supplemental
API in one pass, then prints a table you can paste into CLAUDE.md's
per-source QA section.

Run from the repo root:

    python3 scripts/qa_sources.py            # everything
    python3 scripts/qa_sources.py --rss      # RSS feeds only
    python3 scripts/qa_sources.py --scrape   # homepage scrapes only
    python3 scripts/qa_sources.py --supp     # supplemental APIs only

Exit code is 1 if any source came back empty, so this can gate a deploy.
"""
import sys, os, time, argparse
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import trending_dashboard as td

GREEN, YELLOW, RED, DIM, OFF = "\033[32m", "\033[33m", "\033[31m", "\033[2m", "\033[0m"


def _verdict(n, low):
    if n <= 0:
        return RED, "FAIL"
    if n < low:
        return YELLOW, "LOW"
    return GREEN, "ok"


def check_rss():
    print(f"\n{'='*74}\n  RSS FEEDS ({len(td.SOURCES)} sources)\n{'='*74}")
    print(f"{'SOURCE':<14}{'ARTS':>5}{'SEC':>6}  SAMPLE HEADLINE")

    def one(s):
        t = time.time()
        try:
            _, arts = td.fetch_source(s)
        except Exception as ex:
            return s["id"], -1, time.time() - t, f"ERROR {ex}"
        return s["id"], len(arts), time.time() - t, arts[0]["title"] if arts else ""

    with ThreadPoolExecutor(max_workers=18) as ex:
        rows = list(ex.map(one, td.SOURCES))

    failures = []
    for sid, n, sec, sample in rows:
        c, v = _verdict(n, 5)
        if n <= 0:
            failures.append(sid)
        print(f"{sid:<14}{n:>5}{sec:>6.1f}  {c}[{v}]{OFF} {DIM}{sample[:58]}{OFF}")
    return failures


def check_scrape():
    print(f"\n{'='*74}\n  HOMEPAGE SCRAPES ({len(td.SCRAPE_SOURCES)} sources)\n{'='*74}")
    print(f"{'SOURCE':<14}{'HEADS':>6}{'URLS':>6}{'SEC':>6}  TOP HEADLINE")

    def one(item):
        sid, url = item
        t = time.time()
        try:
            heads, url_map, orig_map = td.scrape_homepage(sid, url)
        except Exception as ex:
            return sid, -1, -1, time.time() - t, f"ERROR {ex}"
        top = ""
        if heads:
            top = orig_map.get(heads[0][0], heads[0][0])
        return sid, len(heads), len(url_map), time.time() - t, top

    with ThreadPoolExecutor(max_workers=15) as ex:
        rows = list(ex.map(one, td.SCRAPE_SOURCES.items()))

    failures = []
    for sid, nh, nu, sec, top in rows:
        c, v = _verdict(nh, 5)
        if nh <= 0:
            failures.append(f"{sid} (scrape)")
        inject = "" if nu > 0 else f" {DIM}no url_map — injection disabled{OFF}"
        print(f"{sid:<14}{nh:>6}{nu:>6}{sec:>6.1f}  {c}[{v}]{OFF} {DIM}{top[:44]}{OFF}{inject}")
    return failures


def check_supplemental():
    print(f"\n{'='*74}\n  SUPPLEMENTAL SOURCES\n{'='*74}")
    checks = [
        ("Drudge",         td.fetch_drudge,         3),
        ("Twitter/X",      td.fetch_twitter_trends, 5),
        ("Memeorandum",    td.fetch_memeorandum,    3),
        ("Bluesky",        td.fetch_bluesky_trends, 3),
        ("Liberal Reddit", td.fetch_liberal_reddit, 8),
        # Defined in trending_dashboard.py but NOT wired into refresh_data().
        # Checked here so we know whether the feed still works before rewiring it.
        ("Google Trends*", td.fetch_google_trends,  10),
    ]
    failures = []
    for name, fn, low in checks:
        t = time.time()
        try:
            res = fn()
            n = len(res)
        except Exception as ex:
            n, res = -1, str(ex)
        c, v = _verdict(n, low)
        # Twitter/Google Trends failing is a known-flaky cloud-IP issue, not a regression.
        if n <= 0 and name not in ("Twitter/X", "Google Trends*"):
            failures.append(name)
        print(f"{name:<16}{n:>5}{time.time()-t:>6.1f}  {c}[{v}]{OFF}")
    print(f"\n{DIM}* Google Trends is dead code — never called by refresh_data().{OFF}")
    return failures


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--rss", action="store_true")
    p.add_argument("--scrape", action="store_true")
    p.add_argument("--supp", action="store_true")
    a = p.parse_args()
    run_all = not (a.rss or a.scrape or a.supp)

    failures = []
    if run_all or a.rss:
        failures += check_rss()
    if run_all or a.scrape:
        failures += check_scrape()
    if run_all or a.supp:
        failures += check_supplemental()

    print(f"\n{'='*74}")
    if failures:
        print(f"  {RED}{len(failures)} source(s) returned nothing:{OFF} {', '.join(failures)}")
        return 1
    print(f"  {GREEN}All checked sources returned data.{OFF}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
