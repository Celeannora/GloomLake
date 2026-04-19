#!/usr/bin/env python3
"""
Goldfish Autoresearch — Synergy-first iterative deck optimizer.

GUI entry point: run_autoresearch(deck_dir, colors, log=...)

This module is a library, not a CLI tool.  The GUI calls run_autoresearch()
directly.  A minimal __main__ block exists for dev/debug only.

Algorithm
---------
1. Load decklist.txt + candidate_pool.csv (with synergy scores — hard prereq).
2. Score the starting deck: goldfish N hands, compute chain_fire_rate for every
   synergy chain detected by synergy_report._find_synergy_chains.
3. Iterative improvement loop:
   a. Perturb: swap K=3 non-land cards from deck with K=3 from candidate pool
      (scored, not random — prefer high composite_score candidates).
   b. Re-goldfish the candidate deck.
   c. Accept if overall_score improves.
   d. Convergence: stop if rolling 15-iter improvement delta < CONVERGENCE_DELTA.
   e. Restart: if 10 consecutive iterations show no gain, apply K=5 shake and
      continue.  Max MAX_RESTARTS restarts before accepting current best.
4. Write best deck to decklist.txt and return structured GoldfishResult.

Scoring
-------
Overall score = WEIGHT_CHAIN * avg_chain_fire_rate
              + WEIGHT_CURVE * perfect_curve_rate
              + WEIGHT_KEEPER * keeper_rate
              - WEIGHT_VARIANCE * kill_turn_stddev

Goldfish cast priority: highest composite_score among castable spells, CMC
tiebreak.  This plays toward chain completion, consistent with synergy being
the highest priority.

Failure mode tracking
---------------------
Each hand is classified as one of:
  mana_screw        — <=1 land by T3
  missing_pieces    — chain cards not seen by T5 despite good mana
  slow_chain        — chain cards seen but not castable by T5 (mana ok, CMC)
  success           — chain fired by T5

Progress
--------
All progress is emitted via log(message: str, level: str) callback where level
is one of: "info", "warn", "error", "success".  GUI wires this to its log panel.
"""

from __future__ import annotations

import csv
import io
import random
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional, Set, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))

from mtg_utils import RepoPaths, parse_decklist
from auto_build import _safe_float, _is_land_card, SCORE_SORT_KEYS
from synergy_engine import load_cards_from_db, score_pairwise, attach_card_data
from synergy_report import _find_synergy_chains


# =============================================================================
# Tunable constants  (GUI may expose these as settings fields)
# =============================================================================

# Goldfish simulation
N_HANDS: int = 10_000          # hands per evaluation — enough to stabilise P(chain)
N_TURNS: int = 5               # turns per hand
ON_PLAY: bool = True           # True = on the play (no T1 draw)
MIN_KEEP_LANDS: int = 2        # opener mulligan floor
MAX_KEEP_LANDS: int = 5        # opener mulligan ceiling
MIN_PLAY_CMC: float = 2.0      # opener must have >=1 spell with CMC <= this

# Convergence
CONVERGENCE_WINDOW: int = 15   # rolling window for early-stop check
CONVERGENCE_DELTA: float = 0.5 # minimum improvement over window to continue
NO_GAIN_RESTART: int = 10      # consecutive no-gain iters before K=5 shake
MAX_RESTARTS: int = 5          # max restart events before accepting best

# Perturbation
K_SWAP: int = 3                # normal perturbation: swap K non-land cards
K_RESTART_SWAP: int = 5        # restart perturbation: swap K_RESTART cards

# Scoring weights
WEIGHT_CHAIN: float = 50.0     # chain fire rate (primary — synergy priority)
WEIGHT_CURVE: float = 20.0     # perfect curve rate
WEIGHT_KEEPER: float = 15.0    # keeper rate (mana health proxy)
WEIGHT_VARIANCE: float = 5.0   # penalty for high kill-turn stddev


# =============================================================================
# Data structures
# =============================================================================

@dataclass
class HandResult:
    """Per-hand simulation result."""
    kept: bool                      # passed mulligan filter
    on_curve_turns: int             # turns where ideal play was made
    kill_turn: Optional[int]        # first turn chain fully fired (None = never)
    chain_fired: bool               # did any detected chain fire by T_max?
    failure_mode: str               # mana_screw | missing_pieces | slow_chain | success
    chain_seen_turn: Optional[int]  # turn all chain pieces were seen (not yet castable)


@dataclass
class GoldfishStats:
    """Aggregate stats for one deck evaluation."""
    n_hands: int = 0
    keeper_rate: float = 0.0
    perfect_curve_rate: float = 0.0   # >= N_TURNS-1 on-curve turns
    chain_fire_rate: float = 0.0      # P(any chain fired by T5)
    avg_kill_turn: float = 0.0        # mean turn chain fired (kept hands only)
    kill_turn_stddev: float = 0.0
    failure_modes: Dict[str, int] = field(default_factory=dict)
    overall_score: float = 0.0

    def compute_overall(self) -> None:
        self.overall_score = (
            WEIGHT_CHAIN   * self.chain_fire_rate
            + WEIGHT_CURVE   * self.perfect_curve_rate
            + WEIGHT_KEEPER  * self.keeper_rate
            - WEIGHT_VARIANCE * self.kill_turn_stddev
        )


@dataclass
class GoldfishResult:
    """Full result returned to GUI."""
    success: bool
    error: str = ""
    iterations: int = 0
    restarts: int = 0
    initial_score: float = 0.0
    final_score: float = 0.0
    delta: float = 0.0
    initial_stats: Optional[GoldfishStats] = None
    final_stats: Optional[GoldfishStats] = None
    swaps_applied: List[Tuple[str, str]] = field(default_factory=list)  # (removed, added)
    convergence_reason: str = ""
    focus_log: List[Tuple[str, str]] = field(default_factory=list)


# =============================================================================
# Card data loading
# =============================================================================

def _load_pool_csv(pool_path: Path) -> List[Dict]:
    """Load candidate_pool.csv rows, sorted by composite synergy score desc."""
    if not pool_path.exists():
        return []
    text = pool_path.read_text(encoding="utf-8")
    reader = csv.DictReader(io.StringIO(text))
    rows = [r for r in reader if r.get("name", "").strip()]
    # Sort by synergy density desc, then weighted_score desc
    def _score(r: Dict) -> float:
        return (
            _safe_float(r.get("synergy_density", "0")) * 100
            + _safe_float(r.get("weighted_score", "0"))
        )
    rows.sort(key=_score, reverse=True)
    return rows


def _has_synergy_scores(pool_rows: List[Dict]) -> bool:
    """True if the pool CSV contains synergy scoring columns."""
    if not pool_rows:
        return False
    return any(pool_rows[0].get(c, "") for c in SCORE_SORT_KEYS)


def _build_deck_from_decklist(
    deck_path: Path,
    card_data: Dict[str, Dict],
) -> Tuple[List[Dict], List[str]]:
    """
    Expand decklist.txt into per-card simulation dicts.
    Returns (deck_cards, unscored_names).
    Each card dict: {name, cmc, is_land, composite_score, qty_key}
    """
    mainboard, _ = parse_decklist(deck_path)
    deck: List[Dict] = []
    unscored: List[str] = []

    for qty, name in mainboard:
        data = card_data.get(name.lower())
        if data is None:
            if name not in unscored:
                unscored.append(name)
            for _ in range(qty):
                deck.append({
                    "name": name, "cmc": None,
                    "is_land": False, "composite_score": 0.0,
                })
            continue

        raw_cmc = data.get("cmc")
        cmc = float(raw_cmc) if raw_cmc not in (None, "") else None
        type_line = (data.get("type_line") or "").lower()
        is_land = "land" in type_line and "spell" not in type_line
        cscore = _safe_float(data.get("weighted_score", "0"))

        for _ in range(qty):
            deck.append({
                "name": name, "cmc": cmc,
                "is_land": is_land, "composite_score": cscore,
            })

    return deck, unscored


def _build_score_lookup(
    pool_rows: List[Dict],
    card_data: Dict[str, Dict],
) -> Dict[str, float]:
    """name.lower() -> composite_score for all pool candidates."""
    lookup: Dict[str, float] = {}
    for row in pool_rows:
        n = row.get("name", "").strip().lower()
        if n:
            lookup[n] = (
                _safe_float(row.get("synergy_density", "0")) * 100
                + _safe_float(row.get("weighted_score", "0"))
            )
    return lookup


# =============================================================================
# Synergy chain extraction
# =============================================================================

def _get_chain_sets(
    deck_cards: List[Dict],
    card_data: Dict[str, Dict],
    paths: RepoPaths,
) -> List[Set[str]]:
    """
    Run synergy scoring on the current deck and return each detected chain
    as a frozenset of card names (lowercased).
    Returns at most 3 chains (matching synergy_report behaviour).
    """
    names = list({c["name"] for c in deck_cards if not c["is_land"]})
    if not names:
        return []

    entries = [
        {"name": n, "qty": sum(1 for c in deck_cards if c["name"] == n),
         "section": "main"}
        for n in names
    ]
    annotated, _ = attach_card_data(entries, card_data)
    scores = score_pairwise(annotated)
    chains = _find_synergy_chains(scores, max_chains=3)
    return [
        {c.lower() for c in ch["path"]}
        for ch in chains
        if len(ch["path"]) >= 2
    ]


# =============================================================================
# Mulligan check
# =============================================================================

def _is_keepable(hand: List[Dict]) -> bool:
    """True if hand passes land + early-play mulligan filter."""
    lands = sum(1 for c in hand if c["is_land"])
    if lands < MIN_KEEP_LANDS or lands > MAX_KEEP_LANDS:
        return False
    has_early = any(
        not c["is_land"]
        and c["cmc"] is not None
        and c["cmc"] <= MIN_PLAY_CMC
        for c in hand
    )
    return has_early


# =============================================================================
# Single hand simulation
# =============================================================================

def _simulate_hand(
    deck: List[Dict],
    chain_sets: List[Set[str]],
    n_turns: int,
    on_play: bool,
) -> HandResult:
    """
    Simulate one goldfish hand.

    Cast priority: highest composite_score among castable spells, CMC tiebreak.
    Tracks chain firing: a chain fires when ALL its members have been cast
    (or, for lands/0-CMC, when they've entered play).
    """
    shuffled = deck[:]
    random.shuffle(shuffled)
    hand = shuffled[:7]
    library = shuffled[7:]

    kept = _is_keepable(hand)

    # Track which chain members have entered play
    in_play_names: Set[str] = set()
    seen_names: Set[str] = {c["name"].lower() for c in hand}

    lands_in_play = 0
    on_curve_turns = 0
    kill_turn: Optional[int] = None
    chain_fired = False
    chain_seen_turn: Optional[int] = None

    # Lands that entered play (for chain tracking)
    for c in hand:
        if c["is_land"]:
            in_play_names.add(c["name"].lower())

    for turn in range(1, n_turns + 1):
        # Draw (skip T1 on play)
        if not (turn == 1 and on_play):
            if library:
                drawn = library.pop(0)
                hand.append(drawn)
                seen_names.add(drawn["name"].lower())
                if drawn["is_land"]:
                    in_play_names.add(drawn["name"].lower())

        # Play land
        land_to_play = next((c for c in hand if c["is_land"]), None)
        if land_to_play:
            hand.remove(land_to_play)
            lands_in_play += 1
            in_play_names.add(land_to_play["name"].lower())

        mana = lands_in_play

        # Castable spells with known CMC
        castable = [
            c for c in hand
            if not c["is_land"]
            and c["cmc"] is not None
            and c["cmc"] <= mana
            and c["cmc"] > 0
        ]

        if castable:
            # Cast by composite_score desc, CMC tiebreak desc
            best = max(
                castable,
                key=lambda c: (c["composite_score"], c["cmc"]),
            )
            hand.remove(best)
            in_play_names.add(best["name"].lower())
            if mana >= turn:
                on_curve_turns += 1

        # Check chain firing
        if not chain_fired and chain_sets:
            # Check if all pieces of any chain are in play
            for chain in chain_sets:
                if chain.issubset(in_play_names):
                    chain_fired = True
                    kill_turn = turn
                    break
            # Track when all chain pieces have been *seen* (hand+drawn)
            if chain_seen_turn is None:
                for chain in chain_sets:
                    if chain.issubset(seen_names):
                        chain_seen_turn = turn
                        break

    # Classify failure mode
    land_count = sum(1 for c in deck[:7] if c["is_land"])  # approximate from deck head
    if chain_fired:
        failure_mode = "success"
    elif lands_in_play <= 1:
        failure_mode = "mana_screw"
    elif chain_seen_turn is not None:
        # Saw the pieces but couldn't cast them all in time
        failure_mode = "slow_chain"
    else:
        failure_mode = "missing_pieces"

    return HandResult(
        kept=kept,
        on_curve_turns=on_curve_turns,
        kill_turn=kill_turn,
        chain_fired=chain_fired,
        failure_mode=failure_mode,
        chain_seen_turn=chain_seen_turn,
    )


# =============================================================================
# Full deck evaluation
# =============================================================================

def evaluate_deck(
    deck: List[Dict],
    chain_sets: List[Set[str]],
    n_hands: int = N_HANDS,
    n_turns: int = N_TURNS,
    on_play: bool = ON_PLAY,
) -> GoldfishStats:
    """Goldfish N_HANDS and return aggregate GoldfishStats."""
    stats = GoldfishStats(n_hands=n_hands)
    kept_count = 0
    perfect_count = 0
    chain_fire_count = 0
    kill_turns: List[float] = []
    failure_modes: Dict[str, int] = defaultdict(int)

    for _ in range(n_hands):
        result = _simulate_hand(deck, chain_sets, n_turns, on_play)
        if result.kept:
            kept_count += 1
            if result.on_curve_turns >= n_turns - 1:
                perfect_count += 1
            if result.chain_fired:
                chain_fire_count += 1
                kill_turns.append(float(result.kill_turn))
        failure_modes[result.failure_mode] += 1

    stats.keeper_rate = kept_count / n_hands if n_hands else 0.0
    stats.perfect_curve_rate = perfect_count / kept_count if kept_count else 0.0
    stats.chain_fire_rate = chain_fire_count / kept_count if kept_count else 0.0
    stats.failure_modes = dict(failure_modes)

    if kill_turns:
        mean = sum(kill_turns) / len(kill_turns)
        stats.avg_kill_turn = mean
        variance = sum((t - mean) ** 2 for t in kill_turns) / len(kill_turns)
        stats.kill_turn_stddev = variance ** 0.5
    else:
        stats.avg_kill_turn = float(n_turns + 1)
        stats.kill_turn_stddev = 0.0

    stats.compute_overall()
    return stats


# =============================================================================
# Deck mutation (perturbation)
# =============================================================================

def _nonland_names_in_deck(deck: List[Dict]) -> List[str]:
    """Unique non-land card names currently in the deck."""
    seen: Set[str] = set()
    result: List[str] = []
    for c in deck:
        if not c["is_land"] and c["name"] not in seen:
            seen.add(c["name"])
            result.append(c["name"])
    return result


def _apply_swap(
    deck: List[Dict],
    remove_names: List[str],
    add_rows: List[Dict],
    score_lookup: Dict[str, float],
) -> List[Dict]:
    """
    Return a new deck with remove_names replaced by add_rows cards.
    Preserves all copies of non-swapped cards.
    """
    new_deck = []
    removed: Dict[str, int] = defaultdict(int)
    for name in remove_names:
        removed[name] += sum(1 for c in deck if c["name"] == name)

    remove_counts: Dict[str, int] = {n: 0 for n in remove_names}
    for card in deck:
        name = card["name"]
        if name in remove_counts and remove_counts[name] < removed[name]:
            remove_counts[name] += 1
            continue
        new_deck.append(card)

    for row in add_rows:
        name = row.get("name", "").strip()
        raw_cmc = row.get("cmc")
        cmc = float(raw_cmc) if raw_cmc not in (None, "") else None
        type_line = (row.get("type_line") or "").lower()
        is_land = "land" in type_line and "spell" not in type_line
        cscore = score_lookup.get(name.lower(), 0.0)
        qty = removed.get(name, 0)
        qty = qty if qty > 0 else sum(removed.values()) // max(len(add_rows), 1)
        qty = max(1, qty)
        for _ in range(qty):
            new_deck.append({
                "name": name, "cmc": cmc,
                "is_land": is_land, "composite_score": cscore,
            })

    return new_deck


def _pick_candidates_to_add(
    pool_rows: List[Dict],
    deck_names: Set[str],
    k: int,
) -> List[Dict]:
    """
    Pick K candidates from pool not already in deck.
    Weighted-random toward top of pool (already sorted by score desc).
    Top half of pool gets 3x weight over bottom half.
    """
    available = [
        r for r in pool_rows
        if r.get("name", "").strip().lower() not in deck_names
        and not _is_land_card(r)
    ]
    if not available:
        return []
    half = max(1, len(available) // 2)
    weights = [3.0] * min(half, len(available)) + [1.0] * max(0, len(available) - half)
    k = min(k, len(available))
    chosen = random.choices(available, weights=weights[:len(available)], k=k * 3)
    # Deduplicate
    seen: Set[str] = set()
    result: List[Dict] = []
    for r in chosen:
        n = r.get("name", "").strip().lower()
        if n not in seen:
            seen.add(n)
            result.append(r)
        if len(result) >= k:
            break
    return result


# =============================================================================
# Main autoresearch loop
# =============================================================================

def run_autoresearch(
    deck_dir: str,
    colors: str,
    *,
    log: Optional[Callable[[str, str], None]] = None,
    n_hands: int = N_HANDS,
    n_turns: int = N_TURNS,
    on_play: bool = ON_PLAY,
) -> GoldfishResult:
    """
    Run iterative goldfish autoresearch on a deck directory.

    Parameters
    ----------
    deck_dir : str
        Path to deck directory containing decklist.txt and candidate_pool.csv.
    colors : str
        WUBRG color identity string (e.g. "WB").
    log : Callable[[str, str], None], optional
        Progress callback (message, level).  Level: info/warn/error/success.
    n_hands : int
        Hands to simulate per evaluation (default N_HANDS=10000).
    n_turns : int
        Turns per hand (default N_TURNS=5).
    on_play : bool
        True = on the play, False = on the draw (default ON_PLAY=True).

    Returns
    -------
    GoldfishResult
        Structured result for GUI consumption.
    """
    if log is None:
        def log(msg: str, level: str = "info") -> None:
            tag = {"info": "INFO", "warn": "WARN", "error": "ERR ",
                   "success": " OK "}.get(level, "    ")
            print(f"[{tag}] {msg}", file=sys.stderr)

    result = GoldfishResult(success=False)
    focus_log: List[Tuple[str, str]] = []
    result.focus_log = focus_log

    # ------------------------------------------------------------------
    # 1. Validate prerequisites
    # ------------------------------------------------------------------
    deck_path_obj = Path(deck_dir)
    decklist_path = deck_path_obj / "decklist.txt"
    pool_path = deck_path_obj / "candidate_pool.csv"

    if not decklist_path.exists():
        result.error = "decklist.txt not found in deck directory."
        log(result.error, "error")
        return result

    if not pool_path.exists():
        result.error = "candidate_pool.csv not found — run synergy analysis first."
        log(result.error, "error")
        return result

    pool_rows = _load_pool_csv(pool_path)
    if not pool_rows:
        result.error = "candidate_pool.csv is empty."
        log(result.error, "error")
        return result

    if not _has_synergy_scores(pool_rows):
        result.error = (
            "candidate_pool.csv has no synergy scores — "
            "run synergy analysis and merge scores first."
        )
        log(result.error, "error")
        return result

    log(f"Pool loaded: {len(pool_rows)} candidates", "info")

    # ------------------------------------------------------------------
    # 2. Load card data from local DB
    # ------------------------------------------------------------------
    paths = RepoPaths()
    all_names = list({
        r.get("name", "").strip()
        for r in pool_rows
        if r.get("name", "").strip()
    })
    log(f"Loading card data for {len(all_names)} pool cards...", "info")
    card_data = load_cards_from_db(all_names, paths)

    # Also load decklist card names not in pool
    mainboard, _ = parse_decklist(decklist_path)
    deck_names_for_load = [name for _, name in mainboard]
    extra = load_cards_from_db(
        [n for n in deck_names_for_load if n.lower() not in card_data],
        paths,
    )
    card_data.update(extra)

    # Build score lookup
    score_lookup = _build_score_lookup(pool_rows, card_data)

    # ------------------------------------------------------------------
    # 3. Build initial deck
    # ------------------------------------------------------------------
    deck, unscored = _build_deck_from_decklist(decklist_path, card_data)
    if len(deck) < 20:
        result.error = f"Deck too small to simulate ({len(deck)} cards)."
        log(result.error, "error")
        return result

    if unscored:
        log(
            f"{len(unscored)} card(s) not in DB — composite_score=0: "
            f"{', '.join(unscored[:5])}",
            "warn",
        )

    log(f"Deck: {len(deck)} cards, {sum(1 for c in deck if c['is_land'])} lands",
        "info")

    # ------------------------------------------------------------------
    # 4. Detect synergy chains
    # ------------------------------------------------------------------
    log("Detecting synergy chains...", "info")
    chain_sets = _get_chain_sets(deck, card_data, paths)
    if chain_sets:
        for i, cs in enumerate(chain_sets, 1):
            log(f"  Chain {i}: {', '.join(sorted(cs))}", "info")
    else:
        log("No synergy chains detected — optimising on curve + keeper rate only.",
            "warn")

    # ------------------------------------------------------------------
    # 5. Evaluate starting deck
    # ------------------------------------------------------------------
    log(f"Evaluating starting deck ({n_hands:,} hands)...", "info")
    initial_stats = evaluate_deck(deck, chain_sets, n_hands, n_turns, on_play)
    result.initial_stats = initial_stats
    result.initial_score = initial_stats.overall_score
    _log_stats(initial_stats, "Initial", log)

    # ------------------------------------------------------------------
    # 6. Iterative improvement
    # ------------------------------------------------------------------
    best_deck = deck[:]
    best_score = initial_stats.overall_score
    best_chains = chain_sets[:]
    best_stats = initial_stats
    swaps_applied: List[Tuple[str, str]] = []

    score_history: List[float] = [best_score]
    no_gain_streak = 0
    restarts = 0
    iteration = 0
    convergence_reason = ""

    log("Starting optimisation loop...", "info")

    while True:
        iteration += 1

        # ── Convergence check (rolling window) ──────────────────────
        if len(score_history) >= CONVERGENCE_WINDOW:
            window = score_history[-CONVERGENCE_WINDOW:]
            window_delta = max(window) - min(window)
            if window_delta < CONVERGENCE_DELTA:
                convergence_reason = (
                    f"Converged: rolling {CONVERGENCE_WINDOW}-iter delta "
                    f"{window_delta:.3f} < {CONVERGENCE_DELTA}"
                )
                log(f"[iter {iteration}] {convergence_reason}", "success")
                break

        # ── Restart check ────────────────────────────────────────────
        if no_gain_streak >= NO_GAIN_RESTART:
            if restarts >= MAX_RESTARTS:
                convergence_reason = (
                    f"Max restarts ({MAX_RESTARTS}) reached with no escape."
                )
                log(f"[iter {iteration}] {convergence_reason}", "warn")
                break
            restarts += 1
            no_gain_streak = 0
            k = K_RESTART_SWAP
            log(
                f"[iter {iteration}] No gain for {NO_GAIN_RESTART} iters — "
                f"restart {restarts}/{MAX_RESTARTS}, K={k} shake",
                "warn",
            )
        else:
            k = K_SWAP

        # ── Perturbation ─────────────────────────────────────────────
        current_nonland_names = _nonland_names_in_deck(best_deck)
        if len(current_nonland_names) < k:
            convergence_reason = "Not enough non-land cards to perturb."
            log(f"[iter {iteration}] {convergence_reason}", "warn")
            break

        remove_names = random.sample(current_nonland_names, k)
        deck_name_set = {c["name"].lower() for c in best_deck}
        add_rows = _pick_candidates_to_add(pool_rows, deck_name_set, k)

        if not add_rows:
            log(f"[iter {iteration}] No candidates available to add.", "warn")
            no_gain_streak += 1
            continue

        candidate_deck = _apply_swap(best_deck, remove_names, add_rows, score_lookup)

        # Re-detect chains for candidate deck
        candidate_chains = _get_chain_sets(candidate_deck, card_data, paths)

        # ── Evaluate ─────────────────────────────────────────────────
        candidate_stats = evaluate_deck(
            candidate_deck, candidate_chains, n_hands, n_turns, on_play,
        )
        delta = candidate_stats.overall_score - best_score

        if delta > 0:
            add_names = [r.get("name", "") for r in add_rows]
            log(
                f"[iter {iteration}] +{delta:.2f} | "
                f"removed: {remove_names} | added: {add_names}",
                "success",
            )
            for rem, add in zip(remove_names, add_names):
                swaps_applied.append((rem, add))
            best_deck = candidate_deck
            best_score = candidate_stats.overall_score
            best_chains = candidate_chains
            best_stats = candidate_stats
            no_gain_streak = 0
        else:
            no_gain_streak += 1

        score_history.append(best_score)

        if iteration % 10 == 0:
            log(
                f"[iter {iteration}] best={best_score:.2f} "
                f"chain_fire={best_stats.chain_fire_rate:.1%} "
                f"no_gain_streak={no_gain_streak}",
                "info",
            )

    # ------------------------------------------------------------------
    # 7. Write best deck back to decklist.txt
    # ------------------------------------------------------------------
    log("Writing optimised deck to decklist.txt...", "info")
    _write_decklist(best_deck, decklist_path, best_stats, swaps_applied)

    # ------------------------------------------------------------------
    # 8. Build result
    # ------------------------------------------------------------------
    result.success = True
    result.iterations = iteration
    result.restarts = restarts
    result.final_score = best_score
    result.delta = best_score - result.initial_score
    result.final_stats = best_stats
    result.swaps_applied = swaps_applied
    result.convergence_reason = convergence_reason

    log(
        f"Done. {iteration} iters, {restarts} restarts. "
        f"Score {result.initial_score:.2f} → {result.final_score:.2f} "
        f"(+{result.delta:.2f})",
        "success",
    )
    _log_stats(best_stats, "Final", log)

    return result


# =============================================================================
# Output helpers
# =============================================================================

def _log_stats(
    stats: GoldfishStats,
    label: str,
    log: Callable[[str, str], None],
) -> None:
    log(
        f"{label}: score={stats.overall_score:.2f} "
        f"chain_fire={stats.chain_fire_rate:.1%} "
        f"curve={stats.perfect_curve_rate:.1%} "
        f"keeper={stats.keeper_rate:.1%} "
        f"avg_kill_T={stats.avg_kill_turn:.2f} "
        f"stddev={stats.kill_turn_stddev:.2f}",
        "info",
    )
    fm = stats.failure_modes
    total = sum(fm.values()) or 1
    log(
        f"  failure modes — mana_screw={fm.get('mana_screw',0)/total:.1%} "
        f"missing_pieces={fm.get('missing_pieces',0)/total:.1%} "
        f"slow_chain={fm.get('slow_chain',0)/total:.1%} "
        f"success={fm.get('success',0)/total:.1%}",
        "info",
    )


def _write_decklist(
    deck: List[Dict],
    path: Path,
    stats: GoldfishStats,
    swaps: List[Tuple[str, str]],
) -> None:
    """Write the optimised deck back to decklist.txt in MTGA format."""
    from collections import Counter
    counts = Counter(c["name"] for c in deck if not c["is_land"])
    land_counts = Counter(c["name"] for c in deck if c["is_land"])

    lines = [
        f"// Autoresearch optimised deck",
        f"// Score: {stats.overall_score:.2f} | "
        f"Chain fire: {stats.chain_fire_rate:.1%} | "
        f"Curve: {stats.perfect_curve_rate:.1%} | "
        f"Keeper: {stats.keeper_rate:.1%}",
        f"// Avg kill turn: {stats.avg_kill_turn:.2f} "
        f"(stddev {stats.kill_turn_stddev:.2f})",
    ]
    if swaps:
        lines.append(f"// Swaps applied: {len(swaps)}")
        for rem, add in swaps:
            lines.append(f"//   - {rem} → + {add}")
    lines += ["", "Deck"]
    for name, qty in sorted(counts.items()):
        lines.append(f"{qty} {name}")
    if land_counts:
        lines.append("")
        for name, qty in sorted(land_counts.items()):
            lines.append(f"{qty} {name}")
    lines += ["", "Sideboard", ""]
    path.write_text("\n".join(lines), encoding="utf-8")


# =============================================================================
# Dev/debug entry point  (not the real interface — GUI calls run_autoresearch)
# =============================================================================

if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser(
        description="Goldfish autoresearch — dev/debug runner."
    )
    p.add_argument("deck_dir", help="Path to deck directory")
    p.add_argument("--colors", default="", help="WUBRG color identity")
    p.add_argument("--hands", type=int, default=N_HANDS)
    p.add_argument("--turns", type=int, default=N_TURNS)
    p.add_argument("--on-draw", action="store_true")
    p.add_argument("--seed", type=int, default=None)
    args = p.parse_args()

    if args.seed is not None:
        random.seed(args.seed)

    r = run_autoresearch(
        args.deck_dir,
        args.colors,
        n_hands=args.hands,
        n_turns=args.turns,
        on_play=not args.on_draw,
    )
    sys.exit(0 if r.success else 1)
