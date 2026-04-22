# Deck Template

This directory contains the template structure for new MTG decks.

## How to use

1. Copy this folder to `Decks/YYYY-MM-DD_Archetype_Name/`
2. Replace all placeholder card names in `decklist.txt` with real cards from `cards_by_category/`
3. Fill out `analysis.md` following the required sections in `AI_INSTRUCTIONS.md`
4. Fill out `sideboard_guide.md` with matchup-specific boarding plans
5. Validate:

```bash
python scripts/validate_decklist.py Decks/YYYY-MM-DD_Archetype_Name/decklist.txt
```

## Deck count requirements

- **Mainboard**: exactly 60 cards
- **Sideboard**: exactly 15 cards (or 0 if no sideboard)
- **Non-basic lands**: max 4 copies of any single card

## File checklist

- [ ] `decklist.txt` — MTGA-importable format, 60 main + 15 side
- [ ] `analysis.md` — includes Database Verification section
- [ ] `sideboard_guide.md` — covers top 5 meta matchups
