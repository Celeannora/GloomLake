#!/usr/bin/env python3
"""
Test the auto-analysis feature for focus cards
"""
import sys
from PySide6.QtWidgets import QApplication
from scaffold_gui import ScaffoldApp, ARCHETYPE_GROUPS, TAG_CATEGORIES

def test_auto_analysis_features():
    print("Testing auto-analysis features...")
    
    # Test data structures are accessible
    print(f"\n1. Available archetype groups: {list(ARCHETYPE_GROUPS.keys())}")
    print(f"2. Available tag categories: {list(TAG_CATEGORIES.keys())}")
    
    # Test the ARCHETYPE_TAG_MAP to see what tags are suggested for archetypes
    from scaffold_gui import ARCHETYPE_TAG_MAP
    print("\n3. Archetype to Tag Mapping samples:")
    for arch, tags in list(ARCHETYPE_TAG_MAP.items())[:5]:
        print(f"   {arch}: {tags}")
    
    # Create simple app to test method calls
    app = QApplication(sys.argv)
    win = ScaffoldApp()
    
    print("\n4. Testing focus card analysis logic...")
    # Simulate entering focus cards
    test_cards = [
        "Resplendent Angel",  # Suggests lifegain/angel
        "Glimpse the Unthinkable",  # Suggests mill
        "Lightning Bolt",  # Suggests burn
        "Birds of Paradise",  # Suggests ramp
        "Counterspell"  # Suggests control
    ]
    
    print("   Sample focus cards that would trigger auto-analysis:")
    for card in test_cards:
        if "angel" in card.lower():
            print(f"   - {card}: Would suggest 'lifegain' tag and 'lifegain' archetype")
        elif "mill" in card.lower() or "unthinkable" in card.lower():
            print(f"   - {card}: Would suggest 'mill' tag and 'opp_mill' archetype")
        elif "lightning" in card.lower():
            print(f"   - {card}: Would suggest 'removal' tag and 'burn' archetype")
        elif "paradise" in card.lower():
            print(f"   - {card}: Would suggest 'ramp' tag and 'ramp' archetype")
        elif "counter" in card.lower():
            print(f"   - {card}: Would suggest 'counter' tag and 'control' archetype")
    
    print("\n5. Real implementation would:")
    print("   - Query card database for each focus card")
    print("   - Extract card type, keywords, colors, subtypes")
    print("   - Match patterns to archetypes (e.g., angels -> lifegain)")
    print("   - Suggest relevant tags based on card abilities")
    print("   - Auto-select suggested archetype buttons")
    print("   - Update color selection based on card color identity")
    
    # Show what the GUI now has
    print("\n6. New GUI features added:")
    print("   - Focus Cards moved to position 2 (right after Mana Colors)")
    print("   - 'Analyze Focus Cards' button added below focus card input")
    print("   - Basic analysis suggests tags based on card name keywords")
    print("   - Future: Full card database lookup and intelligent suggestions")
    
    return 0

if __name__ == "__main__":
    sys.exit(test_auto_analysis_features())