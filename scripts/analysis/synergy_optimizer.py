#!/usr/bin/env python3
"""
Synergy Optimizer — Karpathy-Style Autonomous Deck Optimization Loop

Iteratively improves a deck by proposing card swaps from a candidate pool
and accepting changes that improve the panel EV score. Runs autonomously
for a fixed time budget (no human in the loop).

ALGORITHM
=========
1. Load deck + candidate pool → score both with score_pairwise()
2. Compute baseline EV via run_panel()
3. Loop until time budget exhausted:
   a. Identify the N weakest cards in the current deck (by composite_score)
   b. Identify the N strongest cards in the pool not in the deck
   c. Propose one random swap from those candidates
   d. Score the new deck configuration
   e. If new_EV > best_EV: accept swap, log improvement
   f. Else: discard, try next swap
4. Output: best deck found, optimization trace, EV improvement report

DESIGN NOTES
============
- Greedy hill-climbing (not simulated annealing) — fast and interpretable
- Swap candidates drawn from worst-deck ∩ best-pool to focus search
- Each iteration rescores only the affected cards (partial rescore)
  but falls back to full rescore for accuracy
- Time budget prevents runaway loops
- Full audit trail written to optimizer_log.json

Usage:
    python scripts/analysis/synergy_optimizer.py session.md
    python scripts/analysis/synergy_optimizer.py session.md --time-budget 120
    python scripts/analysis/synergy_optimizer.py session.md --tribe Angel --top-cuts 10
    python scripts/analysis/synergy_optimizer.py session.md --deck decklist.txt
    python scripts/analysis/synergy_optimizer.py session.md --dry-run
"""

from __future__ import annotations

import json
import random
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Path setup — mirrors synergy_analysis.py
# ---------------------------------------------------------------------------
_here = Path(__file__).resolve().parent
sys.path.insert(0, str(_here))
sys.path.insert(0, str(_here.parent / "utils"))
sys.path.insert(0, str(_here.parent / "cli"))
sys.path.insert(0, str(_here.parent))

from synergy_types import CardScore, CardRole, CompositeWeights
from synergy_engine import (
    load_cards_from_db,
    score_pairwise,
    extract_names_from_session,
    extract_deck_entries_from_decklist,
    attach_card_data,
)
from mythic_framework import run_panel, compute_ev, compute_ev_components
from mtg_utils import RepoPaths


# ═══════════════════════════════════════════════════════════════════════════
# Data structures
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class SwapProposal:
    """One proposed card swap: cut one card, add another."""
    cut: str
    add: str
    cut_score: float
    add_score: float
    expected_ev_delta: float  # optimistic estimate before full rescore


@dataclass
class OptimizationStep:
    """Record of one accepted optimization step."""
    iteration: int
    swap: SwapProposal
    ev_before: float
    ev_after: float
    ev_delta: float
    elapsed_seconds: float
    panel_consensus_before: float
    panel_consensus_after: float


@dataclass
class OptimizationResult:
    """Full result of an optimization run."""
    deck_name: str
    tribe: Optional[str]
    time_budget: float
    elapsed: float
    iterations_attempted: int
    iterations_accepted: int
    ev_initial: float
    ev_final: float
    ev_improvement: float
    consensus_initial: float
    consensus_final: float
    steps: List[OptimizationStep]
    final_deck: List[Dict]        # list of {name, qty, section}
    cuts_made: List[str]
    adds_made: List[str]
    rejected_count: int


# ═══════════════════════════════════════════════════════════════════════════
# Deck manipulation helpers
# ═══════════════════════════════════════════════════════════════════════════

def _entries_to_dict(entries: List[Dict]) -> Dict[str, Dict]:
    """Convert list of entry dicts to {lowercased_name: entry} map."""
    return {e["name"].lower(): e for e in entries}


def _apply_swap(
    entries: List[Dict],
    cut_name: str,
    add_name: str,
    add_entry_template: Dict,
) -> List[Dict]:
    """
    Return a new entry list with cut_name removed and add_name inserted.
    Preserves quantity and section of the cut card for the add.
    """
    new_entries = []
    cut_qty = 1
    cut_section = "main"
    for e in entries:
        if e["name"].lower() == cut_name.lower():
            cut_qty = e.get("qty", 1)
            cut_section = e.get("section", "main")
        else:
            new_entries.append(e)
    # Add the new card with the same qty/section as the cut card
    new_entry = dict(add_entry_template)
    new_entry["qty"] = cut_qty
    new_entry["section"] = cut_section
    new_entries.append(new_entry)
    return new_entries


def _score_entries(
    entries: List[Dict],
    card_data: Dict,
    primary_axis: str = "",
) -> Dict[str, CardScore]:
    """Attach card data and run score_pairwise on an entry list."""
    annotated, _ = attach_card_data(entries, card_data)
    return score_pairwise(annotated, primary_axis=primary_axis)


# ═══════════════════════════════════════════════════════════════════════════
# Candidate selection
# ═══════════════════════════════════════════════════════════════════════════

def _select_cut_candidates(
    scores: Dict[str, CardScore],
    n: int = 15,
    exclude_lands: bool = True,
) -> List[Tuple[str, float]]:
    """
    Return the n weakest cards in the deck as cut candidates.
    Sorted ascending by composite_score.
    """
    candidates = [
        (name, sc.composite_score)
        for name, sc in scores.items()
        if not (exclude_lands and sc.profile.is_land)
    ]
    candidates.sort(key=lambda x: x[1])
    return candidates[:n]


def _select_add_candidates(
    pool_scores: Dict[str, CardScore],
    deck_scores: Dict[str, CardScore],
    n: int = 15,
    exclude_lands: bool = True,
) -> List[Tuple[str, float]]:
    """
    Return the n strongest pool cards not already in the deck as add candidates.
    Sorted descending by composite_score.
    """
    deck_names = {name.lower() for name in deck_scores}
    candidates = [
        (name, sc.composite_score)
        for name, sc in pool_scores.items()
        if name.lower() not in deck_names
        and not (exclude_lands and sc.profile.is_land)
    ]
    candidates.sort(key=lambda x: x[1], reverse=True)
    return candidates[:n]


def _propose_swap(
    cut_candidates: List[Tuple[str, float]],
    add_candidates: List[Tuple[str, float]],
    tried_swaps: set,
) -> Optional[SwapProposal]:
    """
    Sample one untried (cut, add) pair from candidates.
    Weights sampling toward weakest cuts and strongest adds.
    Returns None if all combinations exhausted.
    """
    if not cut_candidates or not add_candidates:
        return None

    # Try up to 20 random samples to find an untried pair
    for _ in range(20):
        # Weight toward bottom of cuts and top of adds
        cut_idx = int(random.triangular(0, len(cut_candidates) - 1, 0))
        add_idx = int(random.triangular(0, len(add_candidates) - 1, 0))
        cut_name, cut_score = cut_candidates[cut_idx]
        add_name, add_score = add_candidates[add_idx]
        pair = (cut_name.lower(), add_name.lower())
        if pair not in tried_swaps:
            tried_swaps.add(pair)
            expected_delta = (add_score - cut_score) / 60.0
            return SwapProposal(
                cut=cut_name,
                add=add_name,
                cut_score=round(cut_score, 2),
                add_score=round(add_score, 2),
                expected_ev_delta=round(expected_delta, 4),
            )
    return None


# ═══════════════════════════════════════════════════════════════════════════
# Core optimization loop
# ═══════════════════════════════════════════════════════════════════════════

def optimize(
    deck_entries: List[Dict],
    pool_entries: List[Dict],
    card_data: Dict,
    time_budget: float = 60.0,
    tribe: Optional[str] = None,
    top_cuts: int = 15,
    top_adds: int = 15,
    primary_axis: str = "",
    dry_run: bool = False,
    verbose: bool = False,
    locked_cards: Optional[List[str]] = None,
) -> OptimizationResult:
    """
    Run the Karpathy-style optimization loop.

    Parameters
    ----------
    deck_entries:   Annotated entries for the current deck
    pool_entries:   Annotated entries for the full candidate pool
    card_data:      Card DB rows (from load_cards_from_db)
    time_budget:    Seconds to run (default 60)
    tribe:          Tribe name for panel evaluation
    top_cuts:       How many weakest deck cards to consider cutting each round
    top_adds:       How many strongest pool cards to consider adding each round
    primary_axis:   Axis override for score_pairwise
    dry_run:        If True, score but don't actually swap
    verbose:        Print progress to stderr

    Returns
    -------
    OptimizationResult with full audit trail
    """
    start = time.time()
    deck_name = "deck"

    # ── Initial scoring ────────────────────────────────────────────────────
    if verbose:
        print("[optimizer] Initial scoring...", file=sys.stderr)

    current_entries = list(deck_entries)
    current_scores = _score_entries(current_entries, card_data, primary_axis)

    # Score pool once (does not change during optimization)
    pool_scores = _score_entries(pool_entries, card_data, primary_axis)

    initial_panel = run_panel(current_scores, tribe=tribe, pool_scores=pool_scores)
    best_ev = initial_panel["ev"]
    best_consensus = initial_panel["consensus"]
    best_entries = list(current_entries)
    best_scores = dict(current_scores)

    if verbose:
        print(f"[optimizer] Initial EV={best_ev:.1f} consensus={best_consensus:.1f}",
              file=sys.stderr)

    # ── Optimization state ─────────────────────────────────────────────────
    steps: List[OptimizationStep] = []
    tried_swaps: set = set()
    iterations_attempted = 0
    iterations_accepted = 0
    rejected_count = 0
    cuts_made: List[str] = []
    adds_made: List[str] = []

    # Pool entry lookup for applying swaps
    pool_entry_by_name = {e["name"].lower(): e for e in pool_entries
                          if e.get("found_in_db") and e.get("data")}

    # ── Main loop ──────────────────────────────────────────────────────────
    while time.time() - start < time_budget:
        elapsed = time.time() - start

        # Identify candidates from current best state
        _locked = {c.lower() for c in (locked_cards or [])}
        cut_candidates = [
            (name, score) for name, score in
            _select_cut_candidates(best_scores, n=top_cuts + len(_locked))
            if name.lower() not in _locked
        ][:top_cuts]
        add_candidates = _select_add_candidates(pool_scores, best_scores, n=top_adds)

        if not cut_candidates or not add_candidates:
            if verbose:
                print("[optimizer] No candidates remaining. Stopping.", file=sys.stderr)
            break

        # Propose a swap
        proposal = _propose_swap(cut_candidates, add_candidates, tried_swaps)
        if proposal is None:
            if verbose:
                print("[optimizer] All candidate combinations tried. Stopping.",
                      file=sys.stderr)
            break

        iterations_attempted += 1

        if dry_run:
            if verbose:
                print(f"[dry-run] Would try: cut={proposal.cut} add={proposal.add}",
                      file=sys.stderr)
            continue

        # Get the pool entry template for the card we're adding
        add_template = pool_entry_by_name.get(proposal.add.lower())
        if add_template is None:
            rejected_count += 1
            continue

        # Apply the swap to entry list
        candidate_entries = _apply_swap(
            best_entries, proposal.cut, proposal.add, add_template
        )

        # Score the candidate deck
        try:
            candidate_scores = _score_entries(
                candidate_entries, card_data, primary_axis
            )
        except Exception as e:
            if verbose:
                print(f"[optimizer] Score error: {e}", file=sys.stderr)
            rejected_count += 1
            continue

        # Evaluate candidate
        candidate_panel = run_panel(candidate_scores, tribe=tribe)
        candidate_ev = candidate_panel["ev"]

        if candidate_ev > best_ev:
            # Accept the swap
            ev_delta = candidate_ev - best_ev
            step = OptimizationStep(
                iteration=iterations_attempted,
                swap=proposal,
                ev_before=best_ev,
                ev_after=candidate_ev,
                ev_delta=round(ev_delta, 2),
                elapsed_seconds=round(elapsed, 1),
                panel_consensus_before=best_consensus,
                panel_consensus_after=candidate_panel["consensus"],
            )
            steps.append(step)

            best_ev = candidate_ev
            best_consensus = candidate_panel["consensus"]
            best_entries = candidate_entries
            best_scores = candidate_scores
            cuts_made.append(proposal.cut)
            adds_made.append(proposal.add)
            iterations_accepted += 1

            if verbose:
                print(
                    f"[optimizer] ✓ iter={iterations_attempted:4d} "
                    f"EV {step.ev_before:.1f}→{step.ev_after:.1f} "
                    f"(+{ev_delta:.2f}) "
                    f"cut={proposal.cut} add={proposal.add}",
                    file=sys.stderr,
                )
        else:
            rejected_count += 1
            if verbose and iterations_attempted % 50 == 0:
                print(
                    f"[optimizer] · iter={iterations_attempted:4d} "
                    f"rejected (EV {candidate_ev:.1f} ≤ {best_ev:.1f}) "
                    f"elapsed={elapsed:.1f}s",
                    file=sys.stderr,
                )

    total_elapsed = round(time.time() - start, 1)

    if verbose:
        print(
            f"[optimizer] Done. {iterations_accepted}/{iterations_attempted} accepted. "
            f"EV {initial_panel['ev']:.1f}→{best_ev:.1f} "
            f"in {total_elapsed}s",
            file=sys.stderr,
        )

    # Convert best_entries to clean output format
    final_deck = [
        {"name": e["name"], "qty": e.get("qty", 1), "section": e.get("section", "main")}
        for e in best_entries
    ]

    return OptimizationResult(
        deck_name=deck_name,
        tribe=tribe,
        time_budget=time_budget,
        elapsed=total_elapsed,
        iterations_attempted=iterations_attempted,
        iterations_accepted=iterations_accepted,
        ev_initial=initial_panel["ev"],
        ev_final=best_ev,
        ev_improvement=round(best_ev - initial_panel["ev"], 2),
        consensus_initial=initial_panel["consensus"],
        consensus_final=best_consensus,
        steps=steps,
        final_deck=final_deck,
        cuts_made=cuts_made,
        adds_made=adds_made,
        rejected_count=rejected_count,
    )


# ═══════════════════════════════════════════════════════════════════════════
# Output formatters
# ═══════════════════════════════════════════════════════════════════════════

def format_result_markdown(result: OptimizationResult) -> str:
    """Format optimization result as a markdown report."""
    lines = []
    lines.append("# Synergy Optimizer Report")
    lines.append("")
    lines.append(f"**Deck:** {result.deck_name}  ")
    lines.append(f"**Tribe:** {result.tribe or 'N/A'}  ")
    lines.append(f"**Time Budget:** {result.time_budget}s (ran {result.elapsed}s)  ")
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append("| Metric | Before | After | Delta |")
    lines.append("|--------|-------:|------:|------:|")
    lines.append(f"| EV | {result.ev_initial:.1f} | {result.ev_final:.1f} "
                 f"| **+{result.ev_improvement:.2f}** |")
    lines.append(f"| Consensus | {result.consensus_initial:.1f} | "
                 f"{result.consensus_final:.1f} | "
                 f"**{result.consensus_final - result.consensus_initial:+.2f}** |")
    lines.append(f"| Iterations | — | — | {result.iterations_attempted} |")
    lines.append(f"| Accepted | — | — | {result.iterations_accepted} |")
    lines.append(f"| Rejected | — | — | {result.rejected_count} |")
    lines.append("")

    if result.steps:
        lines.append("## Accepted Swaps (Chronological)")
        lines.append("")
        lines.append("| # | Cut | Add | EV Before | EV After | Δ EV | Time |")
        lines.append("|---|-----|-----|----------:|---------:|-----:|------|")
        for i, step in enumerate(result.steps, 1):
            lines.append(
                f"| {i} | {step.swap.cut} | {step.swap.add} "
                f"| {step.ev_before:.1f} | {step.ev_after:.1f} "
                f"| **+{step.ev_delta:.2f}** | {step.elapsed_seconds}s |"
            )
        lines.append("")

    if result.cuts_made:
        lines.append("## Final Cuts")
        lines.append("")
        for card in result.cuts_made:
            lines.append(f"- ✂️ {card}")
        lines.append("")

    if result.adds_made:
        lines.append("## Final Adds")
        lines.append("")
        for card in result.adds_made:
            lines.append(f"- ➕ {card}")
        lines.append("")

    lines.append("## Optimized Decklist")
    lines.append("")
    lines.append("```")
    lines.append("Deck")
    main = [e for e in result.final_deck if e.get("section", "main") == "main"]
    side = [e for e in result.final_deck if e.get("section") == "side"]
    for e in sorted(main, key=lambda x: x["name"]):
        lines.append(f"{e['qty']} {e['name']}")
    if side:
        lines.append("")
        lines.append("Sideboard")
        for e in sorted(side, key=lambda x: x["name"]):
            lines.append(f"{e['qty']} {e['name']}")
    lines.append("```")
    lines.append("")

    return "\n".join(lines)


def format_result_json(result: OptimizationResult) -> str:
    """Format optimization result as JSON for autoresearch consumption."""
    def _step_dict(s: OptimizationStep) -> dict:
        return {
            "iteration": s.iteration,
            "cut": s.swap.cut,
            "add": s.swap.add,
            "cut_score": s.swap.cut_score,
            "add_score": s.swap.add_score,
            "ev_before": s.ev_before,
            "ev_after": s.ev_after,
            "ev_delta": s.ev_delta,
            "elapsed_seconds": s.elapsed_seconds,
            "consensus_before": s.panel_consensus_before,
            "consensus_after": s.panel_consensus_after,
        }

    return json.dumps({
        "deck_name": result.deck_name,
        "tribe": result.tribe,
        "time_budget": result.time_budget,
        "elapsed": result.elapsed,
        "iterations_attempted": result.iterations_attempted,
        "iterations_accepted": result.iterations_accepted,
        "ev_initial": result.ev_initial,
        "ev_final": result.ev_final,
        "ev_improvement": result.ev_improvement,
        "consensus_initial": result.consensus_initial,
        "consensus_final": result.consensus_final,
        "acceptance_rate": round(
            result.iterations_accepted / max(result.iterations_attempted, 1), 3
        ),
        "steps": [_step_dict(s) for s in result.steps],
        "cuts_made": result.cuts_made,
        "adds_made": result.adds_made,
        "final_deck": result.final_deck,
    }, indent=2)


# ═══════════════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════════════

def _cli() -> None:
    import argparse

    p = argparse.ArgumentParser(
        description="Karpathy-style autonomous deck optimizer.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument("session", help="session.md containing candidate pool")
    p.add_argument("--deck", default="",
                   help="decklist.txt to optimize (default: auto-detect from session dir)")
    p.add_argument("--time-budget", type=float, default=60.0,
                   help="Seconds to run (default: 60)")
    p.add_argument("--tribe", default="", help="Tribe name for TribalChief evaluation")
    p.add_argument("--top-cuts", type=int, default=15,
                   help="How many weakest deck cards to consider cutting (default: 15)")
    p.add_argument("--top-adds", type=int, default=15,
                   help="How many strongest pool cards to consider adding (default: 15)")
    p.add_argument("--primary-axis", default="",
                   help="Comma-separated axis override (e.g. lifegain,token)")
    p.add_argument("--output", default="",
                   help="Write report to this file (default: stdout)")
    p.add_argument("--json", action="store_true", dest="output_json",
                   help="Output JSON instead of markdown")
    p.add_argument("--dry-run", action="store_true",
                   help="Score but do not apply swaps")
    p.add_argument("--verbose", action="store_true",
                   help="Print iteration-by-iteration progress to stderr")
    p.add_argument("--lock-cards", nargs="+", default=[],
                   metavar="CARD",
                   help="Card names that cannot be cut (e.g. --lock-cards \"Hope Estheim\")")
    args = p.parse_args()

    session_path = Path(args.session)
    if not session_path.exists():
        print(f"ERROR: {session_path} not found.", file=sys.stderr)
        sys.exit(2)

    # ── Load pool (from session.md) ────────────────────────────────────────
    content = session_path.read_text(encoding="utf-8")
    pool_names = extract_names_from_session(content)
    if not pool_names:
        print("ERROR: No cards extracted from session.md", file=sys.stderr)
        sys.exit(2)

    pool_entries = [{"name": n, "qty": 1, "section": "pool"} for n in pool_names]

    # ── Load deck (decklist.txt in same dir, or --deck) ────────────────────
    deck_path = Path(args.deck) if args.deck else session_path.parent / "decklist.txt"
    if not deck_path.exists():
        print(f"ERROR: Deck file not found at {deck_path}. "
              f"Use --deck to specify path.", file=sys.stderr)
        sys.exit(2)

    deck_entries_raw = extract_deck_entries_from_decklist(deck_path)
    if not deck_entries_raw:
        print(f"ERROR: No cards extracted from {deck_path}", file=sys.stderr)
        sys.exit(2)

    # ── Load card DB ───────────────────────────────────────────────────────
    paths = RepoPaths()
    all_names = list({e["name"] for e in pool_entries + deck_entries_raw})
    print(f"Loading {len(all_names)} unique cards from DB...", file=sys.stderr)
    card_data = load_cards_from_db(all_names, paths)

    pool_annotated, pool_missing = attach_card_data(pool_entries, card_data)
    deck_annotated, deck_missing = attach_card_data(deck_entries_raw, card_data)

    if deck_missing:
        print(f"[WARN] {len(deck_missing)} deck card(s) not in DB — "
              f"will be treated as zero-score.", file=sys.stderr)

    print(
        f"Pool: {len(pool_annotated)} cards | "
        f"Deck: {len(deck_annotated)} cards | "
        f"Time budget: {args.time_budget}s",
        file=sys.stderr,
    )

    # ── Run optimizer ──────────────────────────────────────────────────────
    result = optimize(
        deck_entries=deck_annotated,
        pool_entries=pool_annotated,
        card_data=card_data,
        time_budget=args.time_budget,
        tribe=args.tribe.strip() or None,
        top_cuts=args.top_cuts,
        top_adds=args.top_adds,
        primary_axis=args.primary_axis,
        dry_run=args.dry_run,
        verbose=args.verbose,
        locked_cards=args.lock_cards or [],
    )
    result.deck_name = session_path.parent.name

    # ── Output ─────────────────────────────────────────────────────────────
    if args.output_json:
        report = format_result_json(result)
        suffix = "optimizer_result.json"
    else:
        report = format_result_markdown(result)
        suffix = "optimizer_report.md"

    if args.output:
        out_path = Path(args.output)
    else:
        out_path = session_path.parent / suffix

    out_path.write_text(report, encoding="utf-8")
    print(f"Report written to {out_path}", file=sys.stderr)

    # Always write JSON log for autoresearch consumption
    json_path = session_path.parent / "optimizer_log.json"
    json_path.write_text(format_result_json(result), encoding="utf-8")
    print(f"JSON log written to {json_path}", file=sys.stderr)

    print(
        f"\nEV: {result.ev_initial:.1f} → {result.ev_final:.1f} "
        f"(+{result.ev_improvement:.2f}) | "
        f"{result.iterations_accepted} swaps accepted in {result.elapsed}s",
        file=sys.stderr,
    )

    sys.exit(0)


if __name__ == "__main__":
    _cli()
