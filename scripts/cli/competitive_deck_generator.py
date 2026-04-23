#!/usr/bin/env python3
"""
Competitive Deck Generator — Tournament-Quality Deck Building
"""

import argparse
import sys
from pathlib import Path
from typing import Dict, List

# Add scripts to path
_here = Path(__file__).resolve().parent.parent.parent
_scripts_dir = _here / "scripts"
sys.path.insert(0, str(_scripts_dir))
sys.path.insert(0, str(_scripts_dir / "analysis"))

from competitive_deck_builder import CompetitiveDeckBuilder, COMPETITIVE_ARCHETYPES

def main():
    parser = argparse.ArgumentParser(description="Generate tournament-quality MTG decks")
    parser.add_argument("--archetype", help="Archetype to build")
    parser.add_argument("--name", default="", help="Custom deck name")
    parser.add_argument("--list-archetypes", action="store_true", help="List available archetypes")
    parser.add_argument("--validate-only", action="store_true", help="Only validate deck quality")
    parser.add_argument("--output-dir", default="Decks", help="Output directory")

    args = parser.parse_args()

    builder = CompetitiveDeckBuilder()

    if args.list_archetypes:
        print("Available Competitive Archetypes:")
        print("=" * 50)
        for key, template in builder.templates.items():
            meta_share = COMPETITIVE_ARCHETYPES[key]["meta_share"]
            print("30")
        return

    if not args.archetype:
        print("Error: --archetype required (use --list-archetypes to see options)")
        return

    if args.archetype not in builder.templates:
        print(f"Error: Unknown archetype '{args.archetype}'")
        print("Use --list-archetypes to see available options")
        return

    # Build the deck
    try:
        maindeck, sideboard = builder.build_deck(args.archetype)

        # Validate quality
        quality_scores = builder.validate_deck_quality(maindeck, sideboard)

        if args.validate_only:
            print(f"Deck Quality Scores for {args.archetype}:")
            for metric, score in quality_scores.items():
                print(".1f")
            return

        # Generate deck name
        deck_name = args.name or f"Competitive_{args.archetype.replace('_', '_').title()}"
        safe_name = deck_name.replace(" ", "_").replace("-", "_")

        # Create output directory
        output_dir = Path(args.output_dir) / f"2026-04-22_{safe_name}"
        output_dir.mkdir(parents=True, exist_ok=True)

        # Write decklist
        decklist_content = generate_decklist(maindeck, sideboard, deck_name)
        decklist_path = output_dir / "decklist.txt"
        decklist_path.write_text(decklist_content, encoding="utf-8")

        # Write analysis
        analysis_content = generate_analysis(maindeck, sideboard, quality_scores, args.archetype)
        analysis_path = output_dir / "analysis.md"
        analysis_path.write_text(analysis_content, encoding="utf-8")

        print(f"[SUCCESS] Competitive deck generated: {output_dir}/")
        print(f"   Maindeck: {len(maindeck)} cards")
        print(f"   Sideboard: {len(sideboard)} cards")
        print("\nQuality Scores:")
        for metric, score in quality_scores.items():
            print(".1f")

    except Exception as e:
        print(f"Error generating deck: {e}")
        return

def generate_decklist(maindeck: List[Dict], sideboard: List[Dict], deck_name: str) -> str:
    """Generate MTGA-format decklist."""
    lines = [f"# {deck_name}", "Deck"]

    # Group maindeck by quantity
    card_counts = {}
    for card in maindeck:
        name = card["name"]
        card_counts[name] = card_counts.get(name, 0) + card.get("qty", 1)

    # Sort by quantity descending, then alphabetically
    for name, qty in sorted(card_counts.items(), key=lambda x: (-x[1], x[0])):
        lines.append(f"{qty} {name}")

    if sideboard:
        lines.append("")
        lines.append("Sideboard")

        # Group sideboard by quantity
        sb_counts = {}
        for card in sideboard:
            name = card["name"]
            sb_counts[name] = sb_counts.get(name, 0) + card.get("qty", 1)

        for name, qty in sorted(sb_counts.items(), key=lambda x: (-x[1], x[0])):
            lines.append(f"{qty} {name}")

    return "\n".join(lines)

def generate_analysis(maindeck: List[Dict], sideboard: List[Dict],
                     quality_scores: Dict[str, float], archetype: str) -> str:
    """Generate deck analysis markdown."""
    template = CompetitiveDeckBuilder().templates[archetype]

    content = f"""# Deck Analysis: {template.name}

**Date:** 2026-04-22
**Format:** Standard
**Colors:** {template.colors}
**Archetype:** {template.name}

---

## Executive Summary

- **Strategy:** {template.name} - competitive archetype ({template.meta_positioning})
- **Meta Share:** {COMPETITIVE_ARCHETYPES[archetype]['meta_share']}%
- **Target Win Rate:** 50%+ vs random meta
- **Key Cards:** {', '.join([card['name'] for card in maindeck[:3]])}

---

## Quality Metrics

"""
    for metric, score in quality_scores.items():
        status = "[PASS]" if score >= 70 else "[WARN]" if score >= 50 else "[FAIL]"
        content += f"- **{metric.replace('_', ' ').title()}:** {status} {score:.1f}/100\n"

    content += """
---

## Mana Base Analysis

- **Land Count:** {len([c for c in maindeck if c.get("type") == "Land"])}
- **Colors:** {template.colors}
- **Efficiency Score:** {quality_scores.get("mana_efficiency", 0):.1f}/100

---

## Curve Analysis

Target curve follows competitive Mono-Green Landfall patterns.

*Note: This deck follows competitive patterns proven in current Standard meta.*
"""

    return content

if __name__ == "__main__":
    main()