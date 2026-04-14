#!/usr/bin/env python3
"""
Sideboard Advisor — Matchup-based sideboard suggestions.

Analyzes a mainboard decklist, identifies archetype weaknesses,
and queries the local card database for sideboard candidates.

Usage:
  python scripts/sideboard_advisor.py Decks/my_deck/decklist.txt
  python scripts/sideboard_advisor.py Decks/my_deck/decklist.txt --meta aggro control mill
  python scripts/sideboard_advisor.py --colors WB --meta aggro graveyard

Flags:
  --meta      Meta archetypes to prepare for (space-separated)
              Available: aggro, control, midrange, combo, opp_mill, self_mill,
                         reanimation, graveyard, tokens, aristocrats, artifacts,
                         enchantress, storm, burn, landfall, infect, stax
  --colors    Color identity (default: read from decklist or prompt)
  --budget    Rarity threshold: all, uncommon_max, common_only
  --limit     Max suggestions per matchup (default: 5)
"""

import argparse
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from mtg_utils import RepoPaths
from search_cards import CARD_TYPES, compute_tags

# ── Static matchup weakness map ───────────────────────────────────────────────
# For each meta archetype: what tags/oracle patterns answer it?
MATCHUP_HATE = {
    "aggro": {
        "description": "Fast creature decks (Boros Energy, Mono Red). Need lifegain, cheap removal, blockers.",
        "want_tags": ["lifegain", "removal", "wipe"],
        "want_oracle": ["prevent", "gain.*life", "destroy target creature", "exile target creature"],
        "want_cmc_max": 3,
    },
    "control": {
        "description": "Counterspell/draw-go decks. Need threats that dodge counters, planeswalkers, enchantments.",
        "want_tags": ["protection", "draw", "tutor"],
        "want_oracle": ["flash", "can't be countered", "whenever your opponent", "hexproof"],
        "want_cmc_max": 4,
    },
    "midrange": {
        "description": "Value-threat decks. Need efficient removal and card advantage.",
        "want_tags": ["removal", "wipe", "draw"],
        "want_oracle": ["exile", "destroy", "return.*to.*hand"],
        "want_cmc_max": 4,
    },
    "combo": {
        "description": "Combo decks. Need interaction, hand disruption, counter magic.",
        "want_tags": ["counter", "removal", "discard"],
        "want_oracle": ["counter target spell", "target player discards", "exile target"],
        "want_cmc_max": 3,
    },
    "opp_mill": {
        "description": "Opponent mill decks. Need library replacement and flash threats.",
        "want_tags": ["protection", "lifegain"],
        "want_oracle": ["shuffle.*graveyard.*library", "if.*would.*mill", "hexproof"],
        "want_cmc_max": 3,
    },
    "reanimation": {
        "description": "Graveyard recursion. Need graveyard exile.",
        "want_tags": ["removal"],
        "want_oracle": ["exile.*graveyard", "exile.*all cards.*graveyard", "cards.*can't.*cast.*graveyard"],
        "want_cmc_max": 3,
    },
    "graveyard": {
        "description": "GY value (delve, threshold, flashback). Need exile effects.",
        "want_tags": ["removal"],
        "want_oracle": ["exile.*graveyard", "exile target card", "rest in peace"],
        "want_cmc_max": 3,
    },
    "tokens": {
        "description": "Go-wide token strategies. Need board wipes and token hate.",
        "want_tags": ["wipe", "removal"],
        "want_oracle": ["all creatures.*get.*-", "destroy all creatures", "exile all creatures", "can't attack"],
        "want_cmc_max": 5,
    },
    "aristocrats": {
        "description": "Sacrifice-based value. Need exile (not destroy) removal and instant removal.",
        "want_tags": ["removal"],
        "want_oracle": ["exile target creature", "can't sacrifice", "can't have triggers"],
        "want_cmc_max": 3,
    },
    "artifacts": {
        "description": "Artifact synergy/combo. Need artifact destruction.",
        "want_tags": ["removal"],
        "want_oracle": ["destroy target artifact", "exile target artifact", "artifacts.*can't"],
        "want_cmc_max": 3,
    },
    "enchantress": {
        "description": "Enchantment-based engines. Need enchantment removal.",
        "want_tags": ["removal"],
        "want_oracle": ["destroy target enchantment", "exile target enchantment", "enchantments.*can't"],
        "want_cmc_max": 3,
    },
    "storm": {
        "description": "Spell-chain combo. Need counterspells and hand disruption.",
        "want_tags": ["counter", "discard"],
        "want_oracle": ["counter target instant or sorcery", "discard.*hand", "your opponent can't cast"],
        "want_cmc_max": 2,
    },
    "burn": {
        "description": "Direct damage decks. Need lifegain and damage prevention.",
        "want_tags": ["lifegain", "protection"],
        "want_oracle": ["gain.*life", "prevent.*damage", "you have hexproof"],
        "want_cmc_max": 3,
    },
    "infect": {
        "description": "Poison counter aggro. Need damage prevention and wipe effects.",
        "want_tags": ["wipe", "lifegain", "removal"],
        "want_oracle": ["prevent.*damage", "destroy all creatures", "remove.*counter"],
        "want_cmc_max": 3,
    },
    "stax": {
        "description": "Resource denial/lockout. Need enchantment/artifact hate and cheap interaction.",
        "want_tags": ["removal", "bounce"],
        "want_oracle": ["destroy target artifact or enchantment", "exile target artifact or enchantment"],
        "want_cmc_max": 3,
    },
    "landfall": {
        "description": "Land-drop synergy. Need land destruction and fast aggro pressure.",
        "want_tags": ["removal", "wipe"],
        "want_oracle": ["destroy target land", "land.*can't", "nonbasic land"],
        "want_cmc_max": 4,
    },
}


def load_mainboard_tags(decklist_path: Path, paths: RepoPaths) -> set:
    """Read main deck and collect all tags to understand existing coverage."""
    tags = set()
    content = decklist_path.read_text(encoding="utf-8")
    in_deck = False
    card_names = []
    for line in content.splitlines():
        line = line.strip()
        if line.lower() == "deck":
            in_deck = True
            continue
        if line.lower() == "sideboard":
            break
        if not in_deck or not line:
            continue
        parts = line.split()
        if parts and parts[0].isdigit():
            name_parts = [p for p in parts[1:] if not p.startswith("(")]
            card_names.append(" ".join(name_parts))

    target = {n.lower() for n in card_names}
    for card_type in CARD_TYPES:
        type_dir = paths.cards_dir / card_type
        if not type_dir.exists():
            continue
        for csv_file in sorted(type_dir.glob("*.csv")):
            try:
                with open(csv_file, encoding="utf-8") as f:
                    for row in csv.DictReader(f):
                        if row.get("name", "").lower() in target:
                            for tag in (row.get("tags") or "").split(";"):
                                if tag.strip():
                                    tags.add(tag.strip())
            except Exception:
                continue
    return tags


def search_sideboard_candidates(
    want_tags: list, want_oracle: list, colors: str,
    cmc_max: int, paths: RepoPaths, limit: int = 5
) -> list:
    """Search the DB for sideboard candidates matching the want profile."""
    import re
    results = []
    color_set = set(colors.upper()) if colors else None

    for card_type in CARD_TYPES:
        type_dir = paths.cards_dir / card_type
        if not type_dir.exists():
            continue
        for csv_file in sorted(type_dir.glob("*.csv")):
            try:
                with open(csv_file, encoding="utf-8") as f:
                    for row in csv.DictReader(f):
                        # Color identity check
                        if color_set:
                            card_ci = set((row.get("color_identity") or "").replace("[", "").replace("]", "").replace('"', "").replace("'", "").split(","))
                            card_ci = {c.strip() for c in card_ci if c.strip()}
                            if not card_ci.issubset(color_set | {"C"}):
                                continue
                        # CMC check
                        try:
                            cmc = float(row.get("cmc") or 99)
                        except (ValueError, TypeError):
                            cmc = 99
                        if cmc > cmc_max:
                            continue
                        # Skip basic lands
                        if "basic" in (row.get("type_line") or "").lower():
                            continue
                        # Tag match
                        card_tags = compute_tags(row)
                        tag_match = any(t in card_tags for t in want_tags)
                        # Oracle match
                        oracle = (row.get("oracle_text") or "").lower()
                        oracle_match = any(re.search(pat, oracle) for pat in want_oracle)
                        if tag_match or oracle_match:
                            results.append(row)
            except Exception:
                continue

    # Sort by rarity (mythic > rare > uncommon > common) then cmc
    rarity_order = {"mythic": 0, "rare": 1, "uncommon": 2, "common": 3}
    results.sort(key=lambda r: (rarity_order.get(r.get("rarity", ""), 4), float(r.get("cmc") or 0)))
    return results[:limit]


def main():
    p = argparse.ArgumentParser(
        description="Sideboard advisor: matchup-based suggestions from local DB.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument("decklist", nargs="?", default=None, help="Path to decklist.txt")
    p.add_argument("--meta", nargs="+", default=list(MATCHUP_HATE.keys()),
                   help="Meta archetypes to prepare for")
    p.add_argument("--colors", default=None, help="Color identity (e.g. WB, WUR)")
    p.add_argument("--limit", type=int, default=5, help="Suggestions per matchup (default 5)")
    args = p.parse_args()

    paths = RepoPaths()
    colors = args.colors or ""

    if args.decklist:
        deck_path = Path(args.decklist)
        if not deck_path.exists():
            print(f"ERROR: {deck_path} not found.", file=sys.stderr)
            sys.exit(1)
        main_tags = load_mainboard_tags(deck_path, paths)
        print(f"Mainboard coverage tags: {', '.join(sorted(main_tags))}", file=sys.stderr)
    else:
        main_tags = set()

    print(f"\n{'='*65}")
    print(f"  SIDEBOARD ADVISOR")
    if colors:
        print(f"  Colors: {colors}")
    print(f"  Meta to prepare for: {', '.join(args.meta)}")
    print(f"{'='*65}")

    total_suggestions = []
    seen_names = set()

    for archetype in args.meta:
        if archetype not in MATCHUP_HATE:
            print(f"\n  ⚠ Unknown archetype: {archetype} — skipping")
            continue
        profile = MATCHUP_HATE[archetype]
        print(f"\n── vs {archetype.upper()} ──────────────────────────────────────────")
        print(f"  {profile['description']}")
        print(f"  Looking for: tags={profile['want_tags']}, cmc≤{profile['want_cmc_max']}\n")

        candidates = search_sideboard_candidates(
            profile["want_tags"], profile["want_oracle"], colors,
            profile["want_cmc_max"], paths, limit=args.limit
        )

        if not candidates:
            print(f"  No candidates found in DB for this matchup.")
            continue

        print(f"  {'Card':<35} {'CMC':>4} {'Rarity':>8}  {'Key Tags'}")
        print(f"  {'-'*35} {'-'*4} {'-'*8}  {'-'*20}")
        for card in candidates:
            if card["name"] in seen_names:
                continue
            seen_names.add(card["name"])
            tags = (card.get("tags") or "").replace(";", ", ")[:30]
            print(f"  {card['name']:<35} {card.get('cmc', '?'):>4} {card.get('rarity', ''):>8}  {tags}")
            total_suggestions.append(card)

    # Deduplicated slot summary
    print(f"\n── SUGGESTED SIDEBOARD SLOTS ({min(15, len(seen_names))} of 15) ────────────────────")
    unique = list({c["name"]: c for c in total_suggestions}.values())[:15]
    if len(unique) < 15:
        print(f"  ⚠ Only {len(unique)} unique suggestions found. Broaden --meta or --colors.")
    for i, card in enumerate(unique, 1):
        print(f"  {i:>2}. {card['name']:<35} ({card.get('rarity', '')})")

    print(f"\n{'='*65}")
    print(f"  Run `search_cards.py --type <type> --tags removal --colors {colors or 'YOUR_COLORS'}` for more options.")
    print(f"  Run `goldfish.py` to verify your mana base supports these additions.")
    print(f"{'='*65}\n")


if __name__ == "__main__":
    main()
