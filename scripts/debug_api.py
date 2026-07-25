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
        print(f"HTML length: {len(html)} chars")

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

        # Does the raw HTML already contain listing data server-side rendered?
        for needle in ("hash_id", "__NEXT_DATA__", "__NUXT__", "price_czk", "estates", "window.__INITIAL_STATE__"):
            count = html.count(needle)
            print(f"Occurrences of '{needle}': {count}")

        next_data_match = re.search(
            r'<script[^>]+id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.DOTALL
        )
        if next_data_match:
            blob = next_data_match.group(1)
            print(f"__NEXT_DATA__ blob length: {len(blob)} chars")
            print("First 500 chars of __NEXT_DATA__:")
            print(blob[:500])

            # Show context around every 'estates' occurrence
            for m in re.finditer("estates", blob):
                start = max(0, m.start() - 80)
                end = min(len(blob), m.end() + 80)
                print(f"  ...context around 'estates' @ {m.start()}: {blob[start:end]!r}")

            # Look for likely API/search-backend config keys or hostnames
            for needle in (
                "apiUrl", "apiUri", "apiBase", "apiHost", "endpoint", "graphql",
                "algolia", "elastic", "typesense", "meilisearch", "searchUrl",
                "gatewayUrl", "baseUrl", "restUrl",
            ):
                count = blob.lower().count(needle.lower())
                if count:
                    print(f"  '{needle}' appears {count}x in __NEXT_DATA__")
                    idx = blob.lower().find(needle.lower())
                    start = max(0, idx - 60)
                    end = min(len(blob), idx + 120)
                    print(f"      context: {blob[start:end]!r}")
        else:
            print("No __NEXT_DATA__ script tag found.")

        # Also scan the whole page (not just __NEXT_DATA__) for backend signatures,
        # in case runtime config lives in a separate inline script tag.
        print("=== Scanning full HTML for backend signatures ===")
        for needle in (
            "apiUrl", "apiUri", "apiBase", "apiHost", "endpoint", "graphql",
            "algolia", "elastic", "typesense", "meilisearch", "searchUrl",
            "gatewayUrl", "baseUrl", "restUrl", "sdapi", "gateway",
        ):
            count = html.lower().count(needle.lower())
            if count:
                print(f"  '{needle}' appears {count}x in full HTML")
                idx = html.lower().find(needle.lower())
                start = max(0, idx - 60)
                end = min(len(html), idx + 150)
                print(f"      context: {html[start:end]!r}")

        script_srcs = sorted(set(re.findall(r'<script[^>]+src="([^"]+)"', html)))
        print(f"Found {len(script_srcs)} <script src> reference(s), first 20:")
        for s in script_srcs[:20]:
            print("   ", s)

        # Dig into the actual JS bundles: Next.js apps hardcode their fetch
        # endpoints inside compiled JS, so grep chunk files for signatures.
        print("=== Scanning JS chunk bundles for API/search-backend signatures ===")
        needles = [
            "/api/", "graphql", "algolia", "elastic", "typesense",
            "meilisearch", "hash_id", "price_czk", "category_main_cb",
            "category_sub_cb", "estates?",
        ]
        found_any = {}
        checked = 0
        for src in script_srcs:
            if checked >= 45:
                break
            full_url = src if src.startswith("http") else "https://www.sreality.cz" + src
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
                    end = min(len(body), idx + 160)
                    ctx = body[start:end]
                    found_any.setdefault(needle, []).append((src, ctx))

        print(f"Checked {checked} JS bundle(s).")
        for needle, hits in found_any.items():
            print(f"\n  Signature '{needle}' found in {len(hits)} bundle(s):")
            for src, ctx in hits[:3]:
                print(f"    file: {src}")
                print(f"    context: {ctx!r}")
        if not found_any:
            print("  No signatures found in the scanned bundles.")

    except Exception as exc:  # noqa: BLE001
        print(f"[ERR] search page fetch -> {exc}")


if __name__ == "__main__":
    main()
