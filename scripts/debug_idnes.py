#!/usr/bin/env python3
"""
Diagnostic: can we get structured listing data from reality.idnes.cz?

I (Claude) could not investigate this site at all -- both direct fetch and
web search of it are blocked in my tooling, for reasons unrelated to
whether a plain script can reach it. This script starts from scratch:
fetch the page, check status/size, look for JSON-LD structured data (common
on classifieds sites for SEO -- <script type="application/ld+json">), look
for an embedded state blob (Next.js/Nuxt/etc.), and fall back to checking
rendered HTML listing cards.
"""

import json
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

SEARCH_URL = (
    "https://reality.idnes.cz/s/pronajem/byty/nad-10000-do-40000-za-mesic/praha/"
    "?dispozice=4-1%7C5-kk%7C5-1%7C6-kk-a-vetsi"
)


def main():
    print(f"Fetching: {SEARCH_URL}")
    try:
        resp = requests.get(SEARCH_URL, headers=HEADERS, timeout=20)
    except Exception as exc:  # noqa: BLE001
        print(f"Request failed entirely: {exc}")
        return

    print(f"Status: {resp.status_code}")
    print(f"Final URL (after redirects): {resp.url}")
    html = resp.text
    print(f"HTML length: {len(html)} chars")

    if resp.status_code != 200:
        print("Non-200 response, dumping first 1000 chars of body:")
        print(html[:1000])
        return

    # JSON-LD structured data is common on classifieds/news sites for SEO
    ld_json_blocks = re.findall(
        r'<script[^>]+type="application/ld\+json"[^>]*>(.*?)</script>', html, re.DOTALL
    )
    print(f"\nFound {len(ld_json_blocks)} JSON-LD <script> block(s)")
    for i, block in enumerate(ld_json_blocks[:5]):
        try:
            data = json.loads(block)
            print(f"  block {i}: type={data.get('@type')}, keys={list(data.keys())[:10]}")
        except json.JSONDecodeError:
            print(f"  block {i}: failed to parse as JSON, first 200 chars: {block[:200]!r}")

    # Check for common embedded-state patterns
    print("\n=== Checking for embedded JS state ===")
    for needle in ("__NEXT_DATA__", "__NUXT__", "window.__INITIAL_STATE__", "dataLayer", "__APOLLO_STATE__"):
        count = html.count(needle)
        if count:
            print(f"  '{needle}' found ({count}x)")

    # Does the page require JS? (look for common "enable javascript" messages)
    lowered = html.lower()
    for phrase in ("enable javascript", "zapněte javascript", "povolte javascript", "noscript"):
        if phrase in lowered:
            print(f"  Possible JS-requirement marker found: '{phrase}'")

    # Look for rendered listing content directly
    print("\n=== Checking for rendered listing card content ===")
    price_matches = re.findall(r'[\d\s]{4,}\s*Kč', html)
    print(f"'... Kč' price-looking strings found: {len(price_matches)}")
    for p in price_matches[:5]:
        print("   ", p.strip())

    detail_links = sorted(set(re.findall(r'href="(https://reality\.idnes\.cz/detail/[^"]+)"', html)))
    print(f"Detail listing links found: {len(detail_links)}")
    for link in detail_links[:5]:
        print("   ", link)

    # robots.txt check, to know if a script should tread carefully / what's disallowed
    print("\n=== Checking robots.txt ===")
    try:
        robots_resp = requests.get("https://reality.idnes.cz/robots.txt", headers=HEADERS, timeout=10)
        print(f"robots.txt status: {robots_resp.status_code}")
        print(robots_resp.text[:1000])
    except Exception as exc:  # noqa: BLE001
        print(f"robots.txt fetch failed: {exc}")


if __name__ == "__main__":
    main()
