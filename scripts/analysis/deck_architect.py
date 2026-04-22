"""
Deck Architect — comprehensive deck analysis module.

This module provides conclusive deck analysis including:
- Meta comparison with known competitive archetypes
- Specific deficiency identification
- Card-by-card role analysis
- Precise recommendations from candidate pool
- Competitive viability scoring and matchup predictions

Usage:
    from deck_architect import analyze_deck_conclusively
    
    result = analyze_deck_conclusively(
        deck_path="Decks/MyDeck/decklist.txt",
        candidate_pool="Decks/MyDeck/candidate_pool.csv",
        tribe="elf"
    )
"""

from __future__ import annotations

import csv
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))

from mtg_utils import RepoPaths, parse_decklist
from synergy_engine import (
    extract_deck_entries_from_decklist,
    load_cards_from_db,
    attach_card_data,
    score_pairwise,
    apply_mythic_judgment,
    compute_synergy_profile,
    infer_primary_axes,
    classify_role,
)
from synergy_types import (
    CardRole,
    SynergyProfile,
    CardScore,
    CompositeWeights,
    CORE_ENGINE_TAGS,
    INTERACTION_TAGS,
)


META_ARCHETYPES: Dict[str, Dict[str, Any]] = {
    "Rakdos Aggro": {
        "colors": "BR",
        "key_cards": [
            "Bloodthirsty Conqueror",
            "Enduring Tenacity",
            "Lord Skitter's Butcher",
            "Midnight Snack",
        ],
        "expected_curve": (1, 2, 3, 4),
        "playstyle": "aggressive",
        "min_creatures": 16,
        "max_avg_cmc": 3.5,
    },
    "Azorius Aggro": {
        "colors": "WU",
        "key_cards": [
            "Stir the Sands",
            "Elas il-Kor, Sadistic Pilgrim",
            "Minister of Inquiries",
            "Audit",
        ],
        "expected_curve": (1, 2, 3, 4),
        "playstyle": "aggressive",
        "min_creatures": 14,
        "max_avg_cmc": 3.0,
    },
    "Orzhov Lifegain": {
        "colors": "WB",
        "key_cards": [
            "South Wind Avatar",
            "Midnight Snack",
            "Caretaker's Talent",
            "Harvestrite Host",
        ],
        "expected_curve": (2, 3, 4, 5),
        "playstyle": "midrange",
        "min_creatures": 12,
        "max_avg_cmc": 4.0,
    },
    "Frog Tribal": {
        "colors": "GU",
        "key_cards": [
            "Iridescent Blademaster",
            "Polukranos Reborn",
            "Kogla and Yidaro",
            "Polukranos",
        ],
        "expected_curve": (2, 3, 4, 5),
        "playstyle": "tribal",
        "min_tribe": 15,
        "tribe": "frog",
    },
    "Elf Tribal": {
        "colors": "G",
        "key_cards": [
            "Llanowar Elves",
            "Elvish Clancaller",
            "Elvish War Priest",
            "Imperious Perfect",
        ],
        "expected_curve": (1, 2, 3, 4),
        "playstyle": "tribal",
        "min_tribe": 18,
        "tribe": "elf",
    },
    "Vampire Tribal": {
        "colors": "BW",
        "key_cards": [
            "Cordial Vampire",
            "Vampire Sovereign",
            "Bishop of Wings",
            "Sanctuary Seeker",
        ],
        "expected_curve": (2, 3, 4, 5),
        "playstyle": "tribal",
        "min_tribe": 15,
        "tribe": "vampire",
    },
    "Tokens/Go Wide": {
        "colors": "W",
        "key_cards": [
            "Anointed Procession",
            "Sacred Fire",
            "Crisis of Conviction",
            "Hunted Witness",
        ],
        "expected_curve": (2, 3, 4, 5),
        "playstyle": "go-wide",
        "min_tokens": 12,
    },
    "Esper Control": {
        "colors": "WU B",
        "key_cards": [
            "Disinformation Campaign",
            "Hieromancer's Cage",
            "Mystic Archaeologist",
            "Sorin, Vengeful Bloodlord",
        ],
        "expected_curve": (3, 4, 5, 6),
        "playstyle": "control",
        "min_removal": 8,
    },
    "Gruul Aggro": {
        "colors": "RG",
        "key_cards": [
            "Questing Beast",
            "Bonecrusher Giant",
            "Klothys, God of Destiny",
            "Shifting Ceratops",
        ],
        "expected_curve": (2, 3, 4, 5),
        "playstyle": "aggressive",
        "min_creatures": 16,
        "max_avg_cmc": 3.5,
    },
    "Dimir Mill": {
        "colors": "UB",
        "key_cards": [
            "Drowned Secrets",
            "Fraying Sanity",
            "S的商品",
            "Consuming Aetherborn",
        ],
        "expected_curve": (2, 3, 4, 5),
        "playstyle": "mill",
        "min_mill_cards": 8,
    },
}


@dataclass
class DeckAnalysisResult:
    competitive_viability: int
    meta_similarity: Dict[str, float]
    deficiencies: List[str]
    recommendations: List[Dict[str, Any]]
    card_analysis: List[Dict[str, Any]]
    matchup_predictions: Dict[str, str]
    one_page_summary: str


def _load_deck(deck_path: str) -> Tuple[List[Dict[str, Any]], RepoPaths]:
    """Load deck entries and card data from decklist."""
    deck_file = Path(deck_path)
    if not deck_file.exists():
        raise FileNotFoundError(f"Deck file not found: {deck_path}")

    entries = extract_deck_entries_from_decklist(deck_file, include_sideboard=False)
    card_names = [e["name"] for e in entries]

    paths = RepoPaths()
    card_data = load_cards_from_db(card_names, paths)

    annotated, missing = attach_card_data(entries, card_data)
    return annotated, paths


def _load_candidate_pool(candidate_pool_path: str) -> Dict[str, Dict[str, Any]]:
    """Load candidate pool CSV into a dict keyed by card name."""
    pool_file = Path(candidate_pool_path)
    if not pool_file.exists():
        return {}

    candidates = {}
    with open(pool_file, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            name = row.get("name", "").strip()
            if name:
                candidates[name.lower()] = row
    return candidates


def _calculate_meta_similarity(
    deck_cards: Dict[str, CardScore],
    deck_colors: Set[str],
    tribe: str = None,
) -> Dict[str, float]:
    """Calculate similarity percentage to known meta archetypes."""
    similarities = {}

    deck_key_cards = set()
    for sc in deck_cards.values():
        deck_key_cards.add(sc.profile.name.lower())

    for archetype, profile in META_ARCHETYPES.items():
        key_cards_lower = {c.lower() for c in profile["key_cards"]}
        matches = len(deck_key_cards & key_cards_lower)
        max_possible = len(key_cards_lower)

        similarity = (matches / max_possible) * 100 if max_possible > 0 else 0

        if profile.get("colors"):
            required_colors = set(profile["colors"])
            color_match = len(required_colors & deck_colors) / len(required_colors) * 100
            similarity = (similarity * 0.7) + (color_match * 0.3)

        if tribe and profile.get("tribe") == tribe:
            similarity = min(similarity + 15, 100)

        similarities[archetype] = round(similarity, 1)

    return dict(sorted(similarities.items(), key=lambda x: x[1], reverse=True))


def _identify_deficiencies(
    deck_cards: Dict[str, CardScore],
    scores: Dict[str, CardScore],
    tribe: str = None,
) -> List[str]:
    """Identify specific deck deficiencies with actionable feedback."""
    deficiencies = []

    total_cards = sum(sc.qty for sc in deck_cards.values())
    if total_cards == 0:
        return ["Deck is empty - no cards to analyze"]

    curve_distribution = {0: 0, 1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
    creatures = []
    removal_cards = 0
    early_game = 0
    tribe_count = 0

    for sc in deck_cards.values():
        cmc_bucket = min(int(sc.profile.cmc), 5)
        curve_distribution[cmc_bucket] += sc.qty

        if "creature" in sc.profile.type_line.lower():
            creatures.append(sc)
            if sc.profile.cmc <= 2:
                early_game += sc.qty

            if tribe and tribe in sc.profile.subtypes:
                tribe_count += sc.qty

        if sc.profile.broad_tags & INTERACTION_TAGS:
            removal_cards += sc.qty

    avg_cmc = sum(sc.profile.cmc * sc.qty for sc in deck_cards.values()) / total_cards

    early_game_frac = early_game / total_cards
    if early_game_frac < 0.15:
        deficiencies.append(
            f"No early interaction — only {early_game_frac*100:.0f}% of deck is 1-2 mana. "
            "Add 4x Lightning Strike or similar early interaction."
        )

    removal_frac = removal_cards / max(total_cards - sum(1 for sc in deck_cards.values() if "land" in sc.profile.type_line.lower()), 1)
    if removal_frac < 0.12:
        deficiencies.append(
            f"Insufficient removal ({removal_frac*100:.0f}% < 12%). "
            "Add 4x Go for the Throat or 3x Infernal Grasps."
        )

    if avg_cmc > 3.5:
        deficiencies.append(
            f"Mana curve too high (avg {avg_cmc:.1f}) — replace 2x 4-drops with 2-drops."
        )

    if avg_cmc < 2.0:
        deck_cards
        deficiencies.append(
            f"Mana curve too low (avg {avg_cmc:.1f}) — add 2-3 top-end finishers."
        )

    if curve_distribution[0] + curve_distribution[1] < 8:
        deficiencies.append(
            f"Not enough 1-drops ({curve_distribution[0]}) or 2-drops ({curve_distribution[1]}). "
            "Aggressive decks need 10+ cheap threats."
        )

    if len(creatures) > 0 and tribe:
        tribe_frac = tribe_count / len(creatures)
        if tribe_frac < 0.50:
            deficiencies.append(
                f"Tribe consistency {tribe_frac*100:.0f}% — add 3-4 more {tribe.capitalize()}s "
                f"(currently {tribe_count}/{len(creatures)} creatures)."
            )

    land_count = sum(sc.qty for sc in deck_cards.values() if sc.profile.is_land)
    if land_count < 17:
        deficiencies.append(
            f"Low land count ({land_count}) — consider 18-20 lands for {avg_cmc:.1f} avg CMC."
        )
    elif land_count > 26:
        deficiencies.append(
            f"High land count ({land_count}) — consider cutting 2-3 lands."
        )

    has_draw = any("draw" in sc.profile.broad_tags for sc in deck_cards.values())
    if not has_draw:
        deficiencies.append(
            "No card draw engine — add 2-3 draw spells for card advantage."
        )

    return deficiencies


def _analyze_card_roles(
    deck_cards: Dict[str, CardScore],
    scores: Dict[str, CardScore],
) -> List[Dict[str, Any]]:
    """Analyze each card's role in the deck."""
    analysis = []

    weights = CompositeWeights()

    for name, sc in deck_cards.items():
        role = sc.role
        profile = sc.profile

        composite = sc.composite_score_with(weights)

        is_glue = False
        is_payoff = False
        is_enabler = False
        is_distraction = False

        if role == CardRole.ENGINE:
            is_glue = True
        elif role == CardRole.PAYOFF:
            is_payoff = True
        elif role == CardRole.ENABLER:
            is_enabler = True
        elif role == CardRole.SUPPORT:
            if sc.synergy_count < 2:
                is_distraction = True

        analysis.append({
            "name": profile.name,
            "role": role.value,
            "qty": sc.qty,
            "cmc": profile.cmc,
            "synergy_score": round(composite, 1),
            "synergy_count": sc.synergy_count,
            "is_glue": is_glue,
            "is_payoff": is_payoff,
            "is_enabler": is_enabler,
            "is_distraction": is_distraction,
            "tags": list(profile.broad_tags | profile.source_tags | profile.payoff_tags),
            "redundant_with": sc.redundant_with[:3] if sc.redundant_with else [],
        })

    analysis.sort(key=lambda x: (-x["synergy_score"], -x["qty"]))
    return analysis


def _generate_recommendations(
    deck_cards: Dict[str, CardScore],
    candidate_pool: Dict[str, Dict[str, Any]],
    tribe: str = None,
) -> List[Dict[str, Any]]:
    """Generate precise add/cut recommendations from candidate pool."""
    recommendations = []

    current_cmc_dist = {}
    for sc in deck_cards.values():
        if not sc.profile.is_land:
            bucket = int(sc.profile.cmc)
            current_cmc_dist[bucket] = current_cmc_dist.get(bucket, 0) + sc.qty

    to_cut = []
    for name, sc in deck_cards.items():
        if sc.role == CardRole.SUPPORT and sc.synergy_count < 2:
            to_cut.append((name, sc, sc.synergy_count))
        elif sc.redundant_with and len(sc.redundant_with) >= 2:
            to_cut.append((name, sc, sc.synergy_count))

    to_cut.sort(key=lambda x: x[2])
    for name, sc, _ in to_cut[:4]:
        recommendations.append({
            "action": "CUT",
            "card": sc.profile.name,
            "qty": sc.qty,
            "reason": f"Low synergy ({sc.synergy_count} partners) or redundant",
            "expected_gain": 0,
        })

    if candidate_pool:
        pool_scores = []
        for name_lower, row in candidate_pool.items():
            try:
                syn_density = float(row.get("synergy_density", "0%").replace("%", ""))
                eng_density = float(row.get("engine_density", "0%").replace("%", ""))
                weighted = float(row.get("weighted_score", 0))
                engine = float(row.get("engine_score", 0))

                combined = (syn_density * 0.3 + eng_density * 0.4 + 
                           min(weighted / 100, 20) * 0.2 + engine / 1000 * 0.1)

                try:
                    cmc = float(row.get("cmc", 3))
                except (ValueError, TypeError):
                    cmc = 3.0

                try:
                    qty_available = int(row.get("qty", 4))
                except (ValueError, TypeError):
                    qty_available = 4

                pool_scores.append({
                    "name": row.get("name", name_lower),
                    "score": combined,
                    "cmc": cmc,
                    "available": qty_available,
                    "synergy_density": syn_density,
                    "engine_density": eng_density,
                })
            except (ValueError, TypeError):
                continue

        pool_scores.sort(key=lambda x: -x["score"])

        current_names = {sc.profile.name.lower() for sc in deck_cards.values()}
        cuts_total = sum(1 for r in recommendations if r["action"] == "CUT")

        for card_info in pool_scores[:8]:
            if card_info["name"].lower() in current_names:
                continue

            if cuts_total >= len([r for r in recommendations if r["action"] == "CUT"]) + 1:
                break

            expected_gain = round(card_info["score"] * 0.05, 1)
            recommendations.append({
                "action": "ADD",
                "card": card_info["name"],
                "qty": min(card_info["available"], 4),
                "reason": f"Synergy {card_info['synergy_density']:.0f}%, Engine {card_info['engine_density']:.0f}%",
                "expected_gain": expected_gain,
                "cmc": card_info["cmc"],
            })

    recommendations.sort(key=lambda x: (
        0 if x["action"] == "ADD" else 1,
        -x.get("expected_gain", 0) if x["action"] == "ADD" else 0
    ))

    return recommendations[:10]


def _calculate_viability(
    deck_cards: Dict[str, CardScore],
    scores: Dict[str, CardScore],
    meta_similarity: Dict[str, float],
    deficiencies: List[str],
) -> int:
    """Calculate competitive viability score (0-100)."""
    base_score = 50.0

    if meta_similarity:
        best_match = max(meta_similarity.values())
        base_score += best_match * 0.15

    weights = CompositeWeights()
    avg_synergy = 0
    count = 0
    for sc in deck_cards.values():
        avg_synergy += sc.composite_score_with(weights)
        count += 1
    avg_synergy = avg_synergy / count if count > 0 else 0
    base_score += min(avg_synergy / 10, 20)

    penalty_per_deficiency = 3
    base_score -= len(deficiencies) * penalty_per_deficiency

    total_cards = sum(sc.qty for sc in deck_cards.values())
    if total_cards >= 60:
        base_score += 5
    elif total_cards < 40:
        base_score -= 10

    creatures = sum(
        sc.qty for sc in deck_cards.values() 
        if "creature" in sc.profile.type_line.lower()
    )
    if creatures >= 16:
        base_score += 3
    elif creatures < 10:
        base_score -= 5

    land_count = sum(sc.qty for sc in deck_cards.values() if sc.profile.is_land)
    if 17 <= land_count <= 25:
        base_score += 3
    else:
        base_score -= 3

    return max(0, min(100, int(base_score)))


def _predict_matchups(
    deck_cards: Dict[str, CardScore],
    meta_similarity: Dict[str, float],
) -> Dict[str, str]:
    """Predict matchup outcomes against expected meta."""
    predictions = {}

    deck_tags = set()
    for sc in deck_cards.values():
        deck_tags.update(sc.profile.broad_tags)
        deck_tags.update(sc.profile.source_tags)
        deck_tags.update(sc.profile.payoff_tags)

    for archetype in ["Rakdos Aggro", "Azorius Aggro", "Esper Control", 
                      "Gruul Aggro", "Elf Tribal", "Frog Tribal"]:
        if archetype in meta_similarity and meta_similarity[archetype] > 40:
            predictions[archetype] = "Favorable"
        elif "control" in deck_tags and archetype == "Azorius Aggro":
            predictions[archetype] = "Unfavorable"
        elif "aggressive" in str(META_ARCHETYPES.get(archetype, {}).get("playstyle", "")):
            if "removal" in deck_tags or "wipe" in deck_tags:
                predictions[archetype] = "Favorable"
            else:
                predictions[archetype] = "Unfavorable"
        elif "tribal" in deck_tags:
            if archetype in ["Elf Tribal", "Frog Tribal"]:
                predictions[archetype] = "Even"
            else:
                predictions[archetype] = "Favorable"
        else:
            predictions[archetype] = "Even"

    return predictions


def _generate_summary(
    viability: int,
    meta_similarity: Dict[str, float],
    deficiencies: List[str],
    recommendations: List[Dict[str, Any]],
    card_analysis: List[Dict[str, Any]],
    matchups: Dict[str, str],
) -> str:
    """Generate one-page summary for deck registration."""
    lines = []
    lines.append("=" * 60)
    lines.append("DECK ANALYSIS SUMMARY")
    lines.append("=" * 60)

    lines.append(f"\n## COMPETITIVE VIABILITY: {viability}/100")

    if viability >= 80:
        lines.append("Rating: TIER 1 - Highly Competitive")
    elif viability >= 60:
        lines.append("Rating: TIER 2 - Competitive")
    elif viability >= 40:
        lines.append("Rating: TIER 3 - Moderate")
    else:
        lines.append("Rating: CASUAL - Needs Work")

    if meta_similarity:
        best_archetype = max(meta_similarity.items(), key=lambda x: x[1])
        lines.append(f"\nPrimary Archetype: {best_archetype[0]} ({best_archetype[1]}% similar)")

    lines.append("\n## KEY DEFICIENCIES")
    for i, deficiency in enumerate(deficiencies[:5], 1):
        lines.append(f"{i}. {deficiency}")

    lines.append("\n## TOP CARDS (Synergy Score)")
    for card in card_analysis[:5]:
        role_marker = ""
        if card["is_glue"]:
            role_marker = " [GLUE]"
        elif card["is_payoff"]:
            role_marker = " [PAYOFF]"
        elif card["is_distraction"]:
            role_marker = " [!]"
        lines.append(f"  {card['name']}: {card['synergy_score']}{role_marker}")

    lines.append("\n## RECOMMENDED CHANGES")
    for rec in recommendations[:6]:
        if rec["action"] == "CUT":
            lines.append(f"  - CUT {rec['qty']}x {rec['card']} ({rec['reason']})")
        else:
            lines.append(f"  + ADD {rec['qty']}x {rec['card']} ({rec['reason']})")

    lines.append("\n## EXPECTED MATCHUPS")
    for archetype, outcome in list(matchups.items())[:5]:
        lines.append(f"  vs {archetype}: {outcome}")

    lines.append("\n" + "=" * 60)
    return "\n".join(lines)


def analyze_deck_conclusively(
    deck_path: str,
    candidate_pool: str = None,
    tribe: str = None,
) -> Dict[str, Any]:
    """
    Perform comprehensive deck analysis.
    
    Args:
        deck_path: Path to decklist.txt file
        candidate_pool: Optional path to candidate_pool.csv for recommendations
        tribe: Optional tribe specification (e.g., "elf", "frog", "vampire")
    
    Returns:
        Dictionary containing:
        - competitive_viability: int 0-100
        - meta_similarity: dict mapping archetype to similarity percentage
        - deficiencies: list of specific deficiency strings
        - recommendations: list of dicts with action, card, expected_gain
        - card_analysis: list of per-card analysis dicts
        - matchup_predictions: dict of archetype -> predicted outcome
        - one_page_summary: formatted summary string
    """
    annotated, paths = _load_deck(deck_path)

    deck_entries = [e for e in annotated if e.get("found_in_db") and e.get("data")]
    
    scores = score_pairwise(deck_entries, primary_axis=tribe or "")
    
    if tribe:
        scores = apply_mythic_judgment(scores, tribe_specified=tribe)

    deck_cards: Dict[str, CardScore] = scores

    deck_colors: Set[str] = set()
    for sc in deck_cards.values():
        colors_str = sc.profile.colors
        if colors_str:
            deck_colors.update(c for c in colors_str if c.isalpha())

    meta_similarity = _calculate_meta_similarity(deck_cards, deck_colors, tribe)

    deficiencies = _identify_deficiencies(deck_cards, scores, tribe)

    card_analysis = _analyze_card_roles(deck_cards, scores)

    candidate_data = {}
    if candidate_pool:
        candidate_data = _load_candidate_pool(candidate_pool)

    recommendations = _generate_recommendations(deck_cards, candidate_data, tribe)

    viability = _calculate_viability(deck_cards, scores, meta_similarity, deficiencies)

    matchup_predictions = _predict_matchups(deck_cards, meta_similarity)

    one_page_summary = _generate_summary(
        viability, meta_similarity, deficiencies, 
        recommendations, card_analysis, matchup_predictions
    )

    return {
        "competitive_viability": viability,
        "meta_similarity": meta_similarity,
        "deficiencies": deficiencies,
        "recommendations": recommendations,
        "card_analysis": card_analysis,
        "matchup_predictions": matchup_predictions,
        "one_page_summary": one_page_summary,
    }


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Deck Architect - Comprehensive Deck Analysis")
    parser.add_argument("deck_path", help="Path to decklist.txt")
    parser.add_argument("--candidate-pool", "-c", help="Path to candidate_pool.csv")
    parser.add_argument("--tribe", "-t", help="Tribe specification (e.g., elf, frog)")
    parser.add_argument("--format", "-f", choices=["text", "json"], default="text",
                       help="Output format")

    args = parser.parse_args()

    result = analyze_deck_conclusively(
        deck_path=args.deck_path,
        candidate_pool=args.candidate_pool,
        tribe=args.tribe
    )

    if args.format == "json":
        import json
        print(json.dumps(result, indent=2))
    else:
        print(result["one_page_summary"])