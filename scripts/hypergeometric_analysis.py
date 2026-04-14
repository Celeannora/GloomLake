#!/usr/bin/env python3
"""
Hypergeometric Analysis — Universal Mana and Access Calculator

Reads any MTGA-format decklist.txt and produces:
  - Land distribution probabilities (opening hand + by-turn)
  - Color source availability (Monte Carlo, reads land color data from DB)
  - Key card / group access probabilities (auto-generated from decklist)
  - Critical opening-hand scenario analysis
  - Mana curve viability assessment (Frank Karsten model)
  - Optional: focus-card combo probability (--combo)

Usage:
    python scripts/hypergeometric_analysis.py Decks/my_deck/decklist.txt
    python scripts/hypergeometric_analysis.py Decks/my_deck/decklist.txt --sims 200000
    python scripts/hypergeometric_analysis.py Decks/my_deck/decklist.txt --seed 42
    python scripts/hypergeometric_analysis.py Decks/my_deck/decklist.txt --turns 7
    python scripts/hypergeometric_analysis.py Decks/my_deck/decklist.txt \\
        --combo "Card A" "Card B" --combo-lands 3

Flags:
    --sims INT          Monte Carlo simulation count (default: 100000)
    --seed INT          Random seed for reproducible output
    --turns INT         Turns to project land-drop probabilities through (default: 6)
    --combo NAMES...    Card names to check for "all in opener" combo probability
    --combo-lands INT   Minimum lands required alongside combo cards (default: 2)
    --on-draw           Model being on the draw (default: on the play)

Exit codes:
    0  Analysis complete
    1  Decklist file not found or unreadable
    2  Deck too small to analyse (<20 cards)
"""

import argparse
import csv
import random
import sys
from collections import defaultdict
from math import comb
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
from mtg_utils import RepoPaths, parse_decklist

# ─── Hypergeometric core ────────────────────────────────────────────────────

def hypergeometric_pmf(N: int, K: int, n: int, k: int) -> float:
    """P(X = k): exactly k successes in n draws from N total with K successes."""
    if k > min(K, n) or k < max(0, n - (N - K)):
        return 0.0
    return comb(K, k) * comb(N - K, n - k) / comb(N, n)


def hypergeometric_cdf_at_least(N: int, K: int, n: int, k_min: int) -> float:
    """P(X >= k_min): probability of drawing at least k_min copies."""
    return sum(hypergeometric_pmf(N, K, n, k) for k in range(k_min, min(K, n) + 1))


def prob_by_turn(
    deck_size: int, copies: int, turn: int, on_play: bool = True
) -> float:
    """Probability of seeing at least 1 copy of a card by the given turn."""
    cards_seen = 7 + (turn - 1) + (0 if on_play else 1)
    return hypergeometric_cdf_at_least(deck_size, copies, cards_seen, 1)


# ─── Card data loading ───────────────────────────────────────────────────────

def load_card_data(card_names: List[str], paths: RepoPaths) -> Dict[str, Dict]:
    """
    Look up cmc, type_line, and color_identity from local DB CSVs.
    Returns only cards that were found; missing cards are silently omitted
    (caller is responsible for emitting a warning).
    """
    try:
        from search_cards import CARD_TYPES
    except ImportError:
        CARD_TYPES = [
            "artifact", "battle", "creature", "enchantment",
            "instant", "land", "other", "planeswalker", "sorcery",
        ]

    target = {n.lower(): n for n in card_names}
    found: Dict[str, Dict] = {}

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
            except Exception:
                continue

    return found


def _land_colors(row: Dict) -> Set[str]:
    """
    Derive the set of colors a land produces from its DB row.

    Checks (in order): 'produced_mana', 'color_identity', oracle_text heuristic.
    Falls back to empty set for colorless / unknown lands.
    """
    # Scryfall CSVs may carry a 'produced_mana' column (e.g. "W,U")
    produced = row.get("produced_mana", "")
    if produced:
        return {c.strip().upper() for c in produced.replace(";", ",").split(",") if c.strip()}

    # Fall back to color_identity
    identity = row.get("color_identity", "")
    if identity:
        colors = {c.strip().upper() for c in identity.replace(";", ",").split(",") if c.strip()}
        # Filter to WUBRG only (identity may include 'C')
        return colors & {"W", "U", "B", "R", "G"}

    # Last resort: scan oracle text for mana symbols
    oracle = (row.get("oracle_text") or "").upper()
    colors: Set[str] = set()
    for color in ("W", "U", "B", "R", "G"):
        if f"{{{color}}}" in oracle or f"ADD {{{color}}}" in oracle:
            colors.add(color)
    return colors


# ─── Deck model ─────────────────────────────────────────────────────────────

def build_deck_model(
    mainboard: List[Tuple[int, str]],
    card_data: Dict[str, Dict],
) -> Tuple[List[Dict], List[str]]:
    """
    Expand the parsed decklist into a per-card list suitable for simulation.

    Each card dict carries:
        name, cmc (float|None), is_land (bool), colors (set[str])

    Returns (deck, unscored_names) where unscored_names are cards absent
    from the DB and therefore excluded from CMC-dependent tallies.
    """
    deck: List[Dict] = []
    unscored: List[str] = []

    for qty, name in mainboard:
        data = card_data.get(name.lower())
        if data is None:
            if name not in unscored:
                unscored.append(name)
            for _ in range(qty):
                deck.append({"name": name, "cmc": None, "is_land": False, "colors": set()})
            continue

        raw_cmc = data.get("cmc")
        cmc: Optional[float] = (
            float(raw_cmc)
            if raw_cmc is not None and str(raw_cmc).strip() != ""
            else None
        )
        type_line = (data.get("type_line") or "").lower()
        is_land = "land" in type_line and "spell" not in type_line
        colors = _land_colors(data) if is_land else set()

        for _ in range(qty):
            deck.append({"name": name, "cmc": cmc, "is_land": is_land, "colors": colors})

    return deck, unscored


# ─── Section 1: Land analysis ─────────────────────────────────────────────────

def analyse_lands(
    deck: List[Dict],
    n_sims: int,
    n_turns: int,
    on_play: bool,
) -> None:
    deck_size = len(deck)
    n_lands = sum(1 for c in deck if c["is_land"])

    print(f"\n## 1. MANA BASE PROBABILITY ({n_lands} lands / {deck_size} cards)")
    print("-" * 52)

    for lands_wanted in range(1, 6):
        p = hypergeometric_cdf_at_least(deck_size, n_lands, 7, lands_wanted)
        print(f"  {lands_wanted}+ lands in opening 7: {p*100:.1f}%")

    print()
    side = "play" if on_play else "draw"
    extra = 0 if on_play else 1
    for turn in range(1, n_turns + 1):
        cards_seen = 7 + (turn - 1) + extra
        p = hypergeometric_cdf_at_least(deck_size, n_lands, cards_seen, turn)
        print(f"  Hit land drop {turn} by turn {turn} (on {side}): {p*100:.1f}%")

    # Color source availability — derive all colors present in the mana base
    color_sources: Dict[str, int] = defaultdict(int)
    for card in deck:
        if card["is_land"]:
            for color in card["colors"]:
                color_sources[color] += 1

    active_colors = sorted(color_sources.keys())
    if active_colors:
        print(f"\n  Color Source Availability (opening 7):")
        for color in active_colors:
            count = color_sources[color]
            p1 = hypergeometric_cdf_at_least(deck_size, count, 7, 1)
            p2 = hypergeometric_cdf_at_least(deck_size, count, 7, 2)
            print(f"  1+ {color} source:  {p1*100:.1f}%   |  2+ {color} sources: {p2*100:.1f}%")

    # Monte Carlo multi-color access
    if len(active_colors) >= 2:
        print(f"\n  Monte Carlo Multi-Color Access ({n_sims:,} sims):")
        _simulate_color_access(deck, n_sims, active_colors, on_play)


def _simulate_color_access(
    deck: List[Dict],
    n_sims: int,
    colors: List[str],
    on_play: bool,
) -> None:
    """
    Monte Carlo: probability of having access to all active colors by turns 1-3.
    Land color data comes from the DB-populated deck model — no hardcoding.
    """
    target_all = set(colors)
    extra = 0 if on_play else 1

    # Cards seen by turn T (on play: 7+T-1, on draw: 7+T)
    windows = {
        "opener (7)": 7,
        "T2 play" if on_play else "T2 draw": 8 + extra,
        "T3 play" if on_play else "T3 draw": 9 + extra,
    }

    counts: Dict[str, int] = {label: 0 for label in windows}

    for _ in range(n_sims):
        shuffled = deck[:]
        random.shuffle(shuffled)
        for label, n_cards in windows.items():
            seen_colors: Set[str] = set()
            for card in shuffled[:n_cards]:
                seen_colors |= card["colors"]
            if target_all.issubset(seen_colors):
                counts[label] += 1

    for label, count in counts.items():
        all_colors = "/".join(colors)
        print(f"  All {all_colors} by {label}: {count/n_sims*100:.1f}%")


# ─── Section 2: Key card access (auto-generated) ─────────────────────────────

def analyse_key_cards(
    mainboard: List[Tuple[int, str]],
    deck_size: int,
    on_play: bool,
) -> None:
    """
    Build and print the access probability table from the parsed decklist.
    Cards are grouped by name; copy count is read directly — no manual list.
    """
    print("\n\n## 2. KEY CARD ACCESS PROBABILITIES")
    print("-" * 52)

    # Aggregate copy counts
    copy_counts: Dict[str, int] = defaultdict(int)
    for qty, name in mainboard:
        copy_counts[name] += qty

    # Sort: 4-ofs first (most consistent), then descending, then alphabetical
    sorted_cards = sorted(copy_counts.items(), key=lambda x: (-x[1], x[0]))

    header = f"  {'Card':<45} {'Opener':>8} {'By T3':>8} {'By T5':>8}"
    print(f"\n{header}")
    print(f"  {'-'*45} {'-'*8} {'-'*8} {'-'*8}")

    for name, copies in sorted_cards:
        p_opener = hypergeometric_cdf_at_least(deck_size, copies, 7, 1)
        p_t3 = prob_by_turn(deck_size, copies, 3, on_play)
        p_t5 = prob_by_turn(deck_size, copies, 5, on_play)
        label = f"{name} (×{copies})"
        print(f"  {label:<45} {p_opener*100:>7.1f}% {p_t3*100:>7.1f}% {p_t5*100:>7.1f}%")


# ─── Section 3: Opening hand scenarios ───────────────────────────────────────

def analyse_opening_hands(
    deck: List[Dict],
    n_sims: int,
    combo_cards: Optional[List[str]],
    combo_lands: int,
) -> None:
    print("\n\n## 3. OPENING HAND SCENARIOS")
    print("-" * 52)

    deck_size = len(deck)
    n_lands = sum(1 for c in deck if c["is_land"])

    # Standard keepable hand (2–5 lands, ≥1 early play CMC≤2)
    keepable = 0
    combo_hit = 0
    combo_names_lower = {c.lower() for c in (combo_cards or [])}

    for _ in range(n_sims):
        random.shuffle(deck)
        hand = deck[:7]

        land_count = sum(1 for c in hand if c["is_land"])
        has_early = any(
            not c["is_land"] and c["cmc"] is not None and c["cmc"] <= 2
            for c in hand
        )

        if 2 <= land_count <= 5 and has_early:
            keepable += 1

        if combo_names_lower:
            hand_names = {c["name"].lower() for c in hand}
            if combo_names_lower.issubset(hand_names) and land_count >= combo_lands:
                combo_hit += 1

    print(f"  Keepable opener (2–5 lands + CMC≤2 play):  {keepable/n_sims*100:.1f}%")

    if combo_cards:
        combo_label = " + ".join(combo_cards)
        print(f"  Combo opener ({combo_label} + {combo_lands}+ lands): {combo_hit/n_sims*100:.1f}%")


# ─── Section 4: Mana curve viability ─────────────────────────────────────────

def analyse_curve(mainboard: List[Tuple[int, str]], card_data: Dict[str, Dict]) -> None:
    print("\n\n## 4. MANA CURVE VIABILITY")
    print("-" * 52)

    n_lands = 0
    cmc_buckets: Dict[int, int] = defaultdict(int)
    unscored_count = 0

    for qty, name in mainboard:
        data = card_data.get(name.lower())
        if data is None:
            unscored_count += qty
            continue
        type_line = (data.get("type_line") or "").lower()
        is_land = "land" in type_line and "spell" not in type_line
        if is_land:
            n_lands += qty
            continue
        raw_cmc = data.get("cmc")
        if raw_cmc is not None and str(raw_cmc).strip() != "":
            bucket = min(int(float(raw_cmc)), 6)
            cmc_buckets[bucket] += qty
        else:
            unscored_count += qty

    total_spells = sum(cmc_buckets.values())
    deck_size = sum(qty for qty, _ in mainboard)

    if total_spells == 0:
        print("  (insufficient card data for curve analysis)")
        return

    total_cmc = sum(cmc * count for cmc, count in cmc_buckets.items())
    avg_cmc = total_cmc / total_spells
    land_ratio = n_lands / deck_size if deck_size else 0

    print(f"  Average CMC (spells only):  {avg_cmc:.2f}")
    print(f"  Land ratio:                 {land_ratio*100:.1f}% ({n_lands}/{deck_size})")
    print()
    print(f"  {'CMC':<6} {'Count':>6} {'% of Spells':>12}")
    print(f"  {'-'*6} {'-'*6} {'-'*12}")
    for cmc in sorted(cmc_buckets):
        count = cmc_buckets[cmc]
        label = f"{cmc}+" if cmc == 6 else str(cmc)
        print(f"  {label:<6} {count:>6} {count/total_spells*100:>11.0f}%")

    if unscored_count:
        print(f"\n  ⚠ {unscored_count} card(s) not in DB — excluded from curve totals")

    # Frank Karsten recommended land count for this avg CMC
    # Approximate: recommended_lands ≈ 14 + (avg_cmc / 0.37)  (60-card heuristic)
    recommended = round(14 + (avg_cmc / 0.37))
    diff = n_lands - recommended
    verdict = (
        "On target ✅" if abs(diff) <= 1
        else f"{'Under' if diff < 0 else 'Over'} by {abs(diff)} land(s) ⚠"
    )
    print(f"\n  Karsten recommended lands:  ~{recommended}")
    print(f"  Running {n_lands} lands → {verdict}")


# ─── Main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        prog="hypergeometric_analysis.py",
        description="Hypergeometric + Monte Carlo analysis for any MTG decklist.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "examples:\n"
            "  %(prog)s Decks/my_deck/decklist.txt\n"
            "  %(prog)s Decks/my_deck/decklist.txt --sims 200000 --seed 42\n"
            "  %(prog)s Decks/my_deck/decklist.txt --turns 7 --on-draw\n"
            "  %(prog)s Decks/my_deck/decklist.txt --combo 'Card A' 'Card B' --combo-lands 3\n"
        ),
    )
    parser.add_argument("decklist", help="path to decklist.txt (MTGA format)")
    parser.add_argument(
        "--sims", type=int, default=100_000, metavar="INT",
        help="Monte Carlo simulation count (default: 100000)",
    )
    parser.add_argument(
        "--seed", type=int, default=None, metavar="INT",
        help="random seed for reproducible output",
    )
    parser.add_argument(
        "--turns", type=int, default=6, metavar="INT",
        help="turns to project land-drop probabilities through (default: 6)",
    )
    parser.add_argument(
        "--on-draw", action="store_true",
        help="model being on the draw (default: on the play)",
    )
    parser.add_argument(
        "--combo", nargs="+", metavar="NAME",
        help="card names that must all appear together in the opening hand",
    )
    parser.add_argument(
        "--combo-lands", type=int, default=2, metavar="INT",
        help="minimum lands required alongside --combo cards (default: 2)",
    )
    args = parser.parse_args()

    deck_path = Path(args.decklist)
    if not deck_path.is_absolute():
        deck_path = RepoPaths().root / deck_path
    if not deck_path.exists():
        print(f"ERROR: decklist not found: {deck_path}", file=sys.stderr)
        sys.exit(1)

    if args.seed is not None:
        random.seed(args.seed)

    mainboard, _ = parse_decklist(deck_path)
    deck_size = sum(qty for qty, _ in mainboard)

    if deck_size < 20:
        print(f"ERROR: deck too small ({deck_size} cards) — need at least 20", file=sys.stderr)
        sys.exit(2)

    card_names = list({name for _, name in mainboard})
    print("Looking up card data...", file=sys.stderr)
    paths = RepoPaths()
    card_data = load_card_data(card_names, paths)

    unscored = [name for name in card_names if name.lower() not in card_data]
    if unscored:
        print(
            f"  ⚠ {len(unscored)} card(s) not in DB — color/CMC data unavailable:",
            file=sys.stderr,
        )
        for name in unscored:
            print(f"    - {name}", file=sys.stderr)
        print(
            "  Run 'python scripts/fetch_and_categorize_cards.py' to update the DB.",
            file=sys.stderr,
        )

    deck, _ = build_deck_model(mainboard, card_data)
    on_play = not args.on_draw

    print("=" * 70)
    print(f"HYPERGEOMETRIC ANALYSIS: {deck_path.parent.name}")
    print(f"Deck: {deck_size} cards  |  Sims: {args.sims:,}  |  {'On Play' if on_play else 'On Draw'}")
    print("=" * 70)

    analyse_lands(deck, args.sims, args.turns, on_play)
    analyse_key_cards(mainboard, deck_size, on_play)
    analyse_opening_hands(deck, args.sims, args.combo, args.combo_lands)
    analyse_curve(mainboard, card_data)

    print("\n" + "=" * 70)
    print("ANALYSIS COMPLETE")
    print("=" * 70)


if __name__ == "__main__":
    main()
