# GloomLake Specification

> ⚠️ **NOTE:** This is a design specification and roadmap. Not all features are implemented. See Changelog.md for current state.
> Last reviewed: April 20, 2026

---

## Project Overview

**Project Name:** GloomLake  
**Type:** MTG Deck Building Analysis Platform  
**Core Functionality:** AI-assisted competitive deck building with live meta data from Untapped.gg and autonomous optimization inspired by karpathy/autoresearch  
**Target Users:** Competitive MTG Arena players seeking data-driven deck analysis

---

## Architecture

```
gloomlake/
├── __init__.py
├── __main__.py          # CLI entry point
├── config.py            # Configuration management
├── cli.py              # Command-line interface
├── types.py            # Type definitions (dataclasses)
├── card_db/            # Card database layer
│   ├── __init__.py
│   ├── sqlite_backend.py
│   ├── csv_importer.py
│   └── cache.py
├── meta/               # Meta data fetching (Untapped.gg)
│   ├── __init__.py
│   ├── fetcher.py
│   └── parser.py
├── analysis/           # Deck analysis & scoring
│   ├── __init__.py
│   ├── synergy.py
│   ├── scoring.py
│   └── thresholds.py
├── optimization/       # Karpathy-inspired autonomous optimization
│   ├── __init__.py
│   ├── engine.py
│   ├── program.md     # Agent instructions
│   └── experiments.py
├── deck/               # Deck utilities
│   ├── __init__.py
│   ├── parser.py
│   ├── builder.py
│   └── export.py
├── gui/                # GUI (customtkinter, not PySide6)
│   ├── __init__.py
│   └── main.py
└── utils/              # Shared utilities
    ├── __init__.py
    └── logging.py

scripts/               # Primary interface (not legacy)
├── search_cards.py
├── validate_decklist.py
├── synergy_analysis.py
├── auto_build.py
└── ...
```

---

## What IS Implemented (v10.x)

- ✅ `scripts/search_cards.py` — Card search with strategy tags
- ✅ `scripts/validate_decklist.py` — Deck legality validator
- ✅ `scripts/synergy_analysis.py` — Pairwise card scoring
- ✅ `scripts/auto_build.py` — Auto deck assembly
- ✅ `scripts/generate_deck_scaffold.py` — Session scaffold generator
- ✅ `scaffold_gui.py` — Customtkinter GUI (project root)
- ✅ `gloomlake/` package (v0.2.0) — CLI (`python -m gloomlake`)
- ✅ 66 unit tests

---

## What Is NOT Yet Implemented

- ❌ Untapped.gg meta fetch (designed but not built)
- ❌ Full SQLite card backend (currently uses CSVs)
- ❌ Autonomous optimization loop (Karpathy-style)
- ❌ PySide6 GUI migration (customtkinter used instead)

---

## Core Features (Implemented + Planned)

### 1. Meta Data Fetching (Untapped.gg) [NOT BUILT]
- Fetch top competitive decks by format (Standard, Historic, etc.)
- Parse deck lists with win rates, game count, colors
- Cache meta data with configurable TTL
- Rate-limited to 20 req/min (respect Untapped API limits)

### 2. Card Database (SQLite) [PARTIAL]
- SQLite backend replacing CSV scans (in progress)
- Full-text search on card names
- Indexed queries on colors, type, cmc, tags
- Import existing CSVs to SQLite

### 3. Deck Analysis [IMPLEMENTED]
- **Synergy Scoring:** Pairwise card interactions
- **Role Classification:** Engine, Enabler, Payoff, Support
- **Density-First Scoring:** "Works with THIS pool" vs generic
- **Threshold Checks:** Gate 2.5 compliance verification

### 4. Autonomous Optimization (Karpathy-style) [NOT BUILT]
- **Program.md:** Agent instructions defining optimization goals
- **Experiment Loop:** Modify deck → evaluate → keep/discard
- **Fixed Time Budget:** Run optimization for N minutes
- **Metric:** Composite synergy score (higher = better)

### 5. CLI Interface [IMPLEMENTED]
```bash
gloomlake meta standard           # Fetch meta decks (not built)
gloomlake analyze deck.txt       # Analyze deck
gloomlake optimize deck.txt      # Run optimization (not built)
gloomlake search --colors WB --type creature --tags lifegain
gloomlake gui                   # Launch GUI
```

---

## Data Flow

1. **Meta Fetch:** Untapped.gg → meta_fetcher → cached JSON (NOT BUILT)
2. **Card Lookup:** CSVs → SQLite → Card dataclass (IN PROGRESS)
3. **Analysis:** decklist → parser → scorer → results (IMPLEMENTED)
4. **Optimization:** scorer → experiment loop → improved deck (NOT BUILT)

---

## Acceptance Criteria

- [x] Card lookups via SQLite (partial — in progress)
- [x] Synergy analysis runs in <2s for 60-card deck
- [ ] Optimization runs autonomously for fixed time budget
- [x] CLI functional (`python -m gloomlake`)
- [x] GUI functional (customtkinter)
- [x] Legacy scripts still work (backward compat)

---

## Dependencies

```toml
[project]
dependencies = [
    "requests>=2.31.0",
    "sqlalchemy>=2.0.0",
    "pyyaml>=6.0.0",
    "rich>=13.0.0",
]
optional = [
    "customtkinter>=5.2",  # GUI (actually used, not PySide6)
    "pytest>=7.0.0",     # Testing
]

[project.optional-dependencies]
dev = [
    "ruff>=0.1.0",
    "mypy>=1.0.0",
]
```
