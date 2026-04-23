#!/usr/bin/env python3
"""
MTG Standard Card Data Fetcher - Letter-Split Version
Splits card database by type (folder) then first letter of card name.
Target: each file ~80KB max for reliable GitHub API access by AI tools.

File naming convention: {type}/{type}_{letter}.csv
  e.g. cards_by_category/{type}/{type}_a.csv
  If a single letter is still too large: creature_s1.csv, creature_s2.csv

Usage:
    python scripts/fetch_and_categorize_cards.py

Outputs to: cards_by_category/ (relative to repo root when run from repo root)
"""

import io
import csv
import math
import os
from datetime import datetime, timezone
from typing import Dict, List, Tuple
from collections import defaultdict

import requests


CARD_TYPES = [
    'artifact', 'battle', 'creature', 'enchantment', 'instant',
    'land', 'other', 'planeswalker', 'sorcery',
]

CSV_FIELDNAMES = [
    'name', 'mana_cost', 'cmc', 'type_line', 'oracle_text',
    'colors', 'color_identity', 'rarity', 'set', 'set_name',
    'collector_number', 'power', 'toughness', 'loyalty',
    'produced_mana', 'keywords', 'tags', 'legal_formats',
]

# ---------------------------------------------------------------------------
# Strategic tag rules (mirrors search_cards.py — keep in sync)
# ---------------------------------------------------------------------------
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


def _compute_tags(oracle_text: str, keywords: str) -> str:
    """Return semicolon-separated strategic tags for a card."""
    tags = set()
    oracle = oracle_text.lower()
    kw = keywords.lower()
    for tag, patterns in _TAG_RULES:
        if any(p in oracle for p in patterns):
            tags.add(tag)
    for kw_word, tag in _KEYWORD_TAG_MAP.items():
        if kw_word in kw:
            tags.add(tag)
    return ";".join(sorted(tags))


class UniversalCardFetcher:
    """Fetch and categorize Standard-legal MTG cards into letter-split CSV files."""

    # Target max file size: 80 KB (well under GitHub API truncation threshold)
    MAX_FILE_SIZE_BYTES = 80 * 1024
    REQUEST_TIMEOUT = 60  # seconds

    def __init__(self, output_dir: str | None = None):
        from mtg_utils import RepoPaths
        self.bulk_data_url = "https://api.scryfall.com/bulk-data"
        self.output_dir = output_dir or str(RepoPaths().cards_dir)

    def get_bulk_data_download_url(self) -> str | None:
        print("Fetching bulk data information from Scryfall...")
        try:
            response = requests.get(self.bulk_data_url, timeout=self.REQUEST_TIMEOUT)
            response.raise_for_status()
            bulk_data = response.json()
            for item in bulk_data.get('data', []):
                if item.get('type') == 'default_cards':
                    download_uri = item.get('download_uri')
                    size_mb = item.get('size', 0) / (1024 * 1024)
                    print(f"Found: {item.get('name')} | {size_mb:.2f} MB | {item.get('updated_at')}")
                    return download_uri
            print("ERROR: Could not find default_cards bulk data")
            return None
        except requests.exceptions.RequestException as e:
            print(f"Error fetching bulk data info: {e}")
            return None

    def download_bulk_data(self, download_url: str) -> List[Dict]:
        """Download bulk card data using streaming to avoid loading 100MB into memory."""
        print("Downloading bulk card data (this may take 30-60 seconds)...")
        try:
            import json
            response = requests.get(download_url, stream=True, timeout=self.REQUEST_TIMEOUT)
            response.raise_for_status()
            # Accumulate chunks with progress
            chunks = []
            downloaded = 0
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                chunks.append(chunk)
                downloaded += len(chunk)
                print(f"  Downloaded {downloaded / (1024 * 1024):.1f} MB...", end='\r')
            print()  # newline after progress
            cards = json.loads(b''.join(chunks))
            print(f"Downloaded {len(cards)} cards")
            return cards
        except Exception as e:
            print(f"Error downloading bulk data: {e}")
            return []

    def filter_standard_legal(self, all_cards: List[Dict]) -> List[Dict]:
        print("Filtering for Standard legality...")
        standard_cards = [
            c for c in all_cards
            if c.get('legalities', {}).get('standard') == 'legal'
        ]
        print(f"Found {len(standard_cards)} Standard-legal cards")
        return standard_cards

    def extract_relevant_data(self, card: Dict) -> Dict:
        oracle = card.get('oracle_text', '')
        keywords = ';'.join(card.get('keywords', []))
        return {
            'name': card.get('name', ''),
            'mana_cost': card.get('mana_cost', ''),
            'cmc': card.get('cmc', 0),
            'type_line': card.get('type_line', ''),
            'oracle_text': oracle,
            'colors': ','.join(card.get('colors', [])),
            'color_identity': ','.join(card.get('color_identity', [])),
            'keywords': keywords,
            'set': card.get('set', '').upper(),
            'set_name': card.get('set_name', ''),
            'rarity': card.get('rarity', ''),
            'collector_number': card.get('collector_number', ''),
            'power': card.get('power', ''),
            'toughness': card.get('toughness', ''),
            'loyalty': card.get('loyalty', ''),
            'produced_mana': ','.join(card.get('produced_mana', [])),
            'tags': _compute_tags(oracle, keywords),
            'legal_formats': ",".join(
                fmt for fmt, status in card.get("legalities", {}).items()
                if status == "legal"
            ),
        }

    def get_primary_type(self, type_line: str) -> str:
        t = type_line.lower()
        if 'creature' in t:     return 'creature'
        if 'instant' in t:      return 'instant'
        if 'sorcery' in t:      return 'sorcery'
        if 'artifact' in t:     return 'artifact'
        if 'enchantment' in t:  return 'enchantment'
        if 'planeswalker' in t: return 'planeswalker'
        if 'land' in t:         return 'land'
        if 'battle' in t:       return 'battle'
        return 'other'

    def process_and_categorize(self, raw_cards: List[Dict]) -> Dict[str, List[Dict]]:
        """Process and categorize cards, deduplicating by lowercase card name."""
        print("Processing and categorizing cards...")
        categorized: Dict[str, List[Dict]] = defaultdict(list)
        seen_names: set = set()

        for card in raw_cards:
            if card.get('layout') in ['token', 'emblem', 'art_series']:
                continue
            if not card.get('name'):
                continue
            name_key = card['name'].lower()
            if name_key in seen_names:
                continue  # keep first (newest) occurrence; Scryfall bulk data is newest-first
            seen_names.add(name_key)
            processed = self.extract_relevant_data(card)
            category = self.get_primary_type(processed['type_line'])
            categorized[category].append(processed)

        for cat in categorized:
            categorized[cat].sort(key=lambda x: x['name'].lower())

        total = sum(len(v) for v in categorized.values())
        print(f"Processed {total} unique cards into {len(categorized)} types")
        return dict(categorized)

    def estimate_csv_size(self, cards: List[Dict]) -> int:
        if not cards:
            return 0
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=CSV_FIELDNAMES)
        writer.writeheader()
        sample = cards[:min(20, len(cards))]
        writer.writerows(sample)
        sample_bytes = len(buf.getvalue().encode('utf-8'))
        avg = sample_bytes / len(sample)
        return int(avg * len(cards))

    def split_by_letter(
        self, cards: List[Dict], type_name: str
    ) -> List[Tuple[str, List[Dict]]]:
        """
        Split cards by first letter of name.
        If a single letter's file would exceed MAX_FILE_SIZE_BYTES, chunk it
        with numeric suffixes: creature_s1.csv, creature_s2.csv, etc.
        Non-alpha names go into {type}_0.csv.
        """
        letter_groups: Dict[str, List[Dict]] = defaultdict(list)
        for card in cards:
            first = card['name'][0].upper() if card['name'] else '0'
            key = first if first.isalpha() else '0'
            letter_groups[key].append(card)

        parts: List[Tuple[str, List[Dict]]] = []
        for letter in sorted(letter_groups.keys()):
            group = letter_groups[letter]
            estimated = self.estimate_csv_size(group)

            if estimated <= self.MAX_FILE_SIZE_BYTES:
                parts.append((f"{type_name}_{letter.lower()}", group))
            else:
                # Use ceiling division to avoid empty final chunk
                num_chunks = math.ceil(estimated / self.MAX_FILE_SIZE_BYTES)
                per_chunk = math.ceil(len(group) / num_chunks)
                for i in range(num_chunks):
                    chunk = group[i * per_chunk:(i + 1) * per_chunk]
                    if chunk:
                        parts.append((f"{type_name}_{letter.lower()}{i + 1}", chunk))

        return parts

    def write_csv_file(
        self, subdir: str, filename: str, cards: List[Dict]
    ) -> float:
        dirpath = os.path.join(self.output_dir, subdir)
        os.makedirs(dirpath, exist_ok=True)
        filepath = os.path.join(dirpath, f"{filename}.csv")

        with open(filepath, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=CSV_FIELDNAMES, extrasaction='ignore')
            writer.writeheader()
            writer.writerows(cards)

        return os.path.getsize(filepath) / 1024

    def export_all(self, categorized: Dict[str, List[Dict]]) -> List[Dict]:
        print("\nExporting letter-split CSV files...")
        all_stats: List[Dict] = []

        for type_name, cards in sorted(categorized.items()):
            if not cards:
                continue
            parts = self.split_by_letter(cards, type_name)
            print(f"\n  [{type_name}] {len(cards)} cards -> {len(parts)} files")

            for filename, part_cards in parts:
                size_kb = self.write_csv_file(type_name, filename, part_cards)
                print(f"    {type_name}/{filename}.csv  ({len(part_cards)} cards, {size_kb:.1f} KB)")
                all_stats.append({
                    'type': type_name,
                    'filename': filename,
                    'cards': len(part_cards),
                    'size_kb': size_kb,
                })

        self.export_index(all_stats)
        return all_stats

    def export_index(self, stats: List[Dict]) -> None:
        """Write _INDEX.md at root of output_dir."""
        index_file = os.path.join(self.output_dir, "_INDEX.md")
        by_type: Dict[str, List[Dict]] = defaultdict(list)
        for s in stats:
            by_type[s['type']].append(s)

        now = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')
        db_dir = self.output_dir

        with open(index_file, 'w', encoding='utf-8') as f:
            f.write("# Card data index\n\n")
            f.write(f"Last updated: {now}\n\n")
            f.write("## How to find a card\n\n")
            f.write(f"**Pattern**: `{db_dir}/{{type}}/{{type}}_{{first_letter}}.csv`\n\n")
            f.write(f"**Example**: Atraxa (creature, A) -> `{db_dir}/creature/creature_a.csv`\n\n")
            f.write("---\n\n")
            f.write("## Files by type\n\n")

            for type_name in sorted(by_type.keys()):
                type_stats = by_type[type_name]
                total_cards = sum(s['cards'] for s in type_stats)
                f.write(f"### {type_name.capitalize()} ({total_cards} cards)\n\n")
                f.write("| File | Cards | Size |\n")
                f.write("|------|-------|------|\n")
                for s in type_stats:
                    f.write(
                        f"| `{s['type']}/{s['filename']}.csv` "
                        f"| {s['cards']} | {s['size_kb']:.1f} KB |\n"
                    )
                f.write("\n")

            f.write("## CSV columns\n\n")
            f.write(
                "`name`, `mana_cost`, `cmc`, `type_line`, `oracle_text`, `colors`, "
                "`color_identity`, `rarity`, `set`, `set_name`, `collector_number`, "
                "`power`, `toughness`, `loyalty`, `produced_mana`, `keywords`\n"
            )

        print(f"\nIndex written: {index_file}")

    def _write_metadata(self, total_cards: int) -> None:
        """Write metadata.json file for database tracking."""
        import json
        from pathlib import Path
        
        metadata = {
            "version": "1.0",
            "last_updated": datetime.now(timezone.utc).isoformat(),
            "total_cards": total_cards,
            "source": "scryfall",
            "format": "standard"
        }
        
        # Create local_db directory inside output_dir
        metadata_dir = Path(self.output_dir) / "local_db"
        metadata_dir.mkdir(parents=True, exist_ok=True)
        
        metadata_path = metadata_dir / "metadata.json"
        
        with open(metadata_path, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, indent=2)
        
        print(f"Metadata written to {metadata_path}")

    def run(self) -> None:
        print("=" * 70)
        print("MTG Standard Card Data Fetcher - Letter-Split Mode")
        print(f"Output directory: {self.output_dir}/")
        print("=" * 70)

        url = self.get_bulk_data_download_url()
        if not url:
            return

        all_cards = self.download_bulk_data(url)
        if not all_cards:
            return

        standard = self.filter_standard_legal(all_cards)
        if not standard:
            return

        categorized = self.process_and_categorize(standard)
        stats = self.export_all(categorized)

        total_files = len(stats)
        total_cards = sum(s['cards'] for s in stats)
        max_size = max((s['size_kb'] for s in stats), default=0)

        print("\n" + "=" * 70)
        print("Done!")
        print(f"  Files created : {total_files}")
        print(f"  Total cards   : {total_cards}")
        print(f"  Largest file  : {max_size:.1f} KB")
        print(f"  Output dir    : {self.output_dir}/")
        print("=" * 70)
        
        # Write metadata for database tracking
        self._write_metadata(total_cards)


if __name__ == "__main__":
    fetcher = UniversalCardFetcher()
    fetcher.run()
