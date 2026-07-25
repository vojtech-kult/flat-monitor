#!/usr/bin/env python3
"""
Posts a message to a Discord channel (via an Incoming Webhook) summarizing
the newly-found flats from the most recent scan.

Reads: data/currently-found.json (or data/testing-data.json, see
TESTING_MODE below)
Requires: DISCORD_WEBHOOK_URL environment variable (a Discord "Incoming
Webhook" URL, created in Discord under Server Settings -> Integrations ->
Webhooks -> New Webhook, pointed at whichever channel you want the
announcements in).
Optional: config/search_config.json can set "discord_role_id" to a Discord
role ID (as a string) to @-ping that role whenever new flats are found
(never pinged for the "nothing found" message).
"""

import json
import os
import sys
from pathlib import Path

import requests

# ============================================================================
# >>>>>>>>>>>>>>>>>>>>>>>>  TESTING MODE  <<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<
# When True, this script reads from data/testing-data.json (fake sample
# listings) instead of the real data/currently-found.json, so you can see
# exactly what a Discord announcement looks like without waiting for an
# actual new listing to show up on sreality.
#
#   SET THIS BACK TO False BEFORE RELYING ON REAL SCAN RESULTS!
#
# A big warning is also printed to the run log whenever this is True, so
# it's hard to miss if you forget to flip it back.
# ============================================================================
TESTING_MODE = False
# ============================================================================

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config" / "search_config.json"
CURRENTLY_FOUND_PATH = ROOT / "data" / "currently-found.json"
TESTING_DATA_PATH = ROOT / "data" / "testing-data.json"

DISCORD_MESSAGE_LIMIT = 2000
NO_RESULTS_MESSAGE = "Žádné nové byty nebyly na sreality.cz nalezeny."


def czech_flat_phrase(count: int) -> str:
    """Returns e.g. '1 nový byt', '3 nové byty', '5 nových bytů' with
    correct Czech noun/adjective agreement."""
    last_digit = count % 10
    last_two = count % 100

    if last_digit == 1 and last_two != 11:
        noun_phrase = "nový byt"
    elif 2 <= last_digit <= 4 and not (12 <= last_two <= 14):
        noun_phrase = "nové byty"
    else:
        noun_phrase = "nových bytů"

    return f"{count} {noun_phrase}"


def build_message_chunks(flats: list, role_id: str = None) -> list:
    """Builds the announcement text, split into multiple messages if it
    would exceed Discord's per-message character limit. If role_id is
    given and there are flats to announce, the very first chunk is
    prefixed with a role ping (never pinged for the "nothing found" case)."""
    if not flats:
        return [NO_RESULTS_MESSAGE]

    header = f"**Nalezeno {czech_flat_phrase(len(flats))} na sreality.cz:**"
    if role_id:
        header = f"<@&{role_id}>\n{header}"

    entries = [
        f"{flat['location']}, {flat['disposition']}\n"
        f"{flat['price']}\n"
        f"{flat['url']}"
        for flat in flats
    ]

    chunks = []
    current_lines = [header]
    current_len = len(header)

    for entry in entries:
        # +2 for the blank line separating entries
        added_len = len(entry) + 2
        if current_len + added_len > DISCORD_MESSAGE_LIMIT and len(current_lines) > (1 if not chunks else 0):
            chunks.append("\n\n".join(current_lines))
            current_lines = [entry]
            current_len = len(entry)
        else:
            current_lines.append(entry)
            current_len += added_len

    if current_lines:
        chunks.append("\n\n".join(current_lines))

    return chunks


def send_to_discord(webhook_url: str, content: str) -> None:
    resp = requests.post(webhook_url, json={"content": content}, timeout=15)
    if not resp.ok:
        print(f"WARNING: Discord webhook returned {resp.status_code}: {resp.text[:300]}", file=sys.stderr)
    resp.raise_for_status()


def load_config() -> dict:
    if not CONFIG_PATH.exists():
        return {}
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def load_json_list(path: Path) -> list:
    if not path.exists():
        return []
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def main():
    webhook_url = os.environ.get("DISCORD_WEBHOOK_URL")
    if not webhook_url:
        print("ERROR: DISCORD_WEBHOOK_URL environment variable is not set", file=sys.stderr)
        sys.exit(1)

    if TESTING_MODE:
        print("=" * 70)
        print("⚠️  TESTING_MODE is ON — reading data/testing-data.json,")
        print("    NOT the real data/currently-found.json.")
        print("    Set TESTING_MODE = False in scripts/notify_discord.py")
        print("    once you're done testing!")
        print("=" * 70)
        flats = load_json_list(TESTING_DATA_PATH)
    else:
        flats = load_json_list(CURRENTLY_FOUND_PATH)

    config = load_config()
    role_id = config.get("discord_role_id") or None

    chunks = build_message_chunks(flats, role_id=role_id)

    print(f"Sending {len(chunks)} message(s) to Discord for {len(flats)} newly-found flat(s)")
    for chunk in chunks:
        send_to_discord(webhook_url, chunk)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
