#!/usr/bin/env python3
"""
autobuild.py — Universal Competitive Deck Builder

Builds a 60+15 competitive deck from scratch using the local card database.
Works backwards from the desired win condition: find payoffs first, then
enablers, then interaction, then lands. Scores everything with the existing
synergy engine and optimizes with a Karpathy-style greedy hill-climb.

This script orchestrates the existing tools:
  - search_cards.py  (card queries)
  - synergy_engine    (pairwise scoring)
  - mythic_framework  (panel evaluation)
  - mana_base_advisor (land math)
  - validate_decklist (final check)

Usage:
    python scripts/cli/autobuild.py --name "Orzhov Lifegain" --colors WB --strategy lifegain
    python scripts/cli/autobuild.py --name "Izzet Prowess" --colors UR --strategy prowess
    python scripts/cli/autobuild.py --name "Mono Green Stompy" --colors G --strategy aggro
    python scripts/cli/autobuild.py --name "Dimir Control" --colors UB --strategy control --tribe Faerie
    python scripts/cli/autobuild.py --colors WB --strategy lifegain --optimize 120

Algorithm (Karpathy-style iterative improvement):
    1. QUERY: Run targeted DB queries by strategy role (payoffs → enablers → interaction → lands)
    2. SCORE: Run score_pairwise() on full candidate pool
    3. SELECT: Greedy-pick top cards by composite_score, respecting hard constraints
    4. EVALUATE: Run mythic panel, check EV
    5. OPTIMIZE: While time budget remains, swap weakest deck card with strongest pool card
    6. VALIDATE: Run validate_decklist.py, output final deck
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from math import comb
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

# ── Path setup ────────────────────────────────────────────────────────────────
_here = Path(__file__).resolve().parent
_scripts = _here.parent
_root = _scripts.parent
sys.path.insert(0, str(_scripts / "utils"))
sys.path.insert(0, str(_scripts / "analysis"))
sys.path.insert(0, str(_scripts / "cli"))
sys.path.insert(0, str(_scripts))

from mtg_utils import RepoPaths
from synergy_engine import (
    load_cards_from_db,
    score_pairwise,
    attach_card_data,
)
from synergy_types import CardScore, CardRole
from mythic_framework import run_panel, compute_ev, compute_ev_components

# ═══════════════════════════════════════════════════════════════════════════════
# Strategy definitions — maps a strategy keyword to the queries needed
# ═══════════════════════════════════════════════════════════════════════════════

STRATEGY_QUERIES: Dict[str, List[Dict[str, str]]] = {
    # ── Lifegain / Lifedrain ──────────────────────────────────────────────
    "lifegain": [
        # Payoffs first (most important)
        {"label": "Lifegain payoffs",      "args": '--type creature --oracle "whenever you gain life" --ranked --limit 40'},
        {"label": "Lifedrain creatures",   "args": '--type creature --oracle "each opponent loses" --tags lifegain --ranked --limit 30'},
        {"label": "Lifegain enablers",     "args": '--type creature --tags lifegain --cmc-max 3 --ranked --limit 40'},
        {"label": "Lifegain enchantments", "args": '--type enchantment --tags lifegain --ranked --limit 20'},
        # Interaction
        {"label": "Cheap removal",         "args": '--type instant,sorcery --tags removal --cmc-max 3 --ranked --limit 20'},
        # Food
        {"label": "Food cards",            "args": '--type creature,enchantment,instant,sorcery --oracle "food" --ranked --limit 20'},
    ],
    # ── Aggro ─────────────────────────────────────────────────────────────
    "aggro": [
        {"label": "Cheap threats",         "args": '--type creature --cmc-max 2 --ranked --limit 40'},
        {"label": "Hasty creatures",       "args": '--type creature --tags haste --cmc-max 3 --ranked --limit 20'},
        {"label": "Pump spells",           "args": '--type instant --tags pump --cmc-max 2 --ranked --limit 20'},
        {"label": "Burn/removal",          "args": '--type instant,sorcery --tags removal --cmc-max 2 --ranked --limit 20'},
    ],
    # ── Control ───────────────────────────────────────────────────────────
    "control": [
        {"label": "Counterspells",         "args": '--type instant --tags counter --ranked --limit 20'},
        {"label": "Removal instants",      "args": '--type instant --tags removal --ranked --limit 30'},
        {"label": "Board wipes",           "args": '--type sorcery --tags wipe --ranked --limit 15'},
        {"label": "Card draw",             "args": '--type instant,sorcery --tags draw --ranked --limit 20'},
        {"label": "Win conditions",        "args": '--type creature,planeswalker --cmc-min 4 --rarity rare,mythic --ranked --limit 20'},
    ],
    # ── Prowess / Spells-matter ───────────────────────────────────────────
    "prowess": [
        {"label": "Prowess creatures",     "args": '--type creature --keywords Prowess --ranked --limit 20'},
        {"label": "Magecraft creatures",   "args": '--type creature --oracle "magecraft" --ranked --limit 15'},
        {"label": "Cheap instants",        "args": '--type instant --cmc-max 2 --ranked --limit 30'},
        {"label": "Cheap sorceries",       "args": '--type sorcery --cmc-max 2 --ranked --limit 20'},
        {"label": "Pump spells",           "args": '--type instant --tags pump --cmc-max 2 --ranked --limit 15'},
    ],
    # ── Mill ──────────────────────────────────────────────────────────────
    "mill": [
        {"label": "Mill payoffs",          "args": '--oracle "opponent mills" --ranked --limit 20'},
        {"label": "Mill enablers",         "args": '--tags mill --ranked --limit 30'},
        {"label": "Control shell",         "args": '--type instant --tags counter,removal --ranked --limit 20'},
    ],
    # ── Tribal ────────────────────────────────────────────────────────────
    "tribal": [
        # Tribal queries need --tribe flag to be useful; handled dynamically
        {"label": "Cheap removal",         "args": '--type instant,sorcery --tags removal --cmc-max 3 --ranked --limit 20'},
        {"label": "Card draw",             "args": '--type instant,sorcery --tags draw --ranked --limit 15'},
    ],
}

# Always-included queries
UNIVERSAL_QUERIES = [
    {"label": "Lands", "args": '--type land --limit 200'},
]


# ═══════════════════════════════════════════════════════════════════════════════
# Hard construction constraints
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class DeckConstraints:
    deck_size: int = 60
    sideboard_size: int = 15
    min_lands: int = 22
    max_lands: int = 26
    min_creatures: int = 16
    max_creatures: int = 32
    min_interaction: int = 4    # removal + counters
    max_cmc_avg: float = 3.0
    min_early_plays: int = 10   # cards CMC <= 2 (non-land)

    @classmethod
    def for_strategy(cls, strategy: str) -> "DeckConstraints":
        overrides = {
            "aggro":   {"min_creatures": 24, "max_cmc_avg": 2.2, "min_early_plays": 16, "min_lands": 20, "max_lands": 23},
            "control": {"min_creatures": 8, "max_creatures": 16, "min_interaction": 10, "max_cmc_avg": 3.5, "min_lands": 24},
            "prowess": {"min_creatures": 16, "max_cmc_avg": 2.0, "min_early_plays": 16, "min_lands": 20, "max_lands": 23},
            "lifegain":{"min_creatures": 20, "max_cmc_avg": 2.8, "min_early_plays": 12},
            "mill":    {"min_creatures": 8, "min_interaction": 8, "max_cmc_avg": 3.0, "min_lands": 24},
        }
        c = cls()
        for k, v in overrides.get(strategy, {}).items():
            setattr(c, k, v)
        return c


# ═══════════════════════════════════════════════════════════════════════════════
# Core functions
# ═══════════════════════════════════════════════════════════════════════════════

def run_search(args_str: str, colors: str) -> List[str]:
    """Run search_cards.py and return list of card names found."""
    import shlex
    cmd = [sys.executable, str(_scripts / "cli" / "search_cards.py")]
    # Use shlex to properly handle quoted arguments
    try:
        parsed_args = shlex.split(args_str)
    except ValueError:
        parsed_args = args_str.split()
    cmd += parsed_args
    if "--colors" not in args_str and colors:
        cmd += ["--colors", colors]
    cmd += ["--format", "names"]

    result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                            cwd=str(_root), timeout=30)
    names = []
    for line in result.stdout.strip().splitlines():
        # Format: "Card Name  [source_file]"
        if "[" in line:
            name = line.split("[")[0].strip()
            if name and not name.startswith("#") and not name.startswith("INFO"):
                names.append(name)
    return names


def query_candidate_pool(strategy: str, colors: str, tribe: Optional[str] = None) -> List[str]:
    """Run all strategy queries and return deduplicated candidate names."""
    queries = STRATEGY_QUERIES.get(strategy, []) + UNIVERSAL_QUERIES

    # Add tribal creature query if tribe specified
    if tribe:
        queries.insert(0, {
            "label": f"{tribe} creatures",
            "args": f'--type creature --subtype "{tribe}" --ranked --limit 40'
        })

    all_names: List[str] = []
    seen: Set[str] = set()

    for q in queries:
        label = q["label"]
        args = q["args"]
        print(f"  [{label}] ...", end=" ", flush=True)
        names = run_search(args, colors)
        new = [n for n in names if n.lower() not in seen]
        for n in new:
            seen.add(n.lower())
            all_names.append(n)
        print(f"{len(names)} found ({len(new)} new)")

    print(f"\n  Total unique candidates: {len(all_names)}")
    return all_names


def score_pool(names: List[str], paths: RepoPaths) -> Dict[str, CardScore]:
    """Load cards from DB and score pairwise synergies."""
    card_data = load_cards_from_db(names, paths)
    scores = score_pairwise(card_data)
    return scores


def _qty_for_role(sc: CardScore) -> int:
    """Determine copy count based on role and CMC — mimic how humans build decks."""
    role = sc.role
    cmc = sc.profile.cmc
    # Core engines at low CMC: 4-of always
    if role in (CardRole.ENGINE, CardRole.ENABLER) and cmc <= 3:
        return 4
    # Cheap payoffs: 4-of
    if role == CardRole.PAYOFF and cmc <= 3:
        return 4
    # Expensive engines/payoffs: 2-3 copies
    if role in (CardRole.ENGINE, CardRole.PAYOFF, CardRole.ENABLER) and cmc >= 4:
        return 2
    # Interaction: 2-3 copies (variety is good)
    if role == CardRole.INTERACTION:
        return 2 if cmc <= 2 else 1
    # Support: 2 copies
    return 2


def greedy_select(
    scores: Dict[str, CardScore],
    constraints: DeckConstraints,
    colors: str,
    paths: RepoPaths,
) -> Tuple[List[Dict], List[Dict]]:
    """
    Greedy-select the best cards respecting construction constraints.
    Uses role-aware copy counts and enforces curve/interaction minimums.
    Returns (maindeck_entries, remaining_pool).
    """
    non_lands = {k: v for k, v in scores.items() if not v.profile.is_land}

    # Sort by composite_score descending
    ranked = sorted(non_lands.items(), key=lambda kv: kv[1].composite_score, reverse=True)

    deck: List[Dict] = []
    deck_names: Set[str] = set()
    creature_count = 0
    interaction_count = 0
    early_plays = 0  # CMC <= 2
    total_cmc = 0.0
    nonland_count = 0

    spell_target = constraints.deck_size - constraints.min_lands
    # Reserve slots for interaction — don't let pass 1 take everything
    pass1_target = spell_target - constraints.min_interaction

    # ── Pass 1: Pick engines/enablers/payoffs (the deck's core) ───────────
    for name, sc in ranked:
        if nonland_count >= pass1_target:
            break
        if sc.role not in (CardRole.ENGINE, CardRole.ENABLER, CardRole.PAYOFF):
            continue

        is_creature = "creature" in sc.profile.type_line.lower()
        if is_creature and creature_count >= constraints.max_creatures:
            continue

        qty = _qty_for_role(sc)
        # Curve check: would adding this card push avg CMC past limit?
        projected_cmc = (total_cmc + sc.profile.cmc * qty) / (nonland_count + qty)
        if nonland_count > 8 and projected_cmc > constraints.max_cmc_avg:
            # Try fewer copies
            qty = max(1, qty - 1)
            projected_cmc = (total_cmc + sc.profile.cmc * qty) / (nonland_count + qty)
            if projected_cmc > constraints.max_cmc_avg + 0.3:
                continue  # Skip entirely if still too heavy

        qty = min(qty, spell_target - nonland_count)
        if qty <= 0:
            continue

        deck.append({"name": sc.profile.name, "qty": qty, "score": sc})
        deck_names.add(name)
        nonland_count += qty
        if is_creature:
            creature_count += qty
        if sc.profile.cmc <= 2:
            early_plays += qty
        total_cmc += sc.profile.cmc * qty

    # ── Pass 2: Add interaction (removal, counters) ───────────────────────
    # Interaction is critical — even if synergy score is low, decks need answers
    interaction_target = max(constraints.min_interaction, 5)
    interaction_cards = [
        (n, s) for n, s in ranked
        if n not in deck_names and (
            s.role == CardRole.INTERACTION
            or "removal" in (s.profile.broad_tags if hasattr(s.profile, "broad_tags") else frozenset())
        )
    ]
    for name, sc in interaction_cards:
        if nonland_count >= spell_target or interaction_count >= interaction_target:
            break
        qty = min(2, spell_target - nonland_count)  # 2 copies of each removal spell (variety)
        if qty <= 0:
            continue
        deck.append({"name": sc.profile.name, "qty": qty, "score": sc})
        deck_names.add(name)
        nonland_count += qty
        interaction_count += qty
        if sc.profile.cmc <= 2:
            early_plays += qty
        total_cmc += sc.profile.cmc * qty

    # ── Pass 3: Fill remaining slots (support, best remaining) ────────────
    for name, sc in ranked:
        if nonland_count >= spell_target:
            break
        if name in deck_names:
            continue
        is_creature = "creature" in sc.profile.type_line.lower()
        if is_creature and creature_count >= constraints.max_creatures:
            continue

        qty = min(2, spell_target - nonland_count)
        if qty <= 0:
            continue

        deck.append({"name": sc.profile.name, "qty": qty, "score": sc})
        deck_names.add(name)
        nonland_count += qty
        if is_creature:
            creature_count += qty
        if sc.profile.cmc <= 2:
            early_plays += qty
        total_cmc += sc.profile.cmc * qty

    # ── Pass 4: Early-play check — swap heavy cards for cheap ones if needed
    if early_plays < constraints.min_early_plays:
        cheap_pool = [
            (n, s) for n, s in ranked
            if n not in deck_names and s.profile.cmc <= 2
        ]
        # Find expensive cards to cut
        deck_by_cmc = sorted(deck, key=lambda e: -e["score"].profile.cmc)
        for expensive in deck_by_cmc:
            if early_plays >= constraints.min_early_plays:
                break
            if expensive["score"].profile.cmc <= 2:
                break
            if not cheap_pool:
                break
            # Swap: cut 1 copy of expensive, add 1 copy of cheap
            cheap_name, cheap_sc = cheap_pool.pop(0)
            expensive["qty"] -= 1
            if expensive["qty"] <= 0:
                deck.remove(expensive)
                deck_names.discard(expensive["name"].lower())
            nonland_count -= 1
            total_cmc -= expensive["score"].profile.cmc
            # Add cheap card
            deck.append({"name": cheap_sc.profile.name, "qty": 1, "score": cheap_sc})
            deck_names.add(cheap_name)
            nonland_count += 1
            early_plays += 1
            total_cmc += cheap_sc.profile.cmc

    avg_cmc = total_cmc / nonland_count if nonland_count > 0 else 0
    print(f"    Creatures: {creature_count}  Interaction: {interaction_count}  "
          f"Early plays: {early_plays}  Avg CMC: {avg_cmc:.2f}")

    # Build remaining pool
    remaining = [
        {"name": sc.profile.name, "qty": 1, "score": sc}
        for name, sc in ranked if name not in deck_names
    ]

    return deck, remaining


def build_mana_base(deck: List[Dict], colors: str, constraints: DeckConstraints,
                    paths: RepoPaths) -> List[Dict]:
    """
    Build a competitive mana base: 4x best duals, then basics proportional to pips.
    No 1-of random lands. Consistency > variety.
    """
    # Count pips needed
    pip_counts = defaultdict(int)
    for entry in deck:
        mana_cost = entry["score"].profile.mana_cost
        for ch in mana_cost:
            if ch in "WUBRG":
                pip_counts[ch] += entry["qty"]

    nonland_cards = sum(e["qty"] for e in deck)
    land_count = constraints.deck_size - nonland_cards
    land_count = max(constraints.min_lands, min(constraints.max_lands, land_count))

    color_list = list(colors.upper())
    basic_names = {"W": "Plains", "U": "Island", "B": "Swamp",
                   "R": "Mountain", "G": "Forest"}
    lands: List[Dict] = []
    slots_used = 0

    if len(color_list) == 1:
        # Monocolor: all basics
        lands.append({"name": basic_names[color_list[0]], "qty": land_count})
        return lands

    # ── Multi-color: pick best duals from DB, at 4 copies each ────────────
    land_names = run_search("--type land --limit 200", colors)
    land_data = load_cards_from_db(land_names, paths)

    # Score lands: prefer untapped duals > tapped duals that gain life > tapped duals
    PREMIUM_DUALS = {
        "WB": ["Godless Shrine", "Concealed Courtyard", "Caves of Koilos", "Brightclimb Pathway"],
        "WU": ["Hallowed Fountain", "Seachrome Coast", "Adarkar Wastes", "Hengegate Pathway"],
        "WR": ["Sacred Foundry", "Inspiring Vantage", "Battlefield Forge", "Needleverge Pathway"],
        "WG": ["Temple Garden", "Blooming Marsh", "Branchloft Pathway", "Razorverge Thicket"],
        "UB": ["Watery Grave", "Darkslick Shores", "Underground River", "Clearwater Pathway"],
        "UR": ["Steam Vents", "Spirebluff Canal", "Shivan Reef", "Riverglide Pathway"],
        "UG": ["Breeding Pool", "Botanical Sanctum", "Yavimaya Coast", "Barkchannel Pathway"],
        "BR": ["Blood Crypt", "Blackcleave Cliffs", "Sulfurous Springs", "Blightstep Pathway"],
        "BG": ["Overgrown Tomb", "Blooming Marsh", "Llanowar Wastes", "Darkbore Pathway"],
        "RG": ["Stomping Ground", "Copperline Gorge", "Karplusan Forest", "Cragcrown Pathway"],
    }

    # Build the color pair key
    sorted_colors = "".join(sorted(color_list))
    preferred_duals = PREMIUM_DUALS.get(sorted_colors, [])

    # Also find duals that exist in the actual DB
    db_land_names_lower = {n.lower(): n for n in land_data.keys()}
    dual_slots = min(12, land_count - len(color_list) * 2)  # Leave room for basics

    selected_duals: List[Tuple[str, int]] = []

    # First: pick premium duals that exist in DB, 4 copies each
    for dual_name in preferred_duals:
        if slots_used >= dual_slots:
            break
        if dual_name.lower() in db_land_names_lower:
            qty = min(4, dual_slots - slots_used)
            selected_duals.append((dual_name, qty))
            slots_used += qty

    # Second: if we still need duals, pick from DB lands with matching color identity
    if slots_used < dual_slots:
        # Find WB-identity lands that aren't basic and we haven't picked yet
        picked_lower = {d[0].lower() for d in selected_duals}
        for name, card in land_data.items():
            if slots_used >= dual_slots:
                break
            if name.lower() in picked_lower:
                continue
            ci = card.get("color_identity", "")
            type_line = card.get("type_line", "")
            if "Basic" in type_line:
                continue
            # Must produce at least one of our colors
            useful = sum(1 for c in color_list if c in ci)
            if useful >= 1:
                oracle = card.get("oracle_text", "").lower()
                # Prefer lands that gain life (for lifegain decks) or enter untapped
                qty = 4 if "gain" in oracle or "enters tapped" not in oracle else 2
                qty = min(qty, dual_slots - slots_used)
                selected_duals.append((card["name"], qty))
                picked_lower.add(name.lower())
                slots_used += qty

    for name, qty in selected_duals:
        lands.append({"name": name, "qty": qty})

    # ── Fill remaining slots with basics, proportional to pip counts ──────
    remaining_slots = land_count - slots_used
    if remaining_slots > 0:
        total_pips = max(1, sum(pip_counts.get(c, 1) for c in color_list))
        allocated = 0
        for i, color in enumerate(color_list):
            if i == len(color_list) - 1:
                basic_qty = remaining_slots - allocated
            else:
                share = pip_counts.get(color, 1) / total_pips
                basic_qty = max(2, round(remaining_slots * share))
                basic_qty = min(basic_qty, remaining_slots - allocated)
            if basic_qty > 0:
                lands.append({"name": basic_names[color], "qty": basic_qty})
                allocated += basic_qty

    return lands


def write_decklist(deck: List[Dict], lands: List[Dict], sideboard: List[Dict],
                   output_path: Path) -> int:
    """Write decklist in MTGA format. Returns total card count."""
    lines = ["Deck"]
    total = 0

    # Non-land cards sorted by qty desc, then name
    for entry in sorted(deck, key=lambda e: (-e["qty"], e["name"])):
        lines.append(f"{entry['qty']} {entry['name']}")
        total += entry["qty"]

    # Lands
    for entry in sorted(lands, key=lambda e: (-e["qty"], e["name"])):
        lines.append(f"{entry['qty']} {entry['name']}")
        total += entry["qty"]

    # Sideboard
    if sideboard:
        lines.append("")
        lines.append("Sideboard")
        for entry in sorted(sideboard, key=lambda e: (-e["qty"], e["name"])):
            lines.append(f"{entry['qty']} {entry['name']}")

    output_path.write_text("\n".join(lines), encoding="utf-8")
    return total


SIDEBOARD_ROLES = {
    # role_label → (preferred tags, preferred roles, preferred oracle patterns)
    "hand_disruption":  (["discard"], [CardRole.INTERACTION], []),
    "graveyard_hate":   ([], [], ["exile.*graveyard", "rest in peace"]),
    "artifact_hate":    ([], [CardRole.INTERACTION], ["destroy.*artifact", "destroy.*enchantment"]),
    "extra_removal":    (["removal", "wipe"], [CardRole.INTERACTION], []),
    "lifegain_tools":   (["lifegain"], [CardRole.ENABLER, CardRole.ENGINE], []),
    "card_advantage":   (["draw"], [CardRole.ENGINE, CardRole.SUPPORT], []),
}


def build_sideboard(remaining: List[Dict], deck_names: Set[str],
                    strategy: str, colors: str, max_cards: int = 15) -> List[Dict]:
    """
    Build a sideboard with matchup awareness.
    Allocates slots across different roles to cover common matchups.
    """
    sb: List[Dict] = []
    sb_names: Set[str] = set()
    total = 0

    # Allocate ~2-3 cards per sideboard role
    slots_per_role = max(2, max_cards // len(SIDEBOARD_ROLES))

    for role_label, (pref_tags, pref_roles, pref_oracle) in SIDEBOARD_ROLES.items():
        if total >= max_cards:
            break

        # Score candidates for this sideboard role
        role_candidates = []
        for entry in remaining:
            sc = entry["score"]
            name_lower = sc.profile.name.lower()
            if name_lower in deck_names or name_lower in sb_names:
                continue
            if sc.profile.is_land:
                continue

            # Check if card matches this sideboard role
            card_tags = sc.profile.broad_tags if hasattr(sc.profile, "broad_tags") else frozenset()
            tag_match = any(t in card_tags for t in pref_tags) if pref_tags else False
            role_match = sc.role in pref_roles if pref_roles else False
            oracle = sc.profile.oracle_text.lower() if hasattr(sc.profile, "oracle_text") else ""
            oracle_match = any(p in oracle for p in pref_oracle) if pref_oracle else False

            if tag_match or role_match or oracle_match:
                role_candidates.append((sc.composite_score, sc.profile.name))

        # Pick top candidates for this role
        role_candidates.sort(reverse=True)
        added_this_role = 0
        for score, name in role_candidates:
            if total >= max_cards or added_this_role >= slots_per_role:
                break
            qty = min(2, max_cards - total)
            sb.append({"name": name, "qty": qty})
            sb_names.add(name.lower())
            total += qty
            added_this_role += qty

    # If we still have slots, fill with best remaining synergy cards
    if total < max_cards:
        for entry in remaining:
            if total >= max_cards:
                break
            sc = entry["score"]
            name_lower = sc.profile.name.lower()
            if name_lower in deck_names or name_lower in sb_names or sc.profile.is_land:
                continue
            qty = min(2, max_cards - total)
            sb.append({"name": sc.profile.name, "qty": qty})
            sb_names.add(name_lower)
            total += qty

    return sb


def validate_deck(decklist_path: Path) -> bool:
    """Run validate_decklist.py and return True if passed."""
    cmd = [sys.executable, str(_scripts / "utils" / "validate_decklist.py"),
           str(decklist_path)]
    result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                            cwd=str(_root), timeout=30)
    return result.returncode == 0


def run_panel_eval(decklist_path: Path) -> Optional[Dict]:
    """Run mythic_framework.py and return JSON results."""
    cmd = [sys.executable, str(_scripts / "analysis" / "mythic_framework.py"),
           str(decklist_path), "--json"]
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                            env=env, cwd=str(_root), timeout=60)
    # Parse JSON from output (skip non-JSON lines)
    for line in result.stdout.splitlines():
        if line.strip().startswith("{"):
            try:
                return json.loads(result.stdout[result.stdout.index("{"):])
            except json.JSONDecodeError:
                pass
    return None


# ═══════════════════════════════════════════════════════════════════════════════
# Karpathy optimization loop
# ═══════════════════════════════════════════════════════════════════════════════

def optimize_deck(
    deck: List[Dict],
    lands: List[Dict],
    remaining: List[Dict],
    all_scores: Dict[str, CardScore],
    constraints: DeckConstraints,
    time_budget: float = 60.0,
) -> Tuple[List[Dict], List[Dict], float]:
    """
    Karpathy-style greedy hill-climbing, fully in-memory.

    Uses composite_score sums as the objective function (no subprocess spawning).
    Accepts swaps that increase total deck composite_score while respecting constraints.
    """
    if time_budget <= 0 or not remaining:
        deck_ev = sum(e["score"].composite_score * e["qty"] for e in deck if e.get("score"))
        return deck, lands, deck_ev

    print(f"\n  Optimizing (budget: {time_budget:.0f}s)...")
    start = time.time()
    best_deck = list(deck)
    best_ev = sum(e["score"].composite_score * e["qty"] for e in best_deck if e.get("score"))
    iterations = 0
    accepted = 0

    print(f"  Initial composite EV: {best_ev:.1f}")

    # Sort deck by score ascending (weakest first), pool by score descending
    deck_weakest = sorted(best_deck, key=lambda e: e["score"].composite_score if e.get("score") else 0)
    pool_strongest = sorted(remaining, key=lambda e: e["score"].composite_score if e.get("score") else 0, reverse=True)

    # Try every (weak_deck_card, strong_pool_card) pair within time budget
    for cut_entry in deck_weakest:
        if time.time() - start >= time_budget:
            break
        cut_sc = cut_entry.get("score")
        if not cut_sc:
            continue

        for add_entry in pool_strongest:
            if time.time() - start >= time_budget:
                break
            iterations += 1
            add_sc = add_entry.get("score")
            if not add_sc:
                continue

            # Quick check: would this swap improve total score?
            ev_delta = (add_sc.composite_score - cut_sc.composite_score) * cut_entry["qty"]
            if ev_delta <= 0:
                continue  # Pool card is weaker, skip

            # Curve check: don't make deck heavier
            is_heavier = add_sc.profile.cmc > cut_sc.profile.cmc
            deck_nonland_count = sum(e["qty"] for e in best_deck)
            current_total_cmc = sum(e["score"].profile.cmc * e["qty"] for e in best_deck if e.get("score"))
            new_total_cmc = current_total_cmc + (add_sc.profile.cmc - cut_sc.profile.cmc) * cut_entry["qty"]
            new_avg_cmc = new_total_cmc / deck_nonland_count if deck_nonland_count > 0 else 0
            if is_heavier and new_avg_cmc > constraints.max_cmc_avg:
                continue  # Would violate curve constraint

            # Accept the swap
            new_deck = [e for e in best_deck if e["name"] != cut_entry["name"]]
            new_deck.append({"name": add_sc.profile.name, "qty": cut_entry["qty"], "score": add_sc})
            new_ev = sum(e["score"].composite_score * e["qty"] for e in new_deck if e.get("score"))

            if new_ev > best_ev:
                best_ev = new_ev
                best_deck = new_deck
                accepted += 1
                print(f"    [{iterations}] -{cut_entry['name']} +{add_sc.profile.name} "
                      f"(+{ev_delta:.1f}) EV={best_ev:.1f}")
                # Re-sort after swap
                deck_weakest = sorted(best_deck, key=lambda e: e["score"].composite_score if e.get("score") else 0)
                break  # Move to next weakest card

    elapsed = time.time() - start
    print(f"  Optimization: {iterations} iters, {accepted} accepted, {elapsed:.1f}s, final EV={best_ev:.1f}")

    return best_deck, lands, best_ev


# ═══════════════════════════════════════════════════════════════════════════════
# CLI entry point
# ═══════════════════════════════════════════════════════════════════════════════

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Universal competitive deck builder",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scripts/cli/autobuild.py --name "Orzhov Lifegain" --colors WB --strategy lifegain
  python scripts/cli/autobuild.py --colors UR --strategy prowess --optimize 120
  python scripts/cli/autobuild.py --colors G --strategy aggro --tribe Elf
        """,
    )
    p.add_argument("--name", default="", help="Deck name (auto-generated if omitted)")
    p.add_argument("--colors", required=True, help="Color identity (e.g., WB, UR, G)")
    p.add_argument("--strategy", required=True,
                   choices=list(STRATEGY_QUERIES.keys()),
                   help="Primary strategy")
    p.add_argument("--tribe", default=None, help="Tribal subtype (e.g., Angel, Elf)")
    p.add_argument("--optimize", type=float, default=0,
                   help="Optimization time budget in seconds (0=skip)")
    p.add_argument("--output-dir", default=None, help="Output directory (default: Decks/)")
    return p


def main():
    args = build_parser().parse_args()
    paths = RepoPaths()
    colors = args.colors.upper()
    strategy = args.strategy

    # Deck name
    if not args.name:
        color_name = {"W": "White", "U": "Blue", "B": "Black", "R": "Red", "G": "Green"}
        cname = "".join(color_name.get(c, c) for c in colors)
        args.name = f"{cname} {strategy.title()}"
    safe_name = args.name.replace(" ", "_").replace("-", "_")

    # Output directory
    deck_date = date.today().isoformat()
    output_base = Path(args.output_dir) if args.output_dir else paths.decks_dir
    deck_dir = output_base / f"{deck_date}_{safe_name}"
    deck_dir.mkdir(parents=True, exist_ok=True)

    constraints = DeckConstraints.for_strategy(strategy)

    print("=" * 70)
    print(f"  AUTOBUILD: {args.name}")
    print(f"  Colors: {colors}  Strategy: {strategy}  Tribe: {args.tribe or 'none'}")
    print(f"  Output: {deck_dir}")
    print("=" * 70)

    # ── Step 1: Query candidate pool ──────────────────────────────────────
    print("\n[1/6] Querying candidate pool...")
    candidates = query_candidate_pool(strategy, colors, args.tribe)

    if len(candidates) < 20:
        print(f"ERROR: Only {len(candidates)} candidates found. Need at least 20.")
        sys.exit(1)

    # ── Step 2: Score pairwise synergies ──────────────────────────────────
    print("\n[2/6] Scoring pairwise synergies...")
    scores = score_pool(candidates, paths)
    print(f"  Scored {len(scores)} non-land cards")

    # ── Step 3: Greedy select best cards ──────────────────────────────────
    print("\n[3/6] Selecting best cards...")
    deck, remaining = greedy_select(scores, constraints, colors, paths)
    deck_names = {e["name"].lower() for e in deck}
    total_nonland = sum(e["qty"] for e in deck)
    print(f"  Selected {total_nonland} non-land cards ({len(deck)} unique)")

    # ── Step 4: Build mana base ───────────────────────────────────────────
    print("\n[4/6] Building mana base...")
    lands = build_mana_base(deck, colors, constraints, paths)
    total_lands = sum(e["qty"] for e in lands)
    print(f"  {total_lands} lands ({len(lands)} unique)")

    # ── Step 5: Build sideboard ───────────────────────────────────────────
    print("\n[5/6] Building sideboard...")
    sideboard = build_sideboard(remaining, deck_names, strategy, colors)
    total_sb = sum(e["qty"] for e in sideboard)
    print(f"  {total_sb} sideboard cards ({len(sideboard)} unique)")

    # ── Step 5b: Optimize (optional) ──────────────────────────────────────
    if args.optimize > 0:
        deck, lands, final_ev = optimize_deck(
            deck, lands, remaining, scores, constraints,
            time_budget=args.optimize,
        )

    # ── Step 6: Write and validate ────────────────────────────────────────
    print("\n[6/6] Writing and validating...")
    decklist_path = deck_dir / "decklist.txt"
    total = write_decklist(deck, lands, sideboard, decklist_path)
    print(f"  Wrote {total} mainboard + {total_sb} sideboard cards")

    # Validate
    print(f"\n  Running validate_decklist.py...")
    valid = validate_deck(decklist_path)
    if valid:
        print(f"  VALIDATION PASSED")
    else:
        print(f"  VALIDATION FAILED — check decklist for issues")

    # Panel evaluation
    print(f"\n  Running mythic panel evaluation...")
    panel = run_panel_eval(decklist_path)
    if panel:
        print(f"  Panel EV:        {panel.get('ev', 0):.1f}")
        print(f"  Consensus:       {panel.get('consensus', 0):.1f}")
        print(f"  Variance:        {panel.get('variance', 0):.1f}")
        print(f"  Avg CMC:         {panel.get('curve', {}).get('avg_cmc', 0):.2f}")
        bottlenecks = panel.get("active_bottlenecks", [])
        if bottlenecks:
            print(f"  Bottlenecks:     {', '.join(bottlenecks)}")
        else:
            print(f"  Bottlenecks:     none")

    print(f"\n{'=' * 70}")
    print(f"  BUILD COMPLETE: {decklist_path}")
    print(f"{'=' * 70}")


if __name__ == "__main__":
    main()
