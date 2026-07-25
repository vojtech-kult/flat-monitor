#!/usr/bin/env python3
"""
Flat rent monitor for sreality.cz

Reads a human-facing sreality.cz search URL from config/search_config.json
and fetches it directly (sreality applies all the filters -- room count,
price, city -- server-side, exactly like a browser would). Each search
results page embeds its listing data as JSON in a `__NEXT_DATA__` script
tag (React Query's dehydrated cache); we parse that instead of trying to
call sreality's internal REST API directly, since that API isn't meant for
external use and has changed shape/path before. Pagination uses the same
"&strana=N" parameter the site's own pagination links use.

Outputs:
  data/dorm-database.json   -> current snapshot of everything matching the search
  data/currently-found.json -> ONLY the listings that are new since the last run
                                (overwritten every run; empty list if nothing new)
"""

import json
import math
import re
import sys
import time
import urllib.parse
from pathlib import Path

import requests

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config" / "search_config.json"
DATABASE_PATH = ROOT / "data" / "dorm-database.json"
CURRENTLY_FOUND_PATH = ROOT / "data" / "currently-found.json"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "cs,en;q=0.8",
}

NEXT_DATA_RE = re.compile(
    r'<script[^>]+id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.DOTALL
)
DETAIL_HREF_RE = re.compile(r'href="(/detail/[^"]+/(\d+))"')


def load_config() -> dict:
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def add_or_replace_query_param(url: str, key: str, value) -> str:
    parsed = urllib.parse.urlparse(url)
    query = urllib.parse.parse_qs(parsed.query)
    query[key] = [str(value)]
    new_query = urllib.parse.urlencode(query, doseq=True)
    return urllib.parse.urlunparse(parsed._replace(query=new_query))


def fetch_page(url: str, timeout: float):
    resp = requests.get(url, headers=HEADERS, timeout=timeout)
    resp.raise_for_status()
    html = resp.text

    match = NEXT_DATA_RE.search(html)
    if not match:
        raise RuntimeError(f"Could not find __NEXT_DATA__ on page: {url}")

    try:
        next_data = json.loads(match.group(1))
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Could not parse __NEXT_DATA__ JSON on page {url}: {exc}") from exc

    # id -> full detail URL, built straight from what the page actually rendered
    id_to_url = {}
    for href, listing_id in DETAIL_HREF_RE.findall(html):
        id_to_url[listing_id] = "https://www.sreality.cz" + href

    return next_data, id_to_url


def find_estates_search_query(next_data: dict):
    """Walk the parsed __NEXT_DATA__ looking for the react-query cache entry
    whose queryKey starts with "estatesSearch"."""
    found = []

    def walk(node):
        if isinstance(node, dict):
            key = node.get("queryKey")
            if isinstance(key, list) and key and key[0] == "estatesSearch":
                found.append(node)
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(next_data)
    return found[0] if found else None


def fetch_all_estates(search_url: str, delay: float, timeout: float) -> list:
    """Fetch every page of results for the given sreality search URL and
    return a list of (raw_result_item, detail_url) tuples."""
    all_items = []

    page = 1
    total = None
    limit = None

    while True:
        page_url = search_url if page == 1 else add_or_replace_query_param(search_url, "strana", page)
        next_data, id_to_url = fetch_page(page_url, timeout=timeout)

        query = find_estates_search_query(next_data)
        if query is None:
            raise RuntimeError(f"No estatesSearch data found on page {page} ({page_url})")

        data = query.get("state", {}).get("data") or {}
        results = data.get("results", [])
        pagination = data.get("pagination", {})

        if total is None:
            total = pagination.get("total", len(results))
            limit = pagination.get("limit", len(results) or 1)
            print(f"Total matching listings reported by site: {total} (page size {limit})")

        for item in results:
            listing_id = str(item.get("id"))
            detail_url = id_to_url.get(listing_id, "")
            all_items.append((item, detail_url))

        if not results:
            break

        num_pages = math.ceil(total / limit) if limit else 1
        if page >= num_pages:
            break

        page += 1
        time.sleep(delay)

    return all_items


def normalize_listings(raw_items: list) -> dict:
    """Reshape raw (item, url) pairs into the compact record format we
    store. sreality already applied our price/room/city filters
    server-side, so no extra client-side filtering is needed here."""
    results = {}
    for item, url in raw_items:
        listing_id = item.get("id")
        if listing_id is None:
            continue
        listing_id = str(listing_id)

        locality = item.get("locality") or {}
        city = locality.get("city") or ""
        city_part = locality.get("cityPart") or ""
        location = f"{city} - {city_part}" if city_part else city

        disposition = (item.get("categorySubCb") or {}).get("name", "unknown")

        results[listing_id] = {
            "id": listing_id,
            "name": item.get("name", ""),
            "price": item.get("priceCzk"),
            "location": location,
            "disposition": disposition,
            "url": url,
        }

    return results


def load_json_file(path: Path, default):
    if not path.exists():
        return default
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json_file(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, sort_keys=True)


def main():
    config = load_config()
    search_url = config["search_url"]

    print(f"Scanning: {search_url}")

    raw_items = fetch_all_estates(
        search_url,
        delay=config.get("request_delay_seconds", 1.0),
        timeout=config.get("request_timeout_seconds", 20),
    )
    print(f"Fetched {len(raw_items)} listings across all pages")

    current = normalize_listings(raw_items)
    print(f"{len(current)} listings after normalizing")

    database = load_json_file(DATABASE_PATH, default={})

    new_ids = set(current) - set(database)
    removed_ids = set(database) - set(current)

    newly_found = [current[i] for i in new_ids]

    if removed_ids:
        print(f"Removing {len(removed_ids)} listing(s) no longer on the site")
    if newly_found:
        print(f"Found {len(newly_found)} new listing(s)")
    else:
        print("No new listings this run")

    # Database becomes exactly the current snapshot (adds new, drops gone,
    # refreshes fields like price for ones that are still active).
    save_json_file(DATABASE_PATH, current)
    save_json_file(CURRENTLY_FOUND_PATH, newly_found)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
