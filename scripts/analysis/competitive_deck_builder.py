#!/usr/bin/env python3
"""
Competitive Deck Builder - Tournament-Quality Deck Generation
"""

from typing import Dict, List, Tuple
from dataclasses import dataclass
from collections import defaultdict

# Competitive archetype templates based on current meta winners
COMPETITIVE_ARCHETYPES = {
    "mono_green_landfall": {
        "name": "Mono-Green Landfall",
        "colors": "G",
        "meta_share": 16.3,
        "curve_target": {"1": 8, "2": 10, "3": 6, "4": 4},
        "land_count": 25,
        "card_slots": {
            "ramp_creatures": ["Badgermole Cub", "Icetill Explorer"],
            "landfall_payoffs": ["Earthbender Ascension", "Tailspike Harpooner"],
            "finishers": ["Colossal Dreadmaw", "Voracious Troll"],
            "utility": ["Pawpatch Formation", "Tectonic Stomp"]
        },
        "slot_counts": {"ramp_creatures": 4, "landfall_payoffs": 4, "finishers": 4, "utility": 4},
        "sideboard_cards": ["Tailspike Harpooner", "Pawpatch Recruit", "Snakeskin Veil"]
    },

    "izzet_prowess": {
        "name": "Izzet Prowess",
        "colors": "UR",
        "meta_share": 15.6,
        "curve_target": {"1": 12, "2": 8, "3": 6, "4": 2},
        "land_count": 23,
        "card_slots": {
            "prowess_creatures": ["Stormchaser Drake", "Third Path Iconoclast"],
            "cheap_spells": ["Lightning Bolt", "Brainstorm"],
            "pump_effects": ["Monstrous Rage", "Ancestral Anger"],
            "finishers": ["Slickshot Show-Off", "Ral, Crackling Wit"]
        },
        "slot_counts": {"prowess_creatures": 4, "cheap_spells": 4, "pump_effects": 4, "finishers": 4},
        "sideboard_cards": ["Disdainful Stroke", "Negate", "Burning Hands"]
    },

    "orzhov_angel_lifegain": {
        "name": "Orzhov Angel Lifegain",
        "colors": "WB",
        "meta_share": 8.0,
        "curve_target": {"1": 6, "2": 10, "3": 8, "4": 6, "5+": 2},
        "land_count": 22,
        "maindeck": [
            # Creatures
            {"name": "Youthful Valkyrie", "qty": 4},
            {"name": "Bishop of Wings", "qty": 4},
            {"name": "Angel of Vitality", "qty": 4},
            {"name": "Ajani's Pridemate", "qty": 4},
            {"name": "Gilded Goose", "qty": 4},
            {"name": "Savvy Hunter", "qty": 4},
            {"name": "Lyra Dawnbringer", "qty": 2},
            {"name": "Baneslayer Angel", "qty": 2},
            {"name": "Celestial Unicorn", "qty": 2},
            # Spells
            {"name": "Fatal Push", "qty": 3},
            {"name": "Heartless Act", "qty": 2},
            {"name": "Power Word Kill", "qty": 2},
            {"name": "March of Otherworldly Light", "qty": 1},
            # Lands
            {"name": "Plains", "qty": 6},
            {"name": "Swamp", "qty": 6},
            {"name": "Wastes", "qty": 4},
            {"name": "Godless Shrine", "qty": 4},
            {"name": "Isolated Chapel", "qty": 2}
        ],
        "sideboard_cards": ["Duress", "Rest in Peace", "Archon of Emeria", "Farewell"]
    }
}

@dataclass
class DeckTemplate:
    """A complete competitive deck template."""
    name: str
    colors: str
    curve_target: Dict[str, int]
    land_count: int
    maindeck: List[Dict]
    sideboard_cards: List[str]
    meta_positioning: str = "balanced"

class CompetitiveDeckBuilder:
    """Builds tournament-quality decks using competitive templates."""

    def __init__(self):
        self.templates = self._load_templates()

    def _load_templates(self) -> Dict[str, DeckTemplate]:
        """Convert archetype definitions to DeckTemplate objects."""
        templates = {}
        for key, data in COMPETITIVE_ARCHETYPES.items():
            # Use direct maindeck if available, otherwise build from slots
            if "maindeck" in data:
                maindeck_cards = data["maindeck"]
            else:
                maindeck_cards = self._build_maindeck_from_slots(data)

            template = DeckTemplate(
                name=data["name"],
                colors=data["colors"],
                curve_target=data["curve_target"],
                land_count=data["land_count"],
                maindeck=maindeck_cards,
                sideboard_cards=data["sideboard_cards"],
                meta_positioning=self._determine_meta_positioning(key)
            )
            templates[key] = template
        return templates

    def _determine_meta_positioning(self, archetype_key: str) -> str:
        """Determine how this archetype positions vs current meta."""
        meta_mapping = {
            "mono_green_landfall": "beats_aggro_and_control",
            "izzet_prowess": "beats_aggro",
            "orzhov_angel_lifegain": "beats_aggro_and_combo"
        }
        return meta_mapping.get(archetype_key, "balanced")

    def _build_maindeck_from_slots(self, archetype_data: Dict) -> List[Dict]:
        """Build maindeck from archetype card slots."""
        maindeck = []
        for slot_name, cards in archetype_data["card_slots"].items():
            count = archetype_data["slot_counts"].get(slot_name, 4)

            # For each slot, add the required number of cards
            # If we have more cards needed than available, use all available
            # If we have fewer cards than needed, use each available card multiple times
            available_cards = len(cards)
            if available_cards >= count:
                # We have enough unique cards, use each once
                for card_name in cards[:count]:
                    maindeck.append({
                        "name": card_name,
                        "qty": 1,
                        "slot": slot_name,
                        "colors": archetype_data["colors"]
                    })
            else:
                # We don't have enough unique cards, distribute copies
                copies_per_card = count // available_cards
                extra_copies = count % available_cards

                for i, card_name in enumerate(cards):
                    qty = copies_per_card + (1 if i < extra_copies else 0)
                    maindeck.append({
                        "name": card_name,
                        "qty": qty,
                        "slot": slot_name,
                        "colors": archetype_data["colors"]
                    })

        return maindeck

    def build_deck(self, archetype: str) -> Tuple[List[Dict], List[Dict]]:
        """
        Build a complete competitive deck.

        Returns (maindeck, sideboard) as lists of card entries.
        """
        if archetype not in self.templates:
            raise ValueError(f"Unknown archetype: {archetype}")

        template = self.templates[archetype]

        # Build maindeck with proper quantities
        maindeck = self._finalize_maindeck(template)

        # Build mana base
        maindeck = self._add_mana_base(maindeck, template)

        # Build sideboard
        sideboard = self._build_sideboard(template)

        return maindeck, sideboard

    def _finalize_maindeck(self, template: DeckTemplate) -> List[Dict]:
        """Convert template cards to proper deck format with quantities."""
        maindeck = []

        # Template cards already have proper quantities
        for card in template.maindeck:
            maindeck.append({
                "name": card["name"],
                "qty": card["qty"],
                "type": "creature",  # Will be overridden by proper type detection
                "cmc": 3,  # Will be overridden by proper CMC data
                "colors": template.colors
            })

        return maindeck

    def _add_mana_base(self, maindeck: List[Dict], template: DeckTemplate) -> List[Dict]:
        """Mana base is already included in the maindeck for direct templates."""
        # For direct templates with explicit maindeck, lands are already included
        key = template.name.lower().replace(" ", "_")
        archetype_data = COMPETITIVE_ARCHETYPES.get(key, {})
        if "maindeck" in archetype_data:
            # Direct template with lands already included in maindeck
            return maindeck

        # Fallback for slot-based templates
        maindeck = [card for card in maindeck if "Land" not in card.get("type", "")]
        colors = template.colors
        land_count = template.land_count
        mana_base = self._build_mana_base(colors, land_count)
        return maindeck + mana_base

    def _build_mana_base(self, colors: str, total_lands: int) -> List[Dict]:
        """Build competitive mana base for given colors."""
        lands = []

        if len(colors) == 1:
            # Monocolor: mostly basics with some utility
            basic_count = total_lands - 3
            utility_count = 3

            # Add basics
            basic_name = {"W": "Plains", "U": "Island", "B": "Swamp",
                         "R": "Mountain", "G": "Forest"}[colors]
            for _ in range(basic_count):
                lands.append({"name": basic_name, "qty": 1, "type": "Basic Land", "colors": colors})

            # Add utility lands (simplified)
            utility_names = ["Wastes", "Castle Ardenvale", "Hive of the Eye Tyrant"]
            for name in utility_names[:utility_count]:
                lands.append({"name": name, "qty": 1, "type": "Land", "colors": ""})

        else:
            # Dual-color: mix of duals and basics
            dual_count = min(12, total_lands // 2)
            basic_count = total_lands - dual_count

            # Dual lands (simplified - would need proper dual land selection)
            dual_names = self._get_dual_lands(colors)
            for name in dual_names[:dual_count]:
                lands.append({"name": name, "qty": 1, "type": "Land", "colors": colors})

            # Basics split between colors
            for color in colors:
                basic_name = {"W": "Plains", "U": "Island", "B": "Swamp",
                             "R": "Mountain", "G": "Forest"}[color]
                for _ in range(basic_count // len(colors)):
                    lands.append({"name": basic_name, "qty": 1, "type": "Basic Land", "colors": color})

        return lands

    def _get_dual_lands(self, colors: str) -> List[str]:
        """Get appropriate dual lands for color pair."""
        dual_mapping = {
            "WU": ["Hallowed Fountain", "Glacial Fortress"],
            "WB": ["Godless Shrine", "Isolated Chapel"],
            "WR": ["Sacred Foundry", "Clifftop Retreat"],
            "WG": ["Temple Garden", "Sunpetal Grove"],
            "UB": ["Watery Grave", "Drowned Catacomb"],
            "UR": ["Steam Vents", "Sulfur Falls"],
            "UG": ["Breeding Pool", "Hinterland Harbor"],
            "BR": ["Blood Crypt", "Dragonskull Summit"],
            "BG": ["Overgrown Tomb", "Woodland Cemetery"],
            "RG": ["Stomping Ground", "Rootbound Crag"]
        }

        sorted_colors = ''.join(sorted(colors))
        return dual_mapping.get(sorted_colors, ["Wastes"] * 10)

    def _build_sideboard(self, template: DeckTemplate) -> List[Dict]:
        """Build 15-card sideboard from template."""
        sideboard = []
        for card_name in template.sideboard_cards:
            sideboard.append({
                "name": card_name,
                "qty": 1,
                "type": "unknown",
                "cmc": 2,
                "colors": template.colors
            })
        return sideboard

    def validate_deck_quality(self, maindeck: List[Dict], sideboard: List[Dict]) -> Dict[str, float]:
        """Validate deck meets competitive standards."""
        return {
            "curve_quality": self._check_curve_quality(maindeck),
            "mana_efficiency": self._check_mana_efficiency(maindeck),
            "role_balance": self._check_role_balance(maindeck),
            "meta_readiness": self._check_meta_readiness(maindeck, sideboard)
        }

    def _check_curve_quality(self, deck: List[Dict]) -> float:
        """Check if curve matches competitive standards."""
        cmc_counts = defaultdict(int)
        for card in deck:
            if card.get("type") != "Land":
                cmc = card.get("cmc", 3)
                cmc_counts[cmc] += card.get("qty", 1)

        # Competitive standard: 40%+ of spells CMC 1-2
        total_spells = sum(cmc_counts.values())
        if total_spells == 0:
            return 0.0

        low_curve = cmc_counts[1] + cmc_counts[2]
        return min(100.0, (low_curve / total_spells) * 100)

    def _check_mana_efficiency(self, deck: List[Dict]) -> float:
        """Check mana base efficiency."""
        lands = [card for card in deck if card.get("type") == "Land"]
        return min(100.0, len(lands) * 4)

    def _check_role_balance(self, deck: List[Dict]) -> float:
        """Check role distribution."""
        creatures = sum(1 for card in deck if card.get("type") == "creature")
        spells = sum(1 for card in deck if card.get("type") not in ["creature", "Land"])
        lands = sum(1 for card in deck if card.get("type") == "Land")

        total = len(deck)
        if total == 0:
            return 0.0

        # Ideal: 40% creatures, 30% spells, 30% lands
        creature_score = min(100, abs(creatures/total - 0.4) * -100 + 100)
        spell_score = min(100, abs(spells/total - 0.3) * -100 + 100)
        land_score = min(100, abs(lands/total - 0.3) * -100 + 100)

        return (creature_score + spell_score + land_score) / 3

    def _check_meta_readiness(self, maindeck: List[Dict], sideboard: List[Dict]) -> float:
        """Check if deck has tools for current meta."""
        # Simplified - check for removal and lifegain
        has_removal = any("removal" in str(card) for card in maindeck + sideboard)
        has_lifegain = any("lifegain" in str(card) for card in maindeck + sideboard)

        score = 50  # Base score
        if has_removal:
            score += 25
        if has_lifegain:
            score += 25

        return min(100.0, score)