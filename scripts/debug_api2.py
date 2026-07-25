#!/usr/bin/env python3
"""
Second-stage diagnostic: sreality's listing data turned out to be embedded
directly in the search page's __NEXT_DATA__ blob (React Query dehydrated
state), under camelCase field names, not fetched from the old
/api/cs/v2/estates endpoint. This script parses that JSON properly to show
us the exact shape of a result item, and probes pagination.
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
    "https://www.sreality.cz/hledani/pronajem/byty/praha"
    "?velikost=4%2B1%2C4%2Bkk%2C5%2B1%2C5%2Bkk&cena-do=42000"
)


def fetch_next_data(url):
    resp = requests.get(url, headers=HEADERS, timeout=20)
    print(f"[{resp.status_code}] GET {url}")
    html = resp.text
    m = re.search(r'<script[^>]+id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.DOTALL)
    if not m:
        print("No __NEXT_DATA__ found!")
        return None, html
    blob = m.group(1)
    try:
        data = json.loads(blob)
    except json.JSONDecodeError as exc:
        print(f"Failed to parse __NEXT_DATA__ as JSON: {exc}")
        return None, html
    return data, html


def find_query(data, key_name):
    """Recursively search the parsed __NEXT_DATA__ for a react-query
    dehydrated query entry whose queryKey[0] == key_name."""
    found = []

    def walk(node):
        if isinstance(node, dict):
            if "queryKey" in node and isinstance(node.get("queryKey"), list):
                if node["queryKey"] and node["queryKey"][0] == key_name:
                    found.append(node)
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(data)
    return found


def main():
    print("=== Fetching page 1 ===")
    data, html = fetch_next_data(SEARCH_URL)
    if data is None:
        return

    matches = find_query(data, "estatesSearch")
    print(f"Found {len(matches)} 'estatesSearch' query cache entrie(s)")

    for q in matches:
        state = q.get("state", {})
        result_data = state.get("data")
        print("\nqueryKey:", json.dumps(q.get("queryKey"), ensure_ascii=False)[:300])
        if result_data is None:
            print("  state.data is None")
            continue
        if isinstance(result_data, dict):
            print("  state.data top-level keys:", list(result_data.keys()))
            for key, val in result_data.items():
                if isinstance(val, list):
                    print(f"    '{key}' is a list of length {len(val)}")
                else:
                    print(f"    '{key}' = {json.dumps(val, ensure_ascii=False)[:200]}")
            # try to find the actual results list
            for key in ("results", "estates", "items", "data"):
                if key in result_data and isinstance(result_data[key], list) and result_data[key]:
                    first = dict(result_data[key][0])
                    first.pop("images", None)  # drop the bulky images array
                    print(f"\n  First item under '{key}' (images omitted):")
                    print(json.dumps(first, ensure_ascii=False, indent=2))
                    break
        elif isinstance(result_data, list):
            print(f"  state.data is a list of length {len(result_data)}")
            if result_data:
                first = dict(result_data[0])
                first.pop("images", None)
                print("  First item (images omitted):")
                print(json.dumps(first, ensure_ascii=False, indent=2))

    # Find actual rendered detail-page links in the HTML, to confirm the
    # real URL pattern (rather than guessing from the old API's seo fields).
    print("\n=== Detail-page hrefs found in rendered HTML ===")
    detail_links = sorted(set(re.findall(r'href="(/detail/[^"]+)"', html)))
    print(f"Found {len(detail_links)} distinct /detail/ href(s), first 10:")
    for link in detail_links[:10]:
        print("   ", link)

    # Look for pagination hints in the raw HTML (rel=next links, "strana", buttons)
    print("\n=== Pagination hints in HTML ===")
    for needle in ("strana=", "rel=\"next\"", "Další", "pagination", "\"page\":"):
        count = html.count(needle)
        if count:
            idx = html.find(needle)
            print(f"'{needle}' appears {count}x, first context: {html[max(0,idx-80):idx+120]!r}")

    # Try requesting page 2 explicitly and see how the embedded queryKey's
    # "page" value and result set change.
    print("\n=== Fetching with &strana=2 to test pagination param ===")
    data2, _ = fetch_next_data(SEARCH_URL + "&strana=2")
    if data2:
        matches2 = find_query(data2, "estatesSearch")
        for q in matches2:
            print("queryKey page 2 attempt:", json.dumps(q.get("queryKey"), ensure_ascii=False)[:300])


if __name__ == "__main__":
    main()
