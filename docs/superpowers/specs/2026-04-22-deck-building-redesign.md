# Deck Building Strategy Redesign

## Problem Statement

The current system produces decks with sophisticated synergy analysis but fails at fundamental deck construction. The Esper Angel Mill deck exemplifies this: 74.5 EV score but 2/13 (15.4%) win rate due to mana bottlenecks, role imbalances, and missing basic constraints.

## Core Issues

1. **Archetype Query Fragmentation** - Separate queries per archetype create incomplete pools for multi-strategy decks
2. **Missing Fundamentals Enforcement** - No constraints on mana curves, role distribution, or basic playability  
3. **Synergy Overoptimization** - Pairwise interaction density ignores whether decks can actually execute
4. **Panel Evaluator Blind Spots** - High EV scores mask critical construction flaws
5. **Gate System Complexity** - 6-gate protocol is over-engineered and misses obvious issues

---

## Proposed Solution: Fundamentals-First Deck Building

### Phase 1: Simplified Archetype System
Replace archetype-specific queries with **strategy role queries** that ensure comprehensive coverage:

```python
STRATEGY_ROLES = {
    "aggro": ["early_creatures", "removal", "lands"],
    "control": ["counters", "removal", "board_wipes", "win_cons", "lands"], 
    "combo": ["combo_pieces", "protection", "win_cons", "lands"],
    "midrange": ["efficient_creatures", "removal", "card_advantage", "win_cons", "lands"],
    "ramp": ["ramp_effects", "win_cons", "protection", "lands"],
}
```

**Multi-strategy decks** combine roles: "Esper Angel Mill" = lifegain + mill + control + tribal_roles

### Phase 2: Hard Construction Constraints
Before any optimization, enforce **minimum viable deck** requirements:

```python
CONSTRUCTION_CONSTRAINTS = {
    "min_lands": 23,
    "max_avg_cmc": 3.2, 
    "min_early_plays": 12,  # CMC 1-2 cards
    "min_removal": 8,
    "min_win_conditions": 6,
    "max_single_card_copies": 4,
    "mana_curve_ideal": [8, 12, 10, 6, 4],  # CMC distribution
}
```

**Validation gates:**
- ✅ Legal (database verification)
- ✅ Constructed (count/copy limits)  
- ✅ Functional (mana curve, role distribution)
- ✅ Balanced (no single points of failure)

### Phase 3: Practical Optimization
Replace sophisticated synergy analysis with **playability-first optimization**:

1. **Mana Curve Optimization** - Ensure smooth curves before synergy
2. **Role Distribution Optimization** - Balance enablers/payoffs before density
3. **Synergy Enhancement** - Only optimize interactions within playable frameworks

### Phase 4: Simplified Evaluation
Replace 10-archetype panel with **practical win rate predictors**:

- **Mana Efficiency** (0-100): How well curve supports game plan
- **Role Balance** (0-100): Distribution of enablers vs payoffs  
- **Interaction Coverage** (0-100): Answer to common threats
- **Game Plan Clarity** (0-100): How focused the strategy is

**Combined Score = (Mana + Roles + Interaction + Clarity) / 4**

---

## Implementation Stages

### Stage 1: Query System Redesign
**Goal:** Create comprehensive candidate pools for any strategy combination

- Replace `ARCHETYPE_QUERIES` with `ROLE_QUERIES`
- Add multi-strategy merge logic
- Ensure 100% coverage of needed card types

### Stage 2: Constraint System Implementation  
**Goal:** Prevent unplayable decks at generation time

- Add `validate_construction()` function
- Hard-block decks that fail basic requirements
- Provide clear feedback on constraint violations

### Stage 3: Optimization Algorithm Rewrite
**Goal:** Produce actually playable optimized decks

- Phase 1: Construction optimization (curves, roles)
- Phase 2: Synergy enhancement within constraints  
- Phase 3: Fine-tuning for EV

### Stage 4: Evaluation System Overhaul
**Goal:** Score decks on real playability, not theoretical synergy

- Replace mythic panel with practical metrics
- Add bottleneck detection for construction issues
- Weight fundamentals higher than sophistication

---

## Success Criteria

- **Deck Playability:** 80%+ of generated decks should be tournament-viable (50%+ win rate)
- **Strategy Coverage:** Handle any combination of archetypes without gaps
- **Construction Soundness:** Zero decks with mana bottlenecks or role imbalances  
- **Optimization Effectiveness:** EV improvements should translate to real win rate gains

This redesign prioritizes **simplicity and fundamentals** over sophisticated complexity, ensuring every generated deck is actually playable before optimizing for perfection.</content>
<parameter name="filePath">docs/superpowers/specs/2026-04-22-deck-building-redesign.md