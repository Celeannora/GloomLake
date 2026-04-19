#!/usr/bin/env python3
"""
Goldfish Autoresearch CLI — Karpathy-style self-contained research loop.

Orchestrates the full deck-building pipeline in a single command:

  Phase 1 — Scaffold   : generate_deck_scaffold.py  (candidate pool + session.md)
  Phase 2 — Synergy    : synergy_analysis.py         (Gate 2.5 scoring + top-N CSV)
  Phase 3 — Auto-build : auto_build.py               (60-card decklist from pool)
  Phase 4 — Validate   : validate_decklist.py        (legality + count check)
  Phase 5 — Goldfish   : goldfish.py                 (opening-hand simulation)

The script is fully agnostic — no card names, deck names, or colors are
hardcoded. Every parameter is supplied at runtime via CLI flags or the
interactive wizard in generate_deck_scaffold.py.

Usage:
    # Minimal — launches generate_deck_scaffold.py interactive wizard
    python scripts/goldfish_autoresearch_cli.py

    # Fully specified (non-interactive)
    python scripts/goldfish_autoresearch_cli.py \\
        --name "Esper Control" \\
        --colors WUB \\
        --archetype control lifegain \\
        --primary-axis lifegain,token \\
        --hands 2000 --turns 6

    # Skip phases you've already run
    python scripts/goldfish_autoresearch_cli.py \\
        --deck-dir Decks/2026-04-19_Esper_Control \\
        --skip-scaffold --skip-synergy \\
        --hands 1000

    # Aggro / burn archetype overrides
    python scripts/goldfish_autoresearch_cli.py \\
        --name "Boros Burn" --colors WR --archetype burn \\
        --min-keep-lands 1 --max-keep-lands 4

Exit codes:
    0   All phases passed
    1   Scaffold failed
    2   Synergy thresholds not met (non-fatal — build continues)
    3   Auto-build failed
    4   Validation failed  ← deck is NOT legal, do not use
    5   Goldfish simulation failed (non-fatal)
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Repo root resolution — works whether run from repo root or scripts/
# ---------------------------------------------------------------------------
_THIS = Path(__file__).resolve()
_SCRIPTS = _THIS.parent
_ROOT = _SCRIPTS.parent

sys.path.insert(0, str(_SCRIPTS))
from mtg_utils import RepoPaths  # noqa: E402

_PATHS = RepoPaths()


# ---------------------------------------------------------------------------
# Subprocess helper
# ---------------------------------------------------------------------------

def _run(
    label: str,
    cmd: list[str],
    *,
    fatal_codes: set[int] | None = None,
    cwd: Path | None = None,
) -> int:
    """Run *cmd*, stream output live, return exit code.

    If the exit code is in *fatal_codes* the process exits immediately.
    Pass ``fatal_codes=None`` to treat all non-zero exits as warnings only.
    """
    fatal_codes = fatal_codes or set()
    print(f"\n{'='*70}", flush=True)
    print(f"  [{label}]", flush=True)
    print(f"  $ {' '.join(str(c) for c in cmd)}", flush=True)
    print(f"{'='*70}", flush=True)

    result = subprocess.run(
        cmd,
        cwd=str(cwd or _ROOT),
    )
    code = result.returncode
    status = "OK" if code == 0 else f"EXIT {code}"
    print(f"\n  [{label}] finished — {status}", flush=True)

    if code in fatal_codes:
        print(f"\nFATAL: {label} returned exit code {code}. Aborting.", file=sys.stderr)
        sys.exit(code)

    return code


# ---------------------------------------------------------------------------
# Phase runners
# ---------------------------------------------------------------------------

def phase_scaffold(args: argparse.Namespace) -> Path:
    """Phase 1 — run generate_deck_scaffold.py, return deck_dir."""
    script = _PATHS.scripts_dir / "generate_deck_scaffold.py"
    cmd = [sys.executable, str(script)]

    if args.name:
        cmd += ["--name", args.name]
    if args.colors:
        cmd += ["--colors", args.colors]
    if args.archetype:
        cmd += ["--archetype"] + args.archetype
    if args.tribe:
        cmd += ["--tribe"] + args.tribe
    if args.extra_tags:
        cmd += ["--extra-tags", args.extra_tags]
    if args.skip_queries:
        cmd += ["--skip-queries"]
    if args.wildcard:
        cmd += ["--wildcard"]

    code = _run("SCAFFOLD", cmd, fatal_codes={1, 2})

    # Resolve the deck directory that was just created
    if args.deck_dir:
        deck_dir = Path(args.deck_dir)
    else:
        deck_dir = _resolve_latest_deck_dir(args)

    if not deck_dir or not deck_dir.exists():
        print(
            "ERROR: Could not locate deck directory after scaffold.",
            file=sys.stderr,
        )
        sys.exit(1)

    return deck_dir


def phase_synergy(deck_dir: Path, args: argparse.Namespace) -> int:
    """Phase 2 — run synergy_analysis.py on candidate_pool.csv, write top-200.csv."""
    script = _PATHS.scripts_dir / "synergy_analysis.py"
    pool_csv = deck_dir / "candidate_pool.csv"
    session_md = deck_dir / "session.md"

    # Prefer session.md (richer context) if it exists, fall back to pool CSV
    input_file = session_md if session_md.exists() else pool_csv

    if not input_file.exists():
        print(f"WARN: {input_file} not found — skipping synergy phase.", file=sys.stderr)
        return 1

    top_n = args.top_n
    output_report = deck_dir / "synergy_report.md"

    cmd = [
        sys.executable, str(script),
        str(input_file),
        "--mode", "pool",
        "--top", str(top_n),
        "--output", str(output_report),
    ]
    if args.primary_axis:
        cmd += ["--primary-axis", args.primary_axis]

    # Exit 1 = thresholds not met (non-fatal), exit 2 = file not found (fatal)
    return _run("SYNERGY", cmd, fatal_codes={2})


def phase_auto_build(deck_dir: Path, args: argparse.Namespace) -> int:
    """Phase 3 — merge top-N scores into pool then call auto_build_decklist()."""
    # auto_build.py is a library — call via the scaffold_gui integration path
    # which exposes auto_build_decklist as a CLI via scaffold_gui.py --auto-build
    # Alternatively use the module directly via -c
    from auto_build import merge_scores_into_candidate_pool, auto_build_decklist

    colors = args.colors or _infer_colors(deck_dir)
    if not colors:
        print("ERROR: --colors required for auto-build phase.", file=sys.stderr)
        sys.exit(3)

    print(f"\n{'='*70}")
    print("  [AUTO-BUILD]")
    print(f"  deck_dir : {deck_dir}")
    print(f"  colors   : {colors}")
    print(f"{'='*70}")

    # Step 3a — merge synergy scores into candidate_pool.csv
    changed, count = merge_scores_into_candidate_pool(str(deck_dir))
    print(f"  merge_scores: changed={changed}, pool_rows={count}")

    # Step 3b — build decklist
    ok, summary, focus_log = auto_build_decklist(
        str(deck_dir),
        colors,
        focus_cards=args.focus or [],
    )

    for msg, level in focus_log:
        tag = {"info": "INFO", "warn": "WARN", "error": "ERR ", "success": " OK "}.get(level, "    ")
        print(f"  [{tag}] {msg}")

    if ok:
        print(f"\n   OK  {summary}")
        return 0
    else:
        print(f"\n  ERR  {summary}", file=sys.stderr)
        sys.exit(3)


def phase_validate(deck_dir: Path) -> int:
    """Phase 4 — validate_decklist.py. Exit 4 on failure."""
    script = _PATHS.scripts_dir / "validate_decklist.py"
    decklist = deck_dir / "decklist.txt"

    if not decklist.exists():
        print(f"ERROR: {decklist} not found — auto-build may have failed.", file=sys.stderr)
        sys.exit(4)

    cmd = [sys.executable, str(script), str(decklist), "--verbose"]
    code = _run("VALIDATE", cmd, fatal_codes={1, 3, 4})
    return code


def phase_goldfish(deck_dir: Path, args: argparse.Namespace) -> int:
    """Phase 5 — goldfish.py simulation."""
    script = _PATHS.scripts_dir / "goldfish.py"
    decklist = deck_dir / "decklist.txt"

    if not decklist.exists():
        print(f"WARN: {decklist} not found — skipping goldfish.", file=sys.stderr)
        return 5

    cmd = [
        sys.executable, str(script),
        str(decklist),
        "--hands", str(args.hands),
        "--turns", str(args.turns),
        "--min-keep-lands", str(args.min_keep_lands),
        "--max-keep-lands", str(args.max_keep_lands),
    ]
    if args.focus:
        cmd += ["--focus"] + args.focus
    if args.seed is not None:
        cmd += ["--seed", str(args.seed)]

    return _run("GOLDFISH", cmd)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _resolve_latest_deck_dir(args: argparse.Namespace) -> Path | None:
    """Find the most-recently-created deck folder matching the given name."""
    decks_root = _PATHS.decks_dir
    if not decks_root.exists():
        return None

    if args.name:
        slug = args.name.replace(" ", "_").replace("/", "_")
        candidates = sorted(decks_root.glob(f"*_{slug}"), reverse=True)
        if candidates:
            return candidates[0]

    # Fall back to the newest folder overall
    all_dirs = sorted(
        (d for d in decks_root.iterdir() if d.is_dir()),
        key=lambda d: d.stat().st_mtime,
        reverse=True,
    )
    return all_dirs[0] if all_dirs else None


def _infer_colors(deck_dir: Path) -> str:
    """Try to read colors from session.md front-matter."""
    session = deck_dir / "session.md"
    if not session.exists():
        return ""
    for line in session.read_text(encoding="utf-8").splitlines():
        if line.startswith("**Colors:**"):
            raw = line.split(":", 1)[-1].strip()
            return raw.replace("/", "").replace(" ", "")
    return ""


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="goldfish_autoresearch_cli.py",
        description="Full deck pipeline: scaffold → synergy → build → validate → goldfish.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    # ── Identity ──────────────────────────────────────────────────────────────
    g = p.add_argument_group("Deck identity")
    g.add_argument("--name", help="Deck name (e.g. 'Esper Control')")
    g.add_argument("--colors", help="Color identity, e.g. WUB, GU, WR")
    g.add_argument(
        "--archetype", nargs="+",
        choices=sorted([
            "aggro", "midrange", "control", "combo", "opp_mill", "self_mill",
            "reanimation", "lifegain", "tribal", "ramp", "tempo", "burn",
            "aristocrats", "tokens", "blink", "stax", "storm", "prowess",
            "enchantress", "artifacts", "equipment", "voltron", "landfall",
            "lands", "infect", "proliferate", "energy", "graveyard",
            "flashback", "madness", "superfriends", "extra_turns", "eldrazi",
            "vehicles", "domain",
        ]),
        metavar="ARCHETYPE",
        help="One or more archetypes",
    )
    g.add_argument("--tribe", nargs="+", metavar="SUBTYPE",
                   help="Creature subtype(s) for tribal builds")
    g.add_argument("--extra-tags", help="Extra search tags, comma-separated")
    g.add_argument("--wildcard", action="store_true",
                   help="Suppress tribal --name filter (tribe as hint only)")

    # ── Phase control ─────────────────────────────────────────────────────────
    g2 = p.add_argument_group("Phase control")
    g2.add_argument("--deck-dir",
                    help="Skip scaffold: use existing deck directory")
    g2.add_argument("--skip-scaffold", action="store_true",
                    help="Skip Phase 1 (requires --deck-dir)")
    g2.add_argument("--skip-synergy", action="store_true",
                    help="Skip Phase 2 synergy scoring")
    g2.add_argument("--skip-build", action="store_true",
                    help="Skip Phase 3 auto-build")
    g2.add_argument("--skip-validate", action="store_true",
                    help="Skip Phase 4 validation (NOT recommended)")
    g2.add_argument("--skip-goldfish", action="store_true",
                    help="Skip Phase 5 goldfish simulation")
    g2.add_argument("--skip-queries", action="store_true",
                    help="Pass --skip-queries to scaffold (offline template)")

    # ── Synergy options ───────────────────────────────────────────────────────
    g3 = p.add_argument_group("Synergy options")
    g3.add_argument("--primary-axis", default="",
                    help="Comma-separated mechanic override, e.g. lifegain,token")
    g3.add_argument("--top-n", type=int, default=200, metavar="N",
                    help="Top-N cards exported to top_N.csv (default: 200)")

    # ── Auto-build options ────────────────────────────────────────────────────
    g4 = p.add_argument_group("Auto-build options")
    g4.add_argument("--focus", nargs="+", metavar="CARD",
                    help="Card name(s) to lock into the mainboard")

    # ── Goldfish options ──────────────────────────────────────────────────────
    g5 = p.add_argument_group("Goldfish simulation options")
    g5.add_argument("--hands", type=int, default=2000,
                    help="Number of hands to simulate (default: 2000)")
    g5.add_argument("--turns", type=int, default=6,
                    help="Turns per hand (default: 6)")
    g5.add_argument("--min-keep-lands", type=int, default=2, metavar="N",
                    help="Min lands to keep opener (default: 2)")
    g5.add_argument("--max-keep-lands", type=int, default=5, metavar="N",
                    help="Max lands to keep opener (default: 5)")
    g5.add_argument("--seed", type=int, default=None, metavar="INT",
                    help="Random seed for reproducible goldfish output")

    return p


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    args = _build_parser().parse_args()

    # Validate skip-scaffold requires deck-dir
    if args.skip_scaffold and not args.deck_dir:
        print("ERROR: --skip-scaffold requires --deck-dir.", file=sys.stderr)
        sys.exit(1)

    deck_dir: Path | None = Path(args.deck_dir) if args.deck_dir else None

    # ── Phase 1: Scaffold ────────────────────────────────────────────────────
    if not args.skip_scaffold:
        deck_dir = phase_scaffold(args)
        print(f"\n  Deck directory: {deck_dir}")
    else:
        print(f"\n  Using existing deck directory: {deck_dir}")

    assert deck_dir is not None

    # ── Phase 2: Synergy ─────────────────────────────────────────────────────
    if not args.skip_synergy:
        synergy_code = phase_synergy(deck_dir, args)
        if synergy_code != 0:
            print(
                f"  [SYNERGY] Thresholds not fully met (exit {synergy_code}) — "
                "continuing to build (non-fatal).",
                file=sys.stderr,
            )
    else:
        print("\n  [SYNERGY] Skipped.")

    # ── Phase 3: Auto-build ──────────────────────────────────────────────────
    if not args.skip_build:
        phase_auto_build(deck_dir, args)
    else:
        print("\n  [AUTO-BUILD] Skipped.")

    # ── Phase 4: Validate ────────────────────────────────────────────────────
    if not args.skip_validate:
        phase_validate(deck_dir)
    else:
        print("\n  [VALIDATE] Skipped — deck legality NOT confirmed.")

    # ── Phase 5: Goldfish ────────────────────────────────────────────────────
    if not args.skip_goldfish:
        phase_goldfish(deck_dir, args)
    else:
        print("\n  [GOLDFISH] Skipped.")

    print(f"\n{'='*70}")
    print(f"  PIPELINE COMPLETE")
    print(f"  Deck directory : {deck_dir}")
    print(f"  Decklist       : {deck_dir / 'decklist.txt'}")
    print(f"  Synergy report : {deck_dir / 'synergy_report.md'}")
    print(f"{'='*70}\n")


if __name__ == "__main__":
    main()
