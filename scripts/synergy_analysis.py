#!/usr/bin/env python3
"""
Synergy Analysis — Gate 2.5 Automation

Reads a card list (from a session.md candidate pool, a decklist.txt, a pool
CSV file, or a plain text file) and produces a Gate 2.5 synergy report:

  - Builds a directional synergy profile for every card (source vs. payoff tags,
    creature subtypes, keywords, CMC, oracle text)
  - Scores pairwise interactions in five passes:
      Pass 1 — Rule-based tag matching (source_tags -> payoff_tags)
      Pass 2 — Oracle text cross-reference (subtype + keyword verification)
      Pass 2b — Oracle payoff bridges (life-gain drain, food, tribe triggers)
      Pass 3 — CMC-bracket-aware REDUNDANT detection (narrow roles only)
      Pass 4 — Oracle-text dependency scoring (Auras, Equipment, conditionals)
  - Role-aware scoring: engine / enabler / payoff / support / interaction
  - DENSITY-FIRST composite scoring: "works well with THIS pool" beats
    "generically good card"
  - Checks all Gate 2.5 thresholds with pool-vs-deck calibration
  - Writes a pre-populated Gate 2.5 markdown block you can paste into session.md

Usage:
    python scripts/synergy_analysis.py Decks/2026-04-03_My_Deck/session.md
    python scripts/synergy_analysis.py Decks/2026-04-03_My_Deck/decklist.txt
    python scripts/synergy_analysis.py decklist.txt --include-sideboard
    python scripts/synergy_analysis.py Decks/2026-04-03_My_Deck/ --format pools
    python scripts/synergy_analysis.py my_candidates.txt --format names
    python scripts/synergy_analysis.py session.md --output report.md
    python scripts/synergy_analysis.py decklist.txt --mode deck
    python scripts/synergy_analysis.py decklist.txt --primary-axis lifegain,token
    python scripts/synergy_analysis.py decklist.txt --report-format json
    python scripts/synergy_analysis.py decklist.txt --verbose

Exit codes:
    0  All Gate 2.5 thresholds passed
    1  One or more thresholds failed (or inconclusive)
    2  Input file not found or no cards extracted
"""

import argparse
import io
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Set

# Ensure stdout can handle Unicode on Windows (cp1252 consoles choke on ≥, →, etc.)
if sys.stdout.encoding and sys.stdout.encoding.lower().replace("-", "") != "utf8":
    sys.stdout = io.TextIOWrapper(
        sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True,
    )

sys.path.insert(0, str(Path(__file__).resolve().parent))

from mtg_utils import RepoPaths
from synergy_engine import (
    load_cards_from_db,
    score_pairwise,
    extract_names_from_session,
    extract_names_from_decklist,  # noqa: F401 — re-exported for backward compat
    extract_deck_entries_from_decklist,
    attach_card_data,
    extract_names_from_pools,
    extract_names_from_text,
)
from synergy_thresholds import check_thresholds
from synergy_report import build_markdown_report, build_json_report, build_top_n_csv
from synergy_types import CompositeWeights


# ═════════════════════════════════════════════════════════════════════════════
# CLI entry point
# ═════════════════════════════════════════════════════════════════════════════

def main() -> None:
    # 1. Parse arguments
    args = _parse_args()

    # 2. Load input
    input_path = Path(args.input_file)
    if not input_path.exists():
        print(f"ERROR: {input_path} not found.", file=sys.stderr)
        sys.exit(2)

    content = input_path.read_text(encoding="utf-8") if input_path.is_file() else ""

    # 3. Detect format
    fmt = _detect_format(args.format, input_path, content)

    # 4. Extract entries
    entries = _extract_entries(fmt, input_path, content, args.include_sideboard)

    # 5. Deduplicate names
    seen: Set[str] = set()
    unique_names: list[str] = []
    for e in entries:
        if e["name"].lower() not in seen:
            seen.add(e["name"].lower())
            unique_names.append(e["name"])

    if not unique_names:
        print("ERROR: No card names extracted from input.", file=sys.stderr)
        sys.exit(2)

    print(f"Loaded {len(unique_names)} unique cards from {input_path.name}",
          file=sys.stderr)
    print("Looking up card data in local database...", file=sys.stderr)

    # 6. Load card data
    paths = RepoPaths()
    card_data = load_cards_from_db(unique_names, paths)
    annotated_entries, missing = attach_card_data(entries, card_data)
    missing_main = [e["name"] for e in missing if e["section"] == "main"]
    not_found = [e["name"] for e in missing]

    if not_found:
        print(f"  {len(not_found)} card(s) not found in DB: "
              f"{', '.join(not_found[:5])}", file=sys.stderr)

    # 7. Determine mode
    effective_mode = args.mode
    if effective_mode == "auto":
        effective_mode = "pool" if len(unique_names) > 40 else "deck"

    inconclusive = False
    if effective_mode == "deck" and missing_main and not args.allow_missing:
        inconclusive = True
        print(f"[WARN] {len(missing_main)} maindeck card(s) missing "
              f"— result INCONCLUSIVE.", file=sys.stderr)

    # 8. Score
    print("Scoring pairwise synergies "
          "(single-pass: tag + oracle + bridges + redundant + dependency)...",
          file=sys.stderr)
    scores = score_pairwise(annotated_entries, primary_axis=args.primary_axis)

    # 9. Check thresholds
    all_passed, threshold_results = check_thresholds(scores, args.mode)

    # 10. Generate report
    if args.report_format == "json":
        report = build_json_report(
            scores, threshold_results, all_passed,
            str(input_path), not_found, args.mode, inconclusive,
        )
    else:
        report = build_markdown_report(
            scores, threshold_results, all_passed,
            str(input_path), not_found, args.mode, inconclusive,
        )

    # 11. Output
    if args.output:
        Path(args.output).write_text(report, encoding="utf-8")
        print(f"Report written to {args.output}", file=sys.stderr)
    else:
        print(report)

    # 12. Top-N CSV export
    if args.top and args.top > 0:
        csv_content = build_top_n_csv(scores, args.top)
        top_path = (
            (Path(args.output).parent if args.output else input_path.parent)
            / f"top_{args.top}.csv"
        )
        top_path.write_text(csv_content, encoding="utf-8")
        print(f"Top {args.top} cards written to {top_path}", file=sys.stderr)

    sys.exit(0 if (all_passed and not inconclusive) else 1)


# ═════════════════════════════════════════════════════════════════════════════
# Argument parsing
# ═════════════════════════════════════════════════════════════════════════════

def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Gate 2.5 synergy analysis "
                    "— role-aware, oracle-verified, density-first.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument("input_file",
                   help="session.md, decklist.txt, pools/ dir, or names list")
    p.add_argument("--format",
                   choices=["auto", "session", "decklist", "names", "pools"],
                   default="auto",
                   help="Input format (default: auto-detect)")
    p.add_argument("--output",
                   help="Write report to this file (default: stdout)")
    p.add_argument("--mode",
                   choices=["auto", "pool", "deck"], default="auto",
                   help="Threshold calibration: pool, deck, or auto (default)")
    p.add_argument("--top", type=int, default=0, metavar="N",
                   help="Write top-N CSV ranked by composite synergy score.")
    p.add_argument("--include-sideboard", action="store_true",
                   help="Include sideboard cards in scoring.")
    p.add_argument("--allow-missing", action="store_true",
                   help="Skip inconclusive guard when maindeck cards "
                        "are missing from DB.")
    p.add_argument("--primary-axis", default="",
                   help="Comma-separated mechanic override, "
                        "e.g. lifegain,token,sacrifice")
    # New flags
    p.add_argument("--report-format",
                   choices=["markdown", "json"], default="markdown",
                   help="Output format: markdown (default) or json")
    p.add_argument("--verbose", action="store_true",
                   help="Show per-pair interaction details in stderr")
    # Weight customization flags
    p.add_argument("--weight-engine-density", type=float, default=40.0,
                   help="Weight for engine density (default: 40.0)")
    p.add_argument("--weight-synergy-density", type=float, default=25.0,
                   help="Weight for synergy density (default: 25.0)")
    p.add_argument("--weight-raw-interactions-cap", type=float, default=20.0,
                   help="Cap for raw interactions weight (default: 20.0)")
    p.add_argument("--weight-role-breadth", type=float, default=3.0,
                   help="Weight for role breadth (default: 3.0)")
    p.add_argument("--weight-oracle-confirmed", type=float, default=2.0,
                   help="Weight for oracle confirmed interactions (default: 2.0)")
    p.add_argument("--weights-config", type=str, default="",
                   help="JSON config file overriding weight defaults")
    # Legacy flags (kept for backward compat, ignored)
    p.add_argument("--min-synergy", type=float, default=3.0,
                   help=argparse.SUPPRESS)
    p.add_argument("--score-mode",
                   choices=["legacy", "role-aware"], default="role-aware",
                   help=argparse.SUPPRESS)
    return p.parse_args()


# ═════════════════════════════════════════════════════════════════════════════
# Format detection
# ═════════════════════════════════════════════════════════════════════════════

def _detect_format(fmt: str, input_path: Path, content: str) -> str:
    """Auto-detect input format from filename and content heuristics."""
    if fmt != "auto":
        return fmt
    if "session.md" in input_path.name.lower() \
            or "# Deck Building Session" in content:
        return "session"
    if input_path.is_dir() or (input_path.parent / "pools").exists():
        return "pools"
    if "Deck\n" in content or content.strip().startswith("Deck"):
        return "decklist"
    return "names"


# ═════════════════════════════════════════════════════════════════════════════
# Entry extraction
# ═════════════════════════════════════════════════════════════════════════════

def _extract_entries(fmt: str, input_path: Path, content: str,
                     include_sideboard: bool) -> List[Dict[str, Any]]:
    """Dispatch to the appropriate extraction function based on format."""
    if fmt == "decklist":
        return extract_deck_entries_from_decklist(
            input_path, include_sideboard=include_sideboard,
        )
    if fmt == "session":
        return [{"name": n, "qty": 1, "section": "pool"}
                for n in extract_names_from_session(content)]
    if fmt == "pools":
        return [{"name": n, "qty": 1, "section": "pool"}
                for n in extract_names_from_pools(input_path)]
    # fmt == "names"
    return [{"name": n, "qty": 1, "section": "pool"}
            for n in extract_names_from_text(content)]


if __name__ == "__main__":
    main()
