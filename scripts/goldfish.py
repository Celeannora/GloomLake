#!/usr/bin/env python3
"""
Goldfish Simulator — Opening hand and curve execution analysis.

Simulates N random opening hands from a decklist.txt and models
greedy curve execution (play lands, cast highest-CMC affordable spell each turn).

Outputs:
  - Land drought/flood probability
  - Key card access probability by turn (for focus cards)
  - Average CMC of spells cast by turn N
  - Perfect curve (1+2+3+4-drop) probability

Usage:
  python scripts/goldfish.py Decks/my_deck/decklist.txt
  python scripts/goldfish.py Decks/my_deck/decklist.txt --hands 2000 --turns 6
  python scripts/goldfish.py Decks/my_deck/decklist.txt --focus "Card Name"
  python scripts/goldfish.py Decks/my_deck/decklist.txt --seed 42
  python scripts/goldfish.py Decks/burn/decklist.txt --min-keep-lands 1 --max-keep-lands 4

Exit codes:
  0  Simulation complete
  1  Decklist file not found
"""

import argparse
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
from mtg_utils import RepoPaths, parse_decklist

# ---------------------------------------------------------------------------
# Mulligan threshold defaults (60-card midrange)
# Override with --min-keep-lands / --max-keep-lands for other archetypes:
#   Aggro/Burn : --min-keep-lands 1 --max-keep-lands 4
#   Ramp/Control: --min-keep-lands 2 --max-keep-lands 6
# ---------------------------------------------------------------------------
_DEFAULT_MIN_KEEP = 2
_DEFAULT_MAX_KEEP = 5


def load_decklist(path: Path) -> List[Dict]:
    """Return list of {name, qty} dicts parsed from decklist.txt."""
    content = path.read_text(encoding="utf-8")
    cards = []
    in_deck = False
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
        if not parts[0].isdigit():
            continue
        qty = int(parts[0])
        name_parts = []
        for part in parts[1:]:
            if part.startswith("("):
                break
            name_parts.append(part)
        name = " ".join(name_parts)
        cards.append({"name": name, "qty": qty})
    return cards


def load_card_data(card_names: List[str], paths: RepoPaths) -> Dict[str, Dict]:
    """Look up cmc and type_line from local card DB CSVs."""
    import csv
    target = {n.lower(): n for n in card_names}
    found: Dict[str, Dict] = {}
    try:
        from search_cards import CARD_TYPES
    except ImportError:
        CARD_TYPES = [
            "artifact", "battle", "creature", "enchantment",
            "instant", "land", "other", "planeswalker", "sorcery",
        ]
    for card_type in CARD_TYPES:
        type_dir = paths.cards_dir / card_type
        if not type_dir.exists():
            continue
        for csv_file in sorted(type_dir.glob("*.csv")):
            try:
                with open(csv_file, encoding="utf-8") as f:
                    for row in csv.DictReader(f):
                        name_lower = row.get("name", "").lower()
                        if name_lower in target and name_lower not in found:
                            found[name_lower] = row
                            if len(found) == len(target):
                                return found
            except Exception as exc:
                # Log skipped file so users can diagnose DB corruption issues
                print(
                    f"  ⚠ skipped {csv_file.name}: {exc}",
                    file=sys.stderr,
                )
                continue
    return found


def build_deck(
    decklist: List[Dict],
    card_data: Dict[str, Dict],
    unscored: List[str],
) -> List[Dict]:
    """Expand decklist to per-card dicts with cmc and is_land.

    Cards not found in the DB are assigned cmc=None and is_land=False.
    They are tracked in `unscored` and excluded from CMC-based tallies
    (curve charts, cast-by-turn averages) so they don't silently skew
    results by injecting an arbitrary fallback value.
    """
    deck: List[Dict] = []
    for entry in decklist:
        name = entry["name"]
        qty = entry["qty"]
        data = card_data.get(name.lower())
        if data is None:
            # Not found in DB — track for warning; exclude from CMC tallies
            if name not in unscored:
                unscored.append(name)
            cmc: Optional[float] = None
            is_land = False
        else:
            raw_cmc = data.get("cmc")
            cmc = float(raw_cmc) if raw_cmc is not None and str(raw_cmc).strip() != "" else None
            type_line = (data.get("type_line") or "").lower()
            is_land = "land" in type_line and "spell" not in type_line
        for _ in range(qty):
            deck.append({"name": name, "cmc": cmc, "is_land": is_land})
    return deck


def simulate_goldfish(
    deck: List[Dict],
    n_hands: int,
    n_turns: int,
    focus_cards: List[str],
    min_keep_lands: int = _DEFAULT_MIN_KEEP,
    max_keep_lands: int = _DEFAULT_MAX_KEEP,
) -> Dict:
    """Main simulation loop.

    Parameters
    ----------
    deck            : expanded card list (one dict per copy)
    n_hands         : number of hands to simulate
    n_turns         : turns per hand to simulate
    focus_cards     : card names to track access probability for
    min_keep_lands  : minimum lands in 7-card opener to avoid mulligan flag
    max_keep_lands  : maximum lands in 7-card opener to avoid mulligan flag
    """
    focus_lower = {f.lower() for f in focus_cards}

    results: Dict = {
        "land_counts": Counter(),
        "mulligans": 0,
        "focus_seen_by_turn": defaultdict(int),
        "avg_cmc_cast_by_turn": defaultdict(list),
        "lands_played_by_turn": defaultdict(list),
        "on_curve_counts": Counter(),
        "total_hands": n_hands,
        "min_keep_lands": min_keep_lands,
        "max_keep_lands": max_keep_lands,
    }

    for _ in range(n_hands):
        shuffled = deck[:]
        random.shuffle(shuffled)
        hand = shuffled[:7]
        library = shuffled[7:]

        land_count = sum(1 for c in hand if c["is_land"])
        results["land_counts"][land_count] += 1

        if land_count < min_keep_lands or land_count > max_keep_lands:
            results["mulligans"] += 1

        seen_focus: set = set()
        for card in hand:
            if card["name"].lower() in focus_lower:
                seen_focus.add(card["name"].lower())

        lands_in_play = 0
        on_curve_turns = 0

        for turn in range(1, n_turns + 1):
            if library:
                drawn = library.pop(0)
                hand.append(drawn)

            for card in hand:
                key = card["name"].lower()
                if key in focus_lower and key not in seen_focus:
                    seen_focus.add(key)
                    results["focus_seen_by_turn"][turn] += 1

            land_to_play = next((c for c in hand if c["is_land"]), None)
            if land_to_play:
                hand.remove(land_to_play)
                lands_in_play += 1

            mana_available = lands_in_play
            results["lands_played_by_turn"][turn].append(lands_in_play)

            # Only consider cards with a known CMC for casting simulation
            castable = [
                c for c in hand
                if not c["is_land"]
                and c["cmc"] is not None
                and c["cmc"] <= mana_available
                and c["cmc"] > 0
            ]
            if castable:
                best = max(castable, key=lambda c: c["cmc"])
                hand.remove(best)
                results["avg_cmc_cast_by_turn"][turn].append(best["cmc"])
                if best["cmc"] > 0 and lands_in_play >= turn:
                    on_curve_turns += 1
            else:
                results["avg_cmc_cast_by_turn"][turn].append(0)

        results["on_curve_counts"][on_curve_turns] += 1

        for card in hand:
            if card["name"].lower() in focus_lower and card["name"].lower() not in seen_focus:
                results["focus_seen_by_turn"][0] += 1

    return results


def print_report(
    results: Dict,
    n_turns: int,
    focus_cards: List[str],
    unscored: List[str],
) -> None:
    N = results["total_hands"]
    min_k = results["min_keep_lands"]
    max_k = results["max_keep_lands"]
    print(f"\n{'='*65}")
    print(f"  GOLDFISH SIMULATOR — {N:,} hands, {n_turns} turns")
    print(f"  Mulligan rule: keep {min_k}–{max_k} lands in opener")
    print(f"{'='*65}\n")

    # Unscored card warning block
    if unscored:
        print("  ⚠ WARNING — CARDS NOT IN DATABASE (excluded from CMC tallies)\n")
        for name in unscored:
            print(f"    - {name}")
        print("\n  Run 'python scripts/fetch_and_categorize_cards.py' to update the DB.")
        print(f"  These cards are counted in land draws but not in curve/cast charts.\n")

    print("── OPENING HAND LAND DISTRIBUTION ────────────────────────────────")
    print(f"  {'Lands':<8} {'Frequency':>10} {'%':>7}  {'Rating':>12}")
    print(f"  {'-'*8} {'-'*10} {'-'*7}  {'-'*12}")

    def _rating(lands: int) -> str:
        if lands < min_k:
            return "Mulligan ⚫" if lands == 0 else "Very Weak ⚠️"
        if lands > max_k:
            return "Flood ⚠️"
        if lands in (min_k, max_k):
            return "Marginal ⚠️"
        return "Good ✅"

    for lands in range(8):
        count = results["land_counts"].get(lands, 0)
        pct = count / N * 100
        print(f"  {lands:<8} {count:>10,} {pct:>6.1f}%  {_rating(lands)}")

    mull_rate = results["mulligans"] / N * 100
    keep_rate = 100 - mull_rate
    print(f"\n  Keeper rate ({min_k}–{max_k} lands): {keep_rate:.1f}%")
    print(f"  Mulligan candidates:         {mull_rate:.1f}%\n")

    print("── AVERAGE CURVE EXECUTION ────────────────────────────────────────")
    print(f"  {'Turn':<6} {'Avg CMC Cast':>13} {'Avg Lands':>11}")
    print(f"  {'-'*6} {'-'*13} {'-'*11}")
    for turn in range(1, n_turns + 1):
        cmcs = results["avg_cmc_cast_by_turn"].get(turn, [0])
        avg_cmc = sum(cmcs) / len(cmcs) if cmcs else 0
        lands = results["lands_played_by_turn"].get(turn, [0])
        avg_lands = sum(lands) / len(lands) if lands else 0
        print(f"  T{turn:<5} {avg_cmc:>12.2f}  {avg_lands:>10.2f}")
    print()

    print("── ON-CURVE PROBABILITY ────────────────────────────────────────────")
    total_on_curve = sum(
        count for turns, count in results["on_curve_counts"].items() if turns >= 3
    )
    p_three_curve = total_on_curve / N * 100
    total_perfect = sum(
        count for turns, count in results["on_curve_counts"].items() if turns >= n_turns - 1
    )
    p_perfect = total_perfect / N * 100
    print(f"  3+ on-curve turns:     {p_three_curve:.1f}%")
    print(f"  {n_turns-1}+ on-curve turns:     {p_perfect:.1f}%")
    print()

    if focus_cards:
        print("── FOCUS CARD ACCESS ──────────────────────────────────────────────")
        cumulative = 0
        print(f"  Card(s): {', '.join(focus_cards)}")
        print(f"  {'By Turn':<12} {'New Sightings':>14} {'Cumulative %':>13}")
        print(f"  {'-'*12} {'-'*14} {'-'*13}")
        opener = results["focus_seen_by_turn"].get(0, 0)
        print(f"  {'In opener':<12} {opener:>14,} {opener/N*100:>12.1f}%")
        for turn in range(1, n_turns + 1):
            new = results["focus_seen_by_turn"].get(turn, 0)
            cumulative += new
            print(f"  {'T'+str(turn):<12} {new:>14,} {cumulative/N*100:>12.1f}%")
        print()

    print(f"{'='*65}\n")


def main() -> None:
    p = argparse.ArgumentParser(
        prog="goldfish.py",
        description="Goldfish hand simulator for any MTG decklist.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "examples:\n"
            "  %(prog)s Decks/my_deck/decklist.txt\n"
            "  %(prog)s Decks/my_deck/decklist.txt --hands 5000 --turns 7\n"
            "  %(prog)s Decks/my_deck/decklist.txt --focus \"Card Name\"\n"
            "  %(prog)s Decks/my_deck/decklist.txt --seed 42\n"
            "  %(prog)s Decks/burn/decklist.txt --min-keep-lands 1 --max-keep-lands 4\n"
        ),
    )
    p.add_argument("decklist", help="path to decklist.txt")
    p.add_argument(
        "--hands", type=int, default=1000,
        help="number of hands to simulate (default: 1000)",
    )
    p.add_argument(
        "--turns", type=int, default=5,
        help="turns per hand to simulate (default: 5)",
    )
    p.add_argument(
        "--focus", nargs="*", default=[],
        help="card name(s) to track access probability for",
    )
    p.add_argument(
        "--seed", type=int, default=None, metavar="INT",
        help="random seed for reproducible simulation output (default: no seed)",
    )
    p.add_argument(
        "--min-keep-lands", type=int, default=_DEFAULT_MIN_KEEP, metavar="N",
        help=(
            f"minimum lands in 7-card opener to avoid mulligan flag "
            f"(default {_DEFAULT_MIN_KEEP}; use 1 for aggro/burn)"
        ),
    )
    p.add_argument(
        "--max-keep-lands", type=int, default=_DEFAULT_MAX_KEEP, metavar="N",
        help=(
            f"maximum lands in 7-card opener to avoid mulligan flag "
            f"(default {_DEFAULT_MAX_KEEP}; use 6 for ramp/control)"
        ),
    )
    args = p.parse_args()

    deck_path = Path(args.decklist)
    if not deck_path.is_absolute():
        deck_path = RepoPaths().root / deck_path
    if not deck_path.exists():
        print(f"ERROR: decklist not found: {deck_path}", file=sys.stderr)
        sys.exit(1)

    # Seed before any random operation for full reproducibility
    if args.seed is not None:
        random.seed(args.seed)

    decklist = load_decklist(deck_path)
    card_names = [e["name"] for e in decklist]

    print("Looking up card data...", file=sys.stderr)
    paths = RepoPaths()
    card_data = load_card_data(card_names, paths)

    # build_deck populates `unscored` in-place; no arbitrary CMC fallback
    unscored: List[str] = []
    deck = build_deck(decklist, card_data, unscored)

    if unscored:
        print(
            f"  ⚠ {len(unscored)} card(s) not found in DB — excluded from CMC tallies:",
            file=sys.stderr,
        )
        for name in unscored:
            print(f"    - {name}", file=sys.stderr)

    print(
        f"Simulating {args.hands:,} hands ({len(deck)}-card deck)...",
        file=sys.stderr,
    )

    results = simulate_goldfish(
        deck,
        args.hands,
        args.turns,
        args.focus,
        min_keep_lands=args.min_keep_lands,
        max_keep_lands=args.max_keep_lands,
    )
    print_report(results, args.turns, args.focus, unscored)


if __name__ == "__main__":
    main()
