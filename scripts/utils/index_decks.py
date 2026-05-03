#!/usr/bin/env python3
"""
Deck Index Generator

Scans the Decks/ directory and auto-generates Decks/_INDEX.md with a
machine-readable registry of all published decks.

Usage:
    python scripts/index_decks.py

Output:
    Decks/_INDEX.md

Run this after adding a new deck to keep the index current.
Also called automatically by the CI workflow.
"""

import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional


# Regex to extract key fields from decklist.txt
QTY_RE = re.compile(r"^\s*(\d+)\s+(.+?)(?:\s+\([A-Z0-9]+\)\s*\d+)?\s*$")


def parse_decklist_meta(decklist_path: Path) -> Dict:
    """
    Extract basic metadata from a decklist.txt:
    - total mainboard count
    - total sideboard count
    - color identity (inferred from filename/analysis.md if available)
    """
    mainboard_count = 0
    sideboard_count = 0
    section = "main"

    try:
        with open(decklist_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("//") or line.startswith("#"):
                    continue
                if line.lower() == "deck":
                    section = "main"
                    continue
                if line.lower() == "sideboard":
                    section = "side"
                    continue
                m = QTY_RE.match(line)
                if m:
                    qty = int(m.group(1))
                    if section == "main":
                        mainboard_count += qty
                    else:
                        sideboard_count += qty
    except Exception:
        pass

    return {
        "mainboard": mainboard_count,
        "sideboard": sideboard_count,
    }


def extract_analysis_meta(analysis_path: Path) -> Dict:
    """
    Extract deck metadata from analysis.md:
    - Colors line
    - Archetype line
    - Win condition
    - Key cards (first 5 from per-card verification section)
    """
    meta = {
        "colors": "",
        "archetype": "",
        "win_condition": "",
        "format": "Standard",
        "key_cards": [],
    }

    if not analysis_path.exists():
        return meta

    try:
        content = analysis_path.read_text(encoding="utf-8")
        lines = content.splitlines()

        for i, line in enumerate(lines):
            ll = line.lower()

            # Colors: look for "**Colors:**" or "**colors:**"
            if "**colors:**" in ll:
                meta["colors"] = line.split(":", 1)[-1].strip().strip("*").strip()

            # Archetype
            elif "**archetype:**" in ll or "archetype:" in ll:
                meta["archetype"] = line.split(":", 1)[-1].strip().strip("*").strip()

            # Format
            elif "**format:**" in ll:
                meta["format"] = line.split(":", 1)[-1].strip().strip("*").strip()

            # Win condition — grab the sentence after the header
            elif "win condition" in ll and "**" in line:
                # Look ahead for the actual text
                for j in range(i + 1, min(i + 5, len(lines))):
                    candidate = lines[j].strip()
                    if candidate and not candidate.startswith("#"):
                        # Strip markdown bold/emphasis
                        clean = re.sub(r"\*+", "", candidate).strip()
                        if clean:
                            meta["win_condition"] = clean[:120]
                            break

            # Key cards from Per-Card Verification section (✓ lines)
            elif line.startswith("✓ ") and len(meta["key_cards"]) < 5:
                # "✓ Card Name (x4) — ..."
                card_match = re.match(r"✓\s+(.+?)\s+\(x\d+\)", line)
                if card_match:
                    meta["key_cards"].append(card_match.group(1))

    except Exception:
        pass

    return meta


def scan_decks(decks_dir: Path) -> List[Dict]:
    """Scan Decks/ and return metadata list, sorted by date descending."""
    entries: List[Dict] = []

    for deck_folder in sorted(decks_dir.iterdir(), reverse=True):
        if not deck_folder.is_dir():
            continue
        if deck_folder.name.startswith(".") or deck_folder.name.startswith("_"):
            continue

        folder_name = deck_folder.name
        decklist = deck_folder / "decklist.txt"
        analysis = deck_folder / "analysis.md"
        sideboard_guide = deck_folder / "sideboard_guide.md"

        # Parse date and archetype from folder name: YYYY-MM-DD_Archetype_Name
        date_str = ""
        archetype_from_folder = folder_name
        date_match = re.match(r"^(\d{4}-\d{2}-\d{2})_(.+)$", folder_name)
        if date_match:
            date_str = date_match.group(1)
            archetype_from_folder = date_match.group(2).replace("_", " ")

        deck_meta = parse_decklist_meta(decklist) if decklist.exists() else {}
        analysis_meta = extract_analysis_meta(analysis)

        entry = {
            "folder": folder_name,
            "date": date_str,
            "archetype": analysis_meta.get("archetype") or archetype_from_folder,
            "colors": analysis_meta.get("colors", ""),
            "format": analysis_meta.get("format", "Standard"),
            "mainboard": deck_meta.get("mainboard", 0),
            "sideboard": deck_meta.get("sideboard", 0),
            "win_condition": analysis_meta.get("win_condition", ""),
            "key_cards": analysis_meta.get("key_cards", []),
            "has_analysis": analysis.exists(),
            "has_sideboard_guide": sideboard_guide.exists(),
            "decklist_path": f"Decks/{folder_name}/decklist.txt",
            "analysis_path": f"Decks/{folder_name}/analysis.md",
        }
        entries.append(entry)

    return entries


def write_index(entries: List[Dict], output_path: Path) -> None:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    lines = [
        "# Deck Registry",
        "",
        f"_Auto-generated by `scripts/index_decks.py` — Last updated: {now}_",
        "",
        f"**Total decks:** {len(entries)}",
        "",
        "---",
        "",
        "## Decks",
        "",
    ]

    if not entries:
        lines.append("_No decks published yet._")
    else:
        # Summary table
        lines += [
            "| Date | Archetype | Colors | Format | Main | Side | Files |",
            "|------|-----------|--------|--------|------|------|-------|",
        ]
        for e in entries:
            analysis_link = f"[analysis]({e['analysis_path']})" if e["has_analysis"] else "—"
            sb_icon = "✓ SB" if e["has_sideboard_guide"] else "—"
            colors = e["colors"] or "—"
            main = e["mainboard"] if e["mainboard"] else "—"
            side = e["sideboard"] if e["sideboard"] else "—"
            lines.append(
                f"| {e['date']} | [{e['archetype']}]({e['decklist_path']}) "
                f"| {colors} | {e['format']} | {main} | {side} "
                f"| {analysis_link} · {sb_icon} |"
            )

        lines += ["", "---", "", "## Deck Details", ""]

        for e in entries:
            lines += [
                f"### {e['archetype']}",
                "",
                f"- **Date:** {e['date']}",
                f"- **Colors:** {e['colors'] or '—'}",
                f"- **Format:** {e['format']}",
                f"- **Mainboard:** {e['mainboard']} cards",
                f"- **Sideboard:** {e['sideboard']} cards",
            ]
            if e["win_condition"]:
                lines.append(f"- **Win Condition:** {e['win_condition']}")
            if e["key_cards"]:
                lines.append(f"- **Key Cards:** {', '.join(e['key_cards'])}")
            lines += [
                f"- **Decklist:** [{e['decklist_path']}]({e['decklist_path']})",
                f"- **Analysis:** [{e['analysis_path']}]({e['analysis_path']})"
                if e["has_analysis"] else "- **Analysis:** —",
                "",
            ]

    output_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"✅ Deck index written: {output_path}  ({len(entries)} decks)")


def main() -> None:
    from mtg_utils import RepoPaths
    paths = RepoPaths()
    decks_dir = paths.decks_dir

    if not decks_dir.exists():
        print(
            f"No {RepoPaths.DECKS_DIR_NAME}/ directory found — skipping index generation.",
            file=sys.stderr,
        )
        return

    entries = scan_decks(decks_dir)
    output_path = decks_dir / "_INDEX.md"
    write_index(entries, output_path)


if __name__ == "__main__":
    main()
