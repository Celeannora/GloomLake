# scripts/analysis/card_analysis.py
#!/usr/bin/env python3
"""
Card analysis logic for reverse search functionality.
"""

from typing import Dict, List, Set
from scripts.utils.card_lookup import CardData

# Mapping from card tags to GUI archetypes
TAG_TO_ARCHETYPE = {
    "lifegain": "lifegain",
    "mill": "opp_mill", 
    "draw": "draw_go",
    "removal": "control",
    "counter": "control",
    "ramp": "ramp",
    "token": "tokens",
    "bounce": "tempo",
    "discard": "discard",
    "tutor": "combo",
    "wipe": "control",
    "reanimation": "reanimator",
    "burn": "burn",
    "infect": "infect",
    "landfall": "landfall",
    "blink": "blink",
    "aristocrats": "aristocrats"
}

# Tribe extraction patterns
TRIBE_PATTERNS = {
    "Angel": ["Angel", "Seraph", "Cherub"],
    "Zombie": ["Zombie", "Ghoul", "Undead"],
    "Elf": ["Elf", "Elves", "Elvish"],
    "Goblin": ["Goblin", "Goblinoid"],
    "Merfolk": ["Merfolk", "Siren", "Triton"],
    "Dragon": ["Dragon", "Wyrm", "Drake"],
    "Vampire": ["Vampire", "Nosferatu"],
    "Human": ["Human", "Warrior", "Soldier", "Knight"],
    "Spirit": ["Spirit", "Ghost", "Phantom"],
    "Elemental": ["Elemental", "Golem", "Construct"],
    "Beast": ["Beast", "Wolf", "Bear", "Lion"],
    "Bird": ["Bird", "Hawk", "Eagle", "Falcon"],
    "Demon": ["Demon", "Fiend", "Devil"],
    "Sliver": ["Sliver"],
    "Myr": ["Myr"],
    "Eldrazi": ["Eldrazi", "Kozilek", "Ulamog", "Emrakul"]
}

def analyze_card_data(card: CardData) -> Dict[str, Set[str]]:
    """Analyze card data to extract properties for GUI sections."""
    result = {
        "colors": set(),
        "archetypes": set(),
        "tribes": set(),
        "tags": set(),
        "suggestions": []
    }
    
    # 1. Colors
    colors = set(card.colors) or set(card.color_identity)
    result["colors"] = colors
    
    # 2. Archetypes from tags
    for tag in card.tags:
        if tag in TAG_TO_ARCHETYPE:
            archetype = TAG_TO_ARCHETYPE[tag]
            result["archetypes"].add(archetype)
            result["suggestions"].append(f"{archetype} (from tag: {tag})")
    
    # 3. Archetypes from oracle text keywords
    oracle_lower = card.oracle_text.lower()
    text_archetypes = _detect_archetypes_from_text(oracle_lower)
    result["archetypes"].update(text_archetypes)
    
    # 4. Tribes from type line
    type_lower = card.type_line.lower()
    for tribe, patterns in TRIBE_PATTERNS.items():
        for pattern in patterns:
            if pattern.lower() in type_lower:
                result["tribes"].add(tribe)
                break
    
    # 5. Tags (use pre-computed tags plus additional ones)
    result["tags"].update(card.tags)
    
    # Add keyword-based tags
    for keyword in card.keywords:
        keyword_lower = keyword.lower()
        if keyword_lower in ["flying", "haste", "trample", "deathtouch", "vigilance"]:
            result["tags"].add(keyword_lower)
        elif keyword_lower == "lifelink":
            result["tags"].add("lifegain")
    
    return result

def _detect_archetypes_from_text(oracle_text: str) -> Set[str]:
    """Detect archetypes from oracle text patterns."""
    archetypes = set()
    
    # Simple pattern matching
    if "gain" in oracle_text and "life" in oracle_text:
        archetypes.add("lifegain")
    
    if "mill" in oracle_text or "library" in oracle_text and "graveyard" in oracle_text:
        archetypes.add("opp_mill")
    
    if "counter target spell" in oracle_text:
        archetypes.add("control")
    
    if "destroy target" in oracle_text or "exile target" in oracle_text:
        archetypes.add("control")
    
    if "add" in oracle_text and ("mana" in oracle_text or "{" in oracle_text):
        archetypes.add("ramp")
    
    if "create" in oracle_text and "token" in oracle_text:
        archetypes.add("tokens")
    
    return archetypes