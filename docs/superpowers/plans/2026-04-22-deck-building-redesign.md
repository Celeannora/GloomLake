# Deck Building Strategy Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the complex, synergy-overoptimized deck building system with a fundamentals-first approach that ensures playable decks before sophisticated optimization.

**Architecture:** Four-stage redesign replacing archetype queries with role-based queries, adding hard construction constraints, simplifying optimization to fundamentals-first, and replacing panel evaluation with practical metrics.

**Tech Stack:** Python, SQLite (card database), pytest (testing), existing MTG analysis framework.

---

## File Structure

**New Files:**
- `scripts/analysis/construction_constraints.py` - Hard deck construction requirements
- `scripts/analysis/practical_optimizer.py` - Fundamentals-first optimization
- `scripts/analysis/practical_evaluator.py` - Playability-focused evaluation metrics
- `scripts/cli/generate_deck_scaffold_v2.py` - Redesigned scaffold generator

**Modified Files:**
- `scripts/cli/generate_deck_scaffold.py` - Update to use role-based queries
- `scripts/analysis/synergy_optimizer.py` - Add construction constraint integration
- `scripts/analysis/mythic_framework.py` - Add practical bottleneck detection
- `docs/reference/AI_INSTRUCTIONS.md` - Simplify gate system

---

## Stage 1: Query System Redesign

### Task 1.1: Define Role-Based Query System

**Files:**
- Create: `scripts/analysis/role_queries.py`
- Modify: `scripts/cli/generate_deck_scaffold.py:122-322`

- [ ] **Step 1: Create role_queries.py with comprehensive role definitions**

```python
ROLE_QUERIES = {
    "early_creatures": [
        {"label": "Aggressive creatures", "args": "--type creature --cmc-max 2 --tags haste,pump"},
        {"label": "Efficient creatures", "args": "--type creature --cmc-max 3 --rarity rare,mythic"},
    ],
    "removal": [
        {"label": "Cheap removal", "args": "--type instant --tags removal --cmc-max 3"},
        {"label": "Board wipes", "args": "--type sorcery --tags wipe"},
    ],
    "win_conditions": [
        {"label": "Finishers", "args": "--type creature --cmc-min 4 --rarity rare,mythic"},
        {"label": "Planeswalkers", "args": "--type planeswalker --cmc-min 3"},
    ],
    "card_advantage": [
        {"label": "Draw effects", "args": "--type instant,sorcery,enchantment --tags draw"},
        {"label": "Token generators", "args": "--oracle create.*token"},
    ],
    "mana_fixing": [
        {"label": "Dual lands", "args": "--type land --oracle tap.*add.*mana"},
        {"label": "Utility lands", "args": "--type land --oracle search.*library.*land"},
    ],
    # Multi-strategy bridge roles
    "lifegain_payoffs": [
        {"label": "Lifegain creatures", "args": "--type creature --tags lifegain"},
        {"label": "Lifegain triggers", "args": "--oracle whenever you gain life"},
    ],
    "mill_effects": [
        {"label": "Opponent mill", "args": "--oracle opponent mills"},
        {"label": "Mill payoffs", "args": "--tags mill"},
    ],
}
```

- [ ] **Step 2: Add multi-strategy merge function**

```python
def merge_strategy_queries(strategies: List[str]) -> List[Dict[str, str]]:
    """Merge queries from multiple strategies, deduplicating by label."""
    seen_labels = {}
    for strategy in strategies:
        for query in ROLE_QUERIES.get(strategy, []):
            label = query["label"]
            if label not in seen_labels:
                seen_labels[label] = query
    return list(seen_labels.values())
```

- [ ] **Step 3: Update generate_deck_scaffold.py to use role-based queries**

```python
# Replace ARCHETYPE_QUERIES section with:
STRATEGY_TO_ROLES = {
    "aggro": ["early_creatures", "removal", "mana_fixing"],
    "control": ["removal", "card_advantage", "win_conditions", "mana_fixing"],
    "lifegain": ["lifegain_payoffs", "card_advantage", "mana_fixing"],
    "mill": ["mill_effects", "removal", "mana_fixing"],
    "tribal": ["early_creatures", "card_advantage", "mana_fixing"],
}

# Update query_plan generation to use roles
query_plan = []
for archetype in archetype_list:
    if archetype in STRATEGY_TO_ROLES:
        roles = STRATEGY_TO_ROLES[archetype]
        role_queries = merge_strategy_queries(roles)
        query_plan.extend(role_queries)
```

- [ ] **Step 4: Test role-based query generation**

Run: `python scripts/cli/generate_deck_scaffold.py --name "Test Lifegain Mill" --colors WUB --archetype lifegain,mill`
Expected: Queries for lifegain_payoffs, card_advantage, mana_fixing, mill_effects, removal

- [ ] **Step 5: Commit role-based query system**

```bash
git add scripts/analysis/role_queries.py scripts/cli/generate_deck_scaffold.py
git commit -m "feat: implement role-based query system for comprehensive deck coverage"
```

---

## Stage 2: Constraint System Implementation

### Task 2.1: Define Construction Constraints

**Files:**
- Create: `scripts/analysis/construction_constraints.py`
- Modify: `scripts/analysis/synergy_optimizer.py:120-135`

- [ ] **Step 1: Create construction_constraints.py with validation functions**

```python
from typing import Dict, List, Tuple
from dataclasses import dataclass

@dataclass
class ConstructionConstraints:
    min_lands: int = 23
    max_avg_cmc: float = 3.2
    min_early_plays: int = 12  # CMC 1-2
    min_removal: int = 8
    min_win_conditions: int = 6
    max_single_card_copies: int = 4

def validate_mana_curve(deck: List[Dict]) -> Tuple[bool, str]:
    """Validate deck has reasonable mana curve."""
    cmc_counts = {}
    for card in deck:
        cmc = card.get('cmc', 0)
        cmc_counts[cmc] = cmc_counts.get(cmc, 0) + card.get('qty', 1)

    # Check minimum early plays (CMC 1-2)
    early_plays = sum(cmc_counts.get(cmc, 0) for cmc in [1, 2])
    if early_plays < 12:
        return False, f"Only {early_plays} early plays (need ≥12)"

    # Check average CMC
    total_cards = sum(cmc_counts.values())
    avg_cmc = sum(cmc * count for cmc, count in cmc_counts.items()) / total_cards
    if avg_cmc > 3.2:
        return False, f"Average CMC {avg_cmc:.1f} too high (max 3.2)"

    return True, "Mana curve acceptable"

def validate_role_distribution(deck: List[Dict]) -> Tuple[bool, str]:
    """Validate deck has balanced role distribution."""
    removal_count = 0
    win_conditions = 0

    for card in deck:
        tags = card.get('tags', '').split(';')
        if 'removal' in tags:
            removal_count += card.get('qty', 1)
        if card.get('cmc', 0) >= 4 and card.get('rarity') in ['rare', 'mythic']:
            win_conditions += card.get('qty', 1)

    if removal_count < 8:
        return False, f"Only {removal_count} removal spells (need ≥8)"
    if win_conditions < 6:
        return False, f"Only {win_conditions} win conditions (need ≥6)"

    return True, "Role distribution balanced"
```

- [ ] **Step 2: Add constraint validation to optimizer**

```python
# In synergy_optimizer.py, add imports and validation
from construction_constraints import ConstructionConstraints, validate_mana_curve, validate_role_distribution

def validate_deck_construction(deck: List[Dict]) -> Tuple[bool, List[str]]:
    """Validate deck meets construction requirements."""
    errors = []

    # Check mana curve
    valid, msg = validate_mana_curve(deck)
    if not valid:
        errors.append(f"Mana curve: {msg}")

    # Check role distribution
    valid, msg = validate_role_distribution(deck)
    if not valid:
        errors.append(f"Role distribution: {msg}")

    # Check land count
    lands = sum(card.get('qty', 1) for card in deck if card.get('type_line', '').startswith('Land'))
    if lands < 23:
        errors.append(f"Land count: {lands} (need ≥23)")

    return len(errors) == 0, errors
```

- [ ] **Step 3: Integrate constraints into optimization loop**

```python
# In optimization loop, add constraint checking
while not time_budget_exceeded:
    # Generate candidate swap
    # ...

    # Check construction constraints before accepting
    if validate_deck_construction(candidate_deck)[0]:
        # Only accept if construction is sound
        if candidate_ev > best_ev:
            accept_swap()
    else:
        # Reject swaps that break construction
        continue
```

- [ ] **Step 4: Test constraint validation**

Run: `python -c "from construction_constraints import validate_mana_curve; print('Constraints loaded')"`
Expected: No errors

- [ ] **Step 5: Commit constraint system**

```bash
git add scripts/analysis/construction_constraints.py scripts/analysis/synergy_optimizer.py
git commit -m "feat: add hard construction constraints to prevent unplayable decks"
```

---

## Stage 3: Optimization Algorithm Rewrite

### Task 3.1: Implement Fundamentals-First Optimization

**Files:**
- Create: `scripts/analysis/practical_optimizer.py`
- Modify: `scripts/analysis/synergy_optimizer.py:1-50`

- [ ] **Step 1: Create practical_optimizer.py with phased optimization**

```python
class PracticalOptimizer:
    """Three-phase optimization: construction → balance → synergy."""

    def optimize_deck(self, deck: List[Dict], candidate_pool: List[Dict]) -> List[Dict]:
        """Main optimization entry point."""
        # Phase 1: Ensure construction fundamentals
        deck = self._optimize_construction(deck, candidate_pool)

        # Phase 2: Balance roles and mana curve
        deck = self._optimize_balance(deck, candidate_pool)

        # Phase 3: Enhance synergy within constraints
        deck = self._optimize_synergy(deck, candidate_pool)

        return deck

    def _optimize_construction(self, deck: List[Dict], pool: List[Dict]) -> List[Dict]:
        """Ensure minimum construction requirements are met."""
        # Add lands if needed
        lands = [c for c in deck if c.get('type_line', '').startswith('Land')]
        if len(lands) < 23:
            needed = 23 - len(lands)
            land_candidates = [c for c in pool if c.get('type_line', '').startswith('Land')]
            # Add best land candidates
            for candidate in land_candidates[:needed]:
                deck.append({**candidate, 'qty': 1})

        return deck

    def _optimize_balance(self, deck: List[Dict], pool: List[Dict]) -> List[Dict]:
        """Balance mana curve and role distribution."""
        # Analyze current curve
        cmc_counts = self._analyze_curve(deck)

        # Identify imbalances
        if cmc_counts.get(1, 0) + cmc_counts.get(2, 0) < 12:
            # Need more early plays
            early_candidates = [c for c in pool if c.get('cmc', 0) <= 2]
            # Add best early candidates...

        return deck

    def _optimize_synergy(self, deck: List[Dict], pool: List[Dict]) -> List[Dict]:
        """Enhance synergy while maintaining construction soundness."""
        # Only optimize synergy after fundamentals are solid
        # Use existing pairwise scoring but with construction constraints
        return deck
```

- [ ] **Step 2: Integrate practical optimizer into existing system**

```python
# In synergy_optimizer.py
from practical_optimizer import PracticalOptimizer

def optimize_with_constraints(deck: List[Dict], pool: List[Dict], time_budget: float):
    """Main optimization function using practical approach."""
    optimizer = PracticalOptimizer()

    # Validate initial deck construction
    valid, errors = validate_deck_construction(deck)
    if not valid:
        print(f"Initial deck construction issues: {errors}")
        # Fix construction issues first
        deck = optimizer._optimize_construction(deck, pool)

    # Proceed with balanced optimization
    return optimizer.optimize_deck(deck, pool)
```

- [ ] **Step 3: Test practical optimization phases**

Run: `python -c "from practical_optimizer import PracticalOptimizer; print('Practical optimizer loaded')"`
Expected: No errors

- [ ] **Step 4: Commit practical optimization**

```bash
git add scripts/analysis/practical_optimizer.py scripts/analysis/synergy_optimizer.py
git commit -m "feat: implement fundamentals-first optimization with construction constraints"
```

---

## Stage 4: Evaluation System Overhaul

### Task 4.1: Replace Panel with Practical Metrics

**Files:**
- Create: `scripts/analysis/practical_evaluator.py`
- Modify: `scripts/analysis/mythic_framework.py:80-120`

- [ ] **Step 1: Create practical_evaluator.py with playability metrics**

```python
from typing import Dict, List, Tuple

class PracticalEvaluator:
    """Evaluate decks on real playability metrics."""

    def evaluate_deck(self, deck: List[Dict]) -> Dict[str, float]:
        """Return practical evaluation scores."""
        return {
            'mana_efficiency': self._score_mana_efficiency(deck),
            'role_balance': self._score_role_balance(deck),
            'interaction_coverage': self._score_interaction_coverage(deck),
            'game_plan_clarity': self._score_game_plan_clarity(deck),
            'bottlenecks': self._detect_bottlenecks(deck),
        }

    def _score_mana_efficiency(self, deck: List[Dict]) -> float:
        """Score mana curve efficiency (0-100)."""
        cmc_counts = {}
        for card in deck:
            cmc = card.get('cmc', 0)
            qty = card.get('qty', 1)
            cmc_counts[cmc] = cmc_counts.get(cmc, 0) + qty

        # Ideal curve: 8, 12, 10, 6, 4 for CMC 1-5
        ideal = [8, 12, 10, 6, 4]
        score = 0

        for i, ideal_count in enumerate(ideal):
            actual = cmc_counts.get(i + 1, 0)
            # Score based on proximity to ideal
            deviation = abs(actual - ideal_count) / ideal_count
            score += max(0, 100 * (1 - deviation))

        return score / len(ideal)

    def _score_role_balance(self, deck: List[Dict]) -> float:
        """Score role distribution balance (0-100)."""
        roles = {'removal': 0, 'win_conditions': 0, 'card_advantage': 0, 'ramp': 0}

        for card in deck:
            tags = card.get('tags', '').split(';')
            qty = card.get('qty', 1)

            if 'removal' in tags:
                roles['removal'] += qty
            if card.get('cmc', 0) >= 4 and card.get('rarity') in ['rare', 'mythic']:
                roles['win_conditions'] += qty
            if 'draw' in tags:
                roles['card_advantage'] += qty
            if 'ramp' in tags:
                roles['ramp'] += qty

        # Check balance - each role should have reasonable representation
        scores = []
        for role, count in roles.items():
            if role == 'removal' and count >= 8:
                scores.append(100)
            elif role == 'win_conditions' and count >= 6:
                scores.append(100)
            elif role in ['card_advantage', 'ramp'] and count >= 4:
                scores.append(100)
            else:
                scores.append(min(100, count * 25))  # Partial credit

        return sum(scores) / len(scores)

    def _detect_bottlenecks(self, deck: List[Dict]) -> List[str]:
        """Detect critical construction issues."""
        issues = []

        # Mana bottleneck detection
        lands = sum(c.get('qty', 1) for c in deck if c.get('type_line', '').startswith('Land'))
        if lands < 23:
            issues.append("mana_bottleneck")

        # Role bottlenecks
        removal = sum(c.get('qty', 1) for c in deck if 'removal' in c.get('tags', ''))
        if removal < 8:
            issues.append("removal_bottleneck")

        win_cons = sum(c.get('qty', 1) for c in deck
                      if c.get('cmc', 0) >= 4 and c.get('rarity') in ['rare', 'mythic'])
        if win_cons < 6:
            issues.append("payoff_bottleneck")

        return issues
```

- [ ] **Step 2: Integrate practical evaluation into mythic framework**

```python
# In mythic_framework.py
from practical_evaluator import PracticalEvaluator

def run_panel(scores: Dict, tribe: str = None) -> Dict:
    """Enhanced panel with practical bottleneck detection."""
    panel_scores = compute_panel_scores(scores, tribe)

    # Add practical evaluation
    evaluator = PracticalEvaluator()
    practical_scores = evaluator.evaluate_deck(scores.get('deck', []))

    # Combine scores
    consensus = (panel_scores['consensus'] + practical_scores['overall']) / 2

    return {
        **panel_scores,
        'practical_scores': practical_scores,
        'bottlenecks': practical_scores['bottlenecks'],
        'consensus': consensus,
    }
```

- [ ] **Step 3: Test practical evaluation metrics**

Run: `python -c "from practical_evaluator import PracticalEvaluator; print('Practical evaluator loaded')"`
Expected: No errors

- [ ] **Step 4: Commit practical evaluation system**

```bash
git add scripts/analysis/practical_evaluator.py scripts/analysis/mythic_framework.py
git commit -m "feat: replace panel evaluation with practical playability metrics"
```

---

## Stage 5: Update Documentation and Testing

### Task 5.1: Simplify AI Instructions

**Files:**
- Modify: `docs/reference/AI_INSTRUCTIONS.md:185-250`

- [ ] **Step 1: Replace complex gate system with simplified protocol**

```markdown
## SIMPLIFIED DECK BUILDING PROTOCOL

### Step 1: Query Generation
Use role-based queries to ensure comprehensive candidate pools:
- Combine multiple strategies (e.g., lifegain + mill + control)
- Run queries for all needed roles
- Ensure 100% coverage of card types

### Step 2: Construction Validation  
Before optimization, ensure deck meets hard requirements:
- ✅ 23+ lands
- ✅ Reasonable mana curve (avg CMC ≤3.2)
- ✅ 12+ early plays (CMC 1-2)
- ✅ 8+ removal spells
- ✅ 6+ win conditions

### Step 3: Practical Optimization
Optimize in phases:
1. Construction fundamentals (curves, roles)
2. Balance and distribution
3. Synergy enhancement within constraints

### Step 4: Playability Evaluation
Score decks on real metrics:
- Mana efficiency (0-100)
- Role balance (0-100)  
- Interaction coverage (0-100)
- Game plan clarity (0-100)
```

- [ ] **Step 2: Remove complex gate references**

Remove: Detailed gate 1-6 instructions, replace with simplified 4-step process

- [ ] **Step 3: Update tool references**

Update: `search_cards.py`, `validate_decklist.py`, `synergy_analysis.py` usage examples

- [ ] **Step 4: Commit documentation updates**

```bash
git add docs/reference/AI_INSTRUCTIONS.md
git commit -m "docs: simplify AI instructions to fundamentals-first protocol"
```

---

## Final Integration and Testing

### Task 6.1: End-to-End Integration Test

**Files:**
- Create: `tests/test_deck_building_redesign.py`
- Modify: `scripts/cli/generate_deck_scaffold.py:1152`

- [ ] **Step 1: Create integration test for redesigned system**

```python
def test_redesigned_deck_building():
    """Test that redesigned system produces playable decks."""
    # Generate scaffold for lifegain + mill + control deck
    result = subprocess.run([
        sys.executable, 'scripts/cli/generate_deck_scaffold.py',
        '--name', 'Test Redesigned',
        '--colors', 'WUB',
        '--archetype', 'lifegain,mill,control'
    ], capture_output=True, text=True)

    assert result.returncode == 0

    # Load generated session
    session_path = Path('Decks/2026-04-22_Test_Redesign/session.md')
    assert session_path.exists()

    # Verify comprehensive queries were generated
    content = session_path.read_text()
    assert 'lifegain_payoffs' in content
    assert 'mill_effects' in content
    assert 'removal' in content
    assert 'card_advantage' in content
```

- [ ] **Step 2: Add integration test to test suite**

Run: `python -m pytest tests/test_deck_building_redesign.py -v`
Expected: PASS

- [ ] **Step 3: Update CLI to use new scaffold generator**

```python
# In generate_deck_scaffold.py main()
if args.use_redesign:
    # Use new role-based system
    from role_queries import merge_strategy_queries
    # ... implement new logic
```

- [ ] **Step 4: Commit integration and final updates**

```bash
git add tests/test_deck_building_redesign.py scripts/cli/generate_deck_scaffold.py
git commit -m "feat: complete deck building redesign integration and testing"
```

---

**Plan complete and saved to `docs/superpowers/plans/2026-04-22-deck-building-redesign.md`. Two execution options:**

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

**Which approach?**