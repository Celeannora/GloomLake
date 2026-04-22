"""
Archetype-to-primary-axis mapping for synergy analysis.

Maps archetype names (as used in generate_deck_scaffold.py and scaffold_gui.py)
to mechanical axes that should be prioritized during synergy scoring.
"""

from typing import Dict, Set

ARCHETYPE_TO_AXES: Dict[str, Set[str]] = {
    # Aggro group
    "aggro": {"haste", "pump", "trample"},
    "burn": {"removal", "haste"},
    "prowess": {"draw", "pump"},
    "infect": {"pump", "trample"},
    
    # Midrange group
    "midrange": {"removal", "draw"},
    "tempo": {"bounce", "counter", "flash"},
    "blink": {"etb", "bounce"},
    "lifegain": {"lifegain", "draw"},
    
    # Control group
    "control": {"counter", "removal", "wipe", "draw"},
    "stax": {"protection"},
    "superfriends": {"protection", "wipe"},
    
    # Combo group
    "combo": {"tutor", "draw"},
    "storm": {"storm_count", "draw", "ramp"},
    "extra_turns": {"draw", "counter"},
    
    # Graveyard group
    "graveyard": {"mill"},
    "reanimation": {"mill", "tutor"},
    "flashback": {"mill", "draw"},
    "madness": {"draw"},
    "self_mill": {"mill"},
    "opp_mill": {"mill"},
    
    # Permanents group
    "tokens": {"token", "pump"},
    "aristocrats": {"sacrifice", "token", "draw"},
    "enchantress": {"enchantress", "draw", "protection"},
    "equipment": {"pump"},
    "artifacts": {"draw", "ramp"},
    "vehicles": {"haste"},
    "voltron": {"pump", "protection"},
    
    # Ramp & Lands group
    "ramp": {"ramp", "draw"},
    "landfall": {"ramp"},
    "lands": {"ramp"},
    "domain": {"ramp"},
    "eldrazi": {"ramp"},
    "energy": {"draw", "pump"},
    "proliferate": {"pump"},
    
    # Tribal (generic - depends on tribe)
    "tribal": {"tribal"},
}

def archetype_to_axes(archetypes: list[str]) -> set[str]:
    """
    Convert a list of archetype names to a set of primary mechanical axes.
    
    Args:
        archetypes: List of archetype strings (e.g., ["lifegain", "tokens"])
        
    Returns:
        Set of axis tags that should be prioritized in synergy analysis.
    """
    axes: set[str] = set()
    for arch in archetypes:
        if arch in ARCHETYPE_TO_AXES:
            axes.update(ARCHETYPE_TO_AXES[arch])
    return axes

def get_axis_weights(axes: set[str]) -> Dict[str, float]:
    """
    Generate weight multipliers for given axes.
    
    Returns a dictionary mapping axis tags to weight multipliers.
    By default, each axis gets a multiplier of 1.5x.
    """
    return {axis: 1.5 for axis in axes}

if __name__ == "__main__":
    # Simple test
    print("Testing archetype mapping:")
    test_cases = [
        ["lifegain"],
        ["tokens", "aristocrats"],
        ["control", "superfriends"],
        ["storm", "combo"],
    ]
    for tc in test_cases:
        axes = archetype_to_axes(tc)
        print(f"{tc} -> {sorted(axes)}")