# Project Context

## Tech Stack
- Language: Python 3.10+
- Core Libraries: sqlite3 (stdlib, card DB), re (text parsing), pathlib (filesystem), collections.OrderedDict
- GUI: PySide6 6.5+ (Qt for Python) — scaffold_gui.py (Qt 6 bindings)
- SVG Assets: mtg-vectors-main (mana symbols, guild/shard watermarks, set symbols)
- Worker Threads: QThread for non-blocking deck generation and synergy builds
- Dev/Test Tools: Pytest 7.0+ (testing), py_compile (syntax check)
- Packaging: pyproject.toml (PEP 621 compliant), pip for dependency management

## Rules
- Always run pytest before marking any task complete.
- Fix every test failure before moving on — never skip.
- Keep functions small and single-purpose (refactor if > 40 lines).
- Prefer explicit over implicit: no magic strings, no unclear variable names.
- SVG assets preferred over programmatic icons; fall back when SVG missing.
- After adding or changing a feature, update /docs (create the folder if missing).
- Toast notifications for transient status; status bar for persistent state.
- Use make_panel() helper for consistent panel styling (glassmorphism pattern).

## File Conventions
- Source code lives in /scripts (autonomous_agent.py, greedy_synergy_engine.py, etc.)
- Root-level: scaffold_gui.py (main GUI entry point, ~2200 lines)
- SVG assets at assets/mtg-vectors-main/svg/ (set, watermark subdirectories)
- Card database at assets/data/cards.db (SQLite)
- Tests live in /tests (mirrors /scripts structure)
- Configuration files stay at the project root
- Generated artifacts go to /generated_decks
- UI audit documentation: root-level YYYY-MM-DD_ui-audit.md

## Architecture
- scripts/autonomous_agent.py — Main agent loop (Mode A: deck building, Mode B: code audit)
- scripts/greedy_synergy_engine.py — Greedy deck selection with synergy scoring
- scripts/research_module.py — Research-backed improvement suggestions
- scripts/analysis/synergy_optimizer.py — Karpathy-style hill-climbing optimizer
- scripts/auto_improve.py — Automated code quality scanner (TODO/FIXME, long funcs)
- scaffold_gui.py — PySide6 GUI with 4 tabs:
  - Scaffold: deck config (colors, archetypes, tribes, tags, focus cards) → CLI generate
  - Quick Build: synergy engine build with live results, charts, deck/land tables
  - Deck Analysis: load .txt decklist → synergy analysis report
  - History: last 15 decks with restore capability

## GUI Features
- SVG mana symbols (WUBRG) from mtg-vectors-main with programmatic fallback
- SVG guild/shard watermarks on color selection (Abzan, Dimir, Esper, etc.)
- Animated mana curve chart (QPropertyAnimation bar build-up)
- Color-pie donut chart (WUBRG distribution)
- Rarity-colored card rows (Common=gray, Uncommon=silver, Rare=gold, Mythic=orange)
- Live deck table search/filter (by name, type, CMC)
- Sortable table columns (click header to sort)
- Keyboard shortcuts: Ctrl+N (new), Ctrl+B (build), Ctrl+E (export), Ctrl+Q (quit), F5 (refresh), F11 (fullscreen)
- QSettings persistence (window geometry, last format)
- Deck validation (60-card min, 4-of limit)
- Multiple export formats: .txt, .csv, Arena import
- Error recovery with retry dialog on build failure
- Color presets dropdown (25 guilds/shards/WUBRG)
- Toast notification system with auto-dismiss
- Right-click context menu on deck tables

## Commit Style (Conventional Commits)
  feat:     new feature
  fix:      bug fix
  refactor: code change with no feature or bug fix
  docs:     documentation only
  test:     adding or fixing tests
  chore:    build or tooling changes