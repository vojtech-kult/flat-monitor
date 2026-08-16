#!/usr/bin/env python3
"""
Diagnostic: can we get structured listing data from ulovdomov.cz?

The search page confirmed it requires JavaScript (no listing data in the
initial HTML). This script:
  1. Confirms that again and lists the JS bundle files referenced.
  2. Greps those bundles for API/GraphQL signatures (same technique that
     found sreality's real data source).
  3. Checks sitemap.xml as a fallback: third-party scrapers for this site
     mentioned working from "the website sitemap or arbitrary listing
     URLs", implying individual listing detail pages might be reachable
     even if the search/list page isn't.
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

SEARCH_URL = "https://www.ulovdomov.cz/pronajem/bytu/praha/4-1?cena-do=40000kc&dispozice=5-kk%2C5-1%2C6-kk&lokace=Praha"


def main():
    print(f"Fetching: {SEARCH_URL}")
    resp = requests.get(SEARCH_URL, headers=HEADERS, timeout=20)
    print(f"Status: {resp.status_code}")
    html = resp.text
    print(f"HTML length: {len(html)} chars")

    lowered = html.lower()
    for phrase in ("nemáte zapnutý javascript", "enable javascript", "noscript"):
        if phrase in lowered:
            print(f"JS-requirement marker found: '{phrase}'")

    for needle in ("__NEXT_DATA__", "__NUXT__", "window.__INITIAL_STATE__"):
        count = html.count(needle)
        print(f"'{needle}' occurrences: {count}")

    script_srcs = sorted(set(re.findall(r'<script[^>]+src="([^"]+)"', html)))
    print(f"\nFound {len(script_srcs)} <script src> reference(s), first 20:")
    for s in script_srcs[:20]:
        print("   ", s)

    print("\n=== Scanning JS bundles for API/GraphQL signatures ===")
    needles = [
        "/api/", "graphql", "algolia", "elastic", "typesense",
        "baseURL", "axios.create", "NEXT_PUBLIC", "process.env",
        "fetch(", "listings", "advertisement", "pronajem",
    ]
    found_any = {}
    checked = 0
    for src in script_srcs:
        if checked >= 40:
            break
        full_url = src if src.startswith("http") else "https://www.ulovdomov.cz" + src
        try:
            r = requests.get(full_url, headers=HEADERS, timeout=15)
            checked += 1
        except Exception as exc:  # noqa: BLE001
            print(f"  [ERR fetching {src}] {exc}")
            continue
        if not r.ok:
            continue
        body = r.text
        for needle in needles:
            if needle in body:
                idx = body.find(needle)
                start = max(0, idx - 80)
                end = min(len(body), idx + 200)
                found_any.setdefault(needle, []).append((src, body[start:end]))

    print(f"Checked {checked} JS bundle(s) (of {len(script_srcs)} total).")
    for needle, hits in found_any.items():
        print(f"\n  Signature '{needle}' found in {len(hits)} bundle(s):")
        for src, ctx in hits[:3]:
            print(f"    file: {src}")
            print(f"    context: {ctx!r}")
    if not found_any:
        print("  No signatures found in the scanned bundles.")

    # Follow up on sitemap-offers.xml: extract a sample listing URL and
    # test whether the detail page itself is server-rendered (unlike the
    # JS-only search page).
    print("\n=== Fetching sitemap-offers.xml ===")
    try:
        r = requests.get("https://www.ulovdomov.cz/sitemap-offers.xml", headers=HEADERS, timeout=20)
        print(f"[{r.status_code}] sitemap-offers.xml (length {len(r.text)})")
        urls = re.findall(r"<loc>(.*?)</loc>", r.text)
        print(f"Found {len(urls)} <loc> URL(s) in sitemap-offers.xml")
        for u in urls[:10]:
            print("   ", u)

        if urls:
            sample_url = urls[0]
            print(f"\n=== Fetching sample listing detail page: {sample_url} ===")
            detail_resp = requests.get(sample_url, headers=HEADERS, timeout=20)
            print(f"Status: {detail_resp.status_code}")
            detail_html = detail_resp.text
            print(f"HTML length: {len(detail_html)} chars")

            for phrase in ("nemáte zapnutý javascript", "noscript"):
                if phrase in detail_html.lower():
                    print(f"  JS-requirement marker found on detail page: '{phrase}'")

            price_matches = re.findall(r'[\d\s]{3,}\s*Kč', detail_html)
            print(f"  '... Kč' price-looking strings on detail page: {len(price_matches)}")
            for p in price_matches[:5]:
                print("     ", p.strip())

            has_next_data = "__NEXT_DATA__" in detail_html
            print(f"  __NEXT_DATA__ present on detail page: {has_next_data}")
    except Exception as exc:  # noqa: BLE001
        print(f"  [ERR] {exc}")


if __name__ == "__main__":
    main()
