# Synergy Analysis Architectural Changes

## Overview
This document consolidates the architectural changes required to address the reported bug: "synergy analysis chooses the same cards more often than not, regardless of selection from the GUI." The solution involves multiple interconnected enhancements across the codebase.

## Root Cause Analysis
1. **Deterministic Scoring**: The synergy analysis algorithm produces identical rankings for identical input pools due to deterministic composite scoring and stable sorting.
2. **GUI Integration Gap**: Archetype selections from the scaffold tab are not passed to the synergy analysis, preventing context-aware scoring.
3. **Missing Primary Axis Override**: The `infer_primary_axes` function uses card pool tags unless an override is provided, but the GUI does not provide this override.
4. **Fixed Weights**: Composite scoring uses hardcoded weights (`CompositeWeights`) with no customization based on archetype preferences.
5. **Stale Candidate Pool**: The synergy analysis reads from `session.md` which may not reflect recent GUI selections.

## Design Solutions

### 1. Primary Axis Override System
**Problem**: Synergy analysis infers primary mechanical axes from the card pool rather than user's archetype selections.

**Solution**:
- Create `synergy_archetype_mapping.py` mapping archetype names to mechanical axes (e.g., "lifegain" → {"lifegain"}).
- Enhance CLI with `--primary-axes` parameter.
- Modify `infer_primary_axes()` in `synergy_engine.py` to respect override.
- Update GUI to collect selected archetypes and pass them as primary axes.

**Files Modified**:
- New: `scripts/synergy_archetype_mapping.py`
- Modified: `scripts/synergy_engine.py` (lines 276-306)
- Modified: `scripts/synergy_analysis.py` (CLI argument parsing)
- Modified: `scaffold_gui.py` (command construction)

### 2. GUI Parameter Passing Enhancement
**Problem**: The synergy tab in `scaffold_gui.py` only passes `--min-synergy` and `--mode` parameters, missing archetype/tag information.

**Solution**:
- Store selected archetypes from the scaffold tab in the GUI state.
- Map archetypes to primary axes using the new mapping module.
- Append `--primary-axes` to the synergy analysis command.
- Optionally add `--weights-json` for custom scoring weights.

**Files Modified**:
- Modified: `scaffold_gui.py` (`_build_synergy_tab`, `_on_synergy`)
- Modified: `scaffold_gui.py` (add state tracking for archetypes)

### 3. Stochastic Ranking Enhancement
**Problem**: Deterministic ranking leads to identical card recommendations.

**Solution**:
- Implement temperature-based stochastic ranking in `synergy_report.py`.
- Add Gaussian noise to composite scores proportional to a temperature parameter.
- Provide CLI flags `--ranking-temperature`, `--ranking-seed`, `--ranking-method`.
- Add GUI controls (slider for variation, seed input, method selection).

**Files Modified**:
- Modified: `scripts/synergy_report.py` (add `stochastic_ranking` function)
- Modified: `scripts/synergy_analysis.py` (add ranking parameters)
- Modified: `scaffold_gui.py` (add variation controls to synergy tab)

### 4. Weight Customization System
**Problem**: Fixed composite weights do not reflect archetype preferences.

**Solution**:
- Extend `CompositeWeights` dataclass in `synergy_types.py` to support archetype multipliers and axis bonuses.
- Add predefined weight profiles (engine-focused, synergy-dense, oracle-priority, role-breadth).
- Allow JSON configuration file via `--weights-json`.
- GUI: expose weight profiles as dropdown or sliders.

**Files Modified**:
- Modified: `scripts/synergy_types.py` (extend `CompositeWeights`)
- New: `config/synergy_weights.json` (example configurations)
- Modified: `scripts/synergy_engine.py` (use configurable weights)
- Modified: `scaffold_gui.py` (add weight customization UI)

### 5. Candidate Pool Regeneration Workflow
**Problem**: Synergy analysis uses stale `session.md` if GUI selections changed.

**Solution**:
- Compute hash of GUI state (archetypes, colors, tribe, tags).
- Compare with cached hash in session directory.
- If mismatch, trigger `generate_deck_scaffold.py` to regenerate candidate pool.
- Provide options: automatic, prompt, or manual regeneration.

**Files Modified**:
- Modified: `scaffold_gui.py` (add regeneration logic in `_on_synergy`)
- New: `scripts/regenerate_pool.py` (optional helper)
- Modified: `scripts/generate_deck_scaffold.py` (expose core generation function)

## Dependencies and Order of Implementation

### Phase 1: Core Infrastructure (Low Risk)
1. **Primary Axis Mapping** (`synergy_archetype_mapping.py`)
   - No dependencies, can be tested independently.
2. **CLI Parameter Addition** (`synergy_analysis.py`)
   - Adds `--primary-axes` flag; backward compatible.
3. **Engine Override Support** (`synergy_engine.py`)
   - Modifies `infer_primary_axes` to use override.

### Phase 2: GUI Integration (Medium Risk)
1. **GUI State Tracking** (`scaffold_gui.py`)
   - Store selected archetypes from scaffold tab.
2. **Command Construction** (`scaffold_gui.py`)
   - Append `--primary-axes` to synergy command.
3. **Basic UI Controls** (`scaffold_gui.py`)
   - Add "Use archetype preferences" checkbox.

### Phase 3: Stochastic Ranking (Medium Risk)
1. **Ranking Algorithm** (`synergy_report.py`)
   - Implement `stochastic_ranking` with temperature.
2. **CLI Integration** (`synergy_analysis.py`)
   - Add ranking flags.
3. **GUI Controls** (`scaffold_gui.py`)
   - Add variation slider, seed input.

### Phase 4: Weight Customization (High Risk)
1. **Extended Dataclass** (`synergy_types.py`)
   - Modify `CompositeWeights` with archetype multipliers.
2. **Weight Loading** (`synergy_engine.py`)
   - Load weights from JSON or defaults.
3. **GUI Weight UI** (`scaffold_gui.py`)
   - Add advanced section for weight customization.

### Phase 5: Pool Regeneration (Medium Risk)
1. **State Hashing** (`scaffold_gui.py`)
   - Compute hash of GUI selections.
2. **Regeneration Trigger** (`scaffold_gui.py`)
   - Call `generate_deck_scaffold.py` if needed.
3. **Caching** (`scaffold_gui.py`)
   - Store hash in session directory.

## Integration with Existing Refactoring Plan
The existing `synergy_revamp.md` plan outlines a major architectural refactor. The changes described here should be integrated into that plan as follows:

- **Primary Axis Override**: Add to Phase 2 (Scoring Engine) of revamp.
- **Stochastic Ranking**: Add to Phase 4 (Report Generation) as a new feature.
- **Weight Customization**: Add to Phase 2 as part of configurable scoring.
- **GUI Integration**: Add as a separate "GUI Integration" phase after core refactor.

## Testing Strategy
1. **Unit Tests**:
   - Test `synergy_archetype_mapping` mapping correctness.
   - Test `stochastic_ranking` with known seed produces deterministic results.
   - Test `infer_primary_axes` with override.
2. **Integration Tests**:
   - Run synergy analysis with `--primary-axes` and verify axis usage.
   - Verify GUI command includes new parameters.
   - Verify ranking variation with temperature > 0.
3. **Regression Tests**:
   - Ensure existing test corpus passes with new changes.
   - Compare outputs with temperature=0 to ensure deterministic match.

## Backward Compatibility
All changes are backward compatible:
- New CLI flags are optional; default behavior unchanged.
- GUI changes additive; existing workflows continue to work.
- No breaking changes to data structures (except additive extensions).

## Performance Considerations
- Stochastic ranking adds O(n) noise generation; negligible impact.
- Primary axis mapping is O(1) lookup.
- Weight customization adds no runtime overhead if using defaults.
- Pool regeneration may add latency but only triggers when GUI state changes.

## Documentation Updates Required
1. **CLI Documentation**: Update `scripts/README.md` with new flags.
2. **GUI Guide**: Update `100-UI-OVERHAUL.md` with new synergy controls.
3. **AI Instructions**: Update `AI_INSTRUCTIONS.md` for Gate 2.5 if scoring changes.
4. **Changelog**: Add entries for each phase.

## Risk Assessment
| Risk | Mitigation |
|------|------------|
| Breaking existing synergy analysis | Extensive testing with test corpus; keep old code as fallback |
| GUI complexity increase | Progressive disclosure; advanced options hidden by default |
| Performance degradation | Profile critical paths; optimize noise generation |
| User confusion about new parameters | Clear tooltips, documentation, default values |

## Success Metrics
1. **Bug Resolution**: Synergy analysis produces different rankings when GUI selections change.
2. **User Satisfaction**: GUI controls provide perceived responsiveness.
3. **Performance**: Analysis completes within 10% of original time.
4. **Adoption**: Users utilize variation and weight customization features.

## Implementation Timeline
The work can be parallelized across multiple developers:
- **Phase 1-2**: 1-2 days (core mapping and GUI integration)
- **Phase 3**: 1 day (stochastic ranking)
- **Phase 4**: 2 days (weight customization)
- **Phase 5**: 1 day (pool regeneration)
- **Testing & Documentation**: 1 day

Total estimated effort: 6-7 person-days.

## Conclusion
The architectural changes address the root cause of the reported bug while enhancing the synergy analysis system with valuable features. The modular design ensures backward compatibility and allows incremental implementation. The integration with the existing synergy revamp plan provides a cohesive roadmap for improving the entire synergy analysis subsystem.