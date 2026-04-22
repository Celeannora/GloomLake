"""
Synergy Report — Gate 2.5 report generation for the MTG-Decks synergy
analysis system.

Pipeline position::

    synergy_types.py        ← enums, dataclasses, constants
    synergy_engine.py       ← pairwise scoring engine
    synergy_thresholds.py   ← threshold calibration & checking
    synergy_report.py       ← YOU ARE HERE (report generation)
"""
from __future__ import annotations

import csv
import io
import json
import random
from collections import defaultdict, deque
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Tuple

from synergy_types import (
    InteractionType, CardRole, CardScore, ThresholdResult, ThresholdStatus,
    ThresholdConfig, ROLE_TAGS, Interaction, DECK_THRESHOLDS, POOL_THRESHOLDS,
    CompositeWeights,
)
from synergy_thresholds import get_thresholds

__all__ = ["build_markdown_report", "build_json_report", "build_top_n_csv", "stochastic_ranking"]

# ── Constants ────────────────────────────────────────────────────────────────
_ENGINE_ROLES = frozenset({CardRole.ENGINE, CardRole.ENABLER, CardRole.PAYOFF})
_SUPPORT_ROLES = frozenset({CardRole.SUPPORT, CardRole.INTERACTION})
_ROLE_ORDER = [CardRole.ENGINE, CardRole.ENABLER, CardRole.PAYOFF,
               CardRole.SUPPORT, CardRole.INTERACTION]
_ITYPE_LETTER = {
    InteractionType.FEEDS: "F", InteractionType.TRIGGERS: "T",
    InteractionType.ENABLES: "E", InteractionType.AMPLIFIES: "A",
    InteractionType.PROTECTS: "P", InteractionType.REDUNDANT: "R",
}
_TOP_COLS = [
    "rank", "name", "qty", "role", "mana_cost", "cmc", "type_line",
    "colors", "rarity", "keywords", "oracle_text", "tags", "pool",
    "engine_score", "engine_density", "synergy_score", "weighted_score",
    "raw_synergy", "synergy_density", "role_breadth",
    "oracle_interactions", "dependency", "top_partners",
]


def stochastic_ranking(
    scores: Dict[str, CardScore],
    temperature: float = 0.0,
    seed: Optional[int] = None,
    weights: Optional[CompositeWeights] = None,
) -> List[Tuple[str, CardScore]]:
    """
    Apply temperature-based stochastic ranking to CardScore dict.

    Parameters
    ----------
    scores : Dict[str, CardScore]
        Mapping of card name to CardScore instances
    temperature : float
        Variation factor (0.0 = deterministic, 0.1 = high variation)
    seed : Optional[int]
        Random seed for reproducibility
    weights : Optional[CompositeWeights]
        Custom weights for composite score; if None, uses default weights.

    Returns
    -------
    List[Tuple[str, CardScore]]
        Ranked (name, score) pairs
    """
    if seed is not None:
        random.seed(seed)

    if temperature <= 0.0:
        # Fast path: deterministic sorting
        if weights is None:
            return sorted(scores.items(), key=lambda x: -x[1].composite_score)
        else:
            return sorted(scores.items(), key=lambda x: -x[1].composite_score_with(weights))

    ranked = []
    for name, score in scores.items():
        base = score.composite_score_with(weights) if weights else score.composite_score
        if base <= 0:
            noise = 0.0
        else:
            # Gaussian noise with stddev proportional to score and temperature
            stddev = temperature * base
            noise = random.gauss(0.0, stddev)
        adjusted = base + noise
        ranked.append((name, score, adjusted))

    # Sort by adjusted score (descending)
    ranked.sort(key=lambda x: -x[2])
    return [(name, score) for name, score, _ in ranked]


# ═════════════════════════════════════════════════════════════════════════════
# Private helpers
# ═════════════════════════════════════════════════════════════════════════════

def _earliest_chain_turn(chain_cards: List[Any],
                         land_count: int = 24, deck_size: int = 60) -> int:
    """Earliest turn a chain can fire based on max CMC among its cards."""
    if not chain_cards:
        return 0
    cmcs: List[float] = []
    for c in chain_cards:
        if hasattr(c, "profile"):
            cmcs.append(float(c.profile.cmc or 0))
        elif hasattr(c, "cmc"):
            cmcs.append(float(c.cmc or 0))
        else:
            cmcs.append(0.0)
    return max(1, int(max(cmcs))) if cmcs else 1


def _find_synergy_chains(scores: Dict[str, CardScore],
                         max_chains: int = 3) -> List[Dict[str, Any]]:
    """Greedy synergy chain detection (max depth 5, top-K branching).

    Uses a greedy best-first search instead of exhaustive BFS to avoid
    combinatorial explosion on large pools (1000+ cards).  At each depth
    level only the top *_CHAIN_BRANCH* neighbours (by composite score,
    oracle-confirmed edges first) are explored.
    """
    _CHAIN_BRANCH = 3          # max neighbours to explore per node
    _MAX_QUEUE    = 5_000      # safety cap on BFS queue size

    if not scores:
        return []
    graph: Dict[str, Dict[str, Tuple[InteractionType, str]]] = defaultdict(dict)
    oracle_edges: Set[frozenset] = set()
    for name, sc in scores.items():
        for ix in sc.interactions:
            if ix.itype == InteractionType.REDUNDANT or ix.partner not in scores:
                continue
            graph[name][ix.partner] = (ix.itype, ix.confidence)
            if ix.confidence == "oracle":
                oracle_edges.add(frozenset([name, ix.partner]))
    hubs = sorted(scores.keys(),
                  key=lambda n: (scores[n].synergy_density,
                                 scores[n].composite_score), reverse=True)
    chains: List[Dict[str, Any]] = []
    used: Set[str] = set()
    for hub in hubs:
        if hub in used or not graph.get(hub):
            continue
        best: List[str] = [hub]
        q: deque = deque([[hub]])
        while q:
            cur = q.popleft()
            if len(cur) > len(best):
                best = cur
            if len(cur) >= 5:
                continue
            last = cur[-1]
            # Only follow the top-K best neighbours (greedy pruning)
            neighbours = sorted(
                graph.get(last, {}).keys(),
                key=lambda n: (
                    0 if frozenset([last, n]) in oracle_edges else 1,
                    -scores[n].composite_score if n in scores else 0,
                ),
            )
            for nb in neighbours[:_CHAIN_BRANCH]:
                if nb not in cur:
                    q.append(cur + [nb])
            if len(q) > _MAX_QUEUE:
                break
        if len(best) >= 2:
            has_oracle = any(frozenset([best[i], best[i+1]]) in oracle_edges
                            for i in range(len(best)-1))
            chains.append({
                "anchor": hub, "path": best,
                "earliest_turn": _earliest_chain_turn(
                    [scores[n] for n in best if n in scores]),
                "oracle_confirmed": has_oracle,
            })
            used.add(hub)
        if len(chains) >= max_chains:
            break
    return chains


def _build_synergy_matrix(scores: Dict[str, CardScore],
                          top_n: int = 10) -> str:
    """ASCII synergy matrix for the top N cards by composite score."""
    if not scores:
        return ""
    top = sorted(scores.items(), key=lambda x: -x[1].composite_score)[:top_n]
    names = [n for n, _ in top]
    if len(names) < 2:
        return ""
    top_set = set(names)
    imap: Dict[Tuple[str, str], str] = {}
    for name in names:
        for ix in scores[name].interactions:
            if ix.partner in top_set:
                imap[(name, ix.partner)] = _ITYPE_LETTER.get(ix.itype, "?")
    dn = [n[:14] for n in names]
    cw = max(len(d) for d in dn) + 1
    lines = ["## Synergy Matrix (Top 10 by Composite)", ""]
    hdr = "| " + " " * cw + " |"
    for d in dn:
        hdr += f" {d:^{cw}} |"
    lines.append(hdr)
    sep = "|:" + "-" * cw + "|"
    for _ in dn:
        sep += f":{'-' * cw}:|"
    lines.append(sep)
    for i, (na, da) in enumerate(zip(names, dn)):
        row = f"| {da:<{cw}}|"
        for j, nb in enumerate(names):
            cell = "—" if i == j else imap.get((na, nb), "")
            row += f" {cell:^{cw}} |"
        lines.append(row)
    lines += ["", "Legend: F=FEEDS T=TRIGGERS E=ENABLES A=AMPLIFIES P=PROTECTS R=REDUNDANT", ""]
    return "\n".join(lines)


def _build_role_distribution(scores: Dict[str, CardScore]) -> str:
    """Role distribution summary table."""
    if not scores:
        return ""
    total = len(scores)
    counts: Dict[CardRole, int] = defaultdict(int)
    for sc in scores.values():
        counts[sc.role] += 1
    lines = ["## Role Distribution", "", "| Role | Count | % |", "|------|:-----:|:-:|"]
    for role in _ROLE_ORDER:
        c = counts.get(role, 0)
        lines.append(f"| {role.value.title()} | {c} | {round(100*c/max(total,1))}% |")
    lines.append("")
    return "\n".join(lines)


def _collect_redundant_pairs(scores: Dict[str, CardScore]) -> List[Tuple[str, str, Set[str]]]:
    """Deduplicate and collect redundant pairs with shared roles."""
    seen: Set[frozenset] = set()
    pairs: List[Tuple[str, str, Set[str]]] = []
    for name, sc in scores.items():
        for partner in sc.redundant_with:
            pk = frozenset([name, partner])
            if pk not in seen and partner in scores:
                seen.add(pk)
                shared = set(sc.profile.broad_tags) & set(scores[partner].profile.broad_tags) & ROLE_TAGS
                pairs.append((name, partner, shared))
    return pairs


# ═════════════════════════════════════════════════════════════════════════════
# Public: Markdown report
# ═════════════════════════════════════════════════════════════════════════════

def build_markdown_report(
    scores: Dict[str, CardScore],
    threshold_results: List[ThresholdResult],
    all_passed: bool,
    source_file: str,
    not_found: List[str],
    mode: str = "auto",
    inconclusive: bool = False,
) -> str:
    """Generate the Gate 2.5 Markdown synergy evaluation report."""
    L: List[str] = [
        "# Gate 2.5: Synergy Evaluation", "",
        f"> Auto-generated by `scripts/synergy_analysis.py` from `{source_file}`",
        "> Interaction confidence: **oracle** = verified against card text · **tag** = tag-pair rule",
        "> Lands excluded from scoring. Role-aware: engine/enabler/payoff cards drive thresholds.",
        "> **Scoring: density-first composite** — cards ranked by how well they work with THIS pool,",
        "> not by generic power level.", "", "---", "",
    ]

    # ── Synergy Scores (grouped by role) ─────────────────────────────────
    sorted_cards = sorted(scores.items(), key=lambda x: -x[1].composite_score)
    role_groups: Dict[CardRole, List[Tuple[str, CardScore]]] = defaultdict(list)
    for name, sc in sorted_cards:
        role_groups[sc.role].append((name, sc))

    TH = ("| Card | Qty | Role | Source Tags | Payoff Tags "
          "| Engine (Density) | Composite | Raw | Dep | Oracle | Key Partners |")
    TS = ("|------|:---:|------|------------|------------|"
          ":----------------:|:---------:|:---:|:---:|:------:|-------------|")

    L += ["## Synergy Scores", ""]
    for role in _ROLE_ORDER:
        grp = role_groups.get(role, [])
        if not grp:
            continue
        L += [f"### {role.value.title()}", "", TH, TS]
        for name, sc in grp:
            p = sc.profile
            src = ", ".join(sorted(p.source_tags)) or "—"
            pay = ", ".join(sorted(p.payoff_tags)) or "—"
            eng = f"{sc.engine_synergy_count} ({sc.engine_density:.0%})"
            pts = sorted(sc.synergy_partners)[:3]
            pstr = ", ".join(pts) + ("…" if len(sc.synergy_partners) > 3 else "")
            L.append(
                f"| {name} | {sc.qty} | {sc.role.value} | {src} | {pay} "
                f"| {eng} | {sc.composite_score:.1f} | {sc.weighted_synergy:.1f} "
                f"| {sc.dependency} | {len(sc.oracle_interactions)} | {pstr or '—'} |")
        L.append("")

    # ── Not-found note ───────────────────────────────────────────────────
    if not_found:
        L += [f"> **Note:** {len(not_found)} card(s) not in local database — excluded from scoring:",
              f"> {', '.join(not_found[:10])}{'...' if len(not_found) > 10 else ''}", ""]

    # ── Pool statistics ──────────────────────────────────────────────────
    pool_size = len(scores)
    dt = get_thresholds(pool_size, mode)
    densities = [s.synergy_density for s in scores.values()]
    avg_d = sum(densities) / len(densities) if densities else 0.0
    eng_sc = [s for s in scores.values() if s.role in _ENGINE_ROLES]
    eng_avg = sum(s.engine_density for s in eng_sc) / max(len(eng_sc), 1)
    hubs = [n for n, s in scores.items() if s.synergy_density >= dt.min_hub_density]
    oracle_tot = sum(len(s.oracle_interactions) for s in scores.values())
    sup_n = sum(1 for s in scores.values() if s.role in _SUPPORT_ROLES)

    L += [
        f"**Pool size (non-land):** {pool_size}  |  **Mode:** {dt.mode_label}",
        f"**Engine/enabler/payoff:** {len(eng_sc)}  |  **Support/interaction:** {sup_n}",
        f"**Avg Density:** {avg_d:.1%} (threshold ≥ {dt.min_avg_density:.0%})",
        f"**Avg Engine Density:** {eng_avg:.1%} (threshold ≥ {dt.min_engine_avg_density:.0%})",
        f"**Hub cards (density ≥ {dt.min_hub_density:.0%}):** {len(hubs)} (min {dt.min_hub_count})",
        f"**Oracle-confirmed interactions:** {oracle_tot}", "", "---", "",
    ]

    # ── Role Distribution ────────────────────────────────────────────────
    L.append(_build_role_distribution(scores))

    # ── Synergy Matrix ───────────────────────────────────────────────────
    mx = _build_synergy_matrix(scores, top_n=10)
    if mx:
        L += ["---", "", mx]

    # ── Threshold Check ──────────────────────────────────────────────────
    L += ["---", "", "## Gate 2.5 Threshold Check", ""]
    for tr in threshold_results:
        if tr.status == ThresholdStatus.PASS:
            pfx = "- [x] [PASS]"
        elif tr.status == ThresholdStatus.FAIL:
            pfx = "- [ ] [FAIL]"
        elif tr.status == ThresholdStatus.WARN:
            pfx = "- ⚠️ [WARN]"
        else:
            pfx = "- ℹ️ [INFO]"
        L.append(f"{pfx} {tr.detail}")

    # ── Verdict ──────────────────────────────────────────────────────────
    if inconclusive:
        verdict = "**⚠️ Result is INCONCLUSIVE — missing maindeck card data prevented a reliable verdict.**"
    elif all_passed:
        verdict = "**✅ All thresholds passed — proceed to Gate 3.**"
    else:
        verdict = "**❌ Cohesion thresholds failed — revisit maindeck engine/support balance before Gate 3.**"
    L += ["", verdict, ""]

    # ── Oracle-Confirmed Interactions ────────────────────────────────────
    opairs: List[Tuple[str, str, str, str]] = []
    for name, sc in sorted_cards:
        for ix in sc.interactions:
            if ix.confidence == "oracle":
                opairs.append((name, ix.partner, ix.itype.value, ix.note))
    if opairs:
        L += ["---", "", "## Oracle-Confirmed Interactions", "",
              "> These interactions were verified against actual card text — highest confidence.", "",
              "| Card A | Card B | Type | Evidence |", "|--------|--------|------|----------|"]
        seen_o: Set[frozenset] = set()
        for na, pa, it, nt in opairs[:30]:
            pk = frozenset([na, pa])
            if pk not in seen_o:
                seen_o.add(pk)
                L.append(f"| {na} | {pa} | {it} | {nt} |")
        L.append("")

    # ── Redundant Pairs ──────────────────────────────────────────────────
    rpairs = _collect_redundant_pairs(scores)
    if rpairs:
        L += ["---", "", "## Redundant Pairs", "",
              "| Card A | Card B | Shared Role | CMC Brackets | Justification for Both |",
              "|--------|--------|-------------|:------------:|------------------------|"]
        for a, b, roles in rpairs[:20]:
            rs = ", ".join(sorted(roles)) if roles else "same role"
            L.append(f"| {a} | {b} | {rs} | {scores[a].profile.cmc}/{scores[b].profile.cmc} | *(fill in)* |")
        L.append("")

    # ── Synergy Chains ───────────────────────────────────────────────────
    L += ["---", "", "## Synergy Chains", "",
          "> Auto-detected chains using hub cards as anchors. Prefer oracle-confirmed interactions.",
          "> Format: [Card A] → [what A produces] → [Card B] → [outcome]", ""]
    chains = _find_synergy_chains(scores, max_chains=3)
    ctiming: List[Tuple[int, int]] = []
    if chains:
        for i, ch in enumerate(chains, 1):
            cstr = " → ".join(f"[{c}]" for c in ch["path"])
            olab = " ⭐oracle" if ch["oracle_confirmed"] else ""
            et = ch["earliest_turn"]
            ctiming.append((i, et))
            tlab = "⚠️ SLOW" if et >= 5 else "✅ ON CURVE"
            L += [f"**Chain {i} — [{ch['anchor']} engine]{olab}:**",
                  cstr + " → [outcome]",
                  f"Earliest firing turn: T{et} (CMC-based, no ramp modeled) — {tlab}"]
            if et >= 5:
                L.append("⚠️ SLOW CHAIN: Requires T5+ to fully assemble. Verify against meta kill turn.")
            L += ["Redundancy: *(fill in)*", "Minimum pieces to function: N of M", ""]
    else:
        L += ["**Chain 1:**", "[Card A] → [output] → [Card B] → [outcome]",
              "Redundancy: *(fill in)*", "Minimum pieces to function: N of M", ""]
    slow = [c for c in ctiming if c[1] >= 5]
    if len(slow) > 1:
        L += [f"> ⚠️ **T6:** {len(slow)} synergy chains require T5+ to assemble. "
              "Consider adding ramp or lower-CMC redundancy.", ""]

    # ── Checklist ────────────────────────────────────────────────────────
    def _tp(tid: str) -> bool:
        return any(t.id == tid and t.status == ThresholdStatus.PASS for t in threshold_results)

    L += ["---", "", "## Gate 2.5 Checklist", "",
          f"- [{'x' if all_passed else ' '}] All candidates scored (Synergy Count, Role Breadth, Dependency)",
          f"- [{'x' if _tp('T1') else ' '}] Avg Synergy Density ≥ {dt.min_avg_density:.0%}",
          f"- [{'x' if _tp('T1b') else ' '}] Avg Engine Density ≥ {dt.min_engine_avg_density:.0%}",
          f"- [{'x' if _tp('T2') else ' '}] ≤ {dt.max_true_isolated_engine} true isolated engine cards",
          f"- [{'x' if len(hubs) >= dt.min_hub_count else ' '}] ≥ {dt.min_hub_count} hub cards",
          f"- [{'x' if _tp('T4') else ' '}] No card with Dependency ≥ 3",
          "- [ ] All REDUNDANT pairs justified  *(fill in above)*",
          "- [ ] 2–3 synergy chains mapped  *(fill in above)*",
          "- [ ] All analysis based on Gate 1 query results — not memory", "",
          "**If any item is unchecked, do not proceed to Gate 3.**"]
    return "\n".join(L)


# ═════════════════════════════════════════════════════════════════════════════
# Public: JSON report
# ═════════════════════════════════════════════════════════════════════════════

def build_json_report(
    scores: Dict[str, CardScore],
    threshold_results: List[ThresholdResult],
    all_passed: bool,
    source_file: str,
    not_found: List[str],
    mode: str = "auto",
    inconclusive: bool = False,
) -> str:
    """Generate a JSON report for machine consumption."""
    pool_size = len(scores)
    engine_count = sum(1 for s in scores.values() if s.role in _ENGINE_ROLES)
    support_count = sum(1 for s in scores.values() if s.role in _SUPPORT_ROLES)

    # Primary axes
    ax: Dict[str, int] = defaultdict(int)
    for sc in scores.values():
        for t in sc.profile.source_tags:
            ax[t] += 1
        for t in sc.profile.payoff_tags:
            ax[t] += 1
    primary_axes = sorted([t for t, c in ax.items() if c >= 3], key=lambda t: -ax[t])

    # Per-card scores
    sd: Dict[str, Any] = {}
    for name, sc in scores.items():
        ixl: List[Dict[str, Any]] = []
        for ix in sc.interactions:
            ixl.append({"partner": ix.partner, "type": ix.itype.value,
                        "note": ix.note, "confidence": ix.confidence})
        sd[name] = {
            "role": sc.role.value, "qty": sc.qty, "section": sc.section,
            "composite_score": round(sc.composite_score, 2),
            "synergy_density": round(sc.synergy_density, 4),
            "engine_density": round(sc.engine_density, 4),
            "weighted_synergy": round(sc.weighted_synergy, 2),
            "dependency": sc.dependency,
            "synergy_count": sc.synergy_count,
            "engine_synergy_count": sc.engine_synergy_count,
            "role_breadth": sc.role_breadth,
            "oracle_interaction_count": len(sc.oracle_interactions),
            "source_tags": sorted(sc.profile.source_tags),
            "payoff_tags": sorted(sc.profile.payoff_tags),
            "partners": sorted(sc.synergy_partners),
            "interactions": ixl,
        }

    # Thresholds
    tl: List[Dict[str, Any]] = []
    for tr in threshold_results:
        tl.append({"id": tr.id, "status": tr.status.value, "label": tr.label,
                    "actual": round(tr.actual, 4), "required": round(tr.required, 4),
                    "detail": tr.detail})

    # Chains
    chains = _find_synergy_chains(scores, max_chains=3)
    cl: List[Dict[str, Any]] = []
    for ch in chains:
        cl.append({"anchor": ch["anchor"], "path": ch["path"],
                    "earliest_turn": ch["earliest_turn"],
                    "oracle_confirmed": ch["oracle_confirmed"]})

    # Redundant pairs
    rpairs = _collect_redundant_pairs(scores)
    rl: List[Dict[str, Any]] = []
    for a, b, roles in rpairs:
        rl.append({"card_a": a, "card_b": b, "shared_roles": sorted(roles)})

    report = {
        "metadata": {
            "source_file": source_file,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "mode": mode,
            "pool_size": pool_size,
            "engine_count": engine_count,
            "support_count": support_count,
        },
        "primary_axes": primary_axes,
        "scores": sd,
        "thresholds": tl,
        "chains": cl,
        "redundant_pairs": rl,
        "all_passed": all_passed,
        "inconclusive": inconclusive,
    }
    return json.dumps(report, indent=2, ensure_ascii=False)


# ═════════════════════════════════════════════════════════════════════════════
# Public: Top-N CSV export
# ═════════════════════════════════════════════════════════════════════════════

def build_top_n_csv(
    scores: Dict[str, CardScore],
    top_n: int,
    pool_data: Optional[Dict[str, Dict[str, Any]]] = None,
) -> str:
    """Generate a top-N CSV export ranked by composite synergy score.

    Extracted from ``synergy_analysis.py`` lines 1054-1118.

    Parameters
    ----------
    scores:
        Mapping of card name → :class:`CardScore`.
    top_n:
        Number of top cards to include.
    pool_data:
        Optional mapping of lowercased card name → raw pool CSV row dict.
        Used to enrich output with rarity, oracle text, etc.

    Returns
    -------
    str
        CSV content as a string.
    """
    if pool_data is None:
        pool_data = {}

    ranked = sorted(scores.items(), key=lambda x: -x[1].composite_score)[:top_n]

    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=_TOP_COLS, extrasaction="ignore")
    writer.writeheader()

    for rank_i, (name, sc) in enumerate(ranked, 1):
        pr = sc.profile
        pd_row = pool_data.get(name.lower(), {})
        oracle = pd_row.get("oracle_text", pr.oracle_text)
        writer.writerow({
            "rank": rank_i,
            "name": pr.name or name,
            "qty": sc.qty,
            "role": sc.role.value,
            "mana_cost": pr.mana_cost or pd_row.get("mana_cost", ""),
            "cmc": pr.cmc if pr.cmc else pd_row.get("cmc", ""),
            "type_line": pr.type_line or pd_row.get("type_line", ""),
            "colors": pr.colors or pd_row.get("colors", ""),
            "rarity": pd_row.get("rarity", ""),
            "keywords": ", ".join(sorted(pr.keywords)),
            "oracle_text": oracle,
            "tags": ", ".join(sorted(pr.broad_tags)),
            "pool": pd_row.get("pool", ""),
            "engine_score": sc.engine_synergy_count,
            "engine_density": f"{sc.engine_density:.1%}",
            "synergy_score": sc.synergy_count,
            "weighted_score": f"{sc.composite_score:.1f}",
            "raw_synergy": f"{sc.weighted_synergy:.1f}",
            "synergy_density": f"{sc.synergy_density:.1%}",
            "role_breadth": sc.role_breadth,
            "oracle_interactions": len(sc.oracle_interactions),
            "dependency": sc.dependency,
            "top_partners": " | ".join(sorted(sc.synergy_partners)[:5]),
        })

    return buf.getvalue()
