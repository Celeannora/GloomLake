# Scripts

This directory contains Python utilities for managing the MTG card database, validating decklists, and generating deck-building scaffolds.

## Requirements

```bash
pip install -r requirements.txt
```

`requests` is the only runtime dependency.

## Scripts

### `fetch_and_categorize_cards.py`

Downloads all Standard-legal cards from the Scryfall bulk data API and writes them
into `cards_by_category/` as letter-split CSV files.

```bash
python scripts/fetch_and_categorize_cards.py
```

- Downloads ~100 MB of bulk data from Scryfall (streamed, not buffered)
- Filters to Standard-legal cards only
- Deduplicates by card name (keeps first/newest printing)
- Splits into `{type}/{type}_{letter}.csv` files, each ≤80 KB
- Adds `battle` card type (introduced in March of the Machine)
- Regenerates `cards_by_category/_INDEX.md`

**Run this after every new MTG set release or Standard rotation.**

---

### `validate_decklist.py`

Validates a decklist against the local card database. Works out of the box
after cloning — no pre-build step required.

**Quick start (after cloning):**

```bash
python scripts/validate_decklist.py Decks/my_deck/decklist.txt
```

**All usage:**

```bash
# Default — reads cards_by_category/ CSVs directly (no setup needed)
python scripts/validate_decklist.py Decks/my_deck/decklist.txt
python scripts/validate_decklist.py --verbose Decks/my_deck/decklist.txt
python scripts/validate_decklist.py --quiet Decks/my_deck/decklist.txt

# Faster backends (run build_local_database.py first)
python scripts/validate_decklist.py --db json Decks/my_deck/decklist.txt
python scripts/validate_decklist.py --db sqlite Decks/my_deck/decklist.txt

# Extra analysis
python scripts/validate_decklist.py --strict Decks/my_deck/decklist.txt
python scripts/validate_decklist.py --show-tags Decks/my_deck/decklist.txt
python scripts/validate_decklist.py --strict --show-tags --verbose Decks/my_deck/decklist.txt
```

**What it checks:**

- Every card exists in the database (Standard-legal)
- Mainboard has exactly 60 cards
- Sideboard has exactly 15 cards (or 0)
- No non-basic land appears more than 4 times (respects cards with unlimited copies like Rat Colony)
- Offers "did you mean?" suggestions for near-miss card names
- Empty or missing decklist detection

**With `--strict`:**

- Land count sanity check (warns if outside 20–28 range)

**With `--show-tags`:**

- Prints synergy tag summary for all mainboard non-land cards (lifegain, removal, draw, etc.)

**Flags:**

| Flag | Description |
|------|-------------|
| `--db csv` | Read cards_by_category/ CSVs directly (default, no setup needed) |
| `--db json` | Read local_db/card_index.json (run `build_local_database.py` first) |
| `--db sqlite` | Read local_db/card_details.db (run `build_local_database.py` first) |
| `--quiet` / `-q` | Suppress info-level logging |
| `--verbose` / `-v` | Print source CSV path for each card |
| `--strict` | Enable extra checks (land count warnings) |
| `--show-tags` | Print synergy tag distribution for the deck |

**Exit codes:** `0` = pass, `1` = illegal cards, `2` = file/database not found, `3` = count violation

---

### `build_local_database.py`

Builds the `local_db/` directory for faster offline validation with `--db json` or `--db sqlite`.

```bash
python scripts/build_local_database.py
```

**Output:**

```
local_db/
├── card_index.json    # Lightweight JSON pointer index (~200-300 KB)
├── card_names.txt     # Plain text card name list (~100 KB)
└── card_details.db    # Full SQLite database (~800 KB)
```

The `local_db/` directory is in `.gitignore` and is not committed to the repo.

---

### `search_cards.py`

Searches the `cards_by_category/` CSV files for cards matching a query. Supports filtering by name, type, color identity, keywords, mana value, rarity, and strategic tags.

```bash
python scripts/search_cards.py --colors W --type creature --tags lifegain
python scripts/search_cards.py --colors UB --type instant --cmc-max 3
python scripts/search_cards.py --name "Lightning"
python scripts/search_cards.py --type creature --colors WB --tags removal --show-tags
python scripts/search_cards.py --type land --colors WU
```

**Flags:**

| Flag | Description |
|------|-------------|
| `--type` | Card type(s), comma-separated (creature, instant, sorcery, etc.) |
| `--colors` | Color identity filter (W, UB, =WB for exact, C for colorless) |
| `--oracle` | Substring match in oracle text |
| `--name` | Substring match in card name |
| `--tags` | Strategy tags, comma-separated (lifegain, draw, removal, etc.) |
| `--cmc-max` | Maximum converted mana cost (inclusive) |
| `--cmc-min` | Minimum converted mana cost (inclusive) |
| `--rarity` | Rarity filter: common, uncommon, rare, mythic (comma-separated) |
| `--keywords` | MTG keyword(s), comma-separated (Flying, Lifelink) |
| `--limit` | Max results (default: 200) |
| `--show-tags` | Print computed tags per card |
| `--format` | Output format: table (default), csv, names |

Used standalone or called internally by `generate_deck_scaffold.py` to build candidate pools.

---

### `generate_deck_scaffold.py`

Generates a complete single-file session scaffold for building a new deck through the full gate system (Gates 1–6) locally. Designed for users running the deck-building process with any AI tool that has limited tool access.

#### Interactive Mode

The easiest way to get started — just run the script with no arguments:

```bash
python scripts/generate_deck_scaffold.py
```

This launches a step-by-step wizard that walks you through deck name, colors, archetype, and options with clear prompts and input validation. You can also explicitly request the wizard with `--interactive` / `-i`.

#### Non-interactive (CLI flags)

```bash
# Basic usage
python scripts/generate_deck_scaffold.py --name "Orzhov Lifegain" --colors WB --archetype lifegain

# Tribal build
python scripts/generate_deck_scaffold.py --name "Simic Frog Tribal" --colors GU --archetype tribal --tribe Frog

# Skip queries (offline template only)
python scripts/generate_deck_scaffold.py --name "Dimir Control" --colors UB --archetype control --skip-queries

# Custom output directory
python scripts/generate_deck_scaffold.py --name "Boros Aggro" --colors WR --archetype aggro --output-dir my_decks/
```

**Flags:**

| Flag | Required | Description |
|------|----------|-------------|
| `--name` | Yes | Deck name (used for folder naming) |
| `--colors` | Yes | Color identity: W, U, B, R, G, WB, WUB, etc. |
| `--archetype` | Yes | One of: `aggro`, `midrange`, `control`, `combo`, `mill`, `lifegain`, `tribal`, `ramp`, `tempo`, `burn` |
| `--tribe` | No | Creature subtype for tribal builds (e.g. Frog, Angel) |
| `--date` | No | Date override in YYYY-MM-DD format (default: today) |
| `--output-dir` | No | Output directory override (default: `Decks/`) |
| `--extra-tags` | No | Additional search tags, comma-separated |
| `--skip-queries` | No | Generate scaffold without running `search_cards.py` queries |
| `--interactive` / `-i` | No | Launch interactive wizard (also triggered when run with no args) |

**What it does:**
1. Runs archetype-specific `search_cards.py` queries to find candidate cards
2. Embeds all candidate pool results directly into the session file
3. Stubs out every required gate section (strategy, synergy, selection, mana base, sideboard, final checks)
4. Pre-populates the deck folder structure
5. Consolidates ALL output into a single `session.md` file

**Output:**

```
Decks/YYYY-MM-DD_Deck_Name/
├── session.md          ← The single consolidated file (all work goes here)
├── decklist.txt        ← Empty template (filled during Gate 3)
├── analysis.md         ← Empty template (filled after all gates)
└── sideboard_guide.md  ← Empty template (filled after Gate 5)
```

**Exit codes:** `0` = success, `1` = invalid arguments, `2` = `cards_by_category/` not found

See [LOCAL_WORKFLOW.md](../LOCAL_WORKFLOW.md) for the full local deck-building guide.

---

### `scaffold_gui.py`

A graphical desktop interface for `generate_deck_scaffold.py`. Same wizard flow, presented as a dark-mode GUI window — no terminal required.

> **Location:** The GUI now lives at the project root (`scaffold_gui.py`), not `scripts/scaffold_gui.py`. The old path still works via a backward-compatible redirect shim.

**Install the GUI dependency first (one-time):**
```bash
pip install customtkinter
```

**Launch:**
```bash
python scaffold_gui.py
```

**Form layout:** Colors → Archetype → Tribal → Tags → Focus Cards → Deck Name → Options → Output

**Features:**
- Click-to-toggle color identity buttons (styled per MTG card frame colors)
- Multi-select archetype grid with hover tooltip descriptions (e.g., "landfall: Trigger abilities when lands enter the battlefield")
- Tribal as standalone section — always visible with enable toggle, inline subtype search, and wildcard mode checkbox (not nested under archetypes)
- "✨ Auto-select from archetype" button pre-fills relevant tags based on selected archetypes
- Tags grouped by category: Offensive / Defensive / Utility
- Focus cards field — quantity determined by synergy analysis (not hardcoded to 4×)
- Auto-generate deck name from guild/shard name + archetype + optional focus character (e.g., "Orzhov Lifegain — Aerith")
- Skip queries checkbox for offline use
- Output directory browser
- Runs scaffold in the background with a result popup on completion

All scaffold logic is delegated to `generate_deck_scaffold.py`. Auto-build logic is handled by `auto_build.py`.

---

### `auto_build.py`

Standalone auto-build logic for constructing a complete decklist from a candidate pool CSV. Extracted from the GUI for reusability.

```bash
# Used programmatically — not a CLI tool
from auto_build import auto_build_decklist
```

Provides:
- `auto_build_decklist()` — 6-phase deck construction (focus cards → nonland fill → color analysis → mana base → sideboard → write)
- `sort_and_rewrite_csv()` — sort candidate pool by synergy scores
- `merge_scores_into_candidate_pool()` — merge synergy analysis results into pool
- Land analysis utilities: color detection, ETB-tapped analysis, Karsten mana requirements

---

### `run_session_queries.py`

Executes all pending `search_cards.py` query placeholders in a `session.md` and fills results in-place. Use this after generating a scaffold with `--skip-queries` (offline mode), or to re-run stale queries.

```bash
# Run all pending queries
python scripts/run_session_queries.py Decks/2026-04-03_My_Deck/session.md

# Preview what would run without making changes
python scripts/run_session_queries.py Decks/2026-04-03_My_Deck/session.md --dry-run

# Force re-run all queries (even ones with existing results)
python scripts/run_session_queries.py Decks/2026-04-03_My_Deck/session.md --force
```

| Flag | Description |
|------|-------------|
| `--dry-run` | Show pending queries without running them |
| `--force` | Re-run all queries, overwriting existing results |
| `--timeout N` | Per-query timeout in seconds (default: 60) |

**Exit codes:** `0` = success, `1` = file not found, `2` = search_cards.py missing, `3` = one or more queries failed

---

### `synergy_analysis.py`

Gate 2.5 automation. Reads cards from a `session.md`, `decklist.txt`, pool CSVs, or plain name list, computes pairwise synergy scores using a single-pass scoring engine, checks all Gate 2.5 thresholds, and writes a report ready to paste into `session.md`.

```bash
# Analyze candidate pool from a session.md
python scripts/synergy_analysis.py Decks/2026-04-03_My_Deck/session.md

# Analyze a finished decklist
python scripts/synergy_analysis.py Decks/2026-04-03_My_Deck/decklist.txt

# Write report to file instead of stdout
python scripts/synergy_analysis.py session.md --output synergy_report.md

# JSON output for machine consumption
python scripts/synergy_analysis.py decklist.txt --report-format json --output report.json

# Override primary mechanic axes
python scripts/synergy_analysis.py decklist.txt --primary-axis lifegain,token,sacrifice

# Export top-20 cards as CSV
python scripts/synergy_analysis.py decklist.txt --top 20
```

| Flag | Description |
|------|-------------|
| `--format` | Input format: `auto` (default), `session`, `decklist`, `names`, `pools` |
| `--output FILE` | Write report to file (default: stdout) |
| `--mode` | Threshold calibration: `auto` (default), `pool`, `deck` |
| `--report-format` | Output format: `markdown` (default), `json` |
| `--top N` | Export top-N cards as CSV ranked by composite score |
| `--include-sideboard` | Include sideboard cards in scoring |
| `--allow-missing` | Skip inconclusive guard when maindeck cards are missing |
| `--primary-axis` | Comma-separated mechanic override (e.g. `lifegain,token`) |
| `--verbose` | Show per-pair interaction details |

**Architecture:** The CLI is a thin wrapper over four modules:

| Module | Responsibility |
|--------|---------------|
| `synergy_types.py` | Enums (`InteractionType`, `CardRole`), data classes (`SynergyProfile`, `CardScore`), constants |
| `synergy_engine.py` | Card loading, profile building, single-pass O(n²) pairwise scoring with confidence weighting |
| `synergy_thresholds.py` | Threshold calibration (pool vs deck mode), structured pass/fail checking |
| `synergy_report.py` | Markdown report (with synergy matrix, role distribution, graph-based chains), JSON export, CSV export |

**What it automates (~70-80% of Gate 2.5):**
- Tag computation for every card (oracle text + keywords)
- Directional source/payoff tag classification
- Single-pass pairwise interaction detection: FEEDS, TRIGGERS, ENABLES, AMPLIFIES, PROTECTS, REDUNDANT
- Confidence-weighted scoring (oracle-confirmed = 1.5×, tag-inferred = 1.0×)
- Role classification: engine / enabler / payoff / support / interaction
- Density-first composite scoring
- All threshold checks with structured results
- Synergy matrix visualization
- Graph-based synergy chain detection
- Pre-filled synergy score table and chain scaffold

**What still requires AI/human review:** Fine-grained ENABLES/TRIGGERS that require reading oracle text semantically, synergy chain descriptions, REDUNDANT pair justifications.

**Exit codes:** `0` = all thresholds passed, `1` = threshold(s) failed or inconclusive, `2` = file not found or no cards extracted

---

### `hypergeometric_analysis.py`

Runs hypergeometric probability calculations for draw consistency analysis. Computes the probability of drawing specific cards or card types by a given turn.

```bash
python scripts/hypergeometric_analysis.py Decks/my_deck/decklist.txt
```

---

### `mana_base_comparison.py`

Compares a deck's mana base against recommended distributions. Useful for validating land counts and color ratios during Gate 4.

```bash
python scripts/mana_base_comparison.py Decks/my_deck/decklist.txt
```

---

### `index_decks.py`

Scans the `Decks/` directory and regenerates the deck index. Run after adding or removing decks.

```bash
python scripts/index_decks.py
```

---

### `mtg_utils.py`

Shared utilities imported by other scripts. Not intended to be run directly.

Provides:
- `RepoPaths` — centralised directory-name configuration (auto-detects repo root)
- `parse_decklist(path)` — MTGA-format decklist parser (handles `//` and `#` comments, `Deck`/`Sideboard` section headers, set code stripping)

---

## Running Tests

```bash
# Using unittest
python -m unittest discover tests/ -v

# Using pytest (if installed)
python -m pytest tests/ -v
```

The test suite covers all synergy analysis modules: types, engine, thresholds, and report generation. Integration tests use the `test-corpus/` directory.

---

## License

MIT License — see [LICENSE](../LICENSE).
