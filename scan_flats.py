#!/usr/bin/env python3
"""
Flat rent monitor for sreality.cz

Reads a human-facing sreality.cz search URL from config/search_config.json,
translates it into calls against sreality's public JSON API
(https://www.sreality.cz/api/cs/v2/estates), and diffs the results against
a local "database" file to figure out what's new and what's disappeared.

Outputs:
  data/dorm-database.json   -> current snapshot of everything matching the search
  data/currently-found.json -> ONLY the listings that are new since the last run
                                (overwritten every run; empty list if nothing new)
"""

import json
import re
import sys
import time
import unicodedata
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

API_BASE = "https://www.sreality.cz/api/cs/v2/estates"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept": "application/json",
}

# sreality path segments -> category_main_cb
CATEGORY_MAIN = {
    "byty": 1,
    "domy": 2,
    "pozemky": 3,
    "komercni": 4,
    "ostatni": 5,
}

# sreality path segments -> category_type_cb
CATEGORY_TYPE = {
    "prodej": 1,
    "pronajem": 2,
    "drazby": 3,
}

# "velikost" values (as used in the search URL) -> category_sub_cb, for byty
DISPOSITION_TO_SUBCB = {
    "1+kk": 2, "1+1": 3,
    "2+kk": 4, "2+1": 5,
    "3+kk": 6, "3+1": 7,
    "4+kk": 8, "4+1": 9,
    "5+kk": 10, "5+1": 11,
    "6+": 12,
    "atypical": 16,
}
SUBCB_TO_DISPOSITION = {v: k for k, v in DISPOSITION_TO_SUBCB.items()}

DISPOSITION_REGEX = re.compile(r"\b([1-6]\s?\+\s?(?:kk|[1-9]))\b", re.IGNORECASE)


def strip_diacritics(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text)
    return "".join(c for c in normalized if not unicodedata.combining(c))


def load_config() -> dict:
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def parse_search_url(search_url: str) -> dict:
    """Turn a sreality.cz/hledani/... URL into API query parameters + a
    locality keyword used for client-side filtering."""
    parsed = urllib.parse.urlparse(search_url)
    path_parts = [p for p in parsed.path.split("/") if p]
    # Expected shape: hledani / <prodej|pronajem|drazby> / <byty|domy|...> / <city-slug>
    if len(path_parts) < 3 or path_parts[0] != "hledani":
        raise ValueError(f"Unexpected sreality search URL shape: {search_url}")

    type_slug = path_parts[1]
    main_slug = path_parts[2]
    city_slug = path_parts[3] if len(path_parts) > 3 else None

    if type_slug not in CATEGORY_TYPE:
        raise ValueError(f"Unknown listing type '{type_slug}' in URL")
    if main_slug not in CATEGORY_MAIN:
        raise ValueError(f"Unknown category '{main_slug}' in URL")

    query = urllib.parse.parse_qs(parsed.query)

    sub_cb_ids = []
    if "velikost" in query:
        raw_sizes = query["velikost"][0].split(",")
        for size in raw_sizes:
            size = size.strip()
            code = DISPOSITION_TO_SUBCB.get(size)
            if code:
                sub_cb_ids.append(code)
            else:
                print(f"WARNING: unrecognized velikost value '{size}', skipping filter for it")

    max_price = None
    if "cena-do" in query:
        try:
            max_price = int(query["cena-do"][0])
        except ValueError:
            print(f"WARNING: could not parse cena-do value '{query['cena-do'][0]}'")

    return {
        "category_type_cb": CATEGORY_TYPE[type_slug],
        "category_main_cb": CATEGORY_MAIN[main_slug],
        "category_sub_cb": sub_cb_ids,
        "max_price": max_price,
        "city_keyword": strip_diacritics(city_slug).lower() if city_slug else None,
    }


def fetch_all_estates(params: dict, delay: float, timeout: float) -> list:
    """Paginate through the sreality API and return the raw estate items."""
    query = {
        "category_main_cb": params["category_main_cb"],
        "category_type_cb": params["category_type_cb"],
        "per_page": 60,
        "page": 1,
    }
    if params["category_sub_cb"]:
        query["category_sub_cb"] = params["category_sub_cb"]

    all_items = []
    page = 1
    total = None

    while True:
        query["page"] = page
        resp = requests.get(API_BASE, params=query, headers=HEADERS, timeout=timeout)
        resp.raise_for_status()
        payload = resp.json()

        items = payload.get("_embedded", {}).get("estates", [])
        all_items.extend(items)

        if total is None:
            total = payload.get("result_size", len(items))

        if not items or len(all_items) >= total:
            break

        page += 1
        time.sleep(delay)

    return all_items


def extract_disposition(item: dict) -> str:
    seo = item.get("seo") or {}
    sub_cb = seo.get("category_sub_cb")
    if isinstance(sub_cb, int) and sub_cb in SUBCB_TO_DISPOSITION:
        return SUBCB_TO_DISPOSITION[sub_cb]

    name = item.get("name", "")
    match = DISPOSITION_REGEX.search(name)
    if match:
        return match.group(1).replace(" ", "")

    return "unknown"


def build_detail_url(item: dict) -> str:
    seo = item.get("seo") or {}
    type_slug = seo.get("category_type_cb")
    main_slug = seo.get("category_main_cb")
    locality_slug = seo.get("locality")
    hash_id = item.get("hash_id")

    if type_slug and main_slug and locality_slug and hash_id:
        return f"https://www.sreality.cz/detail/{type_slug}/{main_slug}/{locality_slug}/{hash_id}"

    # Fallback: sreality also resolves bare hash_id search links reasonably
    if hash_id:
        return f"https://www.sreality.cz/detail/pronajem/byt/-/{hash_id}"
    return ""


def extract_price(item: dict):
    price_block = item.get("price_czk") or {}
    value = price_block.get("value_raw")
    if value is None:
        value = item.get("price")
    return value


def normalize_listings(raw_items: list, city_keyword: str, max_price) -> dict:
    """Filter raw API items down to the ones matching city + price, and
    reshape them into the compact record format we store."""
    results = {}
    for item in raw_items:
        hash_id = item.get("hash_id")
        if hash_id is None:
            continue

        price = extract_price(item)
        if max_price is not None and (price is None or price > max_price):
            continue

        locality = item.get("locality", "") or ""
        if city_keyword and city_keyword not in strip_diacritics(locality).lower():
            continue

        results[str(hash_id)] = {
            "id": str(hash_id),
            "name": item.get("name", ""),
            "price": price,
            "location": locality,
            "disposition": extract_disposition(item),
            "url": build_detail_url(item),
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
    search_params = parse_search_url(config["search_url"])

    print(f"Scanning: {config['search_url']}")
    print(f"Resolved API filters: {search_params}")

    raw_items = fetch_all_estates(
        search_params,
        delay=config.get("request_delay_seconds", 1.0),
        timeout=config.get("request_timeout_seconds", 20),
    )
    print(f"Fetched {len(raw_items)} raw listings from the API")

    current = normalize_listings(
        raw_items,
        city_keyword=search_params["city_keyword"],
        max_price=search_params["max_price"],
    )
    print(f"{len(current)} listings match after price/location filtering")

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
