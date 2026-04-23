#!/usr/bin/env python3
"""
Mana Base Fix — Ensure playable mana bases for generated decks.

Addresses the critical issue where Esper Angel Mill had only 8 basic lands
and insufficient white sources for angel tribal strategy.
"""

from typing import Dict, List, Tuple
from collections import defaultdict

def fix_mana_base(deck: List[Dict], colors: str) -> List[Dict]:
    """
    Fix mana base issues in generated decks.

    Args:
        deck: List of card entries with 'name', 'type_line', 'mana_cost', etc.
        colors: Color identity string (e.g., 'WUB')

    Returns:
        Modified deck with corrected mana base
    """
    # Count current lands
    current_lands = [card for card in deck if 'Land' in card.get('type_line', '')]
    non_lands = [card for card in deck if 'Land' not in card.get('type_line', '')]

    # Analyze mana requirements
    mana_reqs = analyze_mana_requirements(non_lands, colors)

    # Ensure minimum land count
    target_lands = max(24, len(current_lands) + 2)  # At least 24 lands

    # Build proper mana base
    new_lands = build_balanced_mana_base(mana_reqs, target_lands, colors)

    # Replace old lands with new ones
    return non_lands + new_lands

def analyze_mana_requirements(deck: List[Dict], colors: str) -> Dict[str, int]:
    """Analyze colored mana requirements from deck."""
    requirements = defaultdict(int)

    for card in deck:
        mana_cost = card.get('mana_cost', '')
        if mana_cost and mana_cost != '0':
            # Parse mana symbols (simplified)
            for symbol in mana_cost:
                if symbol in 'WUBRG':
                    requirements[symbol] += 1

    # Ensure all colors in identity have minimum sources
    color_list = list(colors.upper())
    for color in color_list:
        if color not in requirements:
            requirements[color] = 2  # Minimum sources even for splash colors

    return dict(requirements)

def build_balanced_mana_base(requirements: Dict[str, int], total_lands: int,
                           colors: str) -> List[Dict]:
    """Build a balanced mana base with proper color distribution."""
    lands = []

    # Use dual lands for primary colors
    color_list = list(colors.upper())

    if len(color_list) >= 2:
        # Prioritize dual lands for 2+ color decks
        dual_land_types = {
            'WU': 'Hallowed Fountain',
            'WB': 'Godless Shrine',
            'WR': 'Sacred Foundry',
            'WG': 'Temple Garden',
            'UB': 'Watery Grave',
            'UR': 'Steam Vents',
            'UG': 'Breeding Pool',
            'BR': 'Blood Crypt',
            'BG': 'Overgrown Tomb',
            'RG': 'Stomping Ground'
        }

        # Add dual lands (up to 8-10)
        dual_count = min(10, total_lands // 2)
        for i in range(dual_count):
            # Cycle through color pairs
            pair_idx = i % len(color_list)
            pair = color_list[pair_idx] + color_list[(pair_idx + 1) % len(color_list)]
            sorted_pair = ''.join(sorted(pair))

            if sorted_pair in dual_land_types:
                lands.append({
                    'name': dual_land_types[sorted_pair],
                    'type_line': 'Land',
                    'mana_cost': '',
                    'oracle_text': f'({pair[0]}/{pair[1]})',
                    'colors': '',
                    'rarity': 'rare',
                    'qty': 1
                })

        # Add basic lands for remaining slots
        remaining_lands = total_lands - len(lands)
        basics_per_color = remaining_lands // len(color_list)

        basic_names = {'W': 'Plains', 'U': 'Island', 'B': 'Swamp',
                      'R': 'Mountain', 'G': 'Forest'}

        for color in color_list:
            for _ in range(basics_per_color):
                lands.append({
                    'name': basic_names[color],
                    'type_line': 'Basic Land — ' + basic_names[color],
                    'mana_cost': '',
                    'oracle_text': f'({color})',
                    'colors': color,
                    'rarity': 'common',
                    'qty': 1
                })

    else:
        # Monocolor deck - use basic lands
        color = color_list[0]
        basic_name = {'W': 'Plains', 'U': 'Island', 'B': 'Swamp',
                     'R': 'Mountain', 'G': 'Forest'}[color]

        for _ in range(total_lands):
            lands.append({
                'name': basic_name,
                'type_line': f'Basic Land — {basic_name}',
                'mana_cost': '',
                'oracle_text': f'({color})',
                'colors': color,
                'rarity': 'common',
                'qty': 1
            })

    return lands</content>
<parameter name="filePath">scripts/utils/fix_mana_base.py