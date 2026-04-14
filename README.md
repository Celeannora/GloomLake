# Gloomlake — MTG Deck Builder

## 🛑 AI ASSISTANTS: STOP AND READ THIS FIRST 🛑

**Before building ANY deck, you MUST:**

1. ⚠️ **STOP** - Do not name any card yet
2. 📚 **READ** `AI_INSTRUCTIONS.md` - Your ONLY authoritative instruction source
3. 🔍 **QUERY DATABASE** - Use `python scripts/search_cards.py` to build your candidate pool
4. ✓ **VERIFY EVERY CARD** - Every card must come from a `search_cards.py` query result
5. 🧪 **RUN VALIDATOR** - Execute `python scripts/validate_decklist.py` before finalizing
6. ❓ **ASK QUESTIONS** - If the archetype or win condition is unclear, ask before building

**Skipping these steps will generate illegal decks.**

📖 **Primary instruction file:** [`AI_INSTRUCTIONS.md`](AI_INSTRUCTIONS.md)

---

## Overview

This repository contains rigorously analyzed, format-legal Magic: The Gathering decklists built through AI-assisted optimization. Every deck undergoes exhaustive mathematical and strategic analysis before publication.

**Repository status**: ✅ Fully self-sufficient — contains a complete Standard card database and AI deck-building instructions.  
**Legality enforcement**: 🚨 STRICT — All cards must be verified against the database. Web sources are prohibited for card selection.  
**Validation**: ✅ Automated validation script prevents illegal cards from entering the repository.

---

## Repository structure

```
Gloomlake/
├── scaffold_gui.py                  # 🖥️ GUI for scaffold generation (customtkinter)
├── Decks/                           # All generated decks (gitignored, local only)
│   └── YYYY-MM-DD_Archetype_Name/
│       ├── session.md               # Consolidated build session (local workflow)
│       ├── decklist.txt             # MTGA-importable decklist
│       ├── analysis.md              # Card-by-card reasoning and strategy
│       └── sideboard_guide.md       # Matchup-specific boarding plans
├── cards_by_category/               # Standard card database (CSV, auto-generated)
│   ├── _INDEX.md                    # File listing and lookup guide
│   ├── artifact/
│   ├── creature/
│   ├── enchantment/
│   ├── instant/
│   ├── land/
│   ├── other/
│   ├── planeswalker/
│   └── sorcery/
├── scripts/
│   ├── search_cards.py                # 🔍 AI card search with strategy tag filtering
│   ├── generate_deck_scaffold.py      # 📝 Session scaffold generator (CLI)
│   ├── auto_build.py                  # 🔧 Auto-build logic (Karsten mana base, scoring)
│   ├── synergy_analysis.py            # 🧪 Gate 2.5 synergy analysis (CLI wrapper)
│   ├── synergy_engine.py              # Pairwise scoring engine
│   ├── synergy_report.py              # Markdown/JSON/CSV report generation
│   ├── synergy_thresholds.py          # Threshold calibration & checking
│   ├── synergy_types.py               # Enums, dataclasses, constants
│   ├── run_session_queries.py         # Run pending session.md queries
│   ├── validate_decklist.py           # Deck legality validator
│   ├── fetch_and_categorize_cards.py  # Regenerates card database from Scryfall
│   ├── build_local_database.py        # Builds local_db/ for fast offline validation
│   ├── hypergeometric_analysis.py     # Draw probability calculator
│   ├── mana_base_advisor.py           # Mana base recommendations
│   ├── mana_base_comparison.py        # Compare mana base configurations
│   ├── goldfish.py                    # Goldfish simulation (test draws)
│   ├── sideboard_advisor.py           # Sideboard suggestions
│   ├── index_decks.py                 # Regenerates Decks/_INDEX.md registry
│   ├── scaffold_gui.py               # Backward-compatible redirect to root GUI
│   └── mtg_utils.py                   # Shared utilities (parser, etc.)
├── tests/
│   ├── __init__.py
│   └── test_synergy.py               # 66 unit tests for synergy modules
├── test-corpus/                     # Test decks for automated testing
├── plans/                           # Architecture plans and design docs
├── .github/DECK_TEMPLATE/           # Template for new decks
├── .github/workflows/validate.yml   # CI validation workflow
├── AI_INSTRUCTIONS.md               # 🔴 SINGLE SOURCE OF TRUTH for AI deck building
├── LOCAL_WORKFLOW.md                 # 💻 Guide for running the process on your own machine
├── Changelog.md
├── requirements.txt
└── README.md
```

---

## Quick start

### GUI mode (recommended)

```bash
pip install customtkinter   # one-time dependency
python scaffold_gui.py
```

The GUI walks you through colour selection, archetype, tribal, tags, focus cards, and deck naming — then runs the scaffold + synergy + auto-build pipeline in one click.

### CLI mode

```bash
python scripts/generate_deck_scaffold.py --name "Orzhov Lifegain" --colors WB --archetype lifegain
```

See **[`LOCAL_WORKFLOW.md`](LOCAL_WORKFLOW.md)** for the full guide.

---

## Card database

All Standard-legal cards are stored in `cards_by_category/`, organized by type and split by first letter of card name:

- **Path format**: `cards_by_category/{type}/{type}_{letter}.csv`
- **Example**: Sheoldred, the Apocalypse (creature, S) → `cards_by_category/creature/creature_s1.csv`
- **File size**: Each file targets ≤80 KB for reliable GitHub API access
- **Index**: `cards_by_category/_INDEX.md` lists every file with card counts and sizes
- **Columns**: `name`, `mana_cost`, `cmc`, `type_line`, `oracle_text`, `colors`, `color_identity`, `rarity`, `set`, `set_name`, `collector_number`, `power`, `toughness`, `loyalty`, `produced_mana`, `keywords`

To update the database after a new set releases or Standard rotates:

```bash
python scripts/fetch_and_categorize_cards.py
```

---

## Supported archetypes

30 archetypes across 7 categories:

| Category | Archetypes |
|----------|-----------|
| **Aggro** | aggro, burn, prowess, infect |
| **Midrange** | midrange, tempo, blink, lifegain |
| **Control** | control, stax, superfriends |
| **Combo** | combo, storm, extra_turns |
| **Graveyard** | graveyard, reanimation, flashback, madness, self_mill, opp_mill |
| **Permanents** | tokens, aristocrats, enchantress, equipment, artifacts, vehicles, voltron |
| **Ramp & Lands** | ramp, landfall, lands, domain, eldrazi, energy, proliferate |

Tribal is a standalone modifier that can be combined with any archetype.

---

## Synergy analysis

The synergy engine scores pairwise card interactions across 5 passes:

1. **Tag interactions** — rule-based source→payoff matching (37 rules)
2. **Oracle cross-reference** — subtype and keyword verification via indexed lookup
3. **Oracle bridges** — payoff pattern detection (lifegain drain, food, tribe triggers)
4. **Redundancy** — CMC-bracket-aware duplicate detection
5. **Dependency** — aura/equipment/conditional scoring

```bash
python scripts/synergy_analysis.py Decks/my_deck/session.md --output report.md --top 200
```

---

## Deck validation

### Online validation (reads cards_by_category/ CSVs directly)

```bash
python scripts/validate_decklist.py Decks/my_deck/decklist.txt
```

### Offline validation (faster, uses pre-built local_db/)

```bash
# One-time setup
python scripts/build_local_database.py

# Then validate quickly
python scripts/validate_decklist.py --db json Decks/my_deck/decklist.txt
python scripts/validate_decklist.py --db sqlite Decks/my_deck/decklist.txt
```

### Validation flags

```bash
--db csv      # Read cards_by_category/ CSVs directly (default, no setup)
--db json     # Use pre-built local_db/card_index.json
--db sqlite   # Use pre-built local_db/card_details.db
--quiet       # Suppress info-level logging
--verbose     # Print source CSV for each card
--strict      # Extra checks (land count sanity warnings)
--show-tags   # Print synergy tag summary for the deck
```

### Exit codes

| Code | Meaning |
|------|---------|
| 0 | Validation passed |
| 1 | Illegal/unrecognised cards found |
| 2 | Decklist file not found |
| 3 | Count violation (wrong 60/15/4-copy counts) |

---

## Testing

```bash
python -m pytest tests/ -v
```

66 unit tests covering synergy types, engine, thresholds, report generation, and integration tests using the `test-corpus/` directory.

---

## For AI assistants

### 🚨 Critical legality requirements

1. **Query database FIRST** — before naming any card
2. **Only use database cards** — never rely on web searches or training memory
3. **Cite every card** — each card must trace back to a `search_cards.py` result
4. **Run validation script** — execute before finalizing deck
5. **Document queries** — list all `search_cards.py` commands run in analysis.md
6. **Ask if unclear** — ask clarifying questions about archetype/win condition before building
7. **Zero tolerance** — even one illegal card invalidates the entire deck

### Card search examples

```bash
# Lifegain creatures in white/black
python scripts/search_cards.py --type creature --colors WB --tags lifegain

# Cheap removal instants
python scripts/search_cards.py --type instant --tags removal --cmc-max 3

# Mill cards across all spell types
python scripts/search_cards.py --type instant,sorcery --tags mill

# Dual lands for a color pair
python scripts/search_cards.py --type land --colors WU
```

**Never trust external sources for card legality** — the database is the only source of truth.

---

## For deck builders (human)

1. Browse `Decks/` organized by date and archetype
2. Import `decklist.txt` directly into MTG Arena
3. Read `analysis.md` for detailed card reasoning and database verification
4. Consult `sideboard_guide.md` for matchup strategies

---

## Formats supported

Only **Standard** has full card database support. All other formats require manual legality verification.

---

## Philosophy

Every card choice is mathematically justified. Every strategic decision is rigorously challenged. No deck is published without surviving brutal self-critique.

**Format legality is non-negotiable.** A brilliant deck with illegal cards is worthless.

---

**Maintained by**: Celeannora  
**Last updated**: April 13, 2026  
