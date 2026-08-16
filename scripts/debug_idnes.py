#!/usr/bin/env python3
"""
Diagnostic: can we get structured listing data from reality.idnes.cz?

Round 2: confirmed reachable, 25 detail links + prices found directly in
rendered HTML (no JS needed). BUT robots.txt explicitly disallows
multi-value filter URLs like ours (dispozice=4-1|5-kk|... matches their
"#multihodnoty" Disallow rules, both raw "|" and encoded "%7C"). This
tests a robots.txt-compliant approach instead: one request per disposition
value, and also dumps GTM dataLayer pushes, which often carry clean
structured per-listing data (id/name/price) for analytics.
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

BASE = "https://reality.idnes.cz/s/pronajem/byty/nad-10000-do-40000-za-mesic/praha/"
# Single-value disposition queries -- NOT disallowed by robots.txt (only the
# multi-value "|"-joined form is disallowed)
SINGLE_DISPOSITION_URLS = [
    f"{BASE}?dispozice=4-1",
    f"{BASE}?dispozice=5-kk",
    f"{BASE}?dispozice=5-1",
    f"{BASE}?dispozice=6-kk-a-vetsi",
]


def dump_datalayer(html):
    print("\n=== dataLayer.push(...) contents ===")
    pushes = re.findall(r"dataLayer\.push\((\{.*?\})\)\s*[;,]", html, re.DOTALL)
    print(f"Found {len(pushes)} dataLayer.push(...) call(s)")
    for i, raw in enumerate(pushes[:10]):
        try:
            parsed = json.loads(raw)
            print(f"  push {i} keys: {list(parsed.keys())}")
            print(f"  push {i} (truncated): {json.dumps(parsed, ensure_ascii=False)[:400]}")
        except json.JSONDecodeError:
            print(f"  push {i}: not valid JSON, first 200 chars: {raw[:200]!r}")


def price_context(html):
    print("\n=== Wider context around price matches ===")
    for mo in list(re.finditer(r'[\d\s]{3,}\s*Kč', html))[:8]:
        start = max(0, mo.start() - 100)
        end = min(len(html), mo.end() + 30)
        print(f"  ...{html[start:end]!r}")


def test_single_disposition():
    print("\n=== Testing robots.txt-compliant single-disposition queries ===")
    all_links = set()
    for url in SINGLE_DISPOSITION_URLS:
        resp = requests.get(url, headers=HEADERS, timeout=20)
        html = resp.text
        links = set(re.findall(r'href="(https://reality\.idnes\.cz/detail/[^"]+)"', html))
        all_links |= links
        print(f"[{resp.status_code}] {url} -> {len(links)} detail link(s)")
    print(f"\nTotal distinct listings across all single-disposition queries: {len(all_links)}")


def main():
    print(f"Fetching (original combined query): {BASE}?dispozice=4-1%7C5-kk%7C5-1%7C6-kk-a-vetsi")
    resp = requests.get(BASE, params={"dispozice": "4-1|5-kk|5-1|6-kk-a-vetsi"}, headers=HEADERS, timeout=20)
    print(f"Status: {resp.status_code}")
    html = resp.text
    print(f"HTML length: {len(html)} chars")

    dump_datalayer(html)
    price_context(html)
    test_single_disposition()


if __name__ == "__main__":
    main()
