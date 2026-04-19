#!/usr/bin/env python3
"""
Low-Memory MTG Card Fetcher — Streaming version safe for Android/Termux.

Streams the Scryfall bulk JSON one card at a time using ijson so the full
100 MB payload is NEVER loaded into RAM. Handles gzip-compressed responses.
Peak RAM usage is under 50 MB regardless of device.

Produces identical output to fetch_and_categorize_cards.py:
    cards_by_category/{type}/{type}_{letter}.csv

Usage:
    python scripts/fetch_cards_lowmem.py

Requirements (auto-installed if missing):
    pip install requests ijson
"""
from __future__ import annotations

import csv
import io
import math
import os
import sys
import zlib
from collections import defaultdict
from pathlib import Path
from typing import Dict, List

try:
    import ijson
except ImportError:
    import subprocess
    print("ijson not found — installing...", flush=True)
    subprocess.check_call([sys.executable, "-m", "pip", "install", "ijson"])
    import ijson

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from mtg_utils import RepoPaths

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
CARD_TYPES = [
    "artifact", "battle", "creature", "enchantment", "instant",
    "land", "other", "planeswalker", "sorcery",
]

CSV_FIELDNAMES = [
    "name", "mana_cost", "cmc", "type_line", "oracle_text",
    "colors", "color_identity", "rarity", "set", "set_name",
    "collector_number", "power", "toughness", "loyalty",
    "produced_mana", "keywords", "tags", "legal_formats",
]

MAX_FILE_BYTES = 80 * 1024
REQUEST_TIMEOUT = 90
CHUNK_SIZE = 256 * 1024  # 256 KB chunks

_TAG_RULES = [
    ("lifegain",    ["you gain", "lifelink", "gain life"]),
    ("mill",        ["mill ", "mills ", "put the top", "from the top",
                     "into their graveyard from their library"]),
    ("draw",        ["draw a card", "draw two", "draw three", "draw x", "draw cards"]),
    ("removal",     ["exile target", "destroy target", "deals damage to target",
                     "deals that much damage"]),
    ("counter",     ["counter target spell", "counter that spell",
                     "counter target ability"]),
    ("ramp",        ["add {", "add mana", "search your library for a basic land",
                     "search your library for a land"]),
    ("token",       ["create a ", "create x ", "create two ", "create three ", "token"]),
    ("bounce",      ["return target", "return up to", "return each"]),
    ("discard",     ["discards a card", "discards two", "each opponent discards",
                     "target player discards"]),
    ("tutor",       ["search your library for a card",
                     "search your library for an instant",
                     "search your library for a sorcery"]),
    ("wipe",        ["destroy all", "exile all", "deals damage to all",
                     "deals damage to each"]),
    ("protection",  ["hexproof", "indestructible", "ward {"]),
    ("pump",        ["+1/+1 counter", "gets +", "+x/+x"]),
    ("reanimation", ["return target creature card from your graveyard",
                     "return up to one target creature card from a graveyard"]),
    ("etb",         ["when ~ enters", "when it enters", "enters the battlefield"]),
    ("tribal",      ["other ", "s you control get", "s you control have"]),
    ("scry",        ["scry "]),
    ("surveil",     ["surveil "]),
]
_KEYWORD_TAG_MAP = {
    "flash": "flash", "haste": "haste", "trample": "trample",
    "flying": "flying", "deathtouch": "deathtouch", "vigilance": "vigilance",
    "reach": "reach", "menace": "menace", "lifelink": "lifegain",
}


def _compute_tags(oracle: str, keywords: str) -> str:
    tags: set[str] = set()
    ol = oracle.lower()
    kw = keywords.lower()
    for tag, patterns in _TAG_RULES:
        if any(p in ol for p in patterns):
            tags.add(tag)
    for kw_word, tag in _KEYWORD_TAG_MAP.items():
        if kw_word in kw:
            tags.add(tag)
    return ";".join(sorted(tags))


def _primary_type(type_line: str) -> str:
    t = type_line.lower()
    if "creature"     in t: return "creature"
    if "instant"      in t: return "instant"
    if "sorcery"      in t: return "sorcery"
    if "artifact"     in t: return "artifact"
    if "enchantment"  in t: return "enchantment"
    if "planeswalker" in t: return "planeswalker"
    if "land"         in t: return "land"
    if "battle"       in t: return "battle"
    return "other"


# ---------------------------------------------------------------------------
# Gzip-transparent stream wrapper
# ---------------------------------------------------------------------------

class GzipStreamWrapper(io.RawIOBase):
    """
    Wraps a requests raw stream and transparently decompresses gzip on the fly.
    Passes plain bytes through unchanged if not gzip-encoded.
    """
    def __init__(self, raw_stream, chunk_size: int = CHUNK_SIZE):
        self._raw = raw_stream
        self._chunk_size = chunk_size
        self._buf = b""
        self._done = False
        # Peek first two bytes to detect gzip magic number 0x1f 0x8b
        peek = raw_stream.read(2)
        if peek[:2] == b"\x1f\x8b":
            # wbits=47 => zlib auto-detects gzip or zlib wrapper
            self._decomp = zlib.decompressobj(wbits=47)
            self._buf = self._decomp.decompress(peek)
        else:
            self._decomp = None
            self._buf = peek

    def readable(self):
        return True

    def readinto(self, b):
        while not self._buf and not self._done:
            chunk = self._raw.read(self._chunk_size)
            if not chunk:
                if self._decomp:
                    self._buf = self._decomp.flush()
                self._done = True
                break
            if self._decomp:
                self._buf = self._decomp.decompress(chunk)
            else:
                self._buf = chunk

        if not self._buf:
            return 0

        n = min(len(b), len(self._buf))
        b[:n] = self._buf[:n]
        self._buf = self._buf[n:]
        return n


# ---------------------------------------------------------------------------
# Streaming fetch
# ---------------------------------------------------------------------------

def _get_bulk_url() -> str:
    print("Fetching Scryfall bulk-data manifest...", flush=True)
    r = requests.get("https://api.scryfall.com/bulk-data", timeout=REQUEST_TIMEOUT)
    r.raise_for_status()
    for item in r.json().get("data", []):
        if item.get("type") == "default_cards":
            mb = item.get("size", 0) / 1024 / 1024
            print(f"  Found: {item['name']} | {mb:.1f} MB", flush=True)
            return item["download_uri"]
    raise RuntimeError("default_cards entry not found in Scryfall bulk-data manifest")


def stream_standard_cards(url: str):
    """Generator: yields one processed card dict at a time, Standard-legal only."""
    print("Streaming card data (2-5 min on mobile)...", flush=True)
    seen: set[str] = set()
    count = total = 0

    with requests.get(url, stream=True, timeout=REQUEST_TIMEOUT) as resp:
        resp.raise_for_status()
        # Wrap raw stream with gzip decompressor
        stream = io.BufferedReader(GzipStreamWrapper(resp.raw))
        for card in ijson.items(stream, "item"):
            total += 1
            if total % 5000 == 0:
                print(f"  Scanned {total:,} | kept {count:,} Standard...",
                      end="\r", flush=True)

            if card.get("legalities", {}).get("standard") != "legal":
                continue
            if card.get("layout") in ("token", "emblem", "art_series"):
                continue

            name = card.get("name", "").strip()
            if not name:
                continue
            key = name.lower()
            if key in seen:
                continue
            seen.add(key)
            count += 1

            oracle   = card.get("oracle_text", "")
            keywords = ";".join(card.get("keywords", []))
            yield {
                "name":             name,
                "mana_cost":        card.get("mana_cost", ""),
                "cmc":              card.get("cmc", 0),
                "type_line":        card.get("type_line", ""),
                "oracle_text":      oracle,
                "colors":           ",".join(card.get("colors", [])),
                "color_identity":   ",".join(card.get("color_identity", [])),
                "rarity":           card.get("rarity", ""),
                "set":              card.get("set", "").upper(),
                "set_name":         card.get("set_name", ""),
                "collector_number": card.get("collector_number", ""),
                "power":            card.get("power", ""),
                "toughness":        card.get("toughness", ""),
                "loyalty":          card.get("loyalty", ""),
                "produced_mana":    ",".join(card.get("produced_mana", [])),
                "keywords":         keywords,
                "tags":             _compute_tags(oracle, keywords),
                "legal_formats":    ",".join(
                    fmt for fmt, st in card.get("legalities", {}).items()
                    if st == "legal"
                ),
            }

    print(f"\n  Done: {total:,} scanned, {count:,} Standard-legal kept.", flush=True)


# ---------------------------------------------------------------------------
# Write CSV shards
# ---------------------------------------------------------------------------

def _estimate_row_bytes(rows: list) -> int:
    if not rows:
        return 0
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=CSV_FIELDNAMES)
    w.writeheader()
    w.writerows(rows[:min(20, len(rows))])
    avg = len(buf.getvalue().encode()) / min(20, len(rows))
    return int(avg * len(rows))


def write_shards(categorized: dict, output_dir: Path) -> None:
    print("\nWriting CSV shards...", flush=True)
    for type_name in sorted(categorized):
        cards = sorted(categorized[type_name], key=lambda c: c["name"].lower())
        if not cards:
            continue

        by_letter: dict = defaultdict(list)
        for c in cards:
            letter = c["name"][0].upper() if c["name"] else "0"
            by_letter[letter if letter.isalpha() else "0"].append(c)

        type_dir = output_dir / type_name
        type_dir.mkdir(parents=True, exist_ok=True)

        file_count = 0
        for letter in sorted(by_letter):
            group = by_letter[letter]
            est = _estimate_row_bytes(group)
            if est <= MAX_FILE_BYTES:
                parts = [(f"{type_name}_{letter.lower()}", group)]
            else:
                n = math.ceil(est / MAX_FILE_BYTES)
                per = math.ceil(len(group) / n)
                parts = [
                    (f"{type_name}_{letter.lower()}{i+1}", group[i*per:(i+1)*per])
                    for i in range(n) if group[i*per:(i+1)*per]
                ]

            for fname, rows in parts:
                fpath = type_dir / f"{fname}.csv"
                with open(fpath, "w", newline="", encoding="utf-8") as f:
                    w = csv.DictWriter(f, fieldnames=CSV_FIELDNAMES, extrasaction="ignore")
                    w.writeheader()
                    w.writerows(rows)
                kb = fpath.stat().st_size / 1024
                print(f"  {type_name}/{fname}.csv  ({len(rows)} cards, {kb:.1f} KB)")
                file_count += 1

        print(f"  [{type_name}] {len(cards)} cards -> {file_count} files", flush=True)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    paths = RepoPaths()
    output_dir = paths.cards_dir

    print("=" * 60)
    print("  MTG LOW-MEMORY STREAMING CARD FETCHER")
    print(f"  Output : {output_dir}/")
    print("  RAM    : < 50 MB (gzip stream, no full JSON load)")
    print("=" * 60 + "\n")

    url = _get_bulk_url()

    categorized: dict = defaultdict(list)
    for card in stream_standard_cards(url):
        categorized[_primary_type(card["type_line"])].append(card)

    total = sum(len(v) for v in categorized.values())
    print(f"\n  Categorized {total} unique Standard cards.", flush=True)

    write_shards(categorized, output_dir)

    print("\n" + "=" * 60)
    print("  DONE — cards_by_category/ is ready.")
    print("  Now run:")
    print("  python scripts/goldfish_autoresearch_cli.py \\")
    print("    --name \"Esper Control\" --colors WUB \\")
    print("    --archetype control lifegain \\")
    print("    --primary-axis lifegain,token \\")
    print("    --hands 2000 --turns 6")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()
