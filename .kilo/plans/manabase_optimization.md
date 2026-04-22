# Mana Base Optimization Plan

## Problem Statement
The user wants to optimize mana bases to be more resilient to mulligans. Poor mana bases lead to frustrating mulligans due to color screw, mana flood, or mana starvation.

## Goal
Enhance the synergy analysis system to:
1. Calculate optimal land counts and color ratios for any deck
2. Predict mulligan probabilities based on manabase composition
3. Suggest mana base improvements during deck analysis
4. Provide mulligan resilience metrics

## Key Components to Develop

### 1. Mana Curve Analysis Enhancement
- Extend existing mana curve calculations to include land counts
- Calculate optimal land count based on:
  - Average CMC of non-land spells
  - Color requirements (pips needed)
  - Mana acceleration sources (rituals, dorks, etc.)
  - High-cost spells that enable keeping land-light hands

### 2. Mulligan Probability Model
Implement a statistical model that predicts:
- Probability of keeping a 7-card hand
- Probability of keeping a 6-card hand (after 1 mulligan)
- Probability of keeping a 5-card hand (after 2 mulligans)
- Expected number of usable lands by turn X
- Color screw probability (not having required colors by turn Y)

### 3. Mana Base Quality Metrics
Develop quantitative scores for:
- **Color Fixing Score**: How well the manabase can produce required colors
- **Mana Curve Smoothness**: Distribution of mana costs across turns
- **Early Game Consistency**: Likelihood of having 2 mana by turn 2, 3 mana by turn 3
- **Late Game Reach**: Ability to cast high-cost spells
- **Flood Resistance**: Probability of drawing too many lands

### 4. Optimization Algorithms
Implement recommendation engines that suggest:
- Optimal land count for the deck
- Ideal color ratio (if playing multiple colors)
- Suggestions for mana fixing artifacts (Signets, Talismans, etc.)
- Land type recommendations (basic vs. duals vs. fetches)
- Mana acceleration recommendations

### 5. Integration Points
- Enhance `mana_base_advisor.py` with mulligan simulation
- Add mana base analysis to `deck_architect.py`
- Create new `mulligan_simulator.py` module
- Update GUI to show mana base quality metrics
- Add mulligan resistance to mythic panel evaluation

## Technical Implementation Plan

### Phase 1: Core Mana Analysis
1. Extend `mana_base_advisor.py` with:
   - Hypergeometric distribution calculations for land draws
   - Mulligan probability simulation (7→6→5 card hands)
   - Color requirement tracking
   - Mana curve visualization data

2. Create `mulligan_simulator.py`:
   ```python
   class MulliganSimulator:
       def __init__(self, decklist, land_count):
           self.deck = parse_decklist(decklist)
           self.land_count = land_count
           self.total_cards = len(self.deck)
       
       def probability_of_keeping_n_cards(self, hand_size, target_lands=(2,3)):
           # Hypergeometric: P(X lands in hand of size N)
           # X = number of lands, N = hand size
           # Population: total_cards, Successes: land_count
       
       def expected_lands_by_turn(self, turn):
           # Expected lands drawn by turn X (accounting for plays/draws)
       
       def color_screw_probability(self, required_colors, turn):
           # Probability of not having required colors by turn
   ```

### Phase 2: Integration with Existing Systems
1. Update `deck_architect.py` to include:
   - Mana base quality scores in EV calculation
   - Mulligan resistance as a fitness component
   - Land count optimization recommendations

2. Enhance mythic panel evaluation:
   - Add mana base considerations to each archetype's evaluation
   - AggroPro cares about early mana consistency
   - ControlMaster cares about late-game mana availability
   - RampSage focuses on acceleration efficiency

### Phase 3: GUI Enhancements
1. Add mana base quality display to GUI:
   - Mana curve histogram
   - Color pie chart
   - Mulligan probability readout (7-card, 6-card, 5-card keep rates)
   - Land count recommendation
   - Suggested landbase improvements

## Key Formulas to Implement

### Hypergeometric Distribution for Land Draws
```
P(X = k) = (C(K, k) * C(N-K, n-k)) / C(N, n)
Where:
N = total cards in deck
K = number of lands in deck
n = hand size
k = number of lands in hand
```

### Mulligan Probability
```
P(keep 7-card) = P(2 ≤ lands ≤ 5)  # Typical keep range
P(keep 6-card) = P(mulligan to 6) * P(2 ≤ lands ≤ 4 | 6 cards)
P(keep 5-card) = P(mulligan to 5) * P(2 ≤ lands ≤ 3 | 5 cards)
```

### Mana Curve Efficiency
```
mana_efficiency = Σ (weight_i * P(can_spend_mana_on_turn_i))
weight_i = importance of being able to cast spells on turn i
```

### Color Fixing Score
```
color_fixing = Σ (P(have_color_C_by_turn_T) * importance_C)
```

## Validation Approach
1. Test against known good manabases from competitive decks
2. Compare predicted mulligan rates with actual playtest data
3. Validate against goldfishing results (turn-by-turn mana availability)
4. Compare recommendations with established mana base theory

## Files to Modify/Create
- `scripts/mana_base_advisor.py` (enhance)
- `scripts/mulligan_simulator.py` (new)
- `scripts/deck_architect.py` (integrate mana base scoring)
- `scripts/analysis/mythic_framework.py` (add mana base to evaluations)
- `scripts/scaffold_gui.py` (add mana base display)
- `scripts/generate_deck_scaffold.py` (optional: suggest manabase)

This plan directly addresses the user's concern about mulligan resilience by providing quantitative tools to analyze and optimize mana bases.