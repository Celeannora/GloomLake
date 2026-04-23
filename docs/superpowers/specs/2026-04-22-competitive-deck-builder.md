# Competitive MTG Deck Builder - Complete System Rewrite

## Analysis of Current Competitive Standard

**Top Decks (April 2026):**
- **Mono-Green Landfall** (16.3%): 23-25 lands, 16-18 creatures, focused landfall payoffs
- **Izzet Prowess** (15.6%): CMC 2.4 avg, storm count payoffs, cheap pump spells
- **Dimir Excruciator** (9.8%): 24 lands, balanced removal, lifegain payoffs

**Competitive Standards:**
- **Mana Curves**: 50%+ of deck CMC 1-2, avg CMC 2.0-2.5
- **Land Counts**: 23-26 lands (60-card), 16-17 (40-card)
- **Role Ratios**: 40-50% creatures, 30-40% spells, 20-25% lands
- **Strategy Focus**: 1-2 win conditions, not 3+ diluted approaches
- **Meta Awareness**: Counter top decks with appropriate tools

## Complete System Rewrite

### Phase 1: Archetype Templates (Competitive Blueprints)

Replace complex queries with proven templates:

```python
COMPETITIVE_ARCHETYPES = {
    "mono_green_landfall": {
        "name": "Mono-Green Landfall",
        "colors": "G",
        "curve_target": {"1": 8, "2": 10, "3": 6, "4+": 4},
        "land_count": 25,
        "card_slots": {
            "ramp_creatures": ["Badgermole Cub", "Icetill Explorer"],
            "landfall_payoffs": ["Earthbender Ascension", "Tectonic Stomp"],
            "finishers": ["Colossal Dreadmaw", "Voracious Troll"],
            "utility": ["Tailspike Harpooner", "Pawpatch Formation"]
        },
        "meta_counter": "aggro_heavy"  # Counters fast decks
    },

    "izzet_prowess": {
        "name": "Izzet Prowess",
        "colors": "UR",
        "curve_target": {"1": 12, "2": 8, "3": 6, "4+": 2},
        "land_count": 23,
        "card_slots": {
            "prowess_creatures": ["Stormchaser Drake", "Third Path Iconoclast"],
            "cheap_spells": ["Lightning Bolt", "Brainstorm"],
            "pump_effects": ["Monstrous Rage", "Ancestral Anger"],
            "finishers": ["Slickshot Show-Off", "Ral, Crackling Wit"]
        },
        "meta_counter": "control_heavy"
    }
}
```

### Phase 2: Automated Mana Base Builder

Replace manual land selection with competitive algorithms:

```python
def build_competitive_mana_base(deck, colors, target_lands):
    """Build mana base matching top tournament decks."""
    mana_reqs = analyze_mana_symbols(deck)

    # Use proven land ratios from meta
    if len(colors) == 1:
        # Monocolor: 20 basics + 3-5 utility
        basics_needed = target_lands - 4
        return [f"{color} Basic Land"] * basics_needed + get_utility_lands(colors, 4)

    elif len(colors) == 2:
        # Dual: 8-10 duals, 8-12 basics, 2-4 utility
        duals = get_dual_lands(colors, min(10, target_lands // 2))
        basics = distribute_basics(colors, target_lands - len(duals) - 2)
        utility = get_utility_lands(colors, 2)
        return duals + basics + utility

    # Handle 3+ colors with fetch/shock lands
    return build_multicolor_mana_base(deck, colors, target_lands)
```

### Phase 3: Curve Optimization Engine

Enforce competitive curve standards:

```python
def optimize_curve(deck, target_curve):
    """Optimize deck to match target CMC distribution."""
    current_curve = analyze_curve(deck)

    # Identify imbalances
    adjustments = {}
    for cmc, target_count in target_curve.items():
        current_count = current_curve.get(cmc, 0)
        if current_count < target_count:
            adjustments[cmc] = target_count - current_count

    # Replace high-curve cards with low-curve alternatives
    replacements = find_curve_replacements(deck, adjustments)

    return apply_replacements(deck, replacements)
```

### Phase 4: Meta-Aware Sideboarding

Automatically build sideboards based on meta:

```python
def build_competitive_sideboard(maindeck, archetype, meta_context):
    """Build sideboard matching competitive practices."""
    meta_counters = COMPETITIVE_ARCHETYPES[archetype]["meta_counter"]

    sideboard_slots = {
        "aggro": ["board_wipes", "life_gain", "tax_effects"],
        "control": ["graveyard_hate", "extra_removal", "artifact_hate"],
        "combo": ["counterspells", "discard", "fast_interaction"]
    }

    # Fill sideboard based on meta positioning
    return fill_sideboard_slots(sideboard_slots[meta_counters], 15)
```

## Implementation: Complete System Replacement

### Step 1: Replace Scaffold Generator with Template System

```python
def generate_competitive_scaffold(archetype_name, colors):
    """Generate deck using competitive template."""
    template = COMPETITIVE_ARCHETYPES[archetype_name]

    # Build maindeck from template slots
    maindeck = []
    for slot_type, card_options in template["card_slots"].items():
        count = template["slot_counts"].get(slot_type, 4)
        selected = select_best_cards(card_options, count)
        maindeck.extend(selected)

    # Optimize curve to template target
    maindeck = optimize_curve(maindeck, template["curve_target"])

    # Build competitive mana base
    lands = build_competitive_mana_base(maindeck, colors, template["land_count"])

    # Create sideboard
    sideboard = build_competitive_sideboard(maindeck, archetype_name, current_meta())

    return maindeck + lands, sideboard
```

### Step 2: Remove Complex Synergy Analysis

Replace with simple quality ranking:

```python
def select_best_cards(card_pool, count, criteria="power_level"):
    """Select top cards by simple metrics."""
    if criteria == "power_level":
        # Sort by rarity, converted mana cost, keywords
        return sorted(card_pool, key=lambda c: card_power_score(c))[:count]
    elif criteria == "synergy":
        # Simple tag matching instead of complex analysis
        return find_tag_synergies(card_pool, count)
```

### Step 3: Add Meta Awareness

```python
def current_meta():
    """Get current meta composition from external data."""
    # Query MTGGoldfish or similar for current top decks
    meta_data = fetch_meta_data()
    return analyze_meta_composition(meta_data)

def adjust_for_meta(deck, meta_context):
    """Adjust deck based on current meta positioning."""
    # Add/removes based on meta weaknesses
    adjustments = calculate_meta_adjustments(deck, meta_context)
    return apply_adjustments(deck, adjustments)
```

## Success Metrics

**Deck Quality Standards:**
- ✅ **Curve**: 50%+ CMC 1-2, avg CMC ≤2.5
- ✅ **Mana**: 95%+ access probability for all colors
- ✅ **Roles**: 40-50% creatures, 30-40% interaction
- ✅ **Meta**: Appropriate tools vs top 3 decks
- ✅ **Win Rate**: 50%+ against random meta decks

**System Performance:**
- ⚡ **Generation**: <30 seconds per deck
- 🎯 **Consistency**: Same archetype always produces similar quality
- 🔄 **Adaptability**: Auto-adjusts to meta changes
- 📊 **Validation**: Built-in quality checks prevent bad decks

This system will produce tournament-ready decks that match current competitive standards, not theoretically optimal but practically unplayable decks.</content>
<parameter name="filePath">docs/superpowers/specs/2026-04-22-competitive-deck-builder.md