#!/usr/bin/env python3
"""
Shared utilities for MTG deck-building scripts.

Provides
--------
RepoPaths       Centralised directory-name configuration (no hardcoded paths).
parse_decklist  MTGA-format decklist parser.
TAG_RULES       Single-source tag pattern list (regex-based, negation-aware).
KEYWORD_TAG_MAP Keyword → tag mapping for MTG keyword abilities.
compute_tags    Derive strategic tags from oracle_text + keywords strings.
CardBackend     Abstract base class for CSV / JSON / SQLite card-lookup backends.

Architecture notes
------------------
- TAG_RULES was previously duplicated between validate_decklist.py and
  search_cards.py.  It now lives here exclusively; both scripts import it.
- compute_tags uses compiled regex patterns with negation look-behind guards
  (e.g. "(?<!no )you gain") to avoid false positives on prevention clauses.
- CardBackend defines the lookup() / suggest() interface once; concrete
  subclasses in validate_decklist.py inherit from it.
"""

import re
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

__all__ = [
    "RepoPaths",
    "CARD_TYPES",
    "parse_decklist",
    "TAG_RULES",
    "KEYWORD_TAG_MAP",
    "compute_tags",
    "CardBackend",
]


# ---------------------------------------------------------------------------
# Centralised repo path configuration
# ---------------------------------------------------------------------------

class RepoPaths:
    """Single source of truth for every repo directory name.

    Usage::

        from mtg_utils import RepoPaths
        paths = RepoPaths()                      # auto-detect repo root
        paths = RepoPaths(root=some_path)         # explicit root

        paths.cards_dir   # .../cards_by_category
        paths.decks_dir   # .../Decks
        paths.local_db    # .../local_db
        paths.scripts_dir # .../scripts
        paths.templates   # .../.github/DECK_TEMPLATE
    """

    # ---- configurable directory names (change here, nowhere else) ---------
    CARDS_DIR_NAME      = "assets/data/cards_by_category"
    DECKS_DIR_NAME      = "Decks"
    LOCAL_DB_DIR_NAME   = "assets/data/local_db"
    SCRIPTS_DIR_NAME    = "scripts"
    TEMPLATES_DIR_NAME  = "assets/templates/template"

    def __init__(self, root: Path | None = None) -> None:
        if root is None:
            # Default: assume this file lives in <repo>/scripts/
            root = Path(__file__).resolve().parent.parent.parent
        self.root = root

    # ---- resolved absolute paths ------------------------------------------
    @property
    def cards_dir(self) -> Path:
        return self.root / self.CARDS_DIR_NAME

    @property
    def decks_dir(self) -> Path:
        return self.root / self.DECKS_DIR_NAME

    @property
    def local_db(self) -> Path:
        return self.root / self.LOCAL_DB_DIR_NAME

    @property
    def scripts_dir(self) -> Path:
        return self.root / self.SCRIPTS_DIR_NAME

    @property
    def templates(self) -> Path:
        return self.root / self.TEMPLATES_DIR_NAME


# ---------------------------------------------------------------------------
# Canonical card-type list (used by 6+ scripts — define once here)
# ---------------------------------------------------------------------------

CARD_TYPES = [
    'artifact', 'battle', 'creature', 'enchantment', 'instant',
    'land', 'other', 'planeswalker', 'sorcery',
]


# ---------------------------------------------------------------------------
# Decklist parser
# ---------------------------------------------------------------------------

def parse_decklist(
    decklist_path: Path,
) -> Tuple[List[Tuple[int, str]], List[Tuple[int, str]]]:
    """
    Parse an MTGA-format decklist.txt file.

    Returns:
        (mainboard, sideboard) where each is a list of (quantity, card_name).

    Handles::
        - Lines starting with '//' or '#' are treated as comments.
        - 'Deck' / 'deck' toggles mainboard section.
        - 'Sideboard' / 'sideboard' toggles sideboard section.
        - Set codes like '(OTJ) 042' are stripped from card names.
        - Blank lines are ignored.
    """
    mainboard: List[Tuple[int, str]] = []
    sideboard: List[Tuple[int, str]] = []
    current_section = 'main'

    with open(decklist_path, encoding='utf-8') as f:
        for raw_line in f:
            line = raw_line.strip()
            if not line or line.startswith('//') or line.startswith('#'):
                continue
            lower = line.lower()
            if lower == 'deck':
                current_section = 'main'
                continue
            if lower == 'sideboard':
                current_section = 'side'
                continue
            parts = line.split(None, 1)
            if len(parts) < 2:
                continue
            try:
                quantity = int(parts[0])
            except ValueError:
                continue
            rest = parts[1]
            card_name = rest.split('(')[0].strip() if '(' in rest else rest.strip()
            if not card_name:
                continue
            if current_section == 'main':
                mainboard.append((quantity, card_name))
            else:
                sideboard.append((quantity, card_name))

    return mainboard, sideboard


# ---------------------------------------------------------------------------
# Tag rules  (SINGLE SOURCE OF TRUTH — import from here, never redefine)
# ---------------------------------------------------------------------------
#
# Each entry is (tag_name, compiled_regex).
#
# Design notes
# ~~~~~~~~~~~~
# 1. Negation guards: prevention clauses like "you gain no life this turn" or
#    "can't gain life" must not fire the lifegain tag.  Negative look-behind
#    assertions handle this without slowing the common case.
#
# 2. Word boundaries: "add {" previously matched any activated ability that
#    produced mana, including situational abilities on non-ramp cards.  The
#    ramp pattern now anchors to the canonical mana-ability phrasing from
#    Scryfall oracle text.
#
# 3. ETB fix: Scryfall stores full card names in oracle text, not "~".
#    The old pattern "when ~ enters" matched nothing.  The new pattern matches
#    "when [CardName] enters" and "when it enters" and "when this enters".
#    The card-name wildcard is restricted to word characters + light punctuation
#    found in real card names (' , - ) to prevent cross-clause false matches
#    on multi-ability cards.  The open '.{0,40}?' from Stage 1 could span
#    clause boundaries; this tighter pattern cannot.
#
# 4. Confidence hint: patterns are ordered from most-specific to least-specific
#    within each tag so the first match is the highest-confidence one.

_TAG_RULES_RAW: List[Tuple[str, str]] = [
    # tag          regex pattern (applied to oracle_text.lower())
    ("lifegain",   r"(?<!no )(?<!can't )(?<!cannot )you gain \d|lifelink|(?<!no )(?<!can't )gain (?:\d+|x) life"),
    ("mill",       r"mill \d|mills \d|put the top \d|from the top of|into (?:their|your) graveyard from (?:their|your|a) library"),
    ("draw",       r"draw (?:a|two|three|four|x|that many) card"),
    ("removal",    r"exile target|destroy target|deals? (?:\d+|x) damage to target|deals? that much damage to"),
    ("counter",    r"counter target (?:spell|ability)|counter that spell"),
    ("ramp",       r"add (?:\{[WUBRGC]\}|mana of any|mana in any)|search your library for (?:a |up to (?:one|two) )(?:basic )?land"),
    ("token",      r"create (?:a|an|x|two|three|four|\d+) (?:\S+ )?(?:token|tokens)"),
    ("bounce",     r"return (?:target|up to \d|each) (?!card to your hand)"),
    ("discard",    r"discards? (?:a|two|that many) card|each opponent discards|target player discards"),
    ("tutor",      r"search your library for (?:a card|an instant|a sorcery|a creature|a land card)"),
    ("wipe",       r"destroy all|exile all|deals? (?:\d+|x) damage to (?:all|each) (?:creature|permanent)"),
    ("protection", r"hexproof|indestructible|ward \{"),
    ("pump",       r"\+1/\+1 counter|gets \+\d|\+x/\+x"),
    ("reanimation",r"return target (?:creature|permanent) card from (?:your|a) graveyard"),
    # ETB: restricted wildcard prevents cross-clause false matches on multi-ability cards.
    # Matches: "when this enters", "when it enters", "when [CardName] enters".
    # Card names contain word chars + limited punctuation (', ,, -, space).
    ("etb",        r"when (?:this|it|[\w][\w ,'\.\-]{0,40}?) enters(?: the battlefield)?"),
    ("tribal",     r"other [a-z]+ you control|[a-z]+s you control (?:get|have|gain)"),
    ("scry",       r"\bscry \d"),
    ("surveil",    r"\bsurveil \d"),
    ("sacrifice",  r"sacrifice (?:a|an|target|this|another|each)"),
    ("energy",     r"energy counter|\{e\}"),
    ("storm_count",r"storm count|number of spells cast (?:before|this turn)"),
    ("enchantress",r"whenever you cast an enchantment|whenever an enchantment enters"),
    ("blink",      r"exile (?:it|target (?:creature|permanent)), then return"),
]

# Compile all patterns once at import time
TAG_RULES: List[Tuple[str, re.Pattern]] = [
    (tag, re.compile(pattern, re.IGNORECASE))
    for tag, pattern in _TAG_RULES_RAW
]

KEYWORD_TAG_MAP: Dict[str, str] = {
    "flash":         "flash",
    "haste":         "haste",
    "trample":       "trample",
    "flying":        "flying",
    "deathtouch":    "deathtouch",
    "vigilance":     "vigilance",
    "reach":         "reach",
    "menace":        "menace",
    "lifelink":      "lifegain",
    "first strike":  "first_strike",
    "double strike": "double_strike",
}


def compute_tags(oracle_text: str, keywords: str) -> Set[str]:
    """Derive strategic tags from oracle_text and keywords strings.

    Uses compiled regex patterns with negation look-behind guards so that
    prevention clauses ("you gain no life", "can't gain life") do not
    incorrectly fire the lifegain tag.

    Parameters
    ----------
    oracle_text : str  Raw oracle text from Scryfall / local DB.
    keywords    : str  Semicolon- or comma-separated keyword list.

    Returns
    -------
    set of tag name strings.
    """
    tags: Set[str] = set()
    oracle = oracle_text.lower()
    kw_raw = keywords.lower()

    for tag, pattern in TAG_RULES:
        if pattern.search(oracle):
            tags.add(tag)

    for kw, tag in KEYWORD_TAG_MAP.items():
        if kw in kw_raw:
            tags.add(tag)

    return tags


# ---------------------------------------------------------------------------
# CardBackend abstract base class
# ---------------------------------------------------------------------------

class CardBackend(ABC):
    """Abstract interface for card-lookup backends.

    Concrete subclasses (CSVBackend, JSONBackend, SQLiteBackend) must implement
    lookup() and suggest().  Defining the interface here means a bug-fix in
    suggest() only needs to be applied once.

    Usage::

        backend: CardBackend = CSVBackend(repo_root)
        found, info = backend.lookup("Sheoldred, the Apocalypse")
        if not found:
            hints = backend.suggest("Sheoldred")
    """

    @abstractmethod
    def lookup(self, card_name: str) -> Tuple[bool, Optional[Dict]]:
        """Return (found, card_dict) for card_name (case-insensitive)."""
        ...

    @abstractmethod
    def suggest(self, card_name: str, n: int = 3) -> List[str]:
        """Return up to n close-match card names for a misspelled query."""
        ...
