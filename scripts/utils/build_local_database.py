#!/usr/bin/env python3
"""
Build Local Database for Offline Validation

Creates a minimal database structure for local/offline deck validation:
    local_db/
    |─── card_index.json      # Lightweight pointer index (~200-300 KB)
    |─── card_names.txt       # Simple list of all legal card names (~100 KB)
    └─── card_details.db      # SQLite database with full card data (~800 KB)

Usage:
    python scripts/build_local_database.py
"""

import csv
import json
import logging
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Set

CARD_TYPES = [
    'artifact', 'battle', 'creature', 'enchantment', 'instant',
    'land', 'other', 'planeswalker', 'sorcery',
]


class LocalDatabaseBuilder:
    def __init__(self, repo_root: Path) -> None:
        from mtg_utils import RepoPaths
        paths = RepoPaths(root=repo_root)
        self.repo_root = repo_root
        self.cards_dir = paths.cards_dir
        self.output_dir = paths.local_db
        # Populated by scan_database(); reused by all export methods
        self.card_index: Dict[str, Dict] = {}
        self.card_names: Set[str] = set()

    def build(self) -> None:
        logging.basicConfig(format="%(levelname)s: %(message)s", level=logging.INFO)
        print("Building local database for offline validation...\n")
        self.output_dir.mkdir(exist_ok=True)

        print("[1/4] Scanning card database...")
        self.scan_database()

        print("[2/4] Creating card_index.json...")
        self.create_pointer_index()

        print("[3/4] Creating card_names.txt...")
        self.create_names_list()

        print("[4/4] Creating card_details.db...")
        self.create_sqlite_db()

        self.print_summary()

    def scan_database(self) -> None:
        """Scan all CSV files and collect card information into self.card_index."""
        if not self.cards_dir.exists():
            logging.error("cards_by_category/ directory not found at %s", self.cards_dir)
            sys.exit(1)

        total_files = 0
        total_rows = 0

        for card_type in CARD_TYPES:
            type_dir = self.cards_dir / card_type
            if not type_dir.exists():
                continue
            for csv_file in sorted(type_dir.glob('*.csv')):
                total_files += 1
                file_rel_path = str(csv_file.relative_to(self.repo_root))
                try:
                    with open(csv_file, encoding='utf-8') as f:
                        for row in csv.DictReader(f):
                            card_name = row.get('name', '').strip()
                            if not card_name:
                                continue
                            name_lower = card_name.lower()
                            self.card_names.add(card_name)
                            if name_lower not in self.card_index:
                                self.card_index[name_lower] = {
                                    'name': card_name,
                                    'type': card_type,
                                    'file': file_rel_path,
                                    'mana_cost': row.get('mana_cost', ''),
                                    'type_line': row.get('type_line', ''),
                                }
                            total_rows += 1
                except Exception as exc:
                    logging.warning("Could not read %s: %s", csv_file.name, exc)

        print(f"  Scanned {total_files} files")
        print(f"  Found {len(self.card_index)} unique cards ({total_rows} total rows)\n")

    def create_pointer_index(self) -> None:
        """Write card_index.json using the data already gathered by scan_database."""
        output_file = self.output_dir / "card_index.json"
        index_data = {
            'version': '1.0',
            'generated': datetime.now(timezone.utc).isoformat(),
            'total_cards': len(self.card_index),
            'cards': self.card_index,
        }
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(index_data, f, indent=2)
        print(f"  Created {output_file.name} ({output_file.stat().st_size:,} bytes)\n")

    def create_names_list(self) -> None:
        """Write card_names.txt using names already gathered by scan_database."""
        output_file = self.output_dir / "card_names.txt"
        with open(output_file, 'w', encoding='utf-8') as f:
            for name in sorted(self.card_names):
                f.write(name + '\n')
        print(f"  Created {output_file.name} ({output_file.stat().st_size:,} bytes)\n")

    def create_sqlite_db(self) -> None:
        """Create SQLite DB reusing card data from self.card_index."""
        output_file = self.output_dir / "card_details.db"
        if output_file.exists():
            output_file.unlink()

        # We need full row data for the SQLite build;
        # card_index only stores a subset, so do one targeted re-read.
        # To avoid a full second disk scan we load only columns we need.
        full_rows: Dict[str, Dict] = {}  # name_lower -> full row data

        for card_type in CARD_TYPES:
            type_dir = self.cards_dir / card_type
            if not type_dir.exists():
                continue
            for csv_file in sorted(type_dir.glob('*.csv')):
                file_rel_path = str(csv_file.relative_to(self.repo_root))
                try:
                    with open(csv_file, encoding='utf-8') as f:
                        for row in csv.DictReader(f):
                            name = row.get('name', '').strip()
                            if not name:
                                continue
                            key = name.lower()
                            if key not in full_rows:
                                full_rows[key] = {
                                    **row,
                                    'card_type': card_type,
                                    'source_file': file_rel_path,
                                }
                except Exception as exc:
                    logging.warning("Could not process %s: %s", csv_file.name, exc)

        with sqlite3.connect(output_file) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                CREATE TABLE cards (
                    name            TEXT PRIMARY KEY COLLATE NOCASE,
                    name_lower      TEXT,
                    mana_cost       TEXT,
                    cmc             REAL,
                    type_line       TEXT,
                    oracle_text     TEXT,
                    colors          TEXT,
                    color_identity  TEXT,
                    rarity          TEXT,
                    set_code        TEXT,
                    set_name        TEXT,
                    collector_number TEXT,
                    power           TEXT,
                    toughness       TEXT,
                    loyalty         TEXT,
                    keywords        TEXT,
                    card_type       TEXT,
                    source_file     TEXT
                )
            ''')
            cursor.execute('CREATE INDEX idx_name_lower ON cards(name_lower)')
            cursor.execute('CREATE INDEX idx_type ON cards(card_type)')

            for key, row in full_rows.items():
                cmc_raw = row.get('cmc', '')
                cmc = float(cmc_raw) if cmc_raw else None
                cursor.execute(
                    'INSERT INTO cards VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                    (
                        row.get('name', '').strip(),
                        key,
                        row.get('mana_cost', ''),
                        cmc,
                        row.get('type_line', ''),
                        row.get('oracle_text', ''),
                        row.get('colors', ''),
                        row.get('color_identity', ''),
                        row.get('rarity', ''),
                        row.get('set', ''),
                        row.get('set_name', ''),
                        row.get('collector_number', ''),
                        row.get('power', ''),
                        row.get('toughness', ''),
                        row.get('loyalty', ''),
                        row.get('keywords', ''),
                        row.get('card_type', ''),
                        row.get('source_file', ''),
                    )
                )
            conn.commit()

        print(f"  Created {output_file.name} ({output_file.stat().st_size:,} bytes)")
        print(f"  Inserted {len(full_rows)} unique cards\n")

    def print_summary(self) -> None:
        print("=" * 60)
        print("\n LOCAL DATABASE SUMMARY\n")
        total_size = 0
        for f in sorted(self.output_dir.glob('*')):
            size = f.stat().st_size
            total_size += size
            print(f"  {f.name:<25} {size:>12,} bytes")
        print(f"\n  {'Total:':<25} {total_size:>12,} bytes  ({total_size / 1024:.1f} KB)")
        print("\n  Files ready in: local_db/")
        print("  card_index.json  - Fast JSON pointer lookup (recommended)")
        print("  card_names.txt   - Simple name list for grep/search")
        print("  card_details.db  - Full SQLite database\n")
        print("\u2705 Local database created successfully!\n")


def main() -> None:
    from mtg_utils import RepoPaths
    paths = RepoPaths()
    builder = LocalDatabaseBuilder(paths.root)
    builder.build()


if __name__ == "__main__":
    main()
