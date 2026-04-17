# Synergy Analysis Variation Enhancement

## Problem Statement
The current synergy analysis produces **identical card rankings** for identical input pools, leading to user perception that "it chooses the same cards more often than not, regardless of selection from the GUI." This deterministic behavior reduces perceived responsiveness to GUI selections and limits exploratory deck building.

## Root Cause
1. **Deterministic composite scoring**: `composite_score` calculation uses fixed weights and deterministic inputs
2. **Stable sorting**: Python's `sorted()` with identical keys produces consistent but arbitrary ordering
3. **No tie-breaking**: Cards with identical composite scores are ordered by Python's internal hashing
4. **No exploration**: No mechanism to surface alternative card combinations

## Design Goals

### Primary Objectives
1. **Controlled variation**: Introduce user-adjustable randomness to rankings
2. **Reproducibility**: Support seeded randomness for consistent results when needed
3. **Context-awareness**: Variation should respect scoring differences (high-scoring cards still favored)
4. **Minimal disruption**: Maintain core scoring logic while adding optional variation

### Secondary Objectives
1. **Progressive exploration**: Multiple runs can reveal different card combinations
2. **Performance preservation**: Variation logic should not significantly impact analysis speed
3. **Backward compatibility**: Default behavior remains deterministic

## Technical Design

### 1. Temperature-Based Stochastic Ranking

#### Concept
Apply Gaussian noise to composite scores proportional to a "temperature" parameter:
- **Temperature = 0.0**: Pure deterministic ranking (default)
- **Temperature = 0.01**: Small variation for tie-breaking
- **Temperature = 0.05**: Moderate variation for exploration
- **Temperature = 0.10**: High variation for broad exploration

#### Mathematical Model
```
adjusted_score = composite_score + N(0, σ²)
where σ = temperature * composite_score
```

This ensures:
- Higher-scoring cards receive larger absolute noise (preserving rank stability)
- Relative ordering of very different scores remains mostly intact
- Similar-scoring cards may swap positions

#### Implementation
```python
# synergy_report.py
import random
import math

def stochastic_ranking(scores, temperature=0.01, seed=None):
    """
    Apply temperature-based stochastic ranking to CardScore dict.
    
    Parameters
    ----------
    scores : Dict[str, CardScore]
        Mapping of card name to CardScore instances
    temperature : float
        Variation factor (0.0 = deterministic, 0.1 = high variation)
    seed : Optional[int]
        Random seed for reproducibility
    
    Returns
    -------
    List[Tuple[str, CardScore]]
        Ranked (name, score) pairs
    """
    if seed is not None:
        random.seed(seed)
    
    if temperature <= 0.0:
        # Fast path: deterministic sorting
        return sorted(scores.items(), key=lambda x: -x[1].composite_score)
    
    ranked = []
    for name, score in scores.items():
        base = score.composite_score
        if base <= 0:
            noise = 0
        else:
            # Gaussian noise with stddev proportional to score and temperature
            stddev = temperature * base
            noise = random.gauss(0, stddev)
        adjusted = base + noise
        ranked.append((name, score, adjusted))
    
    # Sort by adjusted score (descending)
    ranked.sort(key=lambda x: -x[2])
    return [(name, score) for name, score, _ in ranked]
```

### 2. Tier-Based Stochastic Sampling

#### Alternative Approach
Group cards into score tiers and randomize within tiers:

```python
def tiered_stochastic_ranking(scores, tier_width=5.0, seed=None):
    """
    Group cards into composite score tiers, randomize within tiers.
    
    Cards within `tier_width` points are considered equivalent and
    randomized within their tier.
    """
    if seed is not None:
        random.seed(seed)
    
    # Group by tier
    tiers = {}
    for name, score in scores.items():
        tier_key = math.floor(score.composite_score / tier_width)
        tiers.setdefault(tier_key, []).append((name, score))
    
    # Randomize within tiers
    ranked = []
    for tier_key in sorted(tiers.keys(), reverse=True):
        tier_cards = tiers[tier_key]
        random.shuffle(tier_cards)
        ranked.extend(tier_cards)
    
    return ranked
```

### 3. Multi-Objective Exploration

#### Concept
Generate multiple ranking variations by emphasizing different scoring dimensions:

```python
def multi_objective_ranking(scores, weight_profiles, seed=None):
    """
    Generate multiple rankings using different weight profiles.
    
    Each profile adjusts CompositeWeights to emphasize different
    aspects (engine density, oracle interactions, etc.).
    """
    rankings = []
    for profile_name, weights in weight_profiles.items():
        # Recompute composite scores with alternative weights
        temp_scores = {}
        for name, score in scores.items():
            adjusted = score.composite_score_with(weights)
            temp_scores[name] = (score, adjusted)
        
        # Sort by adjusted score
        ranked = sorted(temp_scores.items(), 
                       key=lambda x: -x[1][1])
        rankings.append((profile_name, ranked))
    
    return rankings
```

## Integration Points

### 1. CLI Interface Enhancement
```bash
# New parameters for synergy_analysis.py
--ranking-temperature 0.02      # Add Gaussian noise (default: 0.0)
--ranking-seed 42              # Random seed for reproducibility
--ranking-tier-width 5.0       # Tier-based randomization width
--ranking-method "temperature" # "temperature", "tier", or "deterministic"
--explore-profiles 3           # Generate multiple weight profiles
```

### 2. GUI Integration

#### Synergy Tab Additions
```python
# scaffold_gui.py enhancements
def _build_synergy_tab(self):
    # ... existing code ...
    
    # Variation controls section
    var_frame = QFrame()
    var_layout = QVBoxLayout(var_frame)
    
    # Temperature slider
    temp_label = QLabel("Ranking Variation:")
    temp_slider = QSlider(Qt.Horizontal)
    temp_slider.setRange(0, 100)  # 0.0 to 0.1 in 0.001 increments
    temp_slider.setValue(0)  # Default: deterministic
    temp_slider.valueChanged.connect(self._on_temperature_changed)
    var_layout.addWidget(temp_label)
    var_layout.addWidget(temp_slider)
    
    # Seed for reproducibility
    seed_check = QCheckBox("Use fixed seed for reproducibility")
    seed_input = QLineEdit("42")
    seed_input.setEnabled(False)
    seed_check.toggled.connect(seed_input.setEnabled)
    var_layout.addWidget(seed_check)
    var_layout.addWidget(seed_input)
    
    # Method selection
    method_combo = QComboBox()
    method_combo.addItems(["Deterministic", "Temperature-based", "Tier-based"])
    var_layout.addWidget(QLabel("Ranking method:"))
    var_layout.addWidget(method_combo)
    
    bl.addWidget(var_frame)
```

#### Command Construction Update
```python
def _on_synergy(self):
    # ... existing code ...
    
    # Add variation parameters
    temp = self.temp_slider.value() / 1000.0  # Convert to 0.0-0.1
    if temp > 0:
        cmd.extend(["--ranking-temperature", str(temp)])
    
    if self.seed_check.isChecked():
        seed = self.seed_input.text().strip()
        if seed.isdigit():
            cmd.extend(["--ranking-seed", seed])
    
    method = self.method_combo.currentText().lower()
    if method != "deterministic":
        cmd.extend(["--ranking-method", method])
```

### 3. Report Generation Integration

#### Modified Ranking in synergy_report.py
```python
def build_top_n_csv(scores, top_n, pool_data=None, 
                   ranking_temperature=0.0, ranking_seed=None):
    """Generate top-N CSV with optional stochastic ranking."""
    
    if ranking_temperature > 0.0:
        ranked = stochastic_ranking(scores, ranking_temperature, ranking_seed)
    else:
        ranked = sorted(scores.items(), key=lambda x: -x[1].composite_score)
    
    ranked = ranked[:top_n]
    # ... rest of CSV generation ...
```

#### Report Context Addition
Include variation parameters in report metadata:
```markdown
## Analysis Parameters
- **Ranking method**: Temperature-based variation (temperature=0.02, seed=42)
- **Variation note**: Cards with similar composite scores may appear in different orders across runs
```

## Performance Considerations

### Computational Cost
- **Temperature method**: O(n) additional operations + O(n log n) sorting
- **Tier method**: O(n) grouping + O(n log n) tier sorting
- **Multi-objective**: O(k * n) where k = number of profiles

### Expected Impact
- **Small pools (<100 cards)**: Negligible impact (<10ms)
- **Large pools (1000+ cards)**: <50ms additional time
- **Memory**: Minimal additional allocation

## Testing Strategy

### Unit Tests
```python
def test_stochastic_ranking_deterministic():
    """Temperature=0 should produce identical results to deterministic sort."""
    scores = create_test_scores()
    deterministic = sorted(scores.items(), key=lambda x: -x[1].composite_score)
    stochastic = stochastic_ranking(scores, temperature=0.0, seed=42)
    assert deterministic == stochastic

def test_stochastic_ranking_variation():
    """Temperature>0 should produce variation within bounds."""
    scores = create_test_scores()
    runs = []
    for _ in range(10):
        ranked = stochastic_ranking(scores, temperature=0.05, seed=None)
        runs.append([name for name, _ in ranked])
    
    # Verify some variation occurs
    assert not all(runs[0] == run for run in runs[1:])
    
    # Verify top cards remain similar (stability)
    top_5_all = [run[:5] for run in runs]
    # Should have significant overlap

def test_reproducibility():
    """Same seed should produce identical rankings."""
    scores = create_test_scores()
    run1 = stochastic_ranking(scores, temperature=0.05, seed=42)
    run2 = stochastic_ranking(scores, temperature=0.05, seed=42)
    assert run1 == run2
```

### Integration Tests
1. **CLI parameter validation**: Ensure new flags work correctly
2. **GUI to CLI propagation**: Verify temperature slider translates to correct CLI args
3. **Report consistency**: Ensure CSV and markdown reports reflect stochastic ranking

### User Acceptance Tests
1. **Perceived variation**: Users should see different card suggestions when changing temperature
2. **Reproducibility**: Using same seed should give identical results
3. **Performance**: No noticeable slowdown in analysis

## Risk Assessment

### Low Risk
- **Temperature parameter**: Optional, defaults to 0.0 (deterministic)
- **Seed parameter**: Only affects random number generation
- **Backward compatibility**: Existing workflows unchanged

### Medium Risk
- **Sorting stability**: May affect downstream tools expecting consistent ordering
- **GUI complexity**: Additional controls may confuse users

### Mitigations
1. **Clear defaults**: Temperature=0.0 ensures deterministic behavior
2. **Documentation**: Explain variation controls in tooltips
3. **Warning for high variation**: Alert users when temperature > 0.05

## Success Metrics

### Quantitative
1. **Variation score**: Measure ranking difference between runs
2. **Performance impact**: <10% increase in analysis time
3. **User adoption**: >30% of users enable variation features

### Qualitative
1. **User feedback**: "Cards vary based on my selections"
2. **Exploration value**: Users discover new card combinations
3. **Perceived responsiveness**: GUI feels more interactive

## Implementation Phases

### Phase 1: Core Stochastic Ranking
1. Implement `stochastic_ranking()` function in `synergy_report.py`
2. Add CLI parameters to `synergy_analysis.py`
3. Unit tests for deterministic and stochastic behavior

### Phase 2: GUI Integration
1. Add variation controls to synergy tab
2. Update command construction in `_on_synergy()`
3. Tooltips and documentation

### Phase 3: Advanced Features
1. Tier-based ranking alternative
2. Multi-objective exploration
3. Profile management and saving

### Phase 4: Polish and Optimization
1. Performance optimization for large pools
2. Enhanced reporting of variation parameters
3. User education (tooltips, examples)

## Alternative Approaches Considered

### 1. Deterministic Tie-Breaking
- **Approach**: Use secondary criteria (CMC, alphabetical) for consistent ordering
- **Pros**: Simple, reproducible
- **Cons**: Doesn't address user desire for variation

### 2. Monte Carlo Sampling
- **Approach**: Sample cards with probability proportional to composite score
- **Pros**: True probabilistic selection
- **Cons**: May exclude high-scoring cards by chance

### 3. Ensemble Methods
- **Approach**: Combine multiple ranking strategies
- **Pros**: Robust, diverse results
- **Cons**: Complex, harder to explain

## Recommendation
Implement **Temperature-Based Stochastic Ranking** (Phase 1) as it provides:
1. **Simple control**: Single temperature parameter
2. **Gradual variation**: Linear scaling from deterministic to exploratory
3. **Mathematical robustness**: Gaussian noise preserves score distribution
4. **Easy explanation**: "Adds small random adjustments to scores"

This directly addresses the user complaint while maintaining the core scoring logic that makes synergy analysis valuable.

---

*Last updated: 2026-04-17*  
*Author: Architect Mode*  
*Status: Design Complete*