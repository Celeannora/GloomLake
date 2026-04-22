#!/usr/bin/env python3
"""
Deck Scaffold Generator — Local Workflow Support

Generates a single consolidated session file that walks through the full
gate system (Gates 1–6) for a new deck. Designed for users running the
deck-building process locally with any AI tool that has limited tool access.

The scaffold:
  1. Runs search_cards.py queries based on your archetype/colors
  2. Embeds all candidate pool results directly into the session file
  3. Stubs out every required gate section (strategy, synergy, selection, etc.)
  4. Pre-populates the deck folder structure
  5. Consolidates ALL output into a single session file for easy AI context

Usage:
    python scripts/generate_deck_scaffold.py --name "Orzhov Lifegain" --colors WB --archetype lifegain
    python scripts/generate_deck_scaffold.py --name "Simic Frog Tribal" --colors GU --archetype tribal --tribe Frog
    python scripts/generate_deck_scaffold.py --name "Dimir Control" --colors UB --archetype control
    python scripts/generate_deck_scaffold.py --name "Boros Aggro" --colors WR --archetype aggro

Flags:
    --name          Deck name (used for folder naming)
    --colors        Color identity: W, U, B, R, G, WB, WUB, etc.
    --archetype     Deck archetype: aggro, midrange, control, combo, mill,
                    lifegain, tribal, ramp, tempo, burn
    --tribe         (Optional) Creature subtype for tribal builds (e.g. Frog, Angel)
    --date          (Optional) Date override (default: today, YYYY-MM-DD)
    --output-dir    (Optional) Output directory override (default: Decks/)
    --extra-tags    (Optional) Additional search tags, comma-separated
    --skip-queries  (Optional) Generate scaffold without running queries
                    (for offline template use)

Output:
    Decks/YYYY-MM-DD_Deck_Name/
    ├── session.md          ← THE SINGLE CONSOLIDATED FILE (all work goes here)
    ├── candidate_pool.csv  ← Full card data with oracle text (for AI reference)
    ├── decklist.txt        ← Empty template (filled during Gate 3)
    ├── analysis.md         ← Empty template (filled after all gates)
    └── sideboard_guide.md  ← Empty template (filled after Gate 5)

Exit codes:
    0  Scaffold generated successfully
    1  Invalid arguments
    2  cards_by_category/ not found
"""

import argparse
import csv
import re
import subprocess
import sys
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# ─── Complete MTG creature type list (Scryfall catalog, 325 types) ─────────────
ALL_CREATURE_TYPES: List[str] = [
    "Advisor", "Aetherborn", "Alien", "Ally", "Angel", "Antelope", "Ape",
    "Archer", "Archon", "Armadillo", "Army", "Artifact", "Artificer",
    "Assassin", "Assembly-Worker", "Astartes", "Atog", "Aurochs", "Automaton",
    "Avatar", "Azra", "Badger", "Balloon", "Barbarian", "Bard", "Basilisk",
    "Bat", "Bear", "Beast", "Beaver", "Beeble", "Beholder", "Berserker",
    "Bird", "Bison", "Blinkmoth", "Boar", "Brainiac", "Bringer", "Brushwagg",
    "C'tan", "Camarid", "Camel", "Capybara", "Caribou", "Carrier", "Cat",
    "Centaur", "Chicken", "Child", "Chimera", "Citizen", "Cleric", "Clown",
    "Cockatrice", "Construct", "Coward", "Coyote", "Crab", "Crocodile",
    "Custodes", "Cyberman", "Cyclops", "Dalek", "Dauthi", "Demigod", "Demon",
    "Deserter", "Detective", "Devil", "Dinosaur", "Djinn", "Doctor", "Dog",
    "Dragon", "Drake", "Dreadnought", "Drix", "Drone", "Druid", "Dryad",
    "Dwarf", "Echidna", "Efreet", "Egg", "Elder", "Eldrazi", "Elemental",
    "Elephant", "Elf", "Elk", "Employee", "Eye", "Faerie", "Ferret", "Fish",
    "Flagbearer", "Fox", "Fractal", "Frog", "Fungus", "Gamer", "Gargoyle",
    "Germ", "Giant", "Gith", "Glimmer", "Gnoll", "Gnome", "Goat", "Goblin",
    "God", "Golem", "Gorgon", "Graveborn", "Gremlin", "Griffin", "Guest",
    "Hag", "Halfling", "Hamster", "Harpy", "Head", "Hedgehog", "Hellion",
    "Hero", "Hippo", "Hippogriff", "Homarid", "Homunculus", "Hornet",
    "Horror", "Horse", "Human", "Hydra", "Hyena", "Illusion", "Imp",
    "Incarnation", "Inkling", "Inquisitor", "Insect", "Jackal", "Jellyfish",
    "Juggernaut", "Kangaroo", "Kavu", "Kirin", "Kithkin", "Knight", "Kobold",
    "Kor", "Kraken", "Lamia", "Lammasu", "Leech", "Lemur", "Leviathan",
    "Lhurgoyf", "Licid", "Lizard", "Lobster", "Manticore", "Masticore",
    "Mercenary", "Merfolk", "Metathran", "Minion", "Minotaur", "Mite",
    "Mole", "Monger", "Mongoose", "Monk", "Monkey", "Moogle", "Moonfolk",
    "Mount", "Mouse", "Mutant", "Myr", "Mystic", "Naga", "Nautilus",
    "Necron", "Nephilim", "Nightmare", "Nightstalker", "Ninja", "Noble",
    "Noggle", "Nomad", "Nymph", "Octopus", "Ogre", "Ooze", "Orb", "Orc",
    "Orgg", "Otter", "Ouphe", "Ox", "Oyster", "Pangolin", "Peasant",
    "Pegasus", "Pentavite", "Performer", "Pest", "Phelddagrif", "Phoenix",
    "Phyrexian", "Pilot", "Pincher", "Pirate", "Plant", "Porcupine",
    "Possum", "Praetor", "Primarch", "Prism", "Processor", "Qu", "Rabbit",
    "Raccoon", "Ranger", "Rat", "Rebel", "Reflection", "Reveler", "Rhino",
    "Rigger", "Robot", "Rogue", "Rukh", "Sable", "Salamander", "Samurai",
    "Sand", "Saproling", "Satyr", "Scarecrow", "Scientist", "Scion",
    "Scorpion", "Scout", "Sculpture", "Seal", "Serf", "Serpent", "Servo",
    "Shade", "Shaman", "Shapeshifter", "Shark", "Sheep", "Siren", "Skeleton",
    "Skunk", "Slith", "Sliver", "Sloth", "Slug", "Snail", "Snake", "Soldier",
    "Soltari", "Spawn", "Specter", "Spellshaper", "Sphinx", "Spider", "Spike",
    "Spirit", "Splinter", "Sponge", "Spy", "Squid", "Squirrel", "Starfish",
    "Surrakar", "Survivor", "Symbiote", "Synth", "Teddy", "Tentacle",
    "Tetravite", "Thalakos", "Thopter", "Thrull", "Tiefling", "Time Lord",
    "Toy", "Treefolk", "Trilobite", "Triskelavite", "Troll", "Turtle",
    "Tyranid", "Unicorn", "Urzan", "Vampire", "Varmint", "Vedalken",
    "Villain", "Volver", "Wall", "Walrus", "Warlock", "Warrior", "Wasp",
    "Weasel", "Weird", "Werewolf", "Whale", "Wizard", "Wolf", "Wolverine",
    "Wombat", "Worm", "Wraith", "Wurm", "Yeti", "Zombie", "Zubera",
]
_CREATURE_TYPES_LOWER: Dict[str, str] = {t.lower(): t for t in ALL_CREATURE_TYPES}


# ─── Archetype → query plan mapping ──────────────────────────────────────────

ARCHETYPE_QUERIES: Dict[str, List[Dict[str, str]]] = {
    "aggro": [
        {"label": "Aggressive creatures", "args": "--type creature --tags haste,pump,trample --cmc-max 3"},
        {"label": "Cheap creatures", "args": "--type creature --cmc-max 2"},
        {"label": "Removal instants", "args": "--type instant --tags removal --cmc-max 3"},
        {"label": "Combat tricks / pump", "args": "--type instant --tags pump --cmc-max 2"},
        {"label": "Lands", "args": "--type land"},
    ],
    "midrange": [
        {"label": "Value creatures (2-4 CMC)", "args": "--type creature --cmc-min 2 --cmc-max 4"},
        {"label": "Top-end threats (5+ CMC)", "args": "--type creature --cmc-min 5 --rarity rare,mythic"},
        {"label": "Removal", "args": "--type instant,sorcery --tags removal"},
        {"label": "Card advantage", "args": "--type instant,sorcery,enchantment --tags draw"},
        {"label": "Planeswalkers", "args": "--type planeswalker"},
        {"label": "Lands", "args": "--type land"},
    ],
    "control": [
        {"label": "Counterspells", "args": "--type instant --tags counter"},
        {"label": "Removal instants", "args": "--type instant --tags removal"},
        {"label": "Board wipes", "args": "--type sorcery --tags wipe"},
        {"label": "Card draw", "args": "--type instant,sorcery --tags draw"},
        {"label": "Win conditions", "args": "--type creature,planeswalker --cmc-min 4 --rarity rare,mythic"},
        {"label": "Enchantments", "args": "--type enchantment"},
        {"label": "Lands", "args": "--type land"},
    ],
    "combo": [
        {"label": "Combo creatures", "args": "--type creature --tags etb,draw,tutor"},
        {"label": "Combo spells", "args": "--type instant,sorcery --tags tutor,draw"},
        {"label": "Enabler artifacts", "args": "--type artifact --tags ramp,draw"},
        {"label": "Enabler enchantments", "args": "--type enchantment"},
        {"label": "Protection / counters", "args": "--type instant --tags counter,protection"},
        {"label": "Lands", "args": "--type land"},
    ],
    "opp_mill": [
        {"label": "Opponent mill effects", "args": "--oracle \"opponent mills\""},
        {"label": "Targeted mill effects", "args": "--oracle \"target player mills\""},
        {"label": "Multi-opponent mill", "args": "--oracle \"each opponent mills\""},
        {"label": "Variable mill effects", "args": "--oracle \"mills that many\""},
        {"label": "Mill cards (catch-all)", "args": "--tags mill"},
        {"label": "Lands", "args": "--type land"},
    ],
    "self_mill": [
        {"label": "Library-to-graveyard effects", "args": "--oracle \"put the top\" --oracle \"into your graveyard\""},
        {"label": "Self-mill effects", "args": "--oracle \"mill yourself\""},
        {"label": "Discard / self-mill enablers", "args": "--oracle discard --tags mill"},
        {"label": "Graveyard fillers", "args": "--oracle put.*cards.*graveyard"},
        {"label": "Mill effects (catch-all)", "args": "--tags mill"},
        {"label": "Lands", "args": "--type land"},
    ],
    "reanimation": [
        {"label": "Return creature from graveyard", "args": "--oracle \"return target creature card from your graveyard\""},
        {"label": "Graveyard-to-battlefield", "args": "--oracle return.*from.*graveyard.*battlefield"},
        {"label": "Return to play effects", "args": "--oracle return.*graveyard.*to.*play"},
        {"label": "Reanimation cards (catch-all)", "args": "--tags reanimation"},
        {"label": "Sacrifice enablers", "args": "--oracle \"sacrifice a creature\""},
        {"label": "Discard + reanimate", "args": "--oracle \"discard\" --tags reanimation"},
        {"label": "Lands", "args": "--type land"},
    ],
    "lifegain": [
        {"label": "Lifegain creatures", "args": "--type creature --tags lifegain"},
        {"label": "Lifegain payoffs", "args": "--type creature --oracle \"whenever you gain life\""},
        {"label": "Lifegain spells", "args": "--type instant,sorcery --tags lifegain"},
        {"label": "Lifegain enchantments", "args": "--type enchantment --tags lifegain"},
        {"label": "Removal", "args": "--type instant --tags removal --cmc-max 3"},
        {"label": "Lands", "args": "--type land"},
    ],
    "tribal": [
        {"label": "Tribal creatures (by subtype)", "args": "--type creature"},
        {"label": "Tribal support", "args": "--type instant,sorcery,enchantment --tags tribal,pump"},
        {"label": "Removal", "args": "--type instant --tags removal --cmc-max 3"},
        {"label": "Card draw", "args": "--type instant,sorcery,enchantment --tags draw"},
        {"label": "Lands", "args": "--type land"},
    ],
    "ramp": [
        {"label": "Ramp creatures", "args": "--type creature --tags ramp"},
        {"label": "Ramp spells", "args": "--type instant,sorcery --tags ramp"},
        {"label": "Ramp artifacts", "args": "--type artifact --tags ramp"},
        {"label": "Top-end payoffs", "args": "--type creature,planeswalker --cmc-min 5 --rarity rare,mythic"},
        {"label": "Removal", "args": "--type instant,sorcery --tags removal"},
        {"label": "Lands", "args": "--type land"},
    ],
    "tempo": [
        {"label": "Efficient creatures", "args": "--type creature --cmc-max 3 --tags flash,flying"},
        {"label": "Bounce spells", "args": "--type instant --tags bounce"},
        {"label": "Counterspells", "args": "--type instant --tags counter --cmc-max 3"},
        {"label": "Cheap removal", "args": "--type instant --tags removal --cmc-max 2"},
        {"label": "Card draw", "args": "--type instant --tags draw --cmc-max 3"},
        {"label": "Lands", "args": "--type land"},
    ],
    "burn": [
        {"label": "Burn spells", "args": "--type instant,sorcery --tags removal --oracle \"damage\""},
        {"label": "Aggressive creatures", "args": "--type creature --tags haste --cmc-max 3"},
        {"label": "Reach / finisher spells", "args": "--type instant,sorcery --oracle \"each opponent\" --cmc-max 4"},
        {"label": "Lands", "args": "--type land"},
    ],
    "aristocrats": [
        {"label": "Death triggers", "args": "--oracle \"whenever a creature you control dies\""},
        {"label": "Sacrifice payoffs", "args": "--oracle \"whenever you sacrifice\""},
        {"label": "Sacrifice outlets", "args": "--oracle \"sacrifice a\""},
        {"label": "Mass death payoffs", "args": "--oracle \"creature dies\""},
        {"label": "Sacrifice synergy (catch-all)", "args": "--tags sacrifice"},
        {"label": "Lands", "args": "--type land"},
    ],
    "tokens": [
        {"label": "Token creators", "args": "--oracle create.*token"},
        {"label": "Anthem effects", "args": "--oracle \"creatures you control get\""},
        {"label": "Token payoffs", "args": "--oracle \"for each token you control\""},
        {"label": "Convoke spells", "args": "--keywords Convoke"},
        {"label": "Token cards (catch-all)", "args": "--tags token"},
        {"label": "Lands", "args": "--type land"},
    ],
    "blink": [
        {"label": "Flicker effects", "args": "--oracle exile.*return.*to.*battlefield"},
        {"label": "ETB payoffs", "args": "--oracle \"whenever.*enters the battlefield\""},
        {"label": "Flicker spells", "args": "--oracle flicker"},
        {"label": "Blitz creatures", "args": "--keywords Blitz"},
        {"label": "Blink cards (catch-all)", "args": "--tags blink"},
        {"label": "Lands", "args": "--type land"},
    ],
    "stax": [
        {"label": "Denial effects", "args": "--oracle \"players can't\""},
        {"label": "Tax effects", "args": "--oracle \"costs.*more to cast\""},
        {"label": "Cast triggers", "args": "--oracle \"whenever a player casts a spell\""},
        {"label": "Freeze effects", "args": "--oracle \"don't untap\""},
        {"label": "Restriction effects (catch-all)", "args": "--oracle \"can't\""},
        {"label": "Lands", "args": "--type land"},
    ],
    "storm": [
        {"label": "Storm keyword", "args": "--keywords Storm"},
        {"label": "Spell-count payoffs", "args": "--oracle \"for each spell cast this turn\""},
        {"label": "Ritual / mana burst", "args": "--oracle \"add.*to your mana pool\" --oracle \"this turn\""},
        {"label": "Copy effects", "args": "--oracle \"copy.*for each other spell\""},
        {"label": "Storm spells (catch-all)", "args": "--tags storm_count"},
        {"label": "Lands", "args": "--type land"},
    ],
    "prowess": [
        {"label": "Prowess keyword", "args": "--keywords Prowess"},
        {"label": "Noncreature cast triggers", "args": "--oracle \"whenever you cast a noncreature spell\""},
        {"label": "Spell-cast payoffs", "args": "--oracle \"whenever you cast an instant or sorcery\""},
        {"label": "Magecraft effects", "args": "--oracle magecraft"},
        {"label": "Noncreature spell synergy (catch-all)", "args": "--oracle \"noncreature spell\""},
        {"label": "Lands", "args": "--type land"},
    ],
    "enchantress": [
        {"label": "Enchantment-cast triggers", "args": "--oracle \"whenever you cast an enchantment\""},
        {"label": "Enchantment ETB payoffs", "args": "--oracle \"whenever an enchantment enters the battlefield\""},
        {"label": "Constellation effects", "args": "--oracle constellation"},
        {"label": "Aura + draw combos", "args": "--oracle \"enchant creature\" --oracle \"draw a card\""},
        {"label": "Enchantress cards (catch-all)", "args": "--tags enchantress"},
        {"label": "Lands", "args": "--type land"},
    ],
    "artifacts": [
        {"label": "Artifact ETB payoffs", "args": "--oracle \"whenever an artifact enters the battlefield\""},
        {"label": "Metalcraft effects", "args": "--oracle metalcraft"},
        {"label": "Affinity spells", "args": "--keywords Affinity"},
        {"label": "Improvise spells", "args": "--keywords Improvise"},
        {"label": "Artifact ETB (catch-all)", "args": "--oracle \"artifact enters\""},
        {"label": "Lands", "args": "--type land"},
    ],
    "equipment": [
        {"label": "Equipment cards", "args": "--type artifact --oracle \"equip\""},
        {"label": "Equipped creature payoffs", "args": "--oracle \"whenever equipped creature\""},
        {"label": "Auto-attach effects", "args": "--oracle \"attach.*to.*creature you control\""},
        {"label": "Living weapon", "args": "--oracle \"living weapon\""},
        {"label": "Equip effects (catch-all)", "args": "--oracle \"equip\""},
        {"label": "Lands", "args": "--type land"},
    ],
    "voltron": [
        {"label": "Free aura attach", "args": "--oracle \"put.*aura.*onto the battlefield attached\""},
        {"label": "Double strike + trample", "args": "--oracle \"double strike\" --oracle trample"},
        {"label": "Protection suite", "args": "--oracle hexproof --oracle indestructible"},
        {"label": "Commander damage win", "args": "--oracle \"21 or more combat damage to a player\""},
        {"label": "Equipped creature synergy (catch-all)", "args": "--oracle \"equipped creature\""},
        {"label": "Lands", "args": "--type land"},
    ],
    "landfall": [
        {"label": "Landfall keyword", "args": "--oracle landfall"},
        {"label": "Land ETB triggers", "args": "--oracle \"whenever a land enters the battlefield under your control\""},
        {"label": "Extra land drops", "args": "--oracle \"you may play an additional land\""},
        {"label": "Land tutors", "args": "--oracle \"search your library for.*land\""},
        {"label": "Land enters (catch-all)", "args": "--oracle \"land enters\""},
        {"label": "Lands", "args": "--type land"},
    ],
    "lands": [
        {"label": "Land recursion", "args": "--oracle \"return.*land.*from your graveyard\""},
        {"label": "Graveyard land play", "args": "--oracle \"you may play lands from your graveyard\""},
        {"label": "Dredge effects", "args": "--oracle dredge"},
        {"label": "Land sacrifice synergy", "args": "--oracle sacrifice.*land"},
        {"label": "Land card synergy (catch-all)", "args": "--oracle \"land card\""},
        {"label": "Lands", "args": "--type land"},
    ],
    "infect": [
        {"label": "Infect keyword", "args": "--keywords Infect"},
        {"label": "Poison counter effects", "args": "--oracle \"poison counter\""},
        {"label": "Wither effects", "args": "--oracle wither"},
        {"label": "Pump spells", "args": "--oracle \"gets.*until end of turn\""},
        {"label": "Poison effects (catch-all)", "args": "--oracle \"poison\""},
        {"label": "Lands", "args": "--type land"},
    ],
    "proliferate": [
        {"label": "Proliferate keyword", "args": "--keywords Proliferate"},
        {"label": "Proliferate effects", "args": "--oracle proliferate"},
        {"label": "Counter doublers", "args": "--oracle \"double the number of.*counters\""},
        {"label": "Mass counter placement", "args": "--oracle \"put.*counter.*on each\""},
        {"label": "Proliferate effects (catch-all)", "args": "--oracle \"proliferate\""},
        {"label": "Lands", "args": "--type land"},
    ],
    "energy": [
        {"label": "Energy counter cards", "args": "--oracle \"energy counter\""},
        {"label": "Energy producers", "args": "--oracle \"you get\" --oracle energy"},
        {"label": "Energy spenders", "args": "--oracle pay.*energy"},
        {"label": "Energy cards (catch-all)", "args": "--tags energy"},
        {"label": "Lands", "args": "--type land"},
    ],
    "graveyard": [
        {"label": "Graveyard-count payoffs", "args": "--oracle \"cards in your graveyard\""},
        {"label": "Delve spells", "args": "--keywords Delve"},
        {"label": "Threshold effects", "args": "--keywords Threshold"},
        {"label": "Seven-card threshold", "args": "--oracle \"if seven or more cards are in your graveyard\""},
        {"label": "Reanimation synergy (catch-all)", "args": "--tags reanimation"},
        {"label": "Lands", "args": "--type land"},
    ],
    "flashback": [
        {"label": "Flashback spells", "args": "--keywords Flashback"},
        {"label": "Jump-start spells", "args": "--keywords Jump-start"},
        {"label": "Aftermath spells", "args": "--keywords Aftermath"},
        {"label": "Escape spells", "args": "--keywords Escape"},
        {"label": "Cast-from-graveyard effects", "args": "--oracle \"cast.*from your graveyard\""},
        {"label": "Lands", "args": "--type land"},
    ],
    "madness": [
        {"label": "Madness spells", "args": "--keywords Madness"},
        {"label": "Discard triggers", "args": "--oracle \"whenever you discard a card\""},
        {"label": "Discard-to-draw", "args": "--oracle discard.*card.*draw"},
        {"label": "Impulse cast effects", "args": "--oracle \"you may cast.*from your hand.*exile it\""},
        {"label": "Discard synergy (catch-all)", "args": "--tags discard"},
        {"label": "Lands", "args": "--type land"},
    ],
    "superfriends": [
        {"label": "Planeswalkers", "args": "--type planeswalker"},
        {"label": "Planeswalker synergy", "args": "--oracle \"whenever a planeswalker you control\""},
        {"label": "Loyalty counter effects", "args": "--oracle \"loyalty counter\""},
        {"label": "Planeswalker payoffs", "args": "--oracle \"you control a planeswalker\""},
        {"label": "Planeswalker synergy (catch-all)", "args": "--oracle \"planeswalker\""},
        {"label": "Lands", "args": "--type land"},
    ],
    "extra_turns": [
        {"label": "Extra turn spells", "args": "--oracle \"take an extra turn after this one\""},
        {"label": "Additional turn effects", "args": "--oracle \"takes an additional turn\""},
        {"label": "Extra turn (broad)", "args": "--oracle \"extra turn\""},
        {"label": "Untap-all effects", "args": "--oracle \"untap all\""},
        {"label": "Extra turn effects (catch-all)", "args": "--oracle \"extra turn\""},
        {"label": "Lands", "args": "--type land"},
    ],
    "eldrazi": [
        {"label": "Eldrazi creatures", "args": "--type creature --oracle \"eldrazi\""},
        {"label": "Annihilator keyword", "args": "--keywords Annihilator"},
        {"label": "Colorless mana cards", "args": "--oracle \"colorless mana\""},
        {"label": "Waste lands", "args": "--oracle waste --type land"},
        {"label": "Eldrazi tribal (catch-all)", "args": "--oracle \"eldrazi\""},
        {"label": "Lands", "args": "--type land"},
    ],
    "vehicles": [
        {"label": "Vehicle cards", "args": "--type artifact --keywords Crew"},
        {"label": "Crew keyword", "args": "--keywords Crew"},
        {"label": "Crew + animate", "args": "--oracle crew --oracle \"becomes an artifact creature\""},
        {"label": "Crew payoffs", "args": "--oracle \"whenever you crew\""},
        {"label": "Crew effects (catch-all)", "args": "--oracle \"crew\""},
        {"label": "Lands", "args": "--type land"},
    ],
    "domain": [
        {"label": "Domain keyword", "args": "--oracle domain"},
        {"label": "Basic land type payoffs", "args": "--oracle \"for each basic land type among lands you control\""},
        {"label": "Land type count", "args": "--oracle \"number of basic land types\""},
        {"label": "Basic land tutors", "args": "--oracle \"search your library for a basic land\""},
        {"label": "Domain effects (catch-all)", "args": "--oracle \"domain\""},
        {"label": "Lands", "args": "--type land"},
    ],
}



def run_query(
    repo_root: Path,
    base_args,
    colors: str,
    tribe: Optional[str] = None,
    suppress_tribe: bool = False,
) -> Tuple[str, str, int]:
    """
    Run a search_cards.py query. Returns (command_string, output, result_count).

    Injects --colors <COLORS> for all non-land, non-colorless queries so that
    candidate pools are limited to cards playable in the deck's color identity.
    Land queries are deliberately exempt — broad land pools are intentional
    (dual lands, utility lands, and fetches should appear regardless of color).
    Colorless decks (colors == 'C') are also exempt.

    base_args can be a string (dict-format queries) or a list (list-format queries).
    """
    from mtg_utils import RepoPaths
    paths = RepoPaths(root=repo_root)
    # search_cards.py lives in scripts/cli/, not scripts/ directly
    script = paths.scripts_dir / "cli" / "search_cards.py"
    if not script.exists():
        script = paths.scripts_dir / "search_cards.py"  # legacy fallback
    import shlex

    # Normalise base_args: list-format queries are already a list of tokens;
    # dict-format queries provide a single string that needs shlex splitting.
    if isinstance(base_args, list):
        arg_tokens = list(base_args)  # copy to avoid mutating the original
    else:
        arg_tokens = shlex.split(base_args)

    cmd_parts = [sys.executable, str(script)] + arg_tokens

    # Inject --colors unless:
    #   (a) colors is empty or colorless ('C') — no color filter applies
    #   (b) this is a land query — broad land pool is intentional (duals, fetches)
    #   (c) --colors is already present in the args (avoid double-injection)
    _normalized_colors = colors.upper().strip() if colors else ""
    _is_land_only_query = (
        "--type" in arg_tokens
        and arg_tokens[arg_tokens.index("--type") + 1].lower() == "land"
        and "--oracle" not in arg_tokens
        and "--tags" not in arg_tokens
    )
    if (
        _normalized_colors
        and _normalized_colors != "C"
        and not _is_land_only_query
        and "--colors" not in arg_tokens
    ):
        cmd_parts += ["--colors", _normalized_colors]

    # Tribe is NOT used as a filter on existing queries — it only adds
    # supplemental per-tribe creature queries to the query plan (see main()).
    # Filtering here would exclude non-tribal cards (Changelings, support spells)
    # from the candidate pool, which breaks non-creature archetypes.

    # List-format queries already include --format/--limit; avoid duplicating.
    if "--show-tags" not in arg_tokens:
        cmd_parts += ["--show-tags"]
    if "--format" not in arg_tokens:
        cmd_parts += ["--format", "csv"]
    if "--limit" not in arg_tokens:
        cmd_parts += ["--limit", "9999"]

    # Extra tags are handled as separate supplemental queries in main(),
    # not merged into every existing query (which pollutes OR-based tag matching).

    cmd_str = " ".join(cmd_parts)
    display_cmd = cmd_str.replace(str(script), "search_cards.py")
    display_cmd = display_cmd.replace(sys.executable + " ", "python ")

    try:
        import os as _os
        _env = _os.environ.copy()
        _scripts_root = str(repo_root / "scripts")
        _utils_dir = str(repo_root / "scripts" / "utils")
        _analysis_dir = str(repo_root / "scripts" / "analysis")
        _cli_dir = str(repo_root / "scripts" / "cli")
        _extra = _os.pathsep.join([_scripts_root, _utils_dir, _analysis_dir, _cli_dir])
        _existing = _env.get("PYTHONPATH", "")
        _env["PYTHONPATH"] = (_extra + _os.pathsep + _existing) if _existing else _extra
        _env.setdefault("PYTHONUTF8", "1")
        import sys as _sys
        result = subprocess.run(
            cmd_parts,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=str(repo_root),
            timeout=60,
            env=_env,
        )
        output = result.stdout or result.stderr or "(no output)"

        # Count results from output
        count = 0
        for line in output.splitlines():
            if "Total candidates:" in line:
                try:
                    count = int(line.split(":")[-1].strip())
                except ValueError:
                    pass
                break
            elif "No cards matched" in line:
                count = 0
                break

        # CSV format has no "Total candidates" line — count data rows
        if count == 0 and output.strip() and "No cards matched" not in output:
            csv_lines = [l for l in output.strip().splitlines() if l.strip()]
            if csv_lines and "," in csv_lines[0]:  # looks like CSV header
                count = max(0, len(csv_lines) - 1)  # subtract header row

        return display_cmd, output, count

    except subprocess.TimeoutExpired:
        return display_cmd, "(query timed out after 60s)", 0
    except FileNotFoundError:
        return display_cmd, "(search_cards.py not found)", 0


def sanitize_folder_name(name: str) -> str:
    """Convert deck name to folder-safe format."""
    return name.replace(" ", "_").replace("/", "_").replace("\\", "_")


def generate_session_file(
    deck_date: str,
    deck_name: str,
    colors: str,
    archetype: str,
    query_results: List[Dict],
    tribe: Optional[str] = None,
    consolidated_csv: str = "",
    unique_card_count: int = 0,
) -> str:
    """Generate the consolidated session.md content."""
    from mtg_utils import RepoPaths

    if tribe:
        tribe_list = tribe if isinstance(tribe, list) else [tribe]
        tribe_display = " / ".join(tribe_list) + " Tribal"
    else:
        tribe_display = None
    archetype_display = f"{archetype.title()} ({tribe_display})" if tribe_display else archetype.title()
    color_display = "/".join(colors.upper())

    lines = [
        f"# Deck Building Session: {deck_name}",
        "",
        f"**Date:** {deck_date}",
        f"**Colors:** {color_display}",
        f"**Archetype:** {archetype_display}",
        f"**Format:** Standard",
        "",
        "> This file is the single consolidated workspace for building this deck.",
        "> All gate work, candidate pools, synergy evaluation, and card selections",
        "> go here. When complete, copy the final outputs into decklist.txt,",
        "> analysis.md, and sideboard_guide.md.",
        "",
        "---",
        "",
        "## Pre-Flight Checks",
        "",
        f"- [ ] `{RepoPaths.CARDS_DIR_NAME}/` is present and populated",
        f"- [ ] `{RepoPaths.SCRIPTS_DIR_NAME}/search_cards.py` runs without errors",
        f"- [ ] `{RepoPaths.SCRIPTS_DIR_NAME}/validate_decklist.py` runs without errors",
        "",
        "---",
        "",
        "# GATE 1: DATABASE QUERY — CANDIDATE POOL",
        "",
        "## Queries Run",
        "",
        f"| # | Label | Command | Candidates |",
        f"|---|-------|---------|------------|",
    ]

    for i, qr in enumerate(query_results, 1):
        cmd_short = qr["command"].replace("python ", "").strip()
        lines.append(f"| {i} | {qr['label']} | `{cmd_short}` | {qr['count']} |")

    # Embed consolidated, deduplicated candidate pool (slim: no oracle text)
    # Full card details including oracle text are in candidate_pool.csv
    lines += [
        "",
        "## Candidate Pool",
        "",
        f"> **{unique_card_count} unique cards** across all queries (deduplicated).",
        "> The `pool` column shows which query/queries matched each card.",
        "> Full card details (including oracle text) are in [`candidate_pool.csv`](candidate_pool.csv).",
        "> DO NOT add any card that does not appear in this pool.",
        "",
    ]

    if consolidated_csv:
        # Strip oracle_text column for the inline version to save space
        import csv as _csv_mod
        import io as _io_mod
        reader = _csv_mod.DictReader(_io_mod.StringIO(consolidated_csv))
        slim_cols = [c for c in (reader.fieldnames or []) if c != "oracle_text"]
        slim_buf = _io_mod.StringIO()
        writer = _csv_mod.DictWriter(slim_buf, fieldnames=slim_cols, extrasaction="ignore")
        writer.writeheader()
        for row in reader:
            writer.writerow(row)
        lines.append("```csv")
        lines.extend(slim_buf.getvalue().strip().splitlines())
        lines.append("```")
    else:
        lines.append("*(no results — run with queries enabled)*")

    lines += [""]

    lines += [
        "## Additional Queries",
        "",
        "> If the pool above is insufficient, run additional queries:",
        "> ```bash",
        f"> python {RepoPaths.SCRIPTS_DIR_NAME}/search_cards.py --type <type> --colors <colors> [flags...]",
        "> ```",
        "> Add any new cards to the candidate pool above.",
        "",
        "### Gate 1 Checklist",
        "",
        "- [ ] Every needed card type has been queried",
        "- [ ] Complete candidate pool exists from query results above",
        "- [ ] Zero cards have been named from memory or web sources",
        "",
        "---",
        "",
        "# GATE 2: STRATEGY DEFINITION",
        "",
        "## Win Condition",
        "",
        "**Primary win condition:** (fill in)",
        "",
        "**Target win turn:** Turn N",
        "",
        "**Backup plan:** (fill in)",
        "",
        "## Role Map",
        "",
        "| Role | Required | Candidates Available |",
        "|------|----------|---------------------|",
        "| Win condition | ? | (list from pool) |",
        "| Support / engine | ? | (list from pool) |",
        "| Interaction / removal | ? | (list from pool) |",
        "| Card advantage | ? | (list from pool) |",
        "| Mana / ramp | ? | (list from pool) |",
        "| Lands | 22-26 | (list from pool) |",
        "",
        "### Gate 2 Checklist",
        "",
        "- [ ] One primary win condition defined",
        "- [ ] Target win turn identified",
        "- [ ] All roles have candidates from the pool",
        "- [ ] Strategy uses database-confirmed cards only",
        "",
        "---",
        "",
        "# GATE 2.5: SYNERGY EVALUATION",
        "",
        "## Pairwise Interactions",
        "",
        "> For each candidate, classify interactions using:",
        "> ENABLES / TRIGGERS / AMPLIFIES / PROTECTS / FEEDS / REDUNDANT",
        "",
        "## Synergy Scores",
        "",
        "| Card | Synergy Count | Role Breadth | Dependency | Notes |",
        "|------|--------------|-------------|------------|-------|",
        "| (fill in) | | | | |",
        "",
        "**Average Synergy Count:** X.X (threshold: ≥ 3.0)",
        "**Cards with Synergy Count 0–1:** N (max: 4)",
        "**Hub cards (Synergy Count ≥ 8):** N (min: 2)",
        "",
        "## Synergy Chains",
        "",
        "**Chain 1 — [Primary Win Con]:**",
        "[Card A] → [output] → [Card B] → [output] → [Card C] → [outcome]",
        "Redundancy: (fill in)",
        "Minimum pieces to function: N of M",
        "",
        "**Chain 2 — [Secondary / Defensive]:**",
        "(fill in)",
        "",
        "## Redundant Pairs",
        "",
        "| Card A | Card B | Justification for Both |",
        "|--------|--------|------------------------|",
        "| | | |",
        "",
        "### Gate 2.5 Checklist",
        "",
        "- [ ] All candidates scored (Synergy Count, Role Breadth, Dependency)",
        "- [ ] Average Synergy Count ≥ 3.0",
        "- [ ] ≤ 4 cards with Synergy Count 0–1",
        "- [ ] ≥ 2 hub cards with Synergy Count ≥ 8",
        "- [ ] No card with Dependency ≥ 3",
        "- [ ] All REDUNDANT pairs justified",
        "- [ ] 2–3 synergy chains mapped with redundancy and degradation noted",
        "",
        "---",
        "",
        "# GATE 3: CARD SELECTION",
        "",
        "> For every card, cite the source file from the query output above.",
        "> If you cannot cite it, do not include it.",
        "",
        "## Mainboard (60 cards)",
        "",
        "### Creatures",
        "",
        "| Qty | Card Name | Mana | Source File | Set/Collector | Role/Justification |",
        "|-----|-----------|------|------------|---------------|-------------------|",
        "| | | | | | |",
        "",
        "### Instants",
        "",
        "| Qty | Card Name | Mana | Source File | Set/Collector | Role/Justification |",
        "|-----|-----------|------|------------|---------------|-------------------|",
        "| | | | | | |",
        "",
        "### Sorceries",
        "",
        "| Qty | Card Name | Mana | Source File | Set/Collector | Role/Justification |",
        "|-----|-----------|------|------------|---------------|-------------------|",
        "| | | | | | |",
        "",
        "### Enchantments",
        "",
        "| Qty | Card Name | Mana | Source File | Set/Collector | Role/Justification |",
        "|-----|-----------|------|------------|---------------|-------------------|",
        "| | | | | | |",
        "",
        "### Artifacts",
        "",
        "| Qty | Card Name | Mana | Source File | Set/Collector | Role/Justification |",
        "|-----|-----------|------|------------|---------------|-------------------|",
        "| | | | | | |",
        "",
        "### Planeswalkers",
        "",
        "| Qty | Card Name | Mana | Source File | Set/Collector | Role/Justification |",
        "|-----|-----------|------|------------|---------------|-------------------|",
        "| | | | | | |",
        "",
        "### Gate 3 Checklist",
        "",
        "- [ ] All 60 mainboard cards have a cited source file",
        "- [ ] Every card came from Gate 1 query results",
        "- [ ] Zero cards sourced from web or memory",
        "",
        "---",
        "",
        "# GATE 4: MANA BASE",
        "",
        "## Colored Pip Count",
        "",
        "| Color | Total Pips | Key Cards |",
        "|-------|-----------|-----------|",
        "| | | |",
        "",
        "## Land Selection",
        "",
        "| Qty | Land Name | Source File | Set/Collector | Colors Produced |",
        "|-----|-----------|------------|---------------|-----------------|",
        "| | | | | |",
        "",
        "## Karsten Validation",
        "",
        "| Color | Required Sources | Actual Sources | Status |",
        "|-------|-----------------|----------------|--------|",
        "| | | | |",
        "",
        "### Gate 4 Checklist",
        "",
        "- [ ] Colored pips counted",
        "- [ ] Land sources meet Karsten requirements",
        "- [ ] All lands have cited source files",
        "- [ ] Curve is supported (enough early sources for 1-2 drops)",
        "",
        "---",
        "",
        "# GATE 5: SIDEBOARD",
        "",
        "## Sideboard (15 cards)",
        "",
        "| Qty | Card Name | Mana | Source File | Set/Collector | Role / Target Matchup |",
        "|-----|-----------|------|------------|---------------|----------------------|",
        "| | | | | | |",
        "",
        "### Gate 5 Checklist",
        "",
        "- [ ] All 15 sideboard cards have cited source files",
        "- [ ] Covers: aggro, control, midrange, combo matchups",
        "- [ ] No card sourced from web or memory",
        "",
        "---",
        "",
        "# GATE 6: FINAL VALIDATION",
        "",
        "## Validation Command",
        "",
        "```bash",
        f"python {RepoPaths.SCRIPTS_DIR_NAME}/validate_decklist.py {RepoPaths.DECKS_DIR_NAME}/{deck_date}_{sanitize_folder_name(deck_name)}/decklist.txt --verbose",
        "```",
        "",
        "## Validation Output",
        "",
        "```",
        "(paste validation output here)",
        "```",
        "",
        "## Final Checklist",
        "",
        "- [ ] All needed card types were queried (Gate 1)",
        "- [ ] Strategy fully defined (Gate 2)",
        "- [ ] Synergy evaluation completed — thresholds met (Gate 2.5)",
        "- [ ] All 60 mainboard cards have a cited source file (Gate 3)",
        "- [ ] Mana base validated (Gate 4)",
        "- [ ] All 15 sideboard cards have a cited source file (Gate 5)",
        "- [ ] Zero cards sourced from web searches or memory",
        "- [ ] Set codes and collector numbers recorded",
        "- [ ] Validation script returned exit code 0",
        "",
        "---",
        "",
        "# OUTPUT FILES",
        "",
        "> When all gates are complete, copy the finalized content into these files:",
        "",
        "## → decklist.txt",
        "",
        "> Copy your final 60+15 list in MTGA format:",
        "",
        "```",
        "Deck",
        "4 Card Name (SET) Collector_Number",
        "...",
        "",
        "Sideboard",
        "3 Card Name (SET) Collector_Number",
        "...",
        "```",
        "",
        "## → analysis.md",
        "",
        "> Compile your gate work into the analysis.md template.",
        "> Required sections: Database Query Report, Executive Summary,",
        "> Synergy Evaluation, Card-by-Card Breakdown, Mana Base Analysis,",
        "> Curve Analysis, Matchup Table, Weaknesses, Playtesting Notes.",
        "",
        "## → sideboard_guide.md",
        "",
        "> Write boarding plans for each major matchup.",
        "",
        "---",
        "",
        f"_Generated by `{RepoPaths.SCRIPTS_DIR_NAME}/generate_deck_scaffold.py` on {deck_date}_",
        "",
    ]

    return "\n".join(lines)


def generate_decklist_template() -> str:
    return "\n".join([
        "Deck",
        "// Creatures",
        "",
        "// Instants",
        "",
        "// Sorceries",
        "",
        "// Enchantments",
        "",
        "// Artifacts",
        "",
        "// Planeswalkers",
        "",
        "// Lands",
        "",
        "",
        "Sideboard",
        "",
    ])


# Canonical WUBRG color order for normalization
_COLOR_ORDER = "WUBRG"
_COLOR_NAMES = {"W": "White", "U": "Blue", "B": "Black", "R": "Red", "G": "Green"}


def _normalize_colors(raw: str) -> str:
    """Uppercase, deduplicate, and sort into WUBRG canonical order."""
    seen = dict.fromkeys(c for c in raw.upper() if c in _COLOR_ORDER)
    return "".join(c for c in _COLOR_ORDER if c in seen)


def _valid_colors(raw: str) -> bool:
    """Return True if raw contains only valid color letters and at least one."""
    upper = raw.upper()
    return bool(upper) and all(c in _COLOR_ORDER for c in upper)


def run_interactive_wizard() -> argparse.Namespace:
    """Prompt the user for deck parameters interactively."""
    try:
        return _wizard_prompts()
    except KeyboardInterrupt:
        print("\n  Aborted.")
        raise SystemExit(0)


def _wizard_prompts() -> argparse.Namespace:
    print("=" * 60)
    print("  DECK SCAFFOLD GENERATOR — Interactive Wizard")
    print("=" * 60)
    print()

    # ── Step 1: Deck name ─────────────────────────────────────
    print("  Step 1 — Deck Name")
    name = input("  Name: ").strip()
    while not name:
        print("  (name is required)")
        name = input("  Name: ").strip()
    print()

    # ── Step 2: Colors ────────────────────────────────────────
    print("  Step 2 — Color Identity")
    print("  " + "  ".join(f"{k} {v}" for k, v in _COLOR_NAMES.items()))
    print("  Combine freely: W, WB, GU, WUR, WUBRG, etc.")
    print("  Colorless decks: enter C")
    raw_colors = input("  Colors: ").strip()
    while not raw_colors or (raw_colors.upper() != "C" and not _valid_colors(raw_colors)):
        print("  Invalid — use letters W U B R G only (e.g. WB, GU, WUBRG)")
        raw_colors = input("  Colors: ").strip()
    colors = "C" if raw_colors.upper() == "C" else _normalize_colors(raw_colors)
    print()

    # ── Step 3: Archetype ─────────────────────────────────────
    valid_archetypes = sorted(ARCHETYPE_QUERIES.keys())
    print("  Step 3 — Archetype")
    # Print in 2-column rows
    for i, a in enumerate(valid_archetypes, 1):
        end = "\n" if i % 4 == 0 or i == len(valid_archetypes) else ""
        print(f"  {i:2}. {a:<12}", end=end)
    if len(valid_archetypes) % 4 != 0:
        print()
    print()
    print("  Pick one or more (comma-separated numbers or names, e.g. 5,7 or lifegain,mill)")

    def _parse_archetype_input(raw: str) -> Optional[List[str]]:
        """Parse a multi-archetype input string. Returns list or None if invalid."""
        parts = [p.strip().lower() for p in raw.replace(" ", ",").split(",") if p.strip()]
        if not parts:
            return None
        resolved = []
        for p in parts:
            if p in valid_archetypes:
                resolved.append(p)
            elif p.isdigit() and 1 <= int(p) <= len(valid_archetypes):
                resolved.append(valid_archetypes[int(p) - 1])
            else:
                return None  # invalid token
        return list(dict.fromkeys(resolved))  # deduplicate, preserve order

    archetype_raw = input("  Choice(s): ").strip()
    archetypes: List[str] = []
    while True:
        result = _parse_archetype_input(archetype_raw)
        if result:
            archetypes = result
            break
        print(f"  Invalid — use numbers 1-{len(valid_archetypes)} or archetype names, comma-separated")
        archetype_raw = input("  Choice(s): ").strip()

    # For backwards compat, single archetype stored as string too
    archetype = ",".join(archetypes)
    print()

    # ── Step 4: Tribe (only if tribal) ───────────────────────
    tribes: List[str] = []
    if "tribal" in archetypes:
        print("  Step 4 — Creature Subtypes (Tribal selected)")
        print(f"  {len(ALL_CREATURE_TYPES)} types available. You may add multiple (e.g. Angel + Warrior).")
        print()

        def _pick_one_tribe() -> Optional[str]:
            while True:
                raw = input("  Search subtype: ").strip()
                if not raw:
                    return None
                exact = _CREATURE_TYPES_LOWER.get(raw.lower())
                if exact:
                    return exact
                matches = [t for t in ALL_CREATURE_TYPES if raw.lower() in t.lower()]
                if not matches:
                    print(f"  No types match '{raw}'. Try again (or Enter to stop adding).")
                elif len(matches) == 1:
                    return matches[0]
                elif len(matches) <= 10:
                    print(f"  Matches: {', '.join(matches)}")
                    print("  Type the full name to confirm, or refine your search.")
                else:
                    print(f"  {len(matches)} matches — too many to list. Refine your search.")

        while True:
            picked = _pick_one_tribe()
            if picked is None:
                if not tribes:
                    print("  (at least one subtype is required for tribal)")
                    continue
                break
            if picked in tribes:
                print(f"  '{picked}' already added.")
            else:
                tribes.append(picked)
                print(f"  Added: {picked}  |  Selected so far: {', '.join(tribes)}")
            more = input("  Add another subtype? [y/N]: ").strip().lower()
            if more not in ("y", "yes"):
                break
        print()

    tribe = tribes if tribes else None  # keep as list or None

    # ── Step 5: Extra tags (optional) ────────────────────────
    print("  Step 5 — Extra Search Tags (optional)")
    print("  Available tags: lifegain, removal, draw, counter, ramp, haste,")
    print("                  flying, trample, mill, wipe, pump, bounce, etb,")
    print("                  tutor, flash, tribal, protection, deathtouch")
    extra_tags = input("  Tags (comma-separated, or Enter to skip): ").strip() or None
    print()

    # ── Step 6: Run queries? ──────────────────────────────────
    print("  Step 6 — Run Queries Now?")
    print("  Queries search your local card pool and embed results in the scaffold.")
    run_q = input("  Run queries? [Y/n]: ").strip().lower()
    skip_queries = run_q in ("n", "no")

    print("  Step 6b — Wildcard Mode  (optional)")
    if tribes:
        print("  Skip tribal --name filters so all archetype creatures appear in the pool.")
        print("  The tribe(s) will be noted in the session as an AI hint only.")
        wc = input("  Wildcard? [y/N]: ").strip().lower()
        wildcard = wc in ("y", "yes")
    else:
        wildcard = False
    print()
    print()

    # ── Step 7: Confirmation ──────────────────────────────────
    from datetime import date as _date
    preview_date = _date.today().isoformat()
    print("=" * 60)
    print("  SUMMARY")
    print(f"  Name:       {name}")
    print(f"  Colors:     {colors}")
    archetype_label = ", ".join(archetypes) if len(archetypes) > 1 else archetype
    tribe_label = " / ".join(tribes) + " Tribal" if tribes else ""
    print(f"  Archetype:  {archetype_label}" + (f" ({tribe_label})" if tribe_label else ""))
    print(f"  Extra tags: {extra_tags or 'none'}")
    print(f"  Run queries: {'no (offline template)' if skip_queries else 'yes'}")
    print(f"  Output:     Decks/{preview_date}_{sanitize_folder_name(name)}/")
    print("=" * 60)
    confirm = input("  Confirm? [Y/n]: ").strip().lower()
    if confirm in ("n", "no"):
        print("  Aborted.")
        raise SystemExit(0)
    print()

    return argparse.Namespace(
        name=name,
        colors=colors,
        archetype=archetypes,
        tribe=tribe,
        date=None,
        output_dir=None,
        extra_tags=extra_tags,
        skip_queries=skip_queries,
        interactive=True,
    )


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Generate a deck-building session scaffold with embedded query results.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument("--name", default=None, help="Deck name (e.g. 'Orzhov Lifegain')")
    p.add_argument("--colors", default=None, help="Color identity (e.g. WB, GU, WUR)")
    p.add_argument(
        "--archetype", default=None,
        nargs="+",
        choices=sorted(ARCHETYPE_QUERIES.keys()),
        metavar="ARCHETYPE",
        help=f"Deck archetype(s), one or more of: {', '.join(sorted(ARCHETYPE_QUERIES.keys()))}",
    )
    p.add_argument("--interactive", "-i", action="store_true", help="Launch interactive wizard mode")
    p.add_argument(
        "--tribe",
        nargs="+",
        metavar="SUBTYPE",
        help=f"Creature subtype(s) for tribal — one or more of the {len(ALL_CREATURE_TYPES)} official MTG types (e.g. --tribe Angel Warrior)",
    )
    p.add_argument("--date", help="Date override (YYYY-MM-DD, default: today)")
    p.add_argument("--output-dir", help="Output directory (default: Decks/)")
    p.add_argument("--extra-tags", help="Additional search tags, comma-separated")
    p.add_argument(
        "--skip-queries", action="store_true",
        help="Generate scaffold without running queries (offline template)",
    )
    p.add_argument(
        "--focus-cards", nargs="+", metavar="CARD",
        help="Specific card names to guarantee in the candidate pool (one per arg or comma-separated)",
    )
    p.add_argument(
        "--wildcard", action="store_true",
        help="Suppress tribal --name creature queries — tribe becomes an AI hint at Gate 3 only, not a pool filter. Use when you want the full archetype pool with tribal preference, not tribal-only creatures.",
    )
    return p


def _query_label(q) -> str:
    """Extract a label from a query object (dict or list format)."""
    if isinstance(q, dict):
        return q["label"]
    return " ".join(str(x) for x in q[:4])


def _query_args(q):
    """Extract args from a query object (dict or list format).

    Returns a string for dict-format, a list for list-format.
    """
    if isinstance(q, dict):
        return q["args"]
    return q


def main() -> None:
    from mtg_utils import RepoPaths

    args = build_parser().parse_args()

    # Launch interactive wizard if no core args provided, or if --interactive flag set
    if args.interactive or not any([args.name, args.colors, args.archetype]):
        args = run_interactive_wizard()
    else:
        # Validate required args for non-interactive mode
        missing = [f"--{f}" for f, v in [("name", args.name), ("colors", args.colors), ("archetype", args.archetype)] if not v]
        if missing:
            build_parser().error(f"the following arguments are required: {', '.join(missing)}")
        # Normalize: always store archetype as a list internally
        if isinstance(args.archetype, str):
            args.archetype = [args.archetype]

    paths = RepoPaths()
    repo_root = paths.root

    # Validate card database exists
    if not paths.cards_dir.exists() and not args.skip_queries:
        print(f"ERROR: {RepoPaths.CARDS_DIR_NAME}/ not found.", file=sys.stderr)
        print(f"Run 'python {RepoPaths.SCRIPTS_DIR_NAME}/fetch_and_categorize_cards.py' first.", file=sys.stderr)
        sys.exit(2)

    deck_date = args.date or date.today().isoformat()
    folder_name = f"{deck_date}_{sanitize_folder_name(args.name)}"
    output_base = Path(args.output_dir) if args.output_dir else paths.decks_dir
    deck_dir = output_base / folder_name

    # Create folder
    deck_dir.mkdir(parents=True, exist_ok=True)

    print(f"{'='*70}")
    print(f"  DECK SCAFFOLD GENERATOR")
    print(f"  Name:      {args.name}")
    print(f"  Colors:    {args.colors.upper()}")
    archetype_list = args.archetype if isinstance(args.archetype, list) else [args.archetype]
    wildcard_active = getattr(args, "wildcard", False)
    print(f"  Archetype: {', '.join(archetype_list)}")
    if args.tribe:
        tribe_str = " / ".join(args.tribe) if isinstance(args.tribe, list) else args.tribe
        if wildcard_active:
            print(f"  Tribe:     {tribe_str}  [WILDCARD — hint only, --name filter suppressed]")
        else:
            print(f"  Tribe:     {tribe_str}")
    print(f"  Output:    {deck_dir}/")
    print(f"{'='*70}\n")

    # Build merged query plan from all chosen archetypes (deduplicate by label)
    archetype_list = args.archetype if isinstance(args.archetype, list) else [args.archetype]
    seen_labels: dict = {}
    for arch in archetype_list:
        for q in ARCHETYPE_QUERIES.get(arch, []):
            lbl = _query_label(q)
            if lbl not in seen_labels:
                seen_labels[lbl] = q
    # Always put Lands last
    lands = seen_labels.pop("Lands", None)
    query_plan = list(seen_labels.values())

    # For tribal builds, add one supplemental creature query per tribe by name.
    # These are ADDITIVE — they run alongside the archetype's existing creature
    # queries so non-tribal creatures (Changelings, support creatures) still
    # appear in the pool. The generic "Tribal creatures (by subtype)" placeholder
    # query is removed since per-tribe queries cover it more precisely.
    tribe_arg = getattr(args, "tribe", None)
    if tribe_arg:
        tribe_list = tribe_arg if isinstance(tribe_arg, list) else [tribe_arg]
        # Remove the generic placeholder (if present) — replaced by per-tribe below
        query_plan = [q for q in query_plan if _query_label(q) != "Tribal creatures (by subtype)"]
        # Insert per-tribe name queries at the front, one per tribe.
        # Marked with is_tribe_query so --wildcard can suppress them.
        for t in reversed(tribe_list):
            query_plan.insert(0, {
                "label": f"{t} creatures",
                "args": f"--type creature --subtype \"{t}\"",
                "is_tribe_query": True,
            })

    if lands:
        query_plan.append(lands)
    query_results: List[Dict] = []

    # Inject extra-tags as ONE supplemental query (not merged into every query)
    extra_tags = getattr(args, "extra_tags", None)
    if extra_tags:
        # Insert before Lands so it appears near the end
        insert_pos = len(query_plan) - 1 if lands else len(query_plan)
        query_plan.insert(insert_pos, {
            "label": f"Extra tags: {extra_tags}",
            "args": f"--tags {extra_tags}",
        })

    # Inject focus-card queries (guarantee specific cards appear in pool)
    focus_cards = getattr(args, "focus_cards", None)
    if focus_cards:
        # Flatten any comma-separated values passed as single args
        flat: List[str] = []
        for item in focus_cards:
            flat.extend(c.strip() for c in item.split(",") if c.strip())
        for card_name in flat:
            query_plan.append({
                "label": f"Focus card: {card_name}",
                "args": f"--name \"{card_name}\"",
            })

    if args.skip_queries:
        print("  --skip-queries: Generating template without query results.\n")
        for q in query_plan:
            label = _query_label(q)
            q_args = _query_args(q)
            args_display = q_args if isinstance(q_args, str) else " ".join(q_args)
            query_results.append({
                "label": label,
                "command": f"python {RepoPaths.SCRIPTS_DIR_NAME}/search_cards.py {args_display} --show-tags",
                "output": "(run this query and paste results here)",
                "count": "?",
            })
    else:
        total_candidates = 0
        for i, q in enumerate(query_plan, 1):
            label = _query_label(q)
            print(f"  [{i}/{len(query_plan)}] {label}...")

            wildcard_active = getattr(args, "wildcard", False)
            is_tribe = q.get("is_tribe_query", False) if isinstance(q, dict) else False
            if wildcard_active and is_tribe:
                print(f"         -> skipped (wildcard mode)")
                query_results.append({
                    "label": label,
                    "command": f"# skipped — wildcard mode active",
                    "output": "(skipped — wildcard mode: tribe label used as AI hint only, not as a pool filter)",
                    "count": 0,
                })
                continue
            cmd, output, count = run_query(
                repo_root,
                _query_args(q),
                args.colors.upper(),
                tribe=args.tribe,
            )

            query_results.append({
                "label": label,
                "command": cmd,
                "output": output,
                "count": count,
            })
            total_candidates += count
            print(f"         -> {count} candidates")

        print(f"\n  Total candidates across all queries: {total_candidates}")

    # Build consolidated, deduplicated candidate pool
    import csv as _csv
    import io as _io

    POOL_COLUMNS = ["name", "mana_cost", "cmc", "type_line", "colors", "rarity",
                    "keywords", "oracle_text", "tags", "pool"]
    ORACLE_MAX = 150  # truncate oracle text to keep session.md manageable

    seen_cards: Dict[str, Dict] = {}  # name -> row dict
    for i, qr in enumerate(query_results, 1):
        output = qr.get("output", "")
        if not output or output.startswith("("):
            continue
        reader = _csv.DictReader(_io.StringIO(output))
        pool_label = qr["label"]
        for row in reader:
            card_name = row.get("name", "").strip()
            if not card_name:
                continue
            if card_name in seen_cards:
                # Append this pool label
                existing_pools = seen_cards[card_name]["pool"]
                if pool_label not in existing_pools:
                    seen_cards[card_name]["pool"] += f" | {pool_label}"
            else:
                oracle = row.get("oracle_text", "")
                if len(oracle) > ORACLE_MAX:
                    oracle = oracle[:ORACLE_MAX] + "..."
                seen_cards[card_name] = {
                    "name": card_name,
                    "mana_cost": row.get("mana_cost", ""),
                    "cmc": row.get("cmc", ""),
                    "type_line": row.get("type_line", ""),
                    "colors": row.get("colors", ""),
                    "rarity": row.get("rarity", ""),
                    "keywords": row.get("keywords", ""),
                    "oracle_text": oracle,
                    "tags": row.get("_tags", row.get("tags", "")),
                    "pool": pool_label,
                }

    # Write consolidated CSV file
    consolidated_rows = list(seen_cards.values())
    consolidated_buf = _io.StringIO()
    writer = _csv.DictWriter(consolidated_buf, fieldnames=POOL_COLUMNS,
                             extrasaction="ignore")
    writer.writeheader()
    writer.writerows(consolidated_rows)
    consolidated_csv = consolidated_buf.getvalue()

    consolidated_path = deck_dir / "candidate_pool.csv"
    consolidated_path.write_text(consolidated_csv, encoding="utf-8")
    print(f"  [OK] candidate_pool.csv written ({len(consolidated_rows):,} unique cards, {len(consolidated_csv):,} bytes)")

    session_content = generate_session_file(
        deck_date=deck_date,
        deck_name=args.name,
        colors=args.colors.upper(),
        archetype=", ".join(archetype_list),
        query_results=query_results,
        tribe=args.tribe,
        consolidated_csv=consolidated_csv,
        unique_card_count=len(consolidated_rows),
    )

    # Write files
    session_path = deck_dir / "session.md"
    session_path.write_text(session_content, encoding="utf-8")
    print(f"\n  [OK] session.md written ({len(session_content):,} bytes)")

    decklist_path = deck_dir / "decklist.txt"
    if not decklist_path.exists():
        decklist_path.write_text(generate_decklist_template(), encoding="utf-8")
        print(f"  [OK] decklist.txt template created")

    # Copy analysis template if it exists
    analysis_template = paths.templates / "analysis.md"
    analysis_path = deck_dir / "analysis.md"
    if not analysis_path.exists():
        if analysis_template.exists():
            analysis_path.write_text(
                analysis_template.read_text(encoding="utf-8"), encoding="utf-8"
            )
        else:
            analysis_path.write_text("# Deck Analysis\n\n(fill in after completing all gates)\n", encoding="utf-8")
        print(f"  [OK] analysis.md template created")

    sb_template = paths.templates / "sideboard_guide.md"
    sb_path = deck_dir / "sideboard_guide.md"
    if not sb_path.exists():
        if sb_template.exists():
            sb_path.write_text(
                sb_template.read_text(encoding="utf-8"), encoding="utf-8"
            )
        else:
            sb_path.write_text("# Sideboard Guide\n\n(fill in after completing Gate 5)\n", encoding="utf-8")
        print(f"  [OK] sideboard_guide.md template created")

    # Display paths — use relative if inside repo, absolute otherwise
    try:
        display_session = session_path.relative_to(repo_root)
        display_decklist = decklist_path.relative_to(repo_root)
    except ValueError:
        display_session = session_path
        display_decklist = decklist_path

    print(f"\n{'='*70}")
    print(f"  SCAFFOLD COMPLETE")
    print(f"")
    print(f"  Next steps:")
    print(f"  1. Feed session.md + candidate_pool.csv to your AI tool as context")
    print(f"  2. Work through Gates 1–6 inside session.md")
    print(f"  3. Run: python {RepoPaths.SCRIPTS_DIR_NAME}/validate_decklist.py {display_decklist}")
    print(f"  4. Copy final outputs into decklist.txt, analysis.md, sideboard_guide.md")
    print(f"{'='*70}")


if __name__ == "__main__":
    main()
