#!/usr/bin/env python3
"""
Mana Base Advisor — Frank Karsten-inspired color source calculator.

Given pip requirements and land count, computes:
  1. Minimum sources needed per color (via Monte Carlo)
  2. Probability of accessing N colored mana by turn T (on play and draw)
  3. Recommended land allocation

Usage:
  python scripts/mana_base_advisor.py --pips W:12,B:8 --lands 24
  python scripts/mana_base_advisor.py --pips W:12,B:8,R:6 --lands 24 --sims 500000

Flags:
  --pips      Color pip counts: W:N,B:N,R:N,G:N,U:N
              N = total colored pips of that color across all spells in the deck
  --lands     Total land count in the deck (default: 24)
  --deck-size Total deck size (default: 60)
  --sims      Monte Carlo simulation count (default: 300000)
  --on-draw   Also compute on-draw probabilities (default: on-play only)
"""

import argparse
import random
from collections import defaultdict
from math import comb
from typing import Dict, List, Tuple

DECK_SIZE_DEFAULT = 60
LANDS_DEFAULT = 24
SIMS_DEFAULT = 300_000

# Karsten targets: probability of having N sources of color C by turn T on play
# These are the accepted competitive reliability thresholds:
# 90% → tournament playable, 95% → highly reliable
RELIABILITY_TARGET = 0.90

def hypergeometric_cdf_at_least(N: int, K: int, n: int, k_min: int) -> float:
    """P(X >= k_min) draws from hypergeometric(N, K, n)."""
    if K == 0:
        return 0.0
    total = 0.0
    for k in range(k_min, min(K, n) + 1):
        if k > K or (n - k) > (N - K):
            continue
        total += comb(K, k) * comb(N - K, n - k) / comb(N, n)
    return total

def min_sources_for_reliability(
    deck_size: int,
    land_count: int,
    turn: int,
    pips_needed: int,
    target: float = RELIABILITY_TARGET,
    on_draw: bool = False,
) -> int:
    """
    Binary search for minimum sources of a color needed to cast a spell
    requiring `pips_needed` of that color by `turn` with >= `target` reliability.
    """
    cards_seen = 7 + (turn - 1) + (1 if on_draw else 0)
    cards_seen = min(cards_seen, deck_size)
    for sources in range(0, deck_size + 1):
        p = hypergeometric_cdf_at_least(deck_size, sources, cards_seen, pips_needed)
        if p >= target:
            return sources
    return deck_size

def simulate_mana_access(
    pip_requirements: Dict[str, int],  # {"W": 12, "B": 8}
    land_count: int,
    deck_size: int,
    n_sims: int,
    on_draw: bool = False,
) -> Dict[Tuple[str, int, int], float]:
    """
    Monte Carlo simulation of color access.
    Returns dict: {(color, pips_needed, turn): probability}
    """
    # We simulate with a simplified deck model:
    # Land_count sources spread proportionally to pip requirements
    total_pips = sum(pip_requirements.values()) or 1

    # Build land distribution proportional to pip counts
    # Assume all lands are duals/perfect fixing as best case,
    # and we track whether we have N sources of each color
    # For a more realistic model, distribute sources proportionally

    colors = list(pip_requirements.keys())
    color_sources: Dict[str, int] = {}
    allocated = 0
    for i, color in enumerate(colors):
        if i == len(colors) - 1:
            color_sources[color] = land_count - allocated
        else:
            share = round(land_count * pip_requirements[color] / total_pips)
            color_sources[color] = max(1, share)
            allocated += color_sources[color]

    # Build deck: each land produces colors based on distribution
    # Simple model: land_i produces color proportionally
    # Better: each land is a "shared" land that produces all needed colors (dual model)
    # We'll simulate the realistic case: each land produces 1 color (weighted)

    # Build the deck as a list of color sets per land
    lands = []
    for color, count in color_sources.items():
        lands.extend([{color}] * count)
    # Pad remaining lands as colorless (basic mountains/swamps of least-needed color)
    while len(lands) < land_count:
        lands.append(set())
    non_lands = [set()] * (deck_size - land_count)
    deck = lands + non_lands

    results = defaultdict(int)
    max_pips = max(pip_requirements.values()) if pip_requirements else 1
    turns_to_check = list(range(1, 8))

    for _ in range(n_sims):
        random.shuffle(deck)

        cumulative_colors = defaultdict(int)

        for turn in turns_to_check:
            cards_seen = 7 + (turn - 1) + (1 if on_draw else 0)
            cards_this_turn = deck[cards_seen - 1 : cards_seen]
            for card in cards_this_turn:
                for color in card:
                    cumulative_colors[color] += 1

            # On turn 1, recalculate from scratch
            if turn == 1:
                first_n = deck[:7 + (1 if on_draw else 0)]
                cumulative_colors = defaultdict(int)
                for card in first_n:
                    for color in card:
                        cumulative_colors[color] += 1

            for color, pips_needed in pip_requirements.items():
                for n_pips in range(1, pips_needed + 1):
                    if cumulative_colors[color] >= n_pips:
                        results[(color, n_pips, turn)] += 1

    return {k: v / n_sims for k, v in results.items()}


def main():
    p = argparse.ArgumentParser(
        description="Mana base advisor: Karsten-inspired color source requirements.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument("--pips", required=True,
                   help="Pip requirements: W:12,B:8,R:6 (color:total_pips)")
    p.add_argument("--lands", type=int, default=LANDS_DEFAULT, help="Land count (default 24)")
    p.add_argument("--deck-size", type=int, default=DECK_SIZE_DEFAULT, help="Deck size (default 60)")
    p.add_argument("--sims", type=int, default=SIMS_DEFAULT, help="Simulation count (default 300000)")
    p.add_argument("--on-draw", action="store_true", help="Also show on-draw probabilities")
    args = p.parse_args()

    # Parse pip requirements
    try:
        pip_requirements = {}
        for part in args.pips.split(","):
            color, count = part.strip().split(":")
            pip_requirements[color.upper()] = int(count)
    except Exception:
        p.error("--pips format must be COLOR:N,COLOR:N (e.g. W:12,B:8,R:6)")

    total_pips = sum(pip_requirements.values())
    print(f"\n{'='*65}")
    print(f"  MANA BASE ADVISOR")
    print(f"{'='*65}")
    print(f"  Deck: {args.deck_size} cards, {args.lands} lands")
    print(f"  Colors: {pip_requirements}")
    print(f"  Total pips: {total_pips} across all spells\n")

    # Section 1: Minimum sources per color
    print(f"── MINIMUM SOURCES FOR {RELIABILITY_TARGET*100:.0f}% RELIABILITY ──────────────────────")
    print(f"  {'Color':<8} {'1-pip T1':>9} {'1-pip T2':>9} {'2-pip T2':>9} {'1-pip T3':>9}")
    print(f"  {'-'*8} {'-'*9} {'-'*9} {'-'*9} {'-'*9}")

    recommendations = {}
    for color, pips in pip_requirements.items():
        min_1pip_t1 = min_sources_for_reliability(args.deck_size, args.lands, 1, 1)
        min_1pip_t2 = min_sources_for_reliability(args.deck_size, args.lands, 2, 1)
        min_2pip_t2 = min_sources_for_reliability(args.deck_size, args.lands, 2, 2)
        min_1pip_t3 = min_sources_for_reliability(args.deck_size, args.lands, 3, 1)
        recommendations[color] = min_1pip_t2  # Most common threshold
        print(f"  {color:<8} {min_1pip_t1:>9} {min_1pip_t2:>9} {min_2pip_t2:>9} {min_1pip_t3:>9}")

    print()

    # Section 2: Recommended source allocation
    print(f"── RECOMMENDED LAND ALLOCATION ──────────────────────────────────")
    total_recommended = sum(recommendations.values())
    scale = args.lands / max(total_recommended, 1)
    print(f"  (Proportional to pip counts, scaled to {args.lands} lands)\n")
    total_allocated = 0
    for i, (color, pips) in enumerate(pip_requirements.items()):
        if i == len(pip_requirements) - 1:
            allocated = args.lands - total_allocated
        else:
            allocated = max(1, round(args.lands * pips / total_pips))
            total_allocated += allocated
        recommended_min = recommendations[color]
        status = "✅" if allocated >= recommended_min else f"⚠️  (need ≥{recommended_min})"
        print(f"  {color}: {allocated} sources  {status}")

    print()

    # Section 3: Monte Carlo access probabilities
    print(f"── MONTE CARLO COLOR ACCESS ({args.sims:,} simulations) {'[on play]':>12} ──")
    sim_results = simulate_mana_access(
        pip_requirements, args.lands, args.deck_size, args.sims, on_draw=False
    )

    for color, pips in pip_requirements.items():
        print(f"\n  {color} (total pips in deck: {pips})")
        print(f"  {'Requirement':<20} {'T1':>7} {'T2':>7} {'T3':>7} {'T4':>7} {'T5':>7}")
        print(f"  {'-'*20} {'-'*7} {'-'*7} {'-'*7} {'-'*7} {'-'*7}")
        for n_pips in range(1, min(pips + 1, 4)):
            row = [f"  {n_pips}× {color} available{'':<7}"]
            for turn in range(1, 6):
                prob = sim_results.get((color, n_pips, turn), 0.0)
                flag = "" if prob >= 0.90 else ("⚠" if prob >= 0.75 else "✗")
                row.append(f"{prob*100:>6.1f}%{flag}")
            print("".join(row))

    if args.on_draw:
        print(f"\n── MONTE CARLO [on draw] ────────────────────────────────────────")
        sim_draw = simulate_mana_access(
            pip_requirements, args.lands, args.deck_size, args.sims, on_draw=True
        )
        for color, pips in pip_requirements.items():
            print(f"\n  {color} (on draw)")
            for n_pips in range(1, min(pips + 1, 4)):
                row = [f"  {n_pips}× {color}:"]
                for turn in range(1, 6):
                    prob = sim_draw.get((color, n_pips, turn), 0.0)
                    row.append(f"{prob*100:>6.1f}%")
                print("".join(row))

    print(f"\n{'='*65}")
    print(f"  Tip: Run `search_cards.py --type land --colors <your_colors>` to find dual lands.")
    print(f"  Target ≥90% for turn-2 colored mana. Adjust land count if below threshold.")
    print(f"{'='*65}\n")


if __name__ == "__main__":
    main()
