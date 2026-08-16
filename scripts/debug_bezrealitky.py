#!/usr/bin/env python3
"""
Diagnostic: can we get structured listing data from bezrealitky.cz?

Round 2: the .cz /vyhledat path doesn't render visible listing cards (no
"CZK ..." text, no /nemovitosti-byty-domy/ links found), but __NEXT_DATA__
does contain price/disposition/advert/totalCount mentions. This properly
parses that JSON (like we did for sreality's estatesSearch) instead of
guessing key names, to find the real results array.
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
    "https://www.bezrealitky.cz/vyhledat?disposition=DISP_4_1&disposition=DISP_4_KK"
    "&disposition=DISP_5_1&disposition=DISP_5_KK&disposition=DISP_6_1&disposition=DISP_6_KK"
    "&disposition=DISP_7_1&disposition=DISP_7_KK&estateType=BYT&location=exact"
    "&offerType=PRONAJEM&osm_value=Praha%2C+%C4%8Cesko&priceTo=40000"
    "&regionOsmIds=R435514&currency=CZK"
)


def find_arrays_with_key(node, key_hint, path="root", results=None):
    """Recursively find lists of dicts where items contain a key matching
    key_hint (case-insensitive substring), returning (path, list) pairs."""
    if results is None:
        results = []
    if isinstance(node, dict):
        for k, v in node.items():
            find_arrays_with_key(v, key_hint, f"{path}.{k}", results)
    elif isinstance(node, list):
        if node and isinstance(node[0], dict):
            keys = set()
            for item in node[:3]:
                if isinstance(item, dict):
                    keys.update(item.keys())
            if any(key_hint.lower() in k.lower() for k in keys):
                results.append((path, node))
        for i, v in enumerate(node[:5]):
            find_arrays_with_key(v, key_hint, f"{path}[{i}]", results)
    return results


def main():
    print(f"Fetching: {SEARCH_URL}")
    resp = requests.get(SEARCH_URL, headers=HEADERS, timeout=20)
    print(f"Status: {resp.status_code}")
    html = resp.text
    print(f"HTML length: {len(html)} chars")

    m = re.search(r'<script[^>]+id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.DOTALL)
    if not m:
        print("No __NEXT_DATA__ found!")
        return

    blob = m.group(1)
    try:
        data = json.loads(blob)
    except json.JSONDecodeError as exc:
        print(f"Failed to parse __NEXT_DATA__ as JSON: {exc}")
        return

    print(f"__NEXT_DATA__ parsed OK, length {len(blob)} chars")

    # Search for arrays of dicts that look like listing results
    for hint in ("price", "disposition", "advert"):
        print(f"\n=== Searching for arrays with '{hint}'-like keys ===")
        found = find_arrays_with_key(data, hint)
        for path, arr in found[:3]:
            print(f"  Found at {path}: list of {len(arr)} item(s)")
            if arr:
                print(f"    Sample item keys: {list(arr[0].keys())}")
                print(f"    Sample item (truncated): {json.dumps(arr[0], ensure_ascii=False)[:800]}")

    # Also look for totalCount context directly
    print("\n=== Context around 'totalCount' ===")
    for mo in re.finditer("totalCount", blob):
        start = max(0, mo.start() - 150)
        end = min(len(blob), mo.end() + 100)
        print(f"  ...{blob[start:end]!r}")


if __name__ == "__main__":
    main()
