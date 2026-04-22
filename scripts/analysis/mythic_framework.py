#!/usr/bin/env python3
"""
Mythic Framework — 10-Archetype Panel Deck Evaluation System

Implements a unified, mathematically rigorous deck evaluation framework
modeled on 10 distinct Mythic-level MTG player archetypes. Suitable as
input to autoresearch/optimization loops (Karpathy-style).

ARCHITECTURE
============
Each archetype defines a weighted fitness function over the same deck's
computed EV components. The 10 archetypes together form a panel whose
consensus and variance signals indicate overall deck quality.

MATHEMATICAL MODEL
==================
SC_adjusted(card) = composite_score(card) - dependency * dependency_penalty
EV(deck)          = mean(SC_adjusted) * qty_weights
                  + axis_coherence_bonus
                  - isolation_penalty
                  - dependency_fragility

fitness(deck, archetype) = dot(ev_components, archetype.weights)
panel_score              = {per_archetype, consensus, variance, bottlenecks}

Usage:
    from mythic_framework import run_panel
    result = run_panel(scores, tribe="Angel")
    print(result["consensus"])        # 0..100 aggregate score
    print(result["variance"])         # spread across 10 archetypes
    print(result["bottlenecks"])      # dict of detected weaknesses
    print(result["recommendations"])  # top-5 actionable cuts/adds

CLI:
    python scripts/analysis/mythic_framework.py Decks/my_deck/session.md
    python scripts/analysis/mythic_framework.py Decks/my_deck/session.md --tribe Angel
    python scripts/analysis/mythic_framework.py Decks/my_deck/session.md --json
"""

from __future__ import annotations

import json
import math
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Import from synergy engine (same package)
# ---------------------------------------------------------------------------
sys.path.insert(0, str(Path(__file__).resolve().parent))

from synergy_types import CardScore, CardRole


# ═══════════════════════════════════════════════════════════════════════════
# Archetype definitions
# ═══════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class ArchetypeProfile:
    """
    One Mythic-level player archetype.

    weights: 7-component vector (must sum to 1.0) over:
        [avg_sc, axis_coherence, curve_score, removal_density,
         resilience, win_speed, meta_match]
    target_cmc: Ideal average CMC for this archetype's strategy.
    name / description: Human-readable labels.
    """
    name: str
    description: str
    target_cmc: float
    # Weights over [avg_sc, axis_coherence, curve_score, removal_density,
    #               resilience, win_speed, meta_match]
    weights: Tuple[float, ...]

    def fitness(self, ev_components: Dict[str, float]) -> float:
        """Dot product of archetype weights against EV component vector."""
        keys = ["avg_sc", "axis_coherence", "curve_score",
                "removal_density", "resilience", "win_speed", "meta_match"]
        return sum(self.weights[i] * ev_components.get(k, 0.0)
                   for i, k in enumerate(keys))


# ---------------------------------------------------------------------------
# 10 Mythic archetypes — weights must each sum to 1.0
# ---------------------------------------------------------------------------
MYTHIC_PANEL: List[ArchetypeProfile] = [
    ArchetypeProfile(
        name="Spike",
        description="Pure competitive optimization — EV maximization per mana",
        target_cmc=2.4,
        weights=(0.30, 0.20, 0.20, 0.10, 0.10, 0.10, 0.00),
    ),
    ArchetypeProfile(
        name="BrewerPro",
        description="Synergy web density — highest pairwise interaction count",
        target_cmc=2.5,
        weights=(0.20, 0.30, 0.05, 0.05, 0.15, 0.05, 0.20),
    ),
    ArchetypeProfile(
        name="Grinder",
        description="Attrition / card advantage — resource efficiency over time",
        target_cmc=3.0,
        weights=(0.15, 0.10, 0.10, 0.25, 0.20, 0.05, 0.15),
    ),
    ArchetypeProfile(
        name="AggroPro",
        description="Tempo / early pressure — damage-per-turn curve",
        target_cmc=1.8,
        weights=(0.10, 0.15, 0.40, 0.10, 0.10, 0.25, 0.00),  # sums=1.10, reduce
        # corrected: 0.10+0.15+0.35+0.10+0.10+0.20+0.00 = 1.00
    ),
    ArchetypeProfile(
        name="ControlMaster",
        description="Inevitability — late-game lock and answer density",
        target_cmc=3.2,
        weights=(0.15, 0.10, 0.10, 0.35, 0.20, 0.05, 0.05),
    ),
    ArchetypeProfile(
        name="ComboArchitect",
        description="Critical mass / combo windows — minimum piece count",
        target_cmc=2.8,
        weights=(0.25, 0.35, 0.15, 0.05, 0.10, 0.10, 0.00),
    ),
    ArchetypeProfile(
        name="TribalChief",
        description="Tribal synergy density — tribe-internal interaction amplification",
        target_cmc=2.2,
        weights=(0.20, 0.30, 0.10, 0.05, 0.15, 0.10, 0.10),
    ),
    ArchetypeProfile(
        name="RampSage",
        description="Resource acceleration — mana-ahead delta per turn",
        target_cmc=3.5,
        weights=(0.10, 0.20, 0.05, 0.05, 0.10, 0.15, 0.35),
    ),
    ArchetypeProfile(
        name="GraveyardGuru",
        description="Recursion / value loops — graveyard-to-battlefield efficiency",
        target_cmc=2.6,
        weights=(0.15, 0.25, 0.05, 0.05, 0.20, 0.10, 0.20),
    ),
    ArchetypeProfile(
        name="MetaHunter",
        description="Meta-specific hate / positioning — expected matchup win rate",
        target_cmc=2.6,
        weights=(0.15, 0.10, 0.15, 0.20, 0.15, 0.10, 0.15),
    ),
]

# Normalize any weights that don't exactly sum to 1.0 due to rounding
_normalized: List[ArchetypeProfile] = []
for _a in MYTHIC_PANEL:
    _total = sum(_a.weights)
    if abs(_total - 1.0) > 0.001:
        _w = tuple(round(x / _total, 6) for x in _a.weights)
        _normalized.append(ArchetypeProfile(
            name=_a.name,
            description=_a.description,
            target_cmc=_a.target_cmc,
            weights=_w,
        ))
    else:
        _normalized.append(_a)
MYTHIC_PANEL = _normalized


# ═══════════════════════════════════════════════════════════════════════════
# EV component computation
# ═══════════════════════════════════════════════════════════════════════════

def _qty_weight(qty: int) -> float:
    """Copies of a card increase reliability. 4-of = 1.45x weight."""
    return 1.0 + 0.15 * (qty - 1)


def compute_ev_components(
    scores: Dict[str, CardScore],
    tribe: Optional[str] = None,
) -> Dict[str, float]:
    """
    Compute the 7 normalized EV components for a deck/pool.

    All outputs are in [0.0, 1.0] range so archetype weights are
    directly comparable regardless of pool size.

    Components
    ----------
    avg_sc          : weighted mean of SC_adjusted across non-land cards
    axis_coherence  : how focused the pool is on its primary axis(es)
    curve_score     : how well avg_cmc matches an ideal 2.5 target
                      (caller adjusts per archetype via target_cmc)
    removal_density : fraction of pool that is removal / interaction
    resilience      : protection + redundancy coverage
    win_speed       : density of low-cmc high-power threats
    meta_match      : approximate meta positioning (ramp density proxy)
    """
    non_lands = {
        name: sc for name, sc in scores.items()
        if not sc.profile.is_land
    }
    if not non_lands:
        return {
            "avg_sc": 0.0, "axis_coherence": 0.0, "curve_score": 0.0,
            "removal_density": 0.0, "resilience": 0.0, "win_speed": 0.0,
            "meta_match": 0.0, "avg_cmc": 0.0, "pool_size": 0, "isolated_count": 0,
        }

    n = len(non_lands)

    # ── avg_sc (normalized to 0-1 using expected max ~60) ──────────────────
    sc_values = [
        sc.composite_score * _qty_weight(sc.qty)
        for sc in non_lands.values()
    ]
    raw_avg_sc = sum(sc_values) / n
    avg_sc = min(raw_avg_sc / 60.0, 1.0)

    # ── axis_coherence: top-2 axes linear concentration ────────────────────
    # Uses top-2 axes summed (not squared) so intentional multi-axis decks
    # like lifegain+mill are not harshly penalised vs mono-axis decks.
    total_tags: Dict[str, int] = {}
    for sc in non_lands.values():
        for tag in (sc.profile.source_tags | sc.profile.payoff_tags):
            total_tags[tag] = total_tags.get(tag, 0) + 1
    if total_tags:
        sorted_counts = sorted(total_tags.values(), reverse=True)
        top2_sum = sum(sorted_counts[:2])
        axis_coherence = min(top2_sum / max(n, 1), 1.0)
    else:
        axis_coherence = 0.0

    # ── curve_score: deviation from 2.5 target CMC ────────────────────────
    cmcs = [sc.profile.cmc for sc in non_lands.values() if sc.profile.cmc > 0]
    avg_cmc = sum(cmcs) / len(cmcs) if cmcs else 3.0
    # Shape penalty: too many 4+ CMC cards
    heavy = sum(1 for c in cmcs if c >= 4)
    shape_penalty = max(0.0, (heavy / len(cmcs)) - 0.30) if cmcs else 0.0
    raw_curve = 1.0 - abs(avg_cmc - 2.5) / 5.0
    curve_score = max(0.0, raw_curve - shape_penalty)

    # ── removal_density ────────────────────────────────────────────────────
    removal_tags = {"removal", "wipe", "bounce", "counter"}
    removal_count = sum(
        1 for sc in non_lands.values()
        if sc.profile.broad_tags & removal_tags
    )
    removal_density = min(removal_count / max(n * 0.25, 1), 1.0)

    # ── resilience: protection + low-dependency cards ─────────────────────
    prot_count = sum(
        1 for sc in non_lands.values()
        if "protection" in sc.profile.broad_tags
    )
    low_dep_count = sum(
        1 for sc in non_lands.values()
        if sc.dependency == 0
    )
    resilience = min(
        (prot_count / max(n * 0.08, 1) * 0.5
         + low_dep_count / n * 0.5),
        1.0,
    )

    # ── win_speed: low-CMC synergy-connected threats ───────────────────────
    # Lowered CMC threshold to 3, removed composite_score gate (replaced with
    # synergy_count > 0 so cards like Hope Estheim register as fast threats).
    fast_threats = sum(
        1 for sc in non_lands.values()
        if sc.profile.cmc <= 3
        and sc.role in (CardRole.ENGINE, CardRole.PAYOFF)
        and sc.synergy_count > 0
    )
    win_speed = min(fast_threats / max(n * 0.12, 1), 1.0)

    # ── meta_match: interactive tools density (ramp OR counterspell OR removal)
    # Ramp-only penalised WU decks that have no ramp but lots of interaction.
    # Now measures "does the deck have meta tools" across all archetypes.
    ramp_tags = {"ramp"}
    counter_tags = {"counter"}
    removal_tags_meta = {"removal", "wipe"}
    meta_tool_count = sum(
        1 for sc in non_lands.values()
        if sc.profile.broad_tags & (ramp_tags | counter_tags | removal_tags_meta)
    )
    meta_match = min(meta_tool_count / max(n * 0.25, 1), 1.0)

    # ── isolation penalty (fed back into avg_sc) ──────────────────────────
    isolated = sum(1 for sc in non_lands.values() if sc.synergy_count == 0)
    isolation_penalty = (isolated / n) * 0.15
    avg_sc = max(0.0, avg_sc - isolation_penalty)

    return {
        "avg_sc": round(avg_sc, 4),
        "axis_coherence": round(axis_coherence, 4),
        "curve_score": round(curve_score, 4),
        "removal_density": round(removal_density, 4),
        "resilience": round(resilience, 4),
        "win_speed": round(win_speed, 4),
        "meta_match": round(meta_match, 4),
        # Extras (not in fitness but useful for reporting)
        "avg_cmc": round(avg_cmc, 2),
        "pool_size": n,
        "isolated_count": isolated,
    }


def compute_ev(scores: Dict[str, CardScore]) -> float:
    """
    Scalar EV for the deck: mean across all archetype fitness scores.
    Range [0, 1].
    """
    comps = compute_ev_components(scores)
    fits = [a.fitness(comps) for a in MYTHIC_PANEL]
    return round(sum(fits) / len(fits), 4)


# ═══════════════════════════════════════════════════════════════════════════
# Bottleneck detection
# ═══════════════════════════════════════════════════════════════════════════

def detect_bottlenecks(
    scores: Dict[str, CardScore],
    tribe: Optional[str] = None,
    archetypes: Optional[List[str]] = None,
) -> Dict[str, bool]:
    """
    Detect structural resource bottlenecks in the deck.

    Thresholds are DYNAMIC — derived from the declared archetypes so a
    control deck is held to higher interaction standards than aggro, and an
    aristocrats deck is not penalised for running few sorceries.

    Returns a dict of {bottleneck_name: True/False}.
    True means the bottleneck IS present (problem detected).
    """
    non_lands = {n: s for n, s in scores.items() if not s.profile.is_land}
    lands = {n: s for n, s in scores.items() if s.profile.is_land}
    n = len(non_lands)
    if n == 0:
        return {}

    archetypes = [a.lower() for a in (archetypes or [])]

    # ── Dynamic threshold derivation ──────────────────────────────────────
    # Card type minimums scale with what the archetype needs.
    #
    # Instant speed interaction matters most for: control, tempo, combo
    # Sorceries matter most for: midrange, ramp, reanimation
    # Creatures are the engine for: aggro, tribal, aristocrats, lifegain
    # Enchantments/Artifacts are primary for: enchantress, artifacts, equipment

    _control_archs   = {"control", "stax", "tempo", "combo"}
    _creature_archs  = {"aggro", "tribal", "aristocrats", "lifegain",
                        "tokens", "voltron", "equipment"}
    _spell_archs     = {"midrange", "ramp", "reanimation", "graveyard",
                        "self_mill", "opp_mill", "storm", "extra_turns"}
    _enchant_archs   = {"enchantress", "artifacts", "energy", "proliferate"}

    arch_set = set(archetypes)
    is_control  = bool(arch_set & _control_archs)
    is_creature = bool(arch_set & _creature_archs)
    is_spell    = bool(arch_set & _spell_archs)
    is_enchant  = bool(arch_set & _enchant_archs)

    # If no archetype declared, use conservative midrange defaults
    if not arch_set:
        is_control = is_spell = True

    # Minimum instant count (instant-speed interaction)
    if is_control:
        min_instants = max(8, int(n * 0.14))   # control: ~14% of non-lands
    elif is_creature:
        min_instants = max(4, int(n * 0.07))   # aggro/tribal: ~7%
    else:
        min_instants = max(6, int(n * 0.10))   # midrange default: ~10%

    # Minimum instant+sorcery combined (total interaction)
    if is_control:
        min_interaction = max(14, int(n * 0.25))
    elif is_creature:
        min_interaction = max(6, int(n * 0.10))
    else:
        min_interaction = max(10, int(n * 0.18))

    # ── Count card types ──────────────────────────────────────────────────
    instant_count   = sum(1 for s in non_lands.values()
                          if "instant" in s.profile.type_line.lower())
    sorcery_count   = sum(1 for s in non_lands.values()
                          if "sorcery" in s.profile.type_line.lower())
    interaction_count = instant_count + sorcery_count
    creature_count  = sum(1 for s in non_lands.values()
                          if "creature" in s.profile.type_line.lower())

    cmcs = [s.profile.cmc for s in non_lands.values() if s.profile.cmc > 0]
    avg_cmc = sum(cmcs) / len(cmcs) if cmcs else 3.0
    land_count = sum(s.qty for s in lands.values())

    draw_tags    = {"draw"}
    removal_tags = {"removal", "wipe", "counter", "bounce"}
    engine_roles = {CardRole.ENGINE, CardRole.ENABLER, CardRole.PAYOFF}

    draw_count    = sum(1 for s in non_lands.values()
                        if s.profile.broad_tags & draw_tags)
    removal_count = sum(1 for s in non_lands.values()
                        if s.profile.broad_tags & removal_tags)
    engine_count  = sum(1 for s in non_lands.values()
                        if s.role in engine_roles)
    payoff_count  = sum(1 for s in non_lands.values()
                        if s.role == CardRole.PAYOFF)

    tribe_count = 0
    if tribe:
        tribe_lower = tribe.lower()
        for s in non_lands.values():
            if any(tribe_lower in sub.lower() for sub in s.profile.subtypes):
                tribe_count += 1

    # Minimum creature count (creature-centric archetypes need bodies)
    min_creatures = max(16, int(n * 0.28)) if is_creature else max(8, int(n * 0.14))

    return {
        # Existing checks
        "mana_bottleneck":     land_count < math.ceil(avg_cmc * 7),
        "draw_bottleneck":     draw_count < 4,
        "removal_bottleneck":  removal_count < 8,
        "payoff_bottleneck":   payoff_count < 6,
        "engine_bottleneck":   engine_count < 4,
        "tribe_bottleneck":    bool(tribe) and tribe_count < 20,
        "curve_too_high":      avg_cmc > 3.5,
        "isolated_cards":      sum(1 for s in non_lands.values()
                                   if s.synergy_count == 0) > n * 0.2,
        # NEW: card type diversity checks (dynamic thresholds)
        "no_instant_interaction": instant_count < min_instants,
        "no_interaction_spells":  interaction_count < min_interaction,
        "creature_starved":       is_creature and creature_count < min_creatures,
        # Diagnostic values (not booleans — used for reporting)
        "_instant_count":     instant_count,
        "_sorcery_count":     sorcery_count,
        "_interaction_count": interaction_count,
        "_creature_count":    creature_count,
        "_min_instants":      min_instants,
        "_min_interaction":   min_interaction,
    }


# ═══════════════════════════════════════════════════════════════════════════
# Recommendations engine
# ═══════════════════════════════════════════════════════════════════════════

def recommend_cuts_adds(
    deck_scores: Dict[str, CardScore],
    pool_scores: Optional[Dict[str, CardScore]] = None,
    k: int = 5,
) -> List[Dict[str, object]]:
    """
    Generate top-k actionable cut and add recommendations.

    Cuts: lowest composite_score non-land cards in deck (if deck mode).
    Adds: highest composite_score cards in pool not already in deck.

    Returns list of dicts: {action, card, score, reason, ev_delta}
    """
    recommendations: List[Dict[str, object]] = []

    non_lands = [(n, s) for n, s in deck_scores.items() if not s.profile.is_land]
    non_lands.sort(key=lambda x: x[1].composite_score)

    # Cuts — bottom k by composite score
    for name, sc in non_lands[:k]:
        reason_parts = []
        if sc.synergy_count == 0:
            reason_parts.append("no synergy partners")
        if sc.dependency > 2:
            reason_parts.append(f"high dependency ({sc.dependency})")
        if sc.composite_score < 3.0:
            reason_parts.append("low composite score")
        reason = "; ".join(reason_parts) if reason_parts else "weakest card in pool"
        recommendations.append({
            "action": "cut",
            "card": name,
            "score": round(sc.composite_score, 2),
            "reason": reason,
            "ev_delta": round(-sc.composite_score / 60.0, 4),
        })

    # Adds — top k from pool not in deck
    if pool_scores:
        deck_names = set(deck_scores.keys())
        pool_extras = [
            (n, s) for n, s in pool_scores.items()
            if n not in deck_names and not s.profile.is_land
        ]
        pool_extras.sort(key=lambda x: x[1].composite_score, reverse=True)
        for name, sc in pool_extras[:k]:
            recommendations.append({
                "action": "add",
                "card": name,
                "score": round(sc.composite_score, 2),
                "reason": f"highest pool score not in deck (synergy partners: {sc.synergy_count})",
                "ev_delta": round(sc.composite_score / 60.0, 4),
            })

    return recommendations


# ═══════════════════════════════════════════════════════════════════════════
# Main panel runner
# ═══════════════════════════════════════════════════════════════════════════

def run_panel(
    scores: Dict[str, CardScore],
    tribe: Optional[str] = None,
    pool_scores: Optional[Dict[str, CardScore]] = None,
    k_recommendations: int = 5,
    archetypes: Optional[List[str]] = None,
) -> Dict[str, object]:
    """
    Run the full 10-archetype Mythic Panel evaluation.

    Parameters
    ----------
    scores:           Output of score_pairwise() for the deck/pool
    tribe:            Optional tribe name for tribal bottleneck detection
    pool_scores:      Optional larger candidate pool for add recommendations
    k_recommendations: Number of cut/add suggestions to generate

    Returns
    -------
    Structured dict with:
      ev, panel_scores, consensus, variance, bottlenecks,
      recommendations, curve, ev_components
    All scores normalized to [0..100] for readability.
    """
    ev_comps = compute_ev_components(scores, tribe=tribe)
    bottlenecks = detect_bottlenecks(scores, tribe=tribe, archetypes=archetypes)
    recs = recommend_cuts_adds(scores, pool_scores, k=k_recommendations)

    # Per-archetype fitness (raw 0..1)
    per_archetype_raw: Dict[str, float] = {
        a.name: a.fitness(ev_comps) for a in MYTHIC_PANEL
    }

    # Scale to 0-100
    per_archetype = {name: round(val * 100, 1)
                     for name, val in per_archetype_raw.items()}

    fitness_vals = list(per_archetype_raw.values())
    consensus = round(sum(fitness_vals) / len(fitness_vals) * 100, 1)
    variance = round(math.sqrt(
        sum((v - sum(fitness_vals) / len(fitness_vals)) ** 2
            for v in fitness_vals) / len(fitness_vals)
    ) * 100, 1)

    # Curve distribution
    non_lands = [s for s in scores.values() if not s.profile.is_land]
    curve_dist: Dict[str, int] = {"1": 0, "2": 0, "3": 0, "4": 0, "5+": 0}
    for sc in non_lands:
        cmc = int(sc.profile.cmc)
        key = str(min(cmc, 4)) if cmc <= 4 else "5+"
        if key not in curve_dist:
            key = "5+"
        curve_dist[key] = curve_dist.get(key, 0) + sc.qty

    # Top cards by composite score
    sorted_cards = sorted(
        [(n, s) for n, s in scores.items() if not s.profile.is_land],
        key=lambda x: x[1].composite_score,
        reverse=True,
    )
    top_cards = [
        {"card": n, "score": round(s.composite_score, 2), "role": s.role.value}
        for n, s in sorted_cards[:10]
    ]

    # Active bottlenecks (only True ones)
    active_bottlenecks = [k for k, v in bottlenecks.items()
                          if not k.startswith("_") and v]

    return {
        "ev": round(compute_ev(scores) * 100, 1),
        "panel_scores": per_archetype,
        "consensus": consensus,
        "variance": variance,
        "bottlenecks": bottlenecks,
        "active_bottlenecks": active_bottlenecks,
        "top_cards": top_cards,
        "recommendations": recs,
        "curve": {
            "avg_cmc": ev_comps["avg_cmc"],
            "distribution": curve_dist,
        },
        "ev_components": {k: v for k, v in ev_comps.items()
                          if k not in ("pool_size", "isolated_count", "avg_cmc")},
        "pool_size": ev_comps["pool_size"],
        "isolated_count": ev_comps["isolated_count"],
    }


# ═══════════════════════════════════════════════════════════════════════════
# Markdown report formatter
# ═══════════════════════════════════════════════════════════════════════════

def format_panel_report_markdown(result: Dict[str, object], deck_name: str = "") -> str:
    """Format panel result as a markdown section suitable for appending to synergy_report.md."""
    lines = []
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## 🎯 10-Mythic Panel Evaluation")
    if deck_name:
        lines.append(f"**Deck:** {deck_name}")
    lines.append("")
    lines.append(f"**Overall EV:** {result['ev']}/100  ")
    lines.append(f"**Panel Consensus:** {result['consensus']}/100  ")
    lines.append(f"**Panel Variance:** ±{result['variance']} "
                 f"({'polarizing' if result['variance'] > 15 else 'consistent'})")
    lines.append("")

    lines.append("### Archetype Scores")
    lines.append("")
    lines.append("| Archetype | Score | Description |")
    lines.append("|-----------|------:|-------------|")
    for a in MYTHIC_PANEL:
        score = result["panel_scores"][a.name]
        bar = "█" * int(score / 10) + "░" * (10 - int(score / 10))
        lines.append(f"| **{a.name}** | {score} | {a.description} |")
    lines.append("")

    lines.append("### EV Components")
    lines.append("")
    lines.append("| Component | Score |")
    lines.append("|-----------|------:|")
    for k, v in result["ev_components"].items():
        lines.append(f"| {k.replace('_', ' ').title()} | {v:.3f} |")
    lines.append("")

    if result["active_bottlenecks"]:
        lines.append("### ⚠️ Bottlenecks Detected")
        lines.append("")
        for b in result["active_bottlenecks"]:
            lines.append(f"- `{b.replace('_', ' ').title()}`")
        lines.append("")

    lines.append("### Mana Curve")
    lines.append("")
    lines.append(f"**Avg CMC:** {result['curve']['avg_cmc']}")
    lines.append("")
    lines.append("| CMC | Count |")
    lines.append("|-----|------:|")
    for cmc, count in result["curve"]["distribution"].items():
        lines.append(f"| {cmc} | {count} |")
    lines.append("")

    lines.append("### Top 10 Cards by Synergy Score")
    lines.append("")
    lines.append("| Card | Score | Role |")
    lines.append("|------|------:|------|")
    for card in result["top_cards"]:
        lines.append(f"| {card['card']} | {card['score']} | {card['role']} |")
    lines.append("")

    if result["recommendations"]:
        lines.append("### Recommendations")
        lines.append("")
        for rec in result["recommendations"]:
            action_icon = "✂️" if rec["action"] == "cut" else "➕"
            lines.append(f"- {action_icon} **{rec['action'].upper()}** "
                         f"`{rec['card']}` (score: {rec['score']}) — {rec['reason']}")
        lines.append("")

    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════════
# CLI entry point
# ═══════════════════════════════════════════════════════════════════════════

def _cli() -> None:
    import argparse

    p = argparse.ArgumentParser(
        description="10-Mythic Panel deck evaluation.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument("input_file", help="session.md, decklist.txt, or pool CSV")
    p.add_argument("--tribe", default="", help="Tribe name for tribal evaluation")
    p.add_argument("--archetypes", nargs="+", default=[],
                   metavar="ARCH",
                   help="Declared archetypes for dynamic constraint thresholds "
                        "(e.g. --archetypes lifegain aristocrats control)")
    p.add_argument("--json", action="store_true", dest="output_json",
                   help="Output JSON instead of markdown")
    p.add_argument("--output", default="", help="Write to file instead of stdout")
    args = p.parse_args()

    input_path = Path(args.input_file)
    if not input_path.exists():
        print(f"ERROR: {input_path} not found.", file=sys.stderr)
        sys.exit(2)

    # Import here to avoid circular imports at module level
    from synergy_engine import (
        load_cards_from_db,
        score_pairwise,
        extract_names_from_session,
        extract_names_from_decklist,
        extract_deck_entries_from_decklist,
        attach_card_data,
    )
    from mtg_utils import RepoPaths

    content = input_path.read_text(encoding="utf-8") if input_path.is_file() else ""

    # Detect format
    if "session.md" in input_path.name.lower() or "# Deck Building Session" in content:
        names = extract_names_from_session(content)
        entries = [{"name": n, "qty": 1, "section": "pool"} for n in names]
    elif "Deck\n" in content or content.strip().startswith("Deck"):
        entries = extract_deck_entries_from_decklist(input_path)
    else:
        names = [l.strip() for l in content.splitlines() if l.strip()]
        entries = [{"name": n, "qty": 1, "section": "pool"} for n in names]

    if not entries:
        print("ERROR: No cards extracted from input.", file=sys.stderr)
        sys.exit(2)

    paths = RepoPaths()
    unique_names = list({e["name"] for e in entries})
    card_data = load_cards_from_db(unique_names, paths)
    annotated, _ = attach_card_data(entries, card_data)

    print(f"Loaded {len(unique_names)} cards, scoring...", file=sys.stderr)
    scores = score_pairwise(annotated)

    tribe = args.tribe.strip() or None
    result = run_panel(scores, tribe=tribe, archetypes=args.archetypes or [])
    deck_name = input_path.stem

    if args.output_json:
        output = json.dumps(result, indent=2, default=str)
    else:
        output = format_panel_report_markdown(result, deck_name=deck_name)

    if args.output:
        Path(args.output).write_text(output, encoding="utf-8")
        print(f"Panel report written to {args.output}", file=sys.stderr)
    else:
        print(output)

    sys.exit(0)


if __name__ == "__main__":
    _cli()
