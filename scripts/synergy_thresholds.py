"""
Synergy Thresholds — threshold calibration and pass/fail checking for the
synergy analysis system.

This module extracts the threshold-checking logic from ``synergy_analysis.py``
into a standalone, testable unit.  It returns structured :class:`ThresholdResult`
dataclasses instead of plain strings, while :func:`format_threshold_result` and
:func:`format_threshold_results` provide backward-compatible string rendering.

Pipeline position::

    synergy_types.py        ← enums, dataclasses, constants
    synergy_engine.py       ← pairwise scoring engine
    synergy_thresholds.py   ← YOU ARE HERE (threshold calibration & checking)
"""

from __future__ import annotations

from typing import Dict, List, Tuple

from synergy_types import (
    CardRole,
    CardScore,
    ThresholdConfig,
    ThresholdResult,
    ThresholdStatus,
    DECK_THRESHOLDS,
    POOL_THRESHOLDS,
)

__all__ = [
    "get_thresholds",
    "check_thresholds",
    "format_threshold_result",
    "format_threshold_results",
]


# ═══════════════════════════════════════════════════════════════════════════════
# Threshold selection
# ═══════════════════════════════════════════════════════════════════════════════

def get_thresholds(pool_size: int, mode: str = "auto") -> ThresholdConfig:
    """Return the appropriate :class:`ThresholdConfig` for the given pool size.

    Parameters
    ----------
    pool_size:
        Number of non-land cards in the pool / deck.
    mode:
        ``"auto"`` (default) selects ``"pool"`` when *pool_size* > 40,
        otherwise ``"deck"``.  Pass ``"deck"`` or ``"pool"`` to force a
        specific calibration.

    Returns
    -------
    ThresholdConfig
        The preset threshold configuration for the resolved mode.
    """
    if mode == "auto":
        mode = "pool" if pool_size > 40 else "deck"
    if mode == "deck":
        return DECK_THRESHOLDS
    return POOL_THRESHOLDS


# ═══════════════════════════════════════════════════════════════════════════════
# Threshold checking
# ═══════════════════════════════════════════════════════════════════════════════

_ENGINE_ROLES = frozenset({CardRole.ENGINE, CardRole.ENABLER, CardRole.PAYOFF})
_SUPPORT_ROLES = frozenset({CardRole.SUPPORT, CardRole.INTERACTION})


def check_thresholds(
    scores: Dict[str, CardScore],
    mode: str = "auto",
) -> Tuple[bool, List[ThresholdResult]]:
    """Run all Gate-2.5 threshold checks against scored card data.

    Parameters
    ----------
    scores:
        Mapping of card name → :class:`CardScore` produced by the scoring
        engine.
    mode:
        Threshold calibration mode (``"auto"``, ``"deck"``, or ``"pool"``).

    Returns
    -------
    tuple[bool, list[ThresholdResult]]
        A *(passed, results)* pair.  *passed* is ``True`` only when every
        non-INFO check meets its threshold.  *results* is the ordered list
        of structured :class:`ThresholdResult` records.
    """
    results: List[ThresholdResult] = []
    passed = True

    if not scores:
        results.append(ThresholdResult(
            id="T0",
            status=ThresholdStatus.FAIL,
            label="No cards",
            actual=0.0,
            required=1.0,
            detail="No cards to evaluate.",
        ))
        return False, results

    pool_size = len(scores)
    dt = get_thresholds(pool_size, mode)

    # ── Pre-compute shared aggregates ────────────────────────────────────
    densities = [s.synergy_density for s in scores.values()]
    avg_density = sum(densities) / len(densities)

    engine_scores = [s for s in scores.values() if s.role in _ENGINE_ROLES]
    engine_densities = [s.engine_density for s in engine_scores]
    engine_avg = (
        sum(engine_densities) / len(engine_densities)
        if engine_densities
        else 0.0
    )

    support_count = sum(1 for s in scores.values() if s.role in _SUPPORT_ROLES)
    support_ratio = support_count / max(pool_size, 1)

    # ── T1 — Average Synergy Density ────────────────────────────────────
    if avg_density >= dt.min_avg_density:
        results.append(ThresholdResult(
            id="T1",
            status=ThresholdStatus.PASS,
            label="Avg Synergy Density",
            actual=avg_density,
            required=dt.min_avg_density,
            detail=(
                f"T1: Avg Synergy Density = {avg_density:.1%} "
                f"(≥ {dt.min_avg_density:.0%})"
            ),
        ))
    else:
        results.append(ThresholdResult(
            id="T1",
            status=ThresholdStatus.FAIL,
            label="Avg Synergy Density",
            actual=avg_density,
            required=dt.min_avg_density,
            detail=(
                f"T1: Avg Synergy Density = {avg_density:.1%} "
                f"(need ≥ {dt.min_avg_density:.0%})"
            ),
        ))
        passed = False

    # ── T1b — Average Engine Density ────────────────────────────────────
    if engine_avg >= dt.min_engine_avg_density:
        results.append(ThresholdResult(
            id="T1b",
            status=ThresholdStatus.PASS,
            label="Avg Engine Density",
            actual=engine_avg,
            required=dt.min_engine_avg_density,
            detail=(
                f"T1b: Avg Engine Density = {engine_avg:.1%} "
                f"(≥ {dt.min_engine_avg_density:.0%})"
            ),
        ))
    else:
        results.append(ThresholdResult(
            id="T1b",
            status=ThresholdStatus.FAIL,
            label="Avg Engine Density",
            actual=engine_avg,
            required=dt.min_engine_avg_density,
            detail=(
                f"T1b: Avg Engine Density = {engine_avg:.1%} "
                f"(need ≥ {dt.min_engine_avg_density:.0%})"
            ),
        ))
        passed = False

    # ── T2 — Truly Isolated Engine Cards ────────────────────────────────
    true_isolated = [
        name for name, s in scores.items()
        if s.role in _ENGINE_ROLES and s.engine_density <= 0.10
    ]
    if len(true_isolated) <= dt.max_true_isolated_engine:
        results.append(ThresholdResult(
            id="T2",
            status=ThresholdStatus.PASS,
            label="Truly Isolated Engine Cards",
            actual=float(len(true_isolated)),
            required=float(dt.max_true_isolated_engine),
            detail=(
                f"T2: {len(true_isolated)} truly isolated engine/payoff cards "
                f"(≤ {dt.max_true_isolated_engine})"
            ),
        ))
    else:
        names_preview = ", ".join(true_isolated[:6])
        ellipsis = "..." if len(true_isolated) > 6 else ""
        results.append(ThresholdResult(
            id="T2",
            status=ThresholdStatus.FAIL,
            label="Truly Isolated Engine Cards",
            actual=float(len(true_isolated)),
            required=float(dt.max_true_isolated_engine),
            detail=(
                f"T2: {len(true_isolated)} truly isolated engine/payoff cards "
                f"(max {dt.max_true_isolated_engine}): "
                f"{names_preview}{ellipsis}"
            ),
        ))
        passed = False

    # ── T2b — Low-connectivity support cards (INFO only) ────────────────
    isolated_all = [
        name for name, s in scores.items() if s.synergy_density <= 0.05
    ]
    support_iso = [
        n for n in isolated_all if scores[n].role in _SUPPORT_ROLES
    ]
    if support_iso:
        names_preview = ", ".join(support_iso[:6])
        results.append(ThresholdResult(
            id="T2b",
            status=ThresholdStatus.INFO,
            label="Low-connectivity Support Cards",
            actual=float(len(support_iso)),
            required=0.0,
            detail=(
                f"T2b: {len(support_iso)} low-connectivity support/interaction "
                f"cards (not counted against T2): {names_preview}"
            ),
        ))

    # ── T3 — Hub Cards ──────────────────────────────────────────────────
    hubs = [
        name for name, s in scores.items()
        if s.synergy_density >= dt.min_hub_density
    ]
    if len(hubs) >= dt.min_hub_count:
        names_preview = ", ".join(hubs[:5])
        ellipsis = "..." if len(hubs) > 5 else ""
        results.append(ThresholdResult(
            id="T3",
            status=ThresholdStatus.PASS,
            label="Hub Cards",
            actual=float(len(hubs)),
            required=float(dt.min_hub_count),
            detail=(
                f"T3: {len(hubs)} hub cards "
                f"(density ≥ {dt.min_hub_density:.0%}): "
                f"{names_preview}{ellipsis}"
            ),
        ))
    else:
        results.append(ThresholdResult(
            id="T3",
            status=ThresholdStatus.FAIL,
            label="Hub Cards",
            actual=float(len(hubs)),
            required=float(dt.min_hub_count),
            detail=(
                f"T3: Only {len(hubs)} hub card(s) with density "
                f"≥ {dt.min_hub_density:.0%} (need {dt.min_hub_count}+)"
            ),
        ))
        passed = False

    # ── T3b — Support/Interaction Ratio ─────────────────────────────────
    if support_ratio <= dt.max_support_ratio:
        results.append(ThresholdResult(
            id="T3b",
            status=ThresholdStatus.PASS,
            label="Support/Interaction Ratio",
            actual=support_ratio,
            required=dt.max_support_ratio,
            detail=(
                f"T3b: Support/interaction ratio = {support_ratio:.1%} "
                f"(≤ {dt.max_support_ratio:.0%})"
            ),
        ))
    else:
        results.append(ThresholdResult(
            id="T3b",
            status=ThresholdStatus.FAIL,
            label="Support/Interaction Ratio",
            actual=support_ratio,
            required=dt.max_support_ratio,
            detail=(
                f"T3b: Support/interaction ratio = {support_ratio:.1%} "
                f"(too high — max {dt.max_support_ratio:.0%})"
            ),
        ))
        passed = False

    # ── T4 — High Dependency ────────────────────────────────────────────
    high_dep = [
        (name, s.dependency)
        for name, s in scores.items()
        if s.dependency >= 3
    ]
    if not high_dep:
        results.append(ThresholdResult(
            id="T4",
            status=ThresholdStatus.PASS,
            label="High Dependency",
            actual=0.0,
            required=0.0,
            detail="T4: No cards with Dependency ≥ 3",
        ))
    else:
        dep_strs = ", ".join(f"{n} (dep={d})" for n, d in high_dep)
        results.append(ThresholdResult(
            id="T4",
            status=ThresholdStatus.FAIL,
            label="High Dependency",
            actual=float(len(high_dep)),
            required=0.0,
            detail=f"T4: High-dependency cards found: {dep_strs}",
        ))
        passed = False

    # ── T5 — Oracle Confirmation Rate (INFO only) ───────────────────────
    oracle_confirmed = sum(len(s.oracle_interactions) for s in scores.values())
    total_interactions = sum(s.synergy_count for s in scores.values())
    pct = oracle_confirmed / max(total_interactions, 1)
    results.append(ThresholdResult(
        id="T5",
        status=ThresholdStatus.INFO,
        label="Oracle Confirmation Rate",
        actual=pct,
        required=0.0,
        detail=(
            f"T5: {oracle_confirmed} oracle-confirmed interactions "
            f"({pct:.0%} of total) — remainder are tag-inferred"
        ),
    ))

    return passed, results


# ═══════════════════════════════════════════════════════════════════════════════
# Formatting helpers (backward compatibility)
# ═══════════════════════════════════════════════════════════════════════════════

def format_threshold_result(result: ThresholdResult) -> str:
    """Render a single :class:`ThresholdResult` as a legacy ``[STATUS] …`` string.

    Parameters
    ----------
    result:
        The structured threshold result to format.

    Returns
    -------
    str
        A string in the form ``[PASS] T1: Avg Synergy Density = …``.
    """
    return f"[{result.status.value}] {result.detail}"


def format_threshold_results(results: List[ThresholdResult]) -> List[str]:
    """Render all :class:`ThresholdResult` records as legacy strings.

    Parameters
    ----------
    results:
        Ordered list of threshold results from :func:`check_thresholds`.

    Returns
    -------
    list[str]
        One formatted string per result, suitable for direct printing or
        inclusion in a Markdown report.
    """
    return [format_threshold_result(r) for r in results]
