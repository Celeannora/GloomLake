#!/usr/bin/env python3
"""
Reverse Deck Lookup — Identify deck characteristics from a decklist.

Analyzes an MTGA-format decklist to determine:
- Color identity
- Card type distribution
- Key mechanics/strategic tags
- Likely tribe (if tribal)
- Inferred archetype

Usage:
    python scripts/reverse_deck_lookup.py Decks/Your_Deck/decklist.txt
    python scripts/reverse_deck_lookup.py --input Decks/Your_Deck/
    python scripts/reverse_deck_lookup.py --input Decks/Your_Deck/decklist.txt --verbose
"""

import argparse
import csv
import json
import logging
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from mtg_utils import (
    RepoPaths,
    CARD_TYPES,
    parse_decklist,
    TAG_RULES,
    KEYWORD_TAG_MAP,
    compute_tags,
)

logging.basicConfig(format="%(levelname)s: %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)


_COLOR_NAMES = {
    "W": "Azorius",
    "U": "Dimir",
    "B": "Orzhov",
    "R": "Izzet",
    "G": "Selesnya",
    "WU": "Azorius",
    "UB": "Dimir",
    "BR": "Rakdos",
    "RG": "Gruul",
    "GW": "Selesnya",
    "WB": "Orzhov",
    "UR": "Izzet",
    "BG": "Golgari",
    "RW": "Boros",
    "GU": "Simic",
    "W U": "Azorius",
    "U B": "Dimir",
    "B R": "Rakdos",
    "R G": "Gruul",
    "G W": "Selesnya",
    "W B": "Orzhov",
    "U R": "Izzet",
    "B G": "Golgari",
    "R W": "Boros",
    "G U": "Simic",
}


def _derive_color_identity(colors: List[str]) -> str:
    if not colors:
        return "C (Colorless)"
    unique_colors = sorted(set(colors))
    color_str = "".join(unique_colors)
    faction = _COLOR_NAMES.get(color_str, "")
    if faction:
        return f"{color_str} ({faction})"
    if len(unique_colors) > 1:
        return f"{color_str} (Multicolor)"
    return f"{color_str}"


def _derive_card_type(type_line: str) -> str:
    if not type_line:
        return "unknown"
    type_lower = type_line.lower()
    if "creature" in type_lower:
        return "creature"
    if "instant" in type_lower:
        return "instant"
    if "sorcery" in type_lower:
        return "sorcery"
    if "enchantment" in type_lower:
        return "enchantment"
    if "artifact" in type_lower:
        return "artifact"
    if "land" in type_lower:
        return "land"
    if "planeswalker" in type_lower:
        return "planeswalker"
    if "battle" in type_lower:
        return "battle"
    return "other"


def _derive_tribe(type_line: str, tags: Set[str]) -> Tuple[Optional[str], int]:
    if not type_line:
        return None, 0
    type_lower = type_line.lower()
    if "creature" not in type_lower and "enchantment" not in type_lower:
        return None, 0
    tribes = [
        "angel",
        "demon",
        "dragon",
        "elf",
        "goblin",
        "human",
        "knight",
        "merfolk",
        "shapeshifter",
        "sliver",
        "soldier",
        "spirit",
        "vampire",
        "warrior",
        "wizard",
        "zombie",
        "bird",
        "cat",
        "cleric",
        "druid",
        "giants",
        "hippo",
        "insect",
        "beast",
        "elemental",
        "faerie",
        "ogre",
        "orc",
        "phoenix",
        "saurian",
        "tentacle",
        "treefolk",
        "troll",
        "village",
    ]
    for tribe in tribes:
        if re.search(rf"\b{tribe}\b", type_lower):
            return tribe.title(), 1
    if "tribal" in tags or "tribal" in type_lower:
        return " Tribal", 1
    return None, 0


def _infer_archetype(
    card_type_counts: Dict[str, int],
    mechanics: Set[str],
    tribe: Optional[str],
) -> str:
    creatures = card_type_counts.get("creature", 0)
    instants = card_type_counts.get("instant", 0)
    sorceries = card_type_counts.get("sorcery", 0)
    enchantments = card_type_counts.get("enchantment", 0)
    artifacts = card_type_counts.get("artifact", 0)
    lands = card_type_counts.get("land", 0)

    total_spells = creatures + instants + sorceries + enchantments + artifacts
    if total_spells == 0:
        return "unknown"

    creature_ratio = creatures / total_spells if total_spells > 0 else 0

    if "wipe" in mechanics and "removal" in mechanics:
        if "draw" in mechanics:
            return "control"
        return "midrange"

    if "counter" in mechanics and "draw" in mechanics:
        return "control"

    if "removal" in mechanics and "protection" in mechanics:
        if creatures > 12:
            return "aggro"
        return "midrange"

    if "tribal" in mechanics and tribe:
        return f"{tribe.lower()} tribal"

    if "token" in mechanics and "ramp" in mechanics:
        return "tokens"

    if "reanimation" in mechanics:
        return "reanimator"

    if "mill" in mechanics:
        return "mill"

    if creatures < 8 and creature_ratio < 0.3:
        if "draw" in mechanics:
            return "control"
        if "ramp" in mechanics:
            return "ramp"
        return "spells"

    if creatures > 18 and creature_ratio > 0.6:
        if "lifelink" in mechanics:
            return "aggro"
        if "draw" in mechanics:
            return "midrange"
        return "aggro"

    if creatures > 12 and creature_ratio > 0.5:
        if "draw" in mechanics:
            return "midrange"
        return "aggro"

    if "ramp" in mechanics and creatures > 10:
        return "midrange"

    if "draw" in mechanics:
        if creatures > 10:
            return "midrange"
        return "control"

    return "unknown"


class CardDatabase:
    def __init__(self, paths: RepoPaths):
        self.paths = paths
        self.cards: Dict[str, Dict] = {}
        self._load_from_csv()

    def _load_from_csv(self) -> None:
        cards_dir = self.paths.cards_dir
        if not cards_dir.exists():
            logger.error("Cards directory not found: %s", cards_dir)
            sys.exit(1)
        loaded = 0
        for card_type in CARD_TYPES:
            type_dir = cards_dir / card_type
            if not type_dir.exists():
                continue
            for csv_file in type_dir.glob("*.csv"):
                with open(csv_file, encoding="utf-8") as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        name = row.get("name", "")
                        if not name:
                            continue
                        name_lower = name.lower()
                        if name_lower not in self.cards:
                            self.cards[name_lower] = {
                                "name": name,
                                "mana_cost": row.get("mana_cost", ""),
                                "cmc": row.get("cmc", ""),
                                "type_line": row.get("type_line", ""),
                                "oracle_text": row.get("oracle_text", ""),
                                "colors": row.get("colors", ""),
                                "color_identity": row.get("color_identity", ""),
                                "keywords": row.get("keywords", ""),
                            }
                            loaded += 1
        logger.info("Loaded %d unique cards from CSVs.", loaded)

    def lookup(self, name: str) -> Tuple[bool, Optional[Dict]]:
        name_lower = name.lower()
        entry = self.cards.get(name_lower)
        if entry:
            return True, entry
        for key, val in self.cards.items():
            if name_lower in key or key in name_lower:
                return True, val
        return False, None


def get_card_info(name: str, db: CardDatabase) -> Dict:
    found, info = db.lookup(name)
    if found and info:
        return info
    return {
        "name": name,
        "mana_cost": "",
        "cmc": "",
        "type_line": "",
        "oracle_text": "",
        "colors": "",
        "color_identity": "",
        "keywords": "",
    }


def analyze_deck(path: Path) -> Dict:
    paths = RepoPaths()
    db = CardDatabase(paths)

    if path.is_dir():
        path = path / "decklist.txt"
    if not path.exists():
        logger.error("Decklist not found: %s", path)
        sys.exit(1)

    mainboard, sideboard = parse_decklist(path)

    all_cards: List[Tuple[int, str, Dict]] = []
    missing_cards: List[str] = []

    for qty, name in mainboard + sideboard:
        info = get_card_info(name, db)
        all_cards.append((qty, name, info))
        if not info.get("type_line"):
            missing_cards.append(name)

    color_counts: Counter = Counter()
    card_type_counts: Counter = Counter()
    mechanic_counts: Counter = Counter()
    tag_counts: Counter = Counter()
    tribe_counts: Counter = Counter()

    for qty, name, info in all_cards:
        colors = info.get("colors", "")
        color_identity = info.get("color_identity", colors)
        if color_identity:
            for c in color_identity:
                if c in "WUBRG":
                    color_counts[c] += qty

        type_line = info.get("type_line", "")
        card_type = _derive_card_type(type_line)
        card_type_counts[card_type] += qty

        oracle_text = info.get("oracle_text", "")
        keywords = info.get("keywords", "")
        tags = compute_tags(oracle_text, keywords)
        for tag in tags:
            tag_counts[tag] += qty

        tribe, tribe_qty = _derive_tribe(type_line, tags)
        if tribe:
            tribe_counts[tribe] += qty

    colors_list = list(color_counts.elements())
    color_identity = _derive_color_identity(colors_list)

    mechanics: Set[str] = set()
    for tag, count in tag_counts.most_common():
        if count >= 2:
            mechanics.add(tag)

    main_tribe = tribe_counts.most_common(1)
    tribe_str = ""
    if main_tribe and main_tribe[0][1] >= 3:
        tribe_str = f"{main_tribe[0][0]} ({main_tribe[0][1]} cards)"

    archetype = _infer_archetype(
        dict(card_type_counts),
        mechanics,
        main_tribe[0][0] if main_tribe else None,
    )

    deck_name = path.parent.name if path.parent.name != "scripts" else path.stem

    result = {
        "deck_name": deck_name,
        "color_identity": color_identity,
        "card_type_counts": dict(card_type_counts),
        "mechanics": mechanics,
        "tribe": tribe_str,
        "archetype": archetype,
        "missing_cards": missing_cards,
    }

    return result


def format_output(analysis: Dict) -> str:
    lines = []
    lines.append("=== Deck Profile ===")

    lines.append(f"Colors: {analysis['color_identity']}")

    ctc = analysis["card_type_counts"]
    type_parts = []
    type_labels = {
        "creature": "Creatures",
        "instant": "Instants",
        "sorcery": "Sorceries",
        "enchantment": "Enchantments",
        "artifact": "Artifacts",
        "land": "Lands",
    }
    for t, label in type_labels.items():
        if ctc.get(t):
            type_parts.append(f"{label}: {ctc[t]}")
    lines.append(" | ".join(type_parts))

    if analysis["tribe"]:
        lines.append(f"Tribe: {analysis['tribe']}")

    mechanics = analysis["mechanics"]
    if mechanics:
        lines.append(f"Mechanics: {', '.join(sorted(mechanics))}")

    archetype = analysis["archetype"]
    if archetype != "unknown":
        lines.append(f"Archetype: {archetype}")

    missing = analysis.get("missing_cards", [])
    if missing:
        lines.append(f"\nWarning: {len(missing)} cards not found in DB")

    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Reverse deck lookup - analyze decklist characteristics")
    parser.add_argument(
        "input",
        nargs="?",
        help="Decklist file or deck directory",
    )
    parser.add_argument(
        "--input",
        dest="input_path",
        help="Decklist file or deck directory (explicit flag)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Show detailed output",
    )
    args = parser.parse_args()

    input_path = args.input or args.input_path
    if not input_path:
        parser.print_help()
        sys.exit(1)

    path = Path(input_path)
    if not path.is_absolute():
        path = RepoPaths().root / path

    analysis = analyze_deck(path)
    output = format_output(analysis)
    print(output)

    if args.verbose and analysis.get("missing_cards"):
        print("\n=== Missing Cards ===")
        for name in analysis["missing_cards"]:
            print(f"  - {name}")


if __name__ == "__main__":
    main()