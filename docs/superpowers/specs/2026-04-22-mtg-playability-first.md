# MTG Deck Building Revolution: Playability-First Approach

## The Fundamental Problem

The current system optimizes for **synergy density** but produces decks that lose 85% of games. This is because:

1. **Synergy ≠ Playability** - High synergy scores don't prevent mana floods, curve stalls, or lack of interaction
2. **Missing Fundamentals** - No validation of basic MTG requirements (lands, removal, win conditions)
3. **Over-Engineered Complexity** - 6-gate protocol creates analysis paralysis instead of good decks

## Radical Solution: Archetype Templates + Constraint Satisfaction

Instead of complex synergy optimization, use **proven archetype templates** with hard constraints:

### 1. Archetype Templates (Battle-Tested Frameworks)

```python
ARCHETYPE_TEMPLATES = {
    "aggro": {
        "curve_target": [12, 10, 8, 4, 2],  # CMC distribution
        "min_removal": 6,
        "min_creatures": 20,
        "max_lands": 18,
        "card_slots": {
            "early_drops": {"min": 8, "max": 12, "tags": ["haste", "pump"]},
            "removal": {"min": 6, "max": 8, "tags": ["removal"]},
            "finishers": {"min": 4, "max": 6, "tags": ["evasive", "pump"]},
            "lands": {"min": 16, "max": 18}
        }
    },
    "control": {
        "curve_target": [4, 8, 12, 10, 6],
        "min_removal": 12,
        "min_win_cons": 8,
        "max_lands": 26,
        "card_slots": {
            "counters": {"min": 8, "max": 12, "tags": ["counter"]},
            "removal": {"min": 8, "max": 10, "tags": ["removal"]},
            "card_draw": {"min": 6, "max": 8, "tags": ["draw"]},
            "win_cons": {"min": 6, "max": 10, "tags": ["finishers"]}
        }
    }
}
```

### 2. Constraint Satisfaction Algorithm

**Phase 1: Fill Required Slots**
```python
def build_deck_from_template(archetype, colors):
    deck = []
    
    # Fill each required slot with best available cards
    for slot_name, constraints in ARCHETYPE_TEMPLATES[archetype]["card_slots"].items():
        candidates = query_cards_by_constraints(constraints, colors)
        selected = select_best_cards(candidates, constraints["min"], constraints["max"])
        deck.extend(selected)
    
    # Ensure curve matches target distribution
    deck = balance_curve(deck, ARCHETYPE_TEMPLATES[archetype]["curve_target"])
    
    return deck
```

**Phase 2: Mana Base Auto-Builder**
```python
def build_mana_base(deck, colors):
    """Calculate exact land counts for 95% color access."""
    mana_requirements = analyze_mana_costs(deck)
    
    # Use existing mana_base_advisor but enforce minimums
    land_counts = calculate_optimal_lands(mana_requirements, len(deck))
    
    # Ensure at least 23 lands total
    total_lands = max(23, sum(land_counts.values()))
    
    return distribute_lands(total_lands, mana_requirements, colors)
```

### 3. Simplified Validation

**Hard Requirements (No Exceptions):**
- ✅ 23+ lands
- ✅ Curve within 20% of archetype target
- ✅ Minimum slot requirements met
- ✅ 95%+ mana access probability
- ✅ Legal (database verification)

**Soft Optimization:**
- Maximize card quality within constraints
- Balance creature/removal/spell ratios
- Ensure meta-relevant interaction

### 4. Multi-Strategy Support

For complex decks like "Esper Angel Mill":

```python
def build_multi_strategy_deck(strategies, colors):
    """Merge multiple archetype templates."""
    combined_template = merge_templates(strategies)
    return build_deck_from_template(combined_template, colors)
```

**Template Merging Rules:**
- Take maximum of minimums (more removal if control + aggro)
- Average curve targets
- Combine card slots with conflict resolution

## Implementation Benefits

1. **Guaranteed Playability** - Every deck meets minimum standards
2. **Archetype Fidelity** - Follows proven MTG patterns
3. **Fast Generation** - No complex optimization loops
4. **Predictable Results** - Similar inputs produce similar outputs
5. **Easy Balancing** - Adjust templates, not algorithms

## Migration Path

**Phase 1: Template System** (Replace scaffold generator)
- Implement archetype templates
- Build constraint satisfaction algorithm
- Test against known good decks

**Phase 2: Replace Optimization** (Replace synergy system)
- Remove complex pairwise scoring
- Use template + quality ranking
- Validate win rates improve

**Phase 3: Meta Adaptation** (Template evolution)
- Update templates based on meta changes
- A/B test template variations
- Community feedback integration

This approach shifts from "mathematically optimal synergy" to "battle-tested patterns with quality cards" - the way humans actually build good MTG decks.</content>
<parameter name="filePath">docs/superpowers/specs/2026-04-22-mtg-playability-first.md