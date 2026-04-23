# Debug Report: Why Esper Angel Mill Performs Poorly

## Root Cause Analysis

The Esper Angel Mill deck fails because the deck building system prioritizes **synergy density** over **fundamental playability**. Here's exactly what went wrong:

### 1. Query Strategy Problems

**Overly Broad Queries Created Imbalanced Pool:**
- **453 lifegain creatures** but no requirement for curve distribution
- **168 mill cards** but mill wasn't prioritized over lifegain
- **453 high-cost win conditions** (CMC 4+) flooded the pool with finishers
- **636 land options** but no mana base planning

**Result:** Candidate pool of 1090 cards with no strategic focus or balance constraints.

### 2. Selection Process Failures

**Synergy Optimizer Selected Mathematically Optimal but Strategically Poor Cards:**
- Chose 4x Enduring Tenacity (3-mana enchantment) but ignored that it's not a creature
- Selected angel tribal cards but didn't ensure angel payoffs
- Picked 3x Bloodthirsty Conqueror (5-mana) but no early game to support it
- Included mill commander (Hope Estheim) but almost no mill enablers

**Result:** Deck with high "synergy scores" but no coherent game plan.

### 3. Mana Base Catastrophe

**Only 23 Lands with Poor Distribution:**
- 4 Plains, 2 Island, 2 Swamp = only 8 basic lands
- Heavy reliance on dual lands but insufficient white sources for angels
- Hope Estheim costs {W}{U} but deck has ~12 white sources vs ~16 blue sources

**Result:** Frequent mana flood/stall, inability to cast key cards.

### 4. Curve and Role Imbalances

**Curve Issues:**
- Too many 4-mana angels (Resplendent Angel, Lyra Dawnbringer)
- Not enough 1-2 mana plays
- CMC average too high for Esper colors

**Role Issues:**
- 3 creatures doing mill (Hope Estheim) but no mill payoffs
- 4 lifegain enablers (Midnight Snack) but no lifegain synergies
- Only 2 removal spells in 60-card deck

## Specific Fixes Needed

### Fix 1: Constrain Query Scope by Archetype Priority

Instead of running all queries equally, prioritize based on declared strategy:

```python
# For "Lifegain, Opp_Mill, Control (Angel Tribal)"
STRATEGY_PRIORITY = {
    "primary": "lifegain",      # 60% of card slots
    "secondary": "opp_mill",    # 25% of card slots  
    "tertiary": "control",      # 15% of card slots
    "tribal": "angel"           # Theme constraint
}
```

### Fix 2: Enforce Minimum Curve Requirements

Add hard curve validation before selection:

```python
MINIMUM_CURVE = {
    "cmc_1": 6,    # Early plays
    "cmc_2": 8,    # Efficient creatures
    "cmc_3": 10,   # Value creatures
    "cmc_4_plus": 8 # Finishers
}
```

### Fix 3: Require Role Distribution

Ensure every deck has minimum interaction:

```python
REQUIRED_ROLES = {
    "removal": {"min": 8, "max": 12},
    "win_conditions": {"min": 6, "max": 10},
    "card_advantage": {"min": 4, "max": 8},
    "lands": {"min": 23, "max": 26}
}
```

### Fix 4: Fix Mana Base Generation

Use the existing mana_base_advisor but enforce minimums:

```python
def build_mana_base(deck, colors):
    mana_reqs = analyze_deck_mana_costs(deck)
    land_counts = calculate_optimal_lands(mana_reqs, len(deck))
    
    # Enforce minimums
    total_lands = max(24, sum(land_counts.values()))  # At least 24 lands
    land_counts = redistribute_lands(total_lands, mana_reqs, colors)
    
    return land_counts
```

## Immediate Action Plan

1. **Modify Scaffold Generator** - Add archetype priority weighting to queries
2. **Add Pre-Selection Validation** - Reject decklists that fail curve/role minimums  
3. **Fix Mana Base Logic** - Ensure sufficient colored sources before optimization
4. **Simplify Optimizer** - Remove complex synergy math, use quality + constraints

This will transform the system from "theoretically optimal synergy" to "guaranteed playable decks with good cards".</content>
<parameter name="filePath">debug_report.md