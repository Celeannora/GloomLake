# GloomLake — MTG Deck Builder

> ⚠️ **AI Assistants:** Read [AI_INSTRUCTIONS.md](../reference/AI_INSTRUCTIONS.md) before touching any card.

GloomLake is an AI-assisted Magic: The Gathering deck builder with exhaustive validation, synergy scoring, a 10-archetype mythic panel evaluator, and an autonomous optimizer. Every card is verified against a local Standard database. Build legal decks or get caught by automation.

**Status:** Fully self-sufficient — complete card database + all tools local.

---

## Quick Start

### GUI (recommended)

```bash
pip install -e .[gui]
python scaffold_gui.py
```

The GUI walks you through colour selection, archetype, tribal, focus cards, and deck naming — then runs the full scaffold + synergy + auto-build pipeline in one click.

### CLI

```bash
python scripts/cli/generate_deck_scaffold.py \
  --name "Hope Estheim Angel Mill" \
  --colors WU \
  --archetype lifegain opp_mill control \
  --tribe Angel \
  --focus-cards "Hope Estheim" "Resplendent Angel"
```

---

## Repository Structure

```
GloomLake/
├── scaffold_gui.py              # GUI entry point (run this)
│
├── scripts/
│   ├── cli/
│   │   ├── search_cards.py              # Card search with strategy tags
│   │   └── generate_deck_scaffold.py    # Session scaffold generator
│   │
│   ├── analysis/
│   │   ├── synergy_analysis.py          # Gate 2.5 synergy analysis (CLI)
│   │   ├── synergy_engine.py            # O(n²) pairwise scoring engine
│   │   ├── synergy_types.py             # Enums, dataclasses, constants
│   │   ├── synergy_report.py            # Markdown/JSON/CSV output
│   │   ├── synergy_thresholds.py        # Gate threshold calibration
│   │   ├── synergy_archetype_mapping.py # Archetype → axis mapping
│   │   ├── mythic_framework.py          # 10-archetype panel + EV formulas
│   │   ├── synergy_optimizer.py         # Karpathy-style autonomous optimizer
│   │   ├── deck_architect.py            # Conclusive deck analysis
│   │   ├── reverse_deck_lookup.py       # Deck profile from decklist
│   │   └── mythic_panel.py              # Legacy 5-player panel (deprecated)
│   │
│   └── utils/
│       ├── mtg_utils.py                 # Shared utilities + RepoPaths
│       ├── validate_decklist.py         # Deck legality validator
│       ├── auto_build.py                # Karsten mana base auto-builder
│       ├── fetch_and_categorize_cards.py # Refresh card DB from Scryfall
│       ├── build_local_database.py      # Build SQLite offline DB
│       ├── mana_base_advisor.py         # Colour source calculator
│       ├── goldfish.py                  # Hand simulation
│       ├── hypergeometric_analysis.py   # Draw probability
│       ├── index_decks.py               # Regenerate Decks/_INDEX.md
│       ├── run_session_queries.py       # Run pending session.md queries
│       ├── sideboard_advisor.py         # Sideboard suggestions
│       └── mana_base_comparison.py      # Compare mana configurations
│
├── assets/
│   ├── data/
│   │   ├── cards_by_category/           # Standard card DB (4450 cards, CSV)
│   │   └── local_db/                    # SQLite DB (built on demand)
│   ├── templates/template/              # Deck template files
│   └── mana/                            # SVG mana symbol assets
│
├── docs/
│   ├── getting-started/
│   │   ├── README.md                    # ← You are here
│   │   └── LOCAL_WORKFLOW.md            # Full local execution guide
│   ├── reference/
│   │   └── AI_INSTRUCTIONS.md           # AI deck-building protocol
│   └── changelog/
│       ├── CHANGELOG.md                 # Version history
│       └── SPEC.md                      # Design roadmap
│
├── tests/
│   ├── test_synergy.py                  # 66 unit tests
│   └── fixtures/                        # Test data
│
└── Decks/                               # Generated decks (gitignored)
    └── YYYY-MM-DD_Deck_Name/
        ├── session.md                   # Build session workspace
        ├── decklist.txt                 # MTGA-importable
        ├── analysis.md                  # Card reasoning
        ├── sideboard_guide.md           # Matchup guide
        ├── synergy_report.md            # Synergy analysis output
        ├── panel_report.json            # 10-Mythic Panel JSON
        └── optimizer_report.md          # Optimizer results
```

---

## Core Workflow

```
1. Generate scaffold   →  scripts/cli/generate_deck_scaffold.py
2. Search cards        →  scripts/cli/search_cards.py
3. Synergy analysis    →  scripts/analysis/synergy_analysis.py
4. Mythic panel        →  scripts/analysis/mythic_framework.py  (or --mythic-panel flag)
5. Optimize            →  scripts/analysis/synergy_optimizer.py
6. Validate            →  scripts/utils/validate_decklist.py
```

---

## Key Scripts

### Search Cards

```bash
python scripts/cli/search_cards.py --type creature --colors WU --subtype Angel --tags lifegain
python scripts/cli/search_cards.py --name "Hope Estheim"
python scripts/cli/search_cards.py --type instant --tags counter --colors U --cmc-max 2
```

### Generate Scaffold

```bash
python scripts/cli/generate_deck_scaffold.py \
  --name "My Deck" \
  --colors WU \
  --archetype lifegain control \
  --tribe Angel \
  --focus-cards "Hope Estheim" "Lyra Dawnbringer"
```

### Synergy Analysis + 10-Mythic Panel

```bash
# Full analysis with panel
python scripts/analysis/synergy_analysis.py Decks/my_deck/session.md \
  --mythic-panel \
  --tribe Angel \
  --primary-axis lifegain \
  --output Decks/my_deck/synergy_report.md

# Panel standalone
python scripts/analysis/mythic_framework.py Decks/my_deck/session.md --tribe Angel
python scripts/analysis/mythic_framework.py Decks/my_deck/session.md --json
```

### Autonomous Optimizer

```bash
# Optimize deck from candidate pool — lock key cards from being cut
python scripts/analysis/synergy_optimizer.py Decks/my_deck/session.md \
  --time-budget 120 \
  --tribe Angel \
  --primary-axis lifegain \
  --lock-cards "Hope Estheim" "Resplendent Angel" \
  --verbose
```

### Validate

```bash
python scripts/utils/validate_decklist.py Decks/my_deck/decklist.txt
```

### Refresh Card Database (after new set releases)

```bash
python scripts/utils/fetch_and_categorize_cards.py
python scripts/utils/build_local_database.py
```

---

## Documentation Map

| Need... | Go to... |
|---------|----------|
| Build a deck (AI instructions) | [AI_INSTRUCTIONS.md](../reference/AI_INSTRUCTIONS.md) |
| Full local execution guide | [LOCAL_WORKFLOW.md](LOCAL_WORKFLOW.md) |
| Version history | [CHANGELOG.md](../changelog/CHANGELOG.md) |
| Design roadmap | [SPEC.md](../changelog/SPEC.md) |

---

## Supported Archetypes

`aggro` `aristocrats` `artifacts` `blink` `burn` `combo` `control` `domain` `eldrazi` `enchantress` `energy` `equipment` `extra_turns` `flashback` `graveyard` `infect` `landfall` `lands` `lifegain` `madness` `midrange` `opp_mill` `proliferate` `prowess` `ramp` `reanimation` `self_mill` `stax` `storm` `superfriends` `tempo` `tokens` `tribal` `vehicles` `voltron`

Tribal is a modifier — combine with any archetype via `--tribe <CreatureType>`.

---

## Card Database

- **Location:** `assets/data/cards_by_category/`
- **Size:** 4,450 Standard-legal cards across 8 types
- **Format:** `{type}/{type}_{letter}.csv` (e.g. `creature/creature_h.csv`)
- **Last updated:** April 2026 (includes FIN — Final Fantasy set)

```bash
# Refresh after new set releases
python scripts/utils/fetch_and_categorize_cards.py
```

---

## Testing

```bash
python -m pytest tests/ -v
```

---

## Philosophy

> Every card choice is mathematically justified.
> Format legality is non-negotiable.

**Maintained by:** Celeannora
**Last updated:** April 21, 2026
