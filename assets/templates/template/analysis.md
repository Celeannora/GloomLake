# Deck Analysis: [Archetype Name]

**Date:** YYYY-MM-DD  
**Format:** Standard  
**Colors:** [W/U/B/R/G]

---

## Database Verification

### Files Loaded

- `cards_by_category/creature/creature_x.csv`
- `cards_by_category/instant/instant_x.csv`
- `cards_by_category/land/land_x.csv`

### Legality Confirmation

- [ ] All 60 mainboard cards verified present in database
- [ ] All 15 sideboard cards verified present in database

### Validation Script Result

```bash
$ python scripts/validate_decklist.py Decks/YYYY-MM-DD_Archetype/decklist.txt
✅ VALIDATION PASSED
```

---

## Executive Summary

- **Archetype:** [Aggro / Midrange / Control / Combo]
- **Primary win condition:** [Describe]
- **Target win turn:** Turn [N]
- **Metagame positioning:** [Describe]

---

## Synergy Evaluation

### Synergy Scores

| Card | Synergy Count | Role Breadth | Dependency | Notes |
|------|--------------|-------------|------------|-------|
| [Card Name] | N | N | N | [Key interaction types and partners] |

**Average Synergy Count:** X.X (threshold: ≥ 3.0)  
**Cards with Synergy Count 0–1:** N (max: 4)  
**Hub cards (Synergy Count ≥ 8):** N (min: 2)

### Synergy Chains

**Chain 1 — [Function]:**  
[Card A] → [output] → [Card B] → [output] → [Card C] → [outcome]  
Redundancy: [substitutes available]  
Minimum pieces to function: [N of M]

**Chain 2 — [Function]:**  
[Card X] → ... → [outcome]  
Redundancy: ...  
Minimum pieces to function: ...

### Redundant Pairs

| Card A | Card B | Justification for Both |
|--------|--------|------------------------|
| [Name] | [Name] | [Why both are included] |

---

## Card-by-Card Breakdown

### Creatures

**4x [Card Name]**  
*Source: `cards_by_category/creature/creature_x.csv`*  
[Justification]

### Spells

**4x [Card Name]**  
*Source: `cards_by_category/instant/instant_x.csv`*  
[Justification]

### Lands

**4x [Land Name]**  
*Source: `cards_by_category/land/land_x.csv`*  
[Justification]

---

## Mana Base Analysis

- **Color requirements:** [List pip counts]
- **Land count:** [N] ([Formula justification])
- **Utility lands:** [Describe]

---

## Curve Analysis

| CMC | Cards | Count |
|-----|-------|-------|
| 1   | [Names] | N |
| 2   | [Names] | N |
| 3   | [Names] | N |
| 4+  | [Names] | N |

**Ideal turn sequence:** [Describe turns 1-5]

---

## Matchup Table

| Matchup | Pre-Board | Post-Board |
|---------|-----------|------------|
| Aggro   | ?%        | ?%         |
| Midrange| ?%        | ?%         |
| Control | ?%        | ?%         |

---

## Structural Weaknesses

1. **[Weakness 1]** — Mitigation: [Describe]
2. **[Weakness 2]** — Mitigation: [Describe]
3. **[Weakness 3]** — Mitigation: [Describe]

---

## Playtesting Notes

[Theoretical goldfish analysis, critical turn identification]
