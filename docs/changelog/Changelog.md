# Changelog

## v10.2 — April 13, 2026

### 🐛 Synergy Performance Fix

- **Chain detection timeout fixed** — `_find_synergy_chains()` in `synergy_report.py` used exhaustive BFS that explored all simple paths up to length 5. On large pools (948+ non-land cards), this caused combinatorial explosion (>120s timeout). Replaced with greedy best-first search: only top-3 neighbours explored per node, plus a 5,000-item queue safety cap. Real-world time: **16.9s** (was >120s).
- **Synergy matrix optimized** — `_build_synergy_matrix()` imap loop now only iterates interactions for the top-10 cards instead of all 948+.

### 🐛 Auto-build Copy Count Fix

- **`_copies_for()` no longer defaults to 4x for everything** — copy counts now factor in rarity alongside CMC and Legendary status:
  - Mythic rares: 2 copies (was 4)
  - Rares: 3 copies (was 4)
  - Legendaries: 2 copies regardless of CMC (was 3 for focus, 2 only at CMC 5+)
  - CMC 4: 3 copies, CMC 5: 2 copies, CMC 6+: 1 copy (unchanged)
  - Commons/Uncommons at CMC ≤3: 4 copies (unchanged)
- **Focus cards no longer get hardcoded quantities** — they use the same CMC/rarity logic as regular cards. "Focus" means guaranteed inclusion, not a fixed copy count.
- **`_copy_reason()` updated** — now shows combined reasons like "Focus + Legendary" or "Focus + Rare" instead of "Focus (locked 4x)".

### 🎨 GUI Polish

- **Tag tooltips added** — all 18 Extra Tags buttons now show hover descriptions (e.g., "haste: Creatures can attack the turn they enter"). Uses the same `Tooltip` class as archetype buttons.
- `TAG_CATEGORIES` upgraded from `dict[str, list]` to `dict[str, dict[str, str]]` with per-tag descriptions.

### 📝 Documentation

- `README.md` repo structure updated to include `scaffold_gui.py` and `scripts/auto_build.py`
- `LOCAL_WORKFLOW.md` Quick Start now recommends GUI mode first

---

## v10.1 — April 13, 2026

### 🎉 GUI Overhaul

**Scaffold GUI restructured** — addressing 6 user-reported issues:

1. **Deck Name moved to end of form** with auto-generate option
   - Auto-generates from guild/shard name + archetype (e.g., "Orzhov Lifegain")
   - Optional Focus Character field for thematic naming (e.g., "Orzhov Lifegain — Aerith")
   - 26 guild/shard/wedge names mapped

2. **Archetype descriptions added** — every archetype now has a tooltip description on hover explaining what it does (e.g., "landfall: Trigger abilities when lands enter the battlefield")

3. **Tribal extracted as standalone section** — no longer nested under Tempo/Midrange archetype group. Always visible with enable toggle, inline subtype search, and wildcard mode checkbox

4. **Creature subtype blank space fixed** — search results and chip frames use show/hide pattern to eliminate empty areas

5. **Extra tags auto-select** — new "✨ Auto-select from archetype" button pre-fills relevant tags based on selected archetypes. Tags grouped into Offensive/Defensive/Utility categories

6. **Focus cards quantity no longer hardcoded** — hint text updated to "Quantity determined by synergy analysis" instead of locked 4x/3x

**Architecture improvements:**
- Extracted ~570 lines of auto-build logic into `scripts/auto_build.py` (land analysis, Karsten mana base, card utilities, CSV manipulation)
- Moved `scaffold_gui.py` from `scripts/` to project root (backward-compatible redirect at old path)
- GUI reduced from 2029 lines to 1358 lines

---

## v10.0 — April 13, 2026

### 🎉 Major improvements

**Synergy analysis system rewrite**
- Decomposed the 1,124-line `synergy_analysis.py` monolith into 4 focused modules:
  - `synergy_types.py` — Enums (`InteractionType`, `CardRole`, `ThresholdStatus`), data classes (`SynergyProfile`, `CardScore`, `ThresholdConfig`, `ThresholdResult`), and all constants
  - `synergy_engine.py` — Card loading, profile building, single-pass O(n²) pairwise scoring engine
  - `synergy_thresholds.py` — Threshold calibration and structured pass/fail checking
  - `synergy_report.py` — Markdown, JSON, and CSV report generation
- `synergy_analysis.py` is now a thin ~260-line CLI wrapper

**Performance improvements**
- Merged 5 separate O(n²) pairwise loops into a single pass (~4× less iteration overhead)
- Pre-compiled all regex patterns at module load time
- Pre-built oracle text index for faster cross-reference

**Scoring improvements**
- Confidence-weighted interactions: oracle-confirmed = 1.5×, tag-inferred = 1.0×, heuristic = 0.5×
- `INTERACTION_WEIGHTS` map replaces hardcoded weight values
- Configurable composite score formula via `CompositeWeights` dataclass
- Proper `InteractionType` enum replaces string literals

**Report improvements**
- New synergy matrix visualization (ASCII table showing card-to-card interaction types)
- New role distribution summary table (Engine/Enabler/Payoff/Support/Interaction with counts and %)
- Graph-based synergy chain detection via BFS (replaces simple hub-picking)
- Score table grouped by role with subheadings
- New JSON export format (`--report-format json`) for machine consumption
- Structured `ThresholdResult` objects replace plain string messages

**New CLI flags**
- `--report-format` — Choose between `markdown` (default) and `json` output
- `--verbose` — Show per-pair interaction details

**Testing**
- Added 66 unit tests across 5 test classes covering all modules
- Test categories: types, engine, thresholds, report generation, integration
- Integration tests use `test-corpus/` directory with good/borderline/bad decks
- Run with: `python -m unittest discover tests/ -v`

**Infrastructure**
- Added `CARD_TYPES` to `mtg_utils.py` as single source of truth
- Original monolith preserved as `synergy_analysis_legacy.py` for reference
- Architecture plan documented in `plans/synergy_revamp.md`

### Backward compatibility
- All existing CLI flags preserved (`--format`, `--output`, `--mode`, `--top`, `--include-sideboard`, `--allow-missing`, `--primary-axis`)
- Legacy flags (`--min-synergy`, `--score-mode`) accepted but hidden
- Same exit codes: 0 = passed, 1 = failed/inconclusive, 2 = input error

---

## v9.0 — March 21, 2026

### 🎉 Major improvements

**Search-first deck building protocol**
- Added `scripts/search_cards.py` — AI card search tool with 25+ strategic tags
  - Tags: `lifegain`, `mill`, `draw`, `removal`, `counter`, `ramp`, `token`, `bounce`,
    `discard`, `tutor`, `wipe`, `protection`, `pump`, `reanimation`, `etb`, `tribal`,
    `scry`, `surveil`, `flash`, `haste`, `trample`, `flying`, `deathtouch`, `vigilance`,
    `reach`, `menace`
  - Filters: `--type`, `--colors`, `--tags`, `--oracle`, `--name`, `--cmc-max/min`,
    `--rarity`, `--keywords`, `--format`, `--show-tags`, `--limit`
  - Color identity subset matching (e.g. `WB` finds all cards playable in Orzhov)
  - Exact color match with `=WB` prefix
  - Output formats: table, csv, names
- Replaces manual file-by-file CSV sweeps — AI now runs targeted queries instead
  of opening 100+ files to build a candidate pool

**Strategic tags column added to CSV schema**
- `fetch_and_categorize_cards.py` now computes a `tags` column for every card
- Pre-computed at database generation time for instant querying
- `cards_by_category/` CSVs gain a `tags` column on next `fetch_and_categorize_cards.py` run

**Unified validator**
- `validate_decklist.py` now handles both online (CSV) and offline (local_db) modes
- `--local` flag uses pre-built `local_db/` for fast validation
- `--local --sqlite` uses SQLite backend
- `validate_decklist_local.py` removed (functionality merged)

**Deck registry**
- Added `scripts/index_decks.py` — auto-generates `Decks/_INDEX.md`
- Extracts: date, archetype, colors, format, card count, win condition, key cards
- CI now regenerates index on every push

**CI improvements**
- Validation now also triggers on `cards_by_category/**` changes
- Standard rotation automatically flags all stored decks with newly illegal cards
- CI auto-commits regenerated `Decks/_INDEX.md` after each push

**Cleanup**
- Deleted 3 deprecated stub files: `DECK_BUILDING_PROTOCOL.md`,
  `Deck_builder_instructions.md`, `Deck_building_guidelines.md`

**AI_INSTRUCTIONS.md v9.0**
- Gate 1 now uses `search_cards.py` queries instead of manual CSV sweeps
- Added clarifying questions requirement for ambiguous archetypes
- Added interaction justification requirement to Gate 3
- Added `--local` flag docs to validation section
- Updated session acknowledgment to reference search-first workflow

---

## v5.0 — March 9, 2026

### 🎉 Major improvements

**Automated validation**
- Added `scripts/validate_decklist.py` - automated deck legality validator
- Validates all cards in decklist.txt against cards_by_category directory database
- Provides clear pass/fail output with illegal card identification
- Prevents illegal cards from entering repository
- Exit code integration for CI/CD pipelines

**Consolidated AI instructions**
- Created `AI_INSTRUCTIONS.md` as single source of truth for all AI deck building
- Consolidated content from:
  - `Deck_builder_instructions.md` (13KB)
  - `DECK_BUILDING_PROTOCOL.md` (3.7KB)
  - `Deck_building_guidelines.md` (6.5KB)
- All other instruction files now deprecated
- Reduced instruction overload - AI now has ONE file to follow

**Enhanced README**
- Added prominent "🛑 AI ASSISTANTS: STOP" section at top
- Clear 5-step workflow before deck building begins
- Validation script documentation and examples
- Points to AI_INSTRUCTIONS.md as authoritative source

### Breaking changes
- **Deprecated files** (content merged into AI_INSTRUCTIONS.md):
  - `Deck_builder_instructions.md` → Use `AI_INSTRUCTIONS.md`
  - `DECK_BUILDING_PROTOCOL.md` → Use `AI_INSTRUCTIONS.md`
  - `Deck_building_guidelines.md` → Use `AI_INSTRUCTIONS.md`
  - `AI_DECK_BUILDER_INSTRUCTIONS.md` → Use `AI_INSTRUCTIONS.md`
  - `AI_DECK_BUILDING_GUIDELINES.md` → Use `AI_INSTRUCTIONS.md`

### New files
- `scripts/validate_decklist.py` - 250 lines, full validation with detailed output
- `AI_INSTRUCTIONS.md` - 12.5KB, comprehensive single-file instructions

### Workflow changes

**Old workflow:**
1. AI reads multiple instruction files (often skips some)
2. AI builds deck
3. Manual verification catches illegal cards
4. Back-and-forth to fix issues

**New workflow:**
1. AI reads ONE instruction file (AI_INSTRUCTIONS.md)
2. AI loads database CSVs
3. AI builds deck using verified cards
4. AI runs `validate_decklist.py`
5. Automated validation catches any issues before submission
6. AI includes validation result in analysis.md

### Impact on issues

This release directly addresses:
- **Issue #1**: AI ignoring instructions → Single authoritative file reduces confusion
- **Issue #2**: No database validation → Validation script enforces legality

### Philosophy

> "The best validation is the one that runs automatically."
> "One source of truth beats five sources of confusion."

---

## v4.0 — March 8, 2026 (formerly v3.0)

### Breaking changes
- Card database directory renamed from `cards_by_category/` to `cards_by_category directory/`
- Files reorganized from `creature_part1.csv … creature_part5.csv` (arbitrary row-count chunks, 400KB each) to `creature/creature_a.csv … creature/creature_z.csv` (first-letter splits, ≤80KB each)
- All root markdown files renamed to sentence case

### New
- `cards_by_category directory/` with type subfolders and letter-split CSVs
- Updated `scripts/fetch_and_categorize_cards.py` to output letter-split files
- `Deck_builder_instructions.md` replaces `AI_DECK_BUILDER_INSTRUCTIONS.md`
- `Deck_building_guidelines.md` replaces `AI_DECK_BUILDING_GUIDELINES.md`
- `Rules_reference.md` replaces `MTG_RULES_REFERENCE.md`
- `Changelog.md` replaces `CHANGELOG.md`

### Removed
- `OPTIMIZATION_COMPLETE.md` (stale)
- `TEST_REPORT.md` (stale)
- Old flat-file structure

### Improvements
- Max file size reduced from 400KB to 80KB — no more API truncation
- Direct card lookup: know type + first letter → open one file immediately
- Truncation warnings removed from AI instructions (no longer applicable)
- README fully rewritten to reflect current structure

---

## v3.0 — March 5, 2026

- Initial CSV-only card database (`cards_by_category/`)
- Cards split by type into flat part files (creature_part1–5, land_part1–3, etc.)
- 400KB size limit per file
- Added `AI_DECK_BUILDER_INSTRUCTIONS.md` v4.x series

---

## v2.0 — February 2026

- Initial repository with `standard_cards.json` (monolithic 3MB file)
- Basic deck folder structure
- First decks published
