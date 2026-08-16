#!/usr/bin/env python3
"""
Diagnostic: can we get structured listing data from bezrealitky.cz?

bezrealitky appears to be a Next.js app (like sreality), so first check
for a __NEXT_DATA__ JSON blob (more reliable than parsing rendered HTML
cards). If that's not there or doesn't contain listings, fall back to
inspecting the rendered HTML listing cards directly, since (unlike
sreality) bezrealitky's search results appeared to be server-rendered
into plain HTML with price/disposition/address/link all present as text.
"""

import re
import requests

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "cs,en;q=0.8",
}

# The exact search URL provided by the user
SEARCH_URL = (
    "https://www.bezrealitky.cz/vyhledat?disposition=DISP_4_1&disposition=DISP_4_KK"
    "&disposition=DISP_5_1&disposition=DISP_5_KK&disposition=DISP_6_1&disposition=DISP_6_KK"
    "&disposition=DISP_7_1&disposition=DISP_7_KK&estateType=BYT&location=exact"
    "&offerType=PRONAJEM&osm_value=Praha%2C+%C4%8Cesko&priceTo=40000"
    "&regionOsmIds=R435514&currency=CZK"
)


def main():
    print(f"Fetching: {SEARCH_URL}")
    resp = requests.get(SEARCH_URL, headers=HEADERS, timeout=20)
    print(f"Status: {resp.status_code}")
    html = resp.text
    print(f"HTML length: {len(html)} chars")

    if resp.status_code != 200:
        print("Non-200 response, dumping first 500 chars of body:")
        print(html[:500])
        return

    # Check for embedded __NEXT_DATA__
    m = re.search(r'<script[^>]+id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.DOTALL)
    if m:
        blob = m.group(1)
        print(f"\n__NEXT_DATA__ found, length: {len(blob)} chars")
        for needle in ("price", "disposition", "advert", "listing", "estate", "totalCount", "results"):
            count = blob.lower().count(needle.lower())
            print(f"  occurrences of '{needle}': {count}")
    else:
        print("\nNo __NEXT_DATA__ script tag found.")

    # Check for rendered listing card content directly in the HTML
    print("\n=== Checking for rendered listing card content ===")
    price_matches = re.findall(r'CZK\s*[\d\s,]+', html)
    print(f"'CZK ...' price-looking strings found: {len(price_matches)}")
    for p in price_matches[:5]:
        print("   ", p.strip())

    disposition_matches = re.findall(r'\b[1-9]\s?\+\s?(?:kk|[1-9])\b', html)
    print(f"Disposition-looking strings (e.g. '4+1'): {len(set(disposition_matches))} distinct")
    print("  sample:", sorted(set(disposition_matches))[:10])

    detail_links = sorted(set(re.findall(r'href="(/nemovitosti-byty-domy/[^"]+)"', html)))
    print(f"Detail listing links found: {len(detail_links)}")
    for link in detail_links[:5]:
        print("   ", link)

    # Look for a results/building count string (site showed e.g. "(1,160 buildings)")
    count_match = re.search(r'\(([\d\s,]+)\s*(byt|budov|nemovitost)', html, re.IGNORECASE)
    if count_match:
        print(f"\nResult count string found: {count_match.group(0)!r}")

    # Pagination check
    page2 = re.search(r'href="([^"]*[?&]strana=2[^"]*)"', html) or re.search(r'href="([^"]*[?&]page=2[^"]*)"', html)
    if page2:
        print(f"\nPagination link found: {page2.group(1)}")
    else:
        print("\nNo obvious 'page 2' link found via strana=/page= patterns.")


if __name__ == "__main__":
    main()
