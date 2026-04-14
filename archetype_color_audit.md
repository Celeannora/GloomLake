# Archetype Color Audit Report

**Date:** 2026-04-07
**Scope:** All scripts in `scripts/` that map archetypes to search queries or card filters.

---

## Files Audited

### 1. `scripts/generate_deck_scaffold.py` — COLOR RESTRICTIONS FOUND AND REMOVED

#### Location A: `run_query()` function (line ~389)

**Before:**
```python
cmd_parts += ["--colors", colors]
```
The `run_query()` function automatically injected `--colors <user_colors>` into **every** archetype query. This forced all dict-format archetype queries (aggro, midrange, control, combo, lifegain, tribal, ramp, tempo, burn) to return only cards matching the user's chosen color identity.

**After:**
```python
# color-agnostic: no --colors injection; archetypes search across all colors
```
Removed. Docstring updated to document the color-agnostic behavior.

Also removed the duplicate `--colors` injection in the extra-tags rebuild path (was on the same function's else branch).

#### Location B: `ARCHETYPE_QUERIES` — 28 list-format entries with `--colors {colors}`

Every list-format archetype had a final "catch-all by tag" query that included `"--colors", "{colors}"`. These were:

| Archetype | Line(s) | Entry |
|-----------|---------|-------|
| opp_mill | 150 | `["--tags", "mill", "--colors", "{colors}", ...]` |
| self_mill | 158 | `["--tags", "self_mill", "--colors", "{colors}", ...]` |
| reanimation | 165, 167 | `["--tags", "reanimation", "--colors", "{colors}", ...]` and `["--oracle", "sacrifice a creature", "--colors", "{colors}", ...]` |
| aristocrats | 212 | `["--tags", "aristocrats", "--colors", "{colors}", ...]` |
| tokens | 219 | `["--tags", "token", "--colors", "{colors}", ...]` |
| blink | 226 | `["--tags", "blink", "--colors", "{colors}", ...]` |
| stax | 233 | `["--tags", "stax", "--colors", "{colors}", ...]` |
| storm | 240 | `["--tags", "storm", "--colors", "{colors}", ...]` |
| prowess | 247 | `["--tags", "prowess", "--colors", "{colors}", ...]` |
| enchantress | 254 | `["--tags", "enchantress", "--colors", "{colors}", ...]` |
| artifacts | 261 | `["--tags", "artifacts", "--colors", "{colors}", ...]` |
| equipment | 268 | `["--tags", "equipment", "--colors", "{colors}", ...]` |
| voltron | 275 | `["--tags", "voltron", "--colors", "{colors}", ...]` |
| landfall | 282 | `["--tags", "landfall", "--colors", "{colors}", ...]` |
| lands | 289 | `["--tags", "lands", "--colors", "{colors}", ...]` |
| infect | 295-296 | `["--oracle", "gets.*until end of turn", "--colors", "{colors}", ...]` and `["--tags", "infect", "--colors", "{colors}", ...]` |
| proliferate | 303 | `["--tags", "proliferate", "--colors", "{colors}", ...]` |
| energy | 309 | `["--tags", "energy", "--colors", "{colors}", ...]` |
| graveyard | 316 | `["--tags", "graveyard", "--colors", "{colors}", ...]` |
| madness | 330 | `["--tags", "madness", "--colors", "{colors}", ...]` |
| superfriends | 337 | `["--tags", "superfriends", "--colors", "{colors}", ...]` |
| extra_turns | 344 | `["--tags", "extra_turns", "--colors", "{colors}", ...]` |
| eldrazi | 351 | `["--tags", "eldrazi", "--colors", "{colors}", ...]` |
| vehicles | 358 | `["--tags", "vehicles", "--colors", "{colors}", ...]` |
| domain | 365 | `["--tags", "domain", "--colors", "{colors}", ...]` |

**After:** All `"--colors", "{colors}"` pairs removed. Each modified entry has a `# color-agnostic` comment.

#### Location C: Skip-queries template (line ~1154)

**Before:**
```python
"command": f"python scripts/search_cards.py {q['args']} --colors {args.colors.upper()} --show-tags",
```
**After:**
```python
"command": f"python scripts/search_cards.py {q['args']} --show-tags",
```

---

### 2. `scripts/search_cards.py` — NO COLOR RESTRICTIONS FOUND

Color filtering is entirely user-driven via the `--colors` CLI flag. No archetype-specific logic adds color restrictions. The `color_matches()` function, `TAG_RULES`, `KEYWORD_TAG_MAP`, `compute_tags()`, and `compute_synergy_profile()` are all color-agnostic.

**Status:** Clean, no changes needed.

---

### 3. `scripts/synergy_analysis.py` — NO COLOR RESTRICTIONS FOUND

`INTERACTION_RULES` and `ROLE_TAGS` define pairwise synergy logic purely by tag/mechanic matching. No color identity checks exist in the synergy scoring pipeline.

**Status:** Clean, no changes needed.

---

### 4. `scripts/sideboard_advisor.py` — NO COLOR RESTRICTIONS FOUND (user-driven)

`search_sideboard_candidates()` accepts `colors` as a parameter from the `--colors` CLI flag. The color check at line 190-193 is intentional: sideboard cards must be castable in the deck's colors. This is user-driven (the user passes `--colors WB` to get castable sideboard options), not hardcoded to an archetype.

**Status:** Clean, no changes needed. Color filtering here is appropriate (deck legality).

---

### 5. `scripts/scaffold_gui.py` — NO COLOR RESTRICTIONS FOUND

The GUI is a pure UI wrapper around `generate_deck_scaffold.py`. Color selection is passed through as user input. No additional color filtering logic exists in the GUI layer.

**Status:** Clean, no changes needed.

---

### 6. `scripts/mana_base_advisor.py` — NO COLOR RESTRICTIONS FOUND (user-driven)

Takes `--pips W:12,B:8` as user input. Computes mana base requirements based on the user's deck composition. No hardcoded color restrictions.

**Status:** Clean, no changes needed.

---

## Validation Output

### Aggro — multi-color results confirmed
```
472 cards found — includes W (White Knight, Adelbert Steiner), R (Adrenaline Jockey),
G (Afterburner Expert, Ainok Wayfarer), U (Agent of Kotis), B, and multicolor cards.
```

### Artifacts — non-colorless artifacts included
```
89 cards found — includes colorless artifacts (Adventurer's Airship),
colored artifacts (Aether Syphon UU, Boosted Sloop UR, Biorganic Carapace WU),
and multicolor entries.
```

### Tokens — multi-color options confirmed
```
791 cards found — color distribution across results:
W: 9, R: 6, B: 5, G: 4, U: 3, colorless: 77 (mostly artifacts with token creation),
plus multicolor cards (WB, WG, etc.).
```

---

## Summary

| File | Issues Found | Action |
|------|-------------|--------|
| `generate_deck_scaffold.py` | 30 color restrictions (1 in `run_query()`, 28 in `ARCHETYPE_QUERIES`, 1 in skip-queries template) | All removed |
| `search_cards.py` | 0 | No changes |
| `synergy_analysis.py` | 0 | No changes |
| `sideboard_advisor.py` | 0 (user-driven `--colors` is appropriate) | No changes |
| `scaffold_gui.py` | 0 | No changes |
| `mana_base_advisor.py` | 0 (user-driven `--pips` is appropriate) | No changes |
