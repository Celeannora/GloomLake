# Autoresearch Eval Corpus

Labeled decklists for the Karpathy autoresearch eval loop.

## Structure

```
test-corpus/
  good/        — real cohesive decklists — expected: PASS
  borderline/  — decks with known weak points — expected: FAIL or WARN
  bad/         — incoherent / stub lists — expected: FAIL
```

## Running the eval

```powershell
# Good: Esper Lifegain 60 (expect PASS)
python scripts/synergy_analysis.py test-corpus/good/esper_lifegain_60/decklist.txt --mode deck

# Good: Esper shortlist v3 (expect PASS)
python scripts/synergy_analysis.py test-corpus/good/esper_shortlist_v3/names.txt --format names --mode pool

# Borderline: good-stuff pile (expect FAIL)
python scripts/synergy_analysis.py test-corpus/borderline/good_stuff_60/decklist.txt --mode deck

# Bad: unknown cards (expect FAIL)
python scripts/synergy_analysis.py test-corpus/bad/unknown_cards/decklist.txt --mode deck

# Bad: tiny stub (expect FAIL)
python scripts/synergy_analysis.py test-corpus/bad/tiny/decklist.txt --mode deck
```

## Expected results

| Deck | Label | Expected |
|------|-------|----------|
| esper_lifegain_60 | good | PASS |
| esper_shortlist_v3 | good | PASS |
| good_stuff_60 | borderline | FAIL |
| unknown_cards | bad | FAIL |
| tiny | bad | FAIL |
