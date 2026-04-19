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
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

_THIS = Path(__file__).resolve()
_SCRIPTS = _THIS.parent
_ROOT = _SCRIPTS.parent

sys.path.insert(0, str(_SCRIPTS))
from mtg_utils import RepoPaths  # noqa: E402

_PATHS = RepoPaths()


def _run(
    label: str,
    cmd: list[str],
    *,
    fatal_codes: set[int] | None = None,
    cwd: Path | None = None,
) -> int:
    fatal_codes = fatal_codes or set()
    print(f"\n{'='*70}", flush=True)
    print(f"  [{label}]", flush=True)
    print(f"  $ {' '.join(str(c) for c in cmd)}", flush=True)
    print(f"{'='*70}", flush=True)

    result = subprocess.run(cmd, cwd=str(cwd or _ROOT))
    code = result.returncode
    status = "OK" if code == 0 else f"EXIT {code}"
    print(f"\n  [{label}] finished — {status}", flush=True)

    if code in fatal_codes:
        print(f"\nFATAL: {label} returned exit code {code}. Aborting.", file=sys.stderr)
        sys.exit(code)

    return code


def _effective_primary_axis(args: argparse.Namespace) -> str:
    axes: list[str] = []
    seen: set[str] = set()

    def add_axis(value: str) -> None:
        v = value.strip().lower()
        if v and v not in seen:
            seen.add(v)
            axes.append(v)

    if args.primary_axis:
        for x in args.primary_axis.split(","):
            add_axis(x)

    if args.archetype:
        for a in args.archetype:
            if a == "tribal":
                continue
            add_axis(a)

    if args.tribe:
        for tribe in args.tribe:
            add_axis(tribe)

    return ",".join(axes)


def phase_scaffold(args: argparse.Namespace) -> Path:
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

    _run("SCAFFOLD", cmd, fatal_codes={1, 2})

    if args.deck_dir:
        deck_dir = Path(args.deck_dir)
    else:
        deck_dir = _resolve_latest_deck_dir(args)

    if not deck_dir or not deck_dir.exists():
        print("ERROR: Could not locate deck directory after scaffold.", file=sys.stderr)
        sys.exit(1)

    return deck_dir


def phase_synergy(deck_dir: Path, args: argparse.Namespace) -> int:
    script = _PATHS.scripts_dir / "synergy_analysis.py"
    pool_csv = deck_dir / "candidate_pool.csv"
    session_md = deck_dir / "session.md"
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

    effective_axis = _effective_primary_axis(args)
    if effective_axis:
        cmd += ["--primary-axis", effective_axis]

    return _run("SYNERGY", cmd, fatal_codes={2})


def phase_auto_build(deck_dir: Path, args: argparse.Namespace) -> int:
    from auto_build import merge_scores_into_candidate_pool, auto_build_decklist

    colors = args.colors or _infer_colors(deck_dir)
    if not colors:
        print("ERROR: --colors required for auto-build phase.", file=sys.stderr)
        sys.exit(3)

    print(f"\n{'='*70}")
    print("  [AUTO-BUILD]")
    print(f"  deck_dir : {deck_dir}")
    print(f"  colors   : {colors}")
    if args.tribe:
        print(f"  tribe    : {', '.join(args.tribe)}")
    print(f"{'='*70}")

    changed, count = merge_scores_into_candidate_pool(str(deck_dir))
    print(f"  merge_scores: changed={changed}, pool_rows={count}")

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

    print(f"\n  ERR  {summary}", file=sys.stderr)
    sys.exit(3)


def phase_validate(deck_dir: Path) -> int:
    script = _PATHS.scripts_dir / "validate_decklist.py"
    decklist = deck_dir / "decklist.txt"

    if not decklist.exists():
        print(f"ERROR: {decklist} not found — auto-build may have failed.", file=sys.stderr)
        sys.exit(4)

    cmd = [sys.executable, str(script), str(decklist), "--verbose"]
    return _run("VALIDATE", cmd, fatal_codes={1, 3, 4})


def phase_goldfish(deck_dir: Path, args: argparse.Namespace) -> int:
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


def _resolve_latest_deck_dir(args: argparse.Namespace) -> Path | None:
    decks_root = _PATHS.decks_dir
    if not decks_root.exists():
        return None

    if args.name:
        slug = args.name.replace(" ", "_").replace("/", "_")
        candidates = sorted(decks_root.glob(f"*_{slug}"), reverse=True)
        if candidates:
            return candidates[0]

    all_dirs = sorted(
        (d for d in decks_root.iterdir() if d.is_dir()),
        key=lambda d: d.stat().st_mtime,
        reverse=True,
    )
    return all_dirs[0] if all_dirs else None


def _infer_colors(deck_dir: Path) -> str:
    session = deck_dir / "session.md"
    if not session.exists():
        return ""
    for line in session.read_text(encoding="utf-8").splitlines():
        if line.startswith("**Colors:**"):
            raw = line.split(":", 1)[-1].strip()
            return raw.replace("/", "").replace(" ", "")
    return ""


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="goldfish_autoresearch_cli.py",
        description="Full deck pipeline: scaffold → synergy → build → validate → goldfish.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    g = p.add_argument_group("Deck identity")
    g.add_argument("--name", help="Deck name")
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
    g.add_argument("--tribe", nargs="+", metavar="SUBTYPE", help="Creature subtype(s) for tribal builds")
    g.add_argument("--extra-tags", help="Extra search tags, comma-separated")
    g.add_argument("--wildcard", action="store_true", help="Suppress tribal --name filter")

    g2 = p.add_argument_group("Phase control")
    g2.add_argument("--deck-dir", help="Skip scaffold: use existing deck directory")
    g2.add_argument("--skip-scaffold", action="store_true", help="Skip Phase 1 (requires --deck-dir)")
    g2.add_argument("--skip-synergy", action="store_true", help="Skip Phase 2 synergy scoring")
    g2.add_argument("--skip-build", action="store_true", help="Skip Phase 3 auto-build")
    g2.add_argument("--skip-validate", action="store_true", help="Skip Phase 4 validation")
    g2.add_argument("--skip-goldfish", action="store_true", help="Skip Phase 5 goldfish simulation")
    g2.add_argument("--skip-queries", action="store_true", help="Pass --skip-queries to scaffold")

    g3 = p.add_argument_group("Synergy options")
    g3.add_argument("--primary-axis", default="", help="Comma-separated mechanic override")
    g3.add_argument("--top-n", type=int, default=200, metavar="N", help="Top-N cards exported to top_N.csv")

    g4 = p.add_argument_group("Auto-build options")
    g4.add_argument("--focus", nargs="+", metavar="CARD", help="Card name(s) to lock into the mainboard")

    g5 = p.add_argument_group("Goldfish simulation options")
    g5.add_argument("--hands", type=int, default=2000, help="Number of hands to simulate")
    g5.add_argument("--turns", type=int, default=6, help="Turns per hand")
    g5.add_argument("--min-keep-lands", type=int, default=2, metavar="N", help="Min lands to keep opener")
    g5.add_argument("--max-keep-lands", type=int, default=5, metavar="N", help="Max lands to keep opener")
    g5.add_argument("--seed", type=int, default=None, metavar="INT", help="Random seed")

    return p


def main() -> None:
    args = _build_parser().parse_args()

    if args.skip_scaffold and not args.deck_dir:
        print("ERROR: --skip-scaffold requires --deck-dir.", file=sys.stderr)
        sys.exit(1)

    deck_dir: Path | None = Path(args.deck_dir) if args.deck_dir else None

    if not args.skip_scaffold:
        deck_dir = phase_scaffold(args)
        print(f"\n  Deck directory: {deck_dir}")
    else:
        print(f"\n  Using existing deck directory: {deck_dir}")

    assert deck_dir is not None

    if not args.skip_synergy:
        synergy_code = phase_synergy(deck_dir, args)
        if synergy_code != 0:
            print(
                f"  [SYNERGY] Thresholds not fully met (exit {synergy_code}) — continuing to build (non-fatal).",
                file=sys.stderr,
            )
    else:
        print("\n  [SYNERGY] Skipped.")

    if not args.skip_build:
        phase_auto_build(deck_dir, args)
    else:
        print("\n  [AUTO-BUILD] Skipped.")

    if not args.skip_validate:
        phase_validate(deck_dir)
    else:
        print("\n  [VALIDATE] Skipped — deck legality NOT confirmed.")

    if not args.skip_goldfish:
        phase_goldfish(deck_dir, args)
    else:
        print("\n  [GOLDFISH] Skipped.")

    print(f"\n{'='*70}")
    print("  PIPELINE COMPLETE")
    print(f"  Deck directory : {deck_dir}")
    print(f"  Decklist       : {deck_dir / 'decklist.txt'}")
    print(f"  Synergy report : {deck_dir / 'synergy_report.md'}")
    print(f"{'='*70}\n")


if __name__ == "__main__":
    main()
