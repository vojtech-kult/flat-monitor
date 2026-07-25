#!/usr/bin/env python3
"""
One-off diagnostic: probes several candidate sreality.cz API endpoints and
also greps the real search page HTML for any embedded API path, so we can
see what's actually live right now. Not part of the regular scan -- run
this manually (via the debug workflow) when the main scan starts 404ing.
"""

import re
import requests

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept": "application/json, text/html;q=0.9, */*;q=0.8",
    "Accept-Language": "cs,en;q=0.8",
}


def probe(label, url, params=None):
    try:
        resp = requests.get(url, params=params, headers=HEADERS, timeout=15)
        print(f"[{resp.status_code}] {label}")
        print(f"    URL: {resp.url}")
        ctype = resp.headers.get("content-type", "")
        print(f"    Content-Type: {ctype}")
        snippet = resp.text[:200].replace("\n", " ")
        print(f"    Body start: {snippet}")
    except Exception as exc:  # noqa: BLE001
        print(f"[ERR] {label} -> {exc}")
    print()


def main():
    base = "https://www.sreality.cz/api/cs/v2/estates"

    probe("bare base endpoint, no params", base)
    probe("count endpoint", base + "/count")
    probe(
        "main+type only, no sub_cb",
        base,
        {"category_main_cb": 1, "category_type_cb": 2, "per_page": 1, "page": 1},
    )
    probe(
        "main+type+sub_cb pipe-joined",
        base,
        {
            "category_main_cb": 1,
            "category_type_cb": 2,
            "category_sub_cb": "8|9|10|11",
            "per_page": 1,
            "page": 1,
        },
    )
    probe(
        "main+type+sub_cb[] bracket array",
        base,
        {
            "category_main_cb": 1,
            "category_type_cb": 2,
            "category_sub_cb[]": [8, 9, 10, 11],
            "per_page": 1,
            "page": 1,
        },
    )
    probe("no /cs/ segment", "https://www.sreality.cz/api/v2/estates",
          {"category_main_cb": 1, "category_type_cb": 2, "per_page": 1, "page": 1})
    probe("en locale", "https://www.sreality.cz/api/en/v2/estates",
          {"category_main_cb": 1, "category_type_cb": 2, "per_page": 1, "page": 1})
    probe("api subdomain", "https://api.sreality.cz/cs/v2/estates",
          {"category_main_cb": 1, "category_type_cb": 2, "per_page": 1, "page": 1})

    # Fetch the real search page HTML and hunt for any embedded API path
    print("=== Fetching real search page HTML to look for embedded API refs ===")
    search_url = (
        "https://www.sreality.cz/hledani/pronajem/byty/praha"
        "?velikost=4%2B1%2C4%2Bkk%2C5%2B1%2C5%2Bkk&cena-do=42000"
    )
    try:
        resp = requests.get(search_url, headers=HEADERS, timeout=20)
        print(f"[{resp.status_code}] search page fetch")
        html = resp.text
        # Look for any /api/ style paths referenced in the page or its scripts
        matches = sorted(set(re.findall(r"[\"'](/api/[a-zA-Z0-9/_\-]*)[\"']", html)))
        print(f"Found {len(matches)} distinct /api/ path(s) referenced in HTML:")
        for m in matches[:40]:
            print("   ", m)
        # Also look for fully-qualified api hostnames
        host_matches = sorted(set(re.findall(r"https?://[a-zA-Z0-9_.\-]*api[a-zA-Z0-9_.\-]*\.[a-zA-Z]{2,}", html)))
        print(f"Found {len(host_matches)} api-ish hostname(s) referenced in HTML:")
        for h in host_matches[:40]:
            print("   ", h)
    except Exception as exc:  # noqa: BLE001
        print(f"[ERR] search page fetch -> {exc}")


if __name__ == "__main__":
    main()
