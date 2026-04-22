#!/usr/bin/env python3
"""
Mythic Panel — Simulated 5-Mythic Player Deck Evaluation

Simulates five mythic-rank player archetypes evaluating tribal deck candidates:
  - spike_master: competitive focus, optimization
  - brewer_pro: creative builds, synergy hunting
  - grinder: grindy, attrition focus
  - aggro_pro: fast kills, tempo focus
  - control_master: inevitability, late game

Each player evaluates candidate_pool.csv using distinct criteria and provides
actionable feedback on tribe consistency, tribal payoff density, removal coverage,
card quality, and mana curve.

Usage:
    from scripts.mythic_panel import evaluate_deck
    feedback = evaluate_deck("Decks/my_deck/candidate_pool.csv", tribe="elves")
"""

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class CardCandidate:
    """Represents a card candidate from the pool."""
    name: str
    mana_cost: int
    tribe: Optional[str] = None
    is_anthem: bool = False
    is_removal: bool = False
    is_creature: bool = False
    power: Optional[int] = None
    toughness: Optional[int] = None
    synergy_score: float = 0.0


class MythicPlayer:
    """Base class for mythic player archetypes."""

    def __init__(self, name: str, focus: str, description: str):
        self.name = name
        self.focus = focus
        self.description = description
        self.feedback: List[str] = []

    def evaluate(
        self,
        candidates: List[CardCandidate],
        tribe: Optional[str] = None
    ) -> List[str]:
        """Evaluate candidates and return feedback list."""
        raise NotImplementedError

    def _count_tribe_cards(
        self,
        candidates: List[CardCandidate],
        tribe: Optional[str]
    ) -> int:
        """Count cards matching the tribe."""
        if not tribe:
            return 0
        return sum(1 for c in candidates if c.tribe and tribe.lower() in c.tribe.lower())

    def _count_anthem_cards(self, candidates: List[CardCandidate]) -> int:
        """Count anthem/buff effects."""
        return sum(1 for c in candidates if c.is_anthem)

    def _count_removal_cards(self, candidates: List[CardCandidate]) -> int:
        """Count removal spells."""
        return sum(1 for c in candidates if c.is_removal)

    def _count_creature_cards(self, candidates: List[CardCandidate]) -> int:
        """Count creature cards."""
        return sum(1 for c in candidates if c.is_creature)

    def _get_average_cmc(self, candidates: List[CardCandidate]) -> float:
        """Get average converted mana cost."""
        if not candidates:
            return 0.0
        total = sum(c.mana_cost for c in candidates)
        return total / len(candidates)

    def _get_curve_distribution(
        self,
        candidates: List[CardCandidate]
    ) -> Dict[int, int]:
        """Get mana curve distribution."""
        curve: Dict[int, int] = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0, 6: 0, 7: 0}
        for c in candidates:
            cmc = c.mana_cost
            if cmc >= 7:
                curve[7] = curve.get(7, 0) + 1
            elif cmc in curve:
                curve[cmc] = curve[cmc] + 1
        return curve


class SpikeMaster(MythicPlayer):
    """Competitive focus, optimization-oriented player."""

    def __init__(self):
        super().__init__(
            name="spike_master",
            focus="optimization",
            description="competitive focus, optimization"
        )

    def evaluate(
        self,
        candidates: List[CardCandidate],
        tribe: Optional[str] = None
    ) -> List[str]:
        feedback = []
        tribe_count = self._count_tribe_cards(candidates, tribe)
        creature_count = self._count_creature_cards(candidates)
        removal_count = self._count_removal_cards(candidates)
        avg_cmc = self._get_average_cmc(candidates)

        if tribe_count < 20:
            feedback.append(
                f"{self.name}: Tribe consistency critical — only {tribe_count}/60+ "
                f"cards match {tribe}. Need 20+ tribe cards for competitive reliability."
            )
        else:
            feedback.append(
                f"{self.name}: Tribe consistency solid at {tribe_count} cards. "
                f"Ready for competitive testing."
            )

        if removal_count < 8:
            feedback.append(
                f"{self.name}: Removal coverage insufficient — {removal_count} spells. "
                f"Add 4+ interactive spells for meta adaptability."
            )
        else:
            feedback.append(
                f"{self.name}: Removal suite adequate ({removal_count} spells). "
                f"Adjust based on expected meta."
            )

        if avg_cmc > 3.5:
            feedback.append(
                f"{self.name}: Curve too high at {avg_cmc:.1f} avg CMC. "
                f"Optimize for aggression — lower curve by 0.5."
            )
        else:
            feedback.append(
                f"{self.name}: Mana curve optimized at {avg_cmc:.1f} avg CMC."
            )

        if creature_count < 24:
            feedback.append(
                f"{self.name}: Creature density low at {creature_count}. "
                f"Maximize creature count for clock consistency."
            )

        return feedback


class BrewerPro(MythicPlayer):
    """Creative builds, synergy-hunting player."""

    def __init__(self):
        super().__init__(
            name="brewer_pro",
            focus="synergy hunting",
            description="creative builds, synergy hunting"
        )

    def evaluate(
        self,
        candidates: List[CardCandidate],
        tribe: Optional[str] = None
    ) -> List[str]:
        feedback = []
        tribe_count = self._count_tribe_cards(candidates, tribe)
        anthem_count = self._count_anthem_cards(candidates)

        synergy_cards = [c for c in candidates if c.synergy_score >= 7.0]
        high_synergy = len(synergy_cards)

        if anthem_count < 3:
            feedback.append(
                f"{self.name}: Tribal payoff density critical — only {anthem_count} "
                f"anthem/buff effects. Need 4+ for explosive synergies."
            )
        else:
            feedback.append(
                f"{self.name}: Tribal payoff density strong at {anthem_count} effects."
            )

        if high_synergy < 8:
            feedback.append(
                f"{self.name}: Synergy density low — {high_synergy} high-synergy cards. "
                f"Hunt for more 7.0+ synergy connections."
            )
        else:
            feedback.append(
                f"{self.name}: Synergy network robust with {high_synergy} "
                f"high-synergy connections."
            )

        if tribe_count < 25:
            feedback.append(
                f"{self.name}: Tribe core thin at {tribe_count} cards. "
                f"Expand to 25+ for more consistent triggers."
            )

        avg_synergy = 0.0
        if candidates:
            avg_synergy = sum(c.synergy_score for c in candidates) / len(candidates)
        if avg_synergy < 5.0:
            feedback.append(
                f"{self.name}: Overall synergy score avg {avg_synergy:.1f} is low. "
                f"Seek higher-synergy replacements."
            )

        return feedback


class Grinder(MythicPlayer):
    """Grindy, attrition-focused player."""

    def __init__(self):
        super().__init__(
            name="grinder",
            focus="attrition",
            description="grindy, attrition focus"
        )

    def evaluate(
        self,
        candidates: List[CardCandidate],
        tribe: Optional[str] = None
    ) -> List[str]:
        feedback = []
        creature_count = self._count_creature_cards(candidates)
        removal_count = self._count_removal_cards(candidates)
        curve = self._get_curve_distribution(candidates)

        top_end = curve.get(5, 0) + curve.get(6, 0) + curve.get(7, 0)
        total_creatures = sum(1 for c in candidates if c.is_creature)
        high_toughness = sum(
            1 for c in candidates
            if c.is_creature and c.toughness and c.toughness >= 4
        )

        if removal_count < 10:
            feedback.append(
                f"{self.name}: Attrition suite needs depth — {removal_count} removal "
                f"spells. Aim for 12+ for grindy matchups."
            )
        else:
            feedback.append(
                f"{self.name}: Attrition suite solid at {removal_count} removal spells."
            )

        if high_toughness < 6:
            feedback.append(
                f"{self.name}: High-toughness ground presence weak at "
                f"{high_toughness} creatures. Add 4+ toughness creatures."
            )

        if top_end < 4:
            feedback.append(
                f"{self.name}: Top-end density insufficient ({top_end} cards). "
                f"Add 6+ drops for inevitability in long games."
            )
        else:
            feedback.append(
                f"{self.name}: Top-end presence adequate ({top_end} cards)."
            )

        if total_creatures < 20:
            feedback.append(
                f"{self.name}: Creature count at {total_creatures} — add more "
                f"for attrition battlefield presence."
            )

        return feedback


class AggroPro(MythicPlayer):
    """Fast kills, tempo-focused player."""

    def __init__(self):
        super().__init__(
            name="aggro_pro",
            focus="tempo",
            description="fast kills, tempo focus"
        )

    def evaluate(
        self,
        candidates: List[CardCandidate],
        tribe: Optional[str] = None
    ) -> List[str]:
        feedback = []
        curve = self._get_curve_distribution(candidates)
        tribe_count = self._count_tribe_cards(candidates, tribe)
        creature_count = self._count_creature_cards(candidates)

        turn_one_plays = curve.get(1, 0) + curve.get(2, 0)
        early_creatures = sum(
            1 for c in candidates
            if c.is_creature and c.mana_cost <= 2 and c.power
            and c.power >= 2
        )
        cheap_removal = sum(1 for c in candidates if c.is_removal and c.mana_cost <= 2)

        if turn_one_plays < 8:
            feedback.append(
                f"{self.name}: Turn 1-2 plays insufficient at {turn_one_plays}. "
                f"Need 10+ one-drops and two-drops for tempo."
            )
        else:
            feedback.append(
                f"{self.name}: Fast mana base strong ({turn_one_plays} turn 1-2 plays)."
            )

        if early_creatures < 10:
            feedback.append(
                f"{self.name}: Early pressure creatures low at {early_creatures}. "
                f"Add 12+ 1-2 mana 2+ power creatures."
            )
        else:
            feedback.append(
                f"{self.name}: Early pressure suite ready ({early_creatures} creatures)."
            )

        if tribe_count < 28:
            feedback.append(
                f"{self.name}: Aggro tribe synergy needs {tribe_count}+ — "
                f"maximize tribe trigger frequency."
            )

        if creature_count < 30:
            feedback.append(
                f"{self.name}: Creature count low at {creature_count}. "
                f"Aggro wants 32+ creatures for clock consistency."
            )

        if cheap_removal < 4:
            feedback.append(
                f"{self.name}: Cheap interaction sparse ({cheap_removal} spells). "
                f"Add 4+ at instant speed for tempo plays."
            )

        return feedback


class ControlMaster(MythicPlayer):
    """Inevitability, late-game-focused player."""

    def __init__(self):
        super().__init__(
            name="control_master",
            focus="inevitability",
            description="inevitability, late game"
        )

    def evaluate(
        self,
        candidates: List[CardCandidate],
        tribe: Optional[str] = None
    ) -> List[str]:
        feedback = []
        removal_count = self._count_removal_cards(candidates)
        curve = self._get_curve_distribution(candidates)
        anthem_count = self._count_anthem_cards(candidates)

        top_end = curve.get(5, 0) + curve.get(6, 0) + curve.get(7, 0)
        total_creatures = sum(1 for c in candidates if c.is_creature)
        flyers = sum(
            1 for c in candidates
            if c.is_creature and ("flying" in str(getattr(c, 'keywords', '')).lower() or
            "flying" in str(getattr(c, 'text', '')).lower())
        )

        if removal_count < 12:
            feedback.append(
                f"{self.name}: Control suite insufficient at {removal_count} spells. "
                f"Need 14+ removal for card advantage parity."
            )
        else:
            feedback.append(
                f"{self.name}: Control suite solid at {removal_count} removal spells."
            )

        if top_end < 6:
            feedback.append(
                f"{self.name}: Win condition density low at {top_end} late-game cards. "
                f"Add 8+ top-end bombs for inevitability."
            )
        else:
            feedback.append(
                f"{self.name}: Late-game bombs adequate ({top_end} cards)."
            )

        if anthem_count < 2:
            feedback.append(
                f"{self.name}: Battlefield anthem effects low at {anthem_count}. "
                f"Add 3+ for inevitability swings."
            )

        if total_creatures > 20:
            feedback.append(
                f"{self.name}: Creature count {total_creatures} suitable for "
                f"ctrl — maintain card advantage focus."
            )

        return feedback


def _load_candidates(
    candidate_pool_path: str,
    tribe: Optional[str] = None
) -> List[CardCandidate]:
    """Load candidates from CSV file."""
    candidates: List[CardCandidate] = []
    path = Path(candidate_pool_path)

    if not path.exists():
        raise FileNotFoundError(f"Candidate pool not found: {candidate_pool_path}")

    with open(path, newline="", encoding="utf-8") as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            try:
                candidate = CardCandidate(
                    name=row.get("name", ""),
                    mana_cost=int(row.get("mana_cost", 0)),
                    tribe=row.get("tribe", ""),
                    is_anthem=row.get("is_anthem", "").lower() in ("true", "1", "yes"),
                    is_removal=row.get("is_removal", "").lower() in ("true", "1", "yes"),
                    is_creature=row.get("is_creature", "").lower() in ("true", "1", "yes"),
                    power=int(row.get("power", 0)) if row.get("power") else None,
                    toughness=int(row.get("toughness", 0)) if row.get("toughness") else None,
                    synergy_score=float(row.get("synergy_score", 0.0)),
                )
                candidates.append(candidate)
            except (ValueError, KeyError):
                continue

    return candidates


def evaluate_deck(candidate_pool_path: str, tribe: str = None) -> list[str]:
    """
    Run 5-mythic-panel evaluation on a deck candidate pool.

    Args:
        candidate_pool_path: Path to candidate_pool.csv file.
        tribe: Optional tribe name for consistency checking.

    Returns:
        List of feedback strings from all 5 mythic players.

    Example:
        >>> feedback = evaluate_deck("Decks/elves/candidate_pool.csv", tribe="elves")
        >>> for line in feedback:
        ...     print(line)
    """
    candidates = _load_candidates(candidate_pool_path, tribe)

    players: List[MythicPlayer] = [
        SpikeMaster(),
        BrewerPro(),
        Grinder(),
        AggroPro(),
        ControlMaster(),
    ]

    feedback: List[str] = []
    feedback.append(f"=== 5-Mythic Panel Evaluation ===")
    feedback.append(f"Candidates: {len(candidates)}, Tribe: {tribe or 'N/A'}")
    feedback.append("")

    for player in players:
        player_feedback = player.evaluate(candidates, tribe)
        feedback.extend(player_feedback)
        feedback.append("")

    return feedback


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python mythic_panel.py <candidate_pool.csv> [tribe]")
        sys.exit(1)

    pool_path = sys.argv[1]
    tribe_arg = sys.argv[2] if len(sys.argv) > 2 else None

    try:
        results = evaluate_deck(pool_path, tribe_arg)
        for line in results:
            print(line)
    except FileNotFoundError as e:
        print(f"Error: {e}")
        sys.exit(1)