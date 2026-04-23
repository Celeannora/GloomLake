#!/usr/bin/env python3
"""
Test card examples for auto-analysis
"""

print("CARD EXAMPLES FOR AUTO-ANALYSIS TESTING")
print("=" * 60)

print("\nEnter these in Focus Cards (Card 1), then click 'Analyze':")
print("-" * 60)

test_sets = [
    {
        "name": "ANGEL LIFEGAIN DECK",
        "cards": [
            "Resplendent Angel",
            "Lyra Dawnbringer", 
            "Serra Ascendant",
            "Ajani's Pridemate",
            "Shattered Angel"
        ],
        "expected": {
            "colors": "White (W)",
            "archetypes": "lifegain",
            "tribal": "Angel",
            "tags": "lifegain, draw",
            "name": "Mono-White Lifegain Angel"
        }
    },
    {
        "name": "MILL DECK",
        "cards": [
            "Glimpse the Unthinkable",
            "Mind Funeral",
            "Hedron Crab",
            "Archive Trap",
            "Jace's Phantasm"
        ],
        "expected": {
            "colors": "Blue (U), Black (B)",
            "archetypes": "opp_mill",
            "tribal": "None",
            "tags": "mill",
            "name": "Dimir Mill"
        }
    },
    {
        "name": "BURN DECK",
        "cards": [
            "Lightning Bolt",
            "Lava Spike",
            "Rift Bolt",
            "Goblin Guide",
            "Eidolon of the Great Revel"
        ],
        "expected": {
            "colors": "Red (R)",
            "archetypes": "burn",
            "tribal": "Goblin",
            "tags": "removal, haste",
            "name": "Mono-Red Burn"
        }
    },
    {
        "name": "GRAVEYARD DECK",
        "cards": [
            "Tarmogoyf",
            "Thoughtseize",
            "Dark Confidant",
            "Gravecrawler",
            "Bloodghast"
        ],
        "expected": {
            "colors": "Black (B), Green (G)",
            "archetypes": "graveyard",
            "tribal": "Zombie",
            "tags": "mill, draw",
            "name": "Golgari Graveyard"
        }
    }
]

for test in test_sets:
    print(f"\n{test['name']}:")
    print("-" * 40)
    for i, card in enumerate(test['cards'], 1):
        print(f"  {i}. {card}")
    print(f"\n  Expected results:")
    print(f"    • Colors: {test['expected']['colors']}")
    print(f"    • Archetype: {test['expected']['archetypes']}")
    print(f"    • Tribal: {test['expected']['tribal']}")
    print(f"    • Tags: {test['expected']['tags']}")
    print(f"    • Name: {test['expected']['name']}")

print("\n" + "=" * 60)
print("HOW TO TEST:")
print("1. Stop current GUI: Get-Job | Stop-Job; Get-Job | Remove-Job")
print("2. Copy a set of cards above")
print("3. Start GUI: Start-Job -ScriptBlock { python scaffold_gui.py }")
print("4. Paste cards in Focus Cards (Card 1)")
print("5. Click 'Analyze Focus Cards & Auto-Fill All Sections'")
print("6. Check log for analysis results")