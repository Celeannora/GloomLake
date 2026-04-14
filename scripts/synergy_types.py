"""
Synergy Types — shared constants, enums, and data classes for the synergy
analysis system.

This module is the single source of truth for every type, constant, and
configuration value used across the synergy analysis pipeline:

    synergy_types.py   ← YOU ARE HERE (enums, dataclasses, constants)
    synergy_profile.py ← profile builder (compute_synergy_profile)
    synergy_scoring.py ← pairwise scoring engine
    synergy_report.py  ← threshold checks & markdown output

All other synergy modules import from here; this file has **no** intra-project
imports and produces **no** side effects on import.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Set, Tuple

__all__ = [
    # Enums
    "InteractionType",
    "CardRole",
    "ThresholdStatus",
    # Weight mapping
    "INTERACTION_WEIGHTS",
    # Data classes
    "Interaction",
    "SynergyProfile",
    "CardScore",
    "CompositeWeights",
    "ThresholdConfig",
    "ThresholdResult",
    # Interaction rules & role constants
    "INTERACTION_RULES",
    "ROLE_TAGS",
    "ORACLE_KEYWORDS",
    "DEP_PATTERNS",
    "INTERACTION_TAGS",
    "SUPPORT_TAGS",
    "CORE_ENGINE_TAGS",
    "PAYOFF_BRIDGE_PATTERNS",
    # Directional oracle-text patterns
    "DIRECTIONAL_PATTERNS",
    # Preset threshold configs
    "DECK_THRESHOLDS",
    "POOL_THRESHOLDS",
]


# ═══════════════════════════════════════════════════════════════════════════════
# Enums
# ═══════════════════════════════════════════════════════════════════════════════

class InteractionType(Enum):
    """Type of directional interaction between two cards."""
    FEEDS = "FEEDS"
    TRIGGERS = "TRIGGERS"
    ENABLES = "ENABLES"
    AMPLIFIES = "AMPLIFIES"
    PROTECTS = "PROTECTS"
    REDUNDANT = "REDUNDANT"


class CardRole(Enum):
    """Functional role a card plays in a synergy web."""
    ENGINE = "engine"
    ENABLER = "enabler"
    PAYOFF = "payoff"
    SUPPORT = "support"
    INTERACTION = "interaction"


class ThresholdStatus(Enum):
    """Result status for a single threshold check."""
    PASS = "PASS"
    FAIL = "FAIL"
    WARN = "WARN"
    INFO = "INFO"


# ═══════════════════════════════════════════════════════════════════════════════
# Interaction weight mapping
# ═══════════════════════════════════════════════════════════════════════════════

INTERACTION_WEIGHTS: Dict[InteractionType, float] = {
    InteractionType.FEEDS: 2.0,
    InteractionType.TRIGGERS: 2.0,
    InteractionType.ENABLES: 2.0,
    InteractionType.AMPLIFIES: 1.5,
    InteractionType.PROTECTS: 1.0,
    InteractionType.REDUNDANT: 0.0,
}


# ═══════════════════════════════════════════════════════════════════════════════
# Data classes
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class Interaction:
    """A single detected interaction between two cards."""
    partner: str
    itype: InteractionType
    note: str
    confidence: str  # "oracle", "tag", "inferred"


@dataclass
class SynergyProfile:
    """Rich synergy profile for a single card.

    Replaces the plain dict returned by ``compute_synergy_profile`` in
    search_cards.py.
    """
    name: str
    broad_tags: frozenset
    source_tags: frozenset
    payoff_tags: frozenset
    subtypes: frozenset
    keywords: frozenset
    cmc: float
    type_line: str
    oracle_text: str
    is_land: bool
    mana_cost: str = ""
    colors: str = ""


@dataclass
class CardScore:
    """Per-card scoring record used during synergy analysis.

    Replaces the 15-key dict built in ``synergy_analysis.py`` (line ~414).
    """
    profile: SynergyProfile
    qty: int = 1
    section: str = "pool"
    role: CardRole = CardRole.SUPPORT
    synergy_partners: Set[str] = field(default_factory=set)
    engine_partners: Set[str] = field(default_factory=set)
    support_partners: Set[str] = field(default_factory=set)
    role_breadth_types: Set[str] = field(default_factory=set)
    dependency: int = 0
    interactions: List[Interaction] = field(default_factory=list)
    redundant_with: List[str] = field(default_factory=list)
    weighted_synergy: float = 0.0
    engine_synergy: float = 0.0
    # Pool-size context (set after scoring)
    _pool_size: int = 0
    _engine_pool_size: int = 0

    # ── Computed properties ──────────────────────────────────────────────

    @property
    def synergy_count(self) -> int:
        """Number of unique synergy partners."""
        return len(self.synergy_partners)

    @property
    def synergy_density(self) -> float:
        """Fraction of the pool this card synergises with."""
        return self.synergy_count / max(self._pool_size - 1, 1)

    @property
    def engine_synergy_count(self) -> int:
        """Number of unique engine-cluster partners."""
        return len(self.engine_partners)

    @property
    def engine_density(self) -> float:
        """Density within the engine cluster (engine/enabler/payoff only)."""
        if self.role in (CardRole.ENGINE, CardRole.ENABLER, CardRole.PAYOFF):
            return self.engine_synergy_count / max(self._engine_pool_size - 1, 1)
        return 0.0

    @property
    def role_breadth(self) -> int:
        """Number of distinct interaction types this card participates in."""
        return len(self.role_breadth_types)

    @property
    def oracle_interactions(self) -> List[Interaction]:
        """Interactions confirmed by oracle-text cross-reference."""
        return [i for i in self.interactions if i.confidence == "oracle"]

    @property
    def composite_score(self) -> float:
        """Density-first composite score (default weights)."""
        return (
            self.engine_density * _DEFAULT_WEIGHTS.engine_density
            + self.synergy_density * _DEFAULT_WEIGHTS.synergy_density
            + min(self.weighted_synergy, _DEFAULT_WEIGHTS.raw_interactions_cap)
            + self.role_breadth * _DEFAULT_WEIGHTS.role_breadth
            + len(self.oracle_interactions) * _DEFAULT_WEIGHTS.oracle_confirmed
        )

    def composite_score_with(self, weights: CompositeWeights) -> float:
        """Composite score using caller-supplied weights."""
        return (
            self.engine_density * weights.engine_density
            + self.synergy_density * weights.synergy_density
            + min(self.weighted_synergy, weights.raw_interactions_cap)
            + self.role_breadth * weights.role_breadth
            + len(self.oracle_interactions) * weights.oracle_confirmed
        )


@dataclass
class CompositeWeights:
    """Configurable weights for the density-first composite score."""
    engine_density: float = 40.0
    synergy_density: float = 25.0
    raw_interactions_cap: float = 20.0
    role_breadth: float = 3.0
    oracle_confirmed: float = 2.0


# Module-level default weights instance (used by CardScore.composite_score)
_DEFAULT_WEIGHTS = CompositeWeights()


@dataclass
class ThresholdConfig:
    """Gate 2.5 threshold configuration for pool-vs-deck calibration."""
    min_avg_density: float
    min_engine_avg_density: float
    max_isolated_frac: float
    max_true_isolated_engine: int
    min_hub_density: float
    min_hub_count: int
    max_support_ratio: float
    mode_label: str


@dataclass
class ThresholdResult:
    """Structured result for a single threshold check."""
    id: str
    status: ThresholdStatus
    label: str
    actual: float
    required: float
    detail: str


# ═══════════════════════════════════════════════════════════════════════════════
# Constants — extracted from synergy_analysis.py
# ═══════════════════════════════════════════════════════════════════════════════

# ─── Directional interaction rules ───────────────────────────────────────────
# Each tuple: (field_a, val_a, field_b, val_b, InteractionType, note_template)
INTERACTION_RULES: List[Tuple[str, str, str, str, InteractionType, str]] = [
    # ── FEEDS ────────────────────────────────────────────────────────────────
    ("source_tags", "lifegain",    "payoff_tags", "lifegain",    InteractionType.FEEDS,    "{a} produces life gain → {b} has a life-gain trigger"),
    ("source_tags", "token",       "payoff_tags", "token",       InteractionType.FEEDS,    "{a} creates tokens → {b} benefits from token creation"),
    ("source_tags", "draw",        "payoff_tags", "draw",        InteractionType.FEEDS,    "{a} draws cards → {b} rewards card draw"),
    ("source_tags", "etb",         "payoff_tags", "etb",         InteractionType.FEEDS,    "{a} has ETB → {b} reacts to creatures entering"),
    ("source_tags", "pump",        "payoff_tags", "pump",        InteractionType.FEEDS,    "{a} places counters → {b} scales with counters"),
    ("source_tags", "discard",     "payoff_tags", "discard",     InteractionType.FEEDS,    "{a} forces discard → {b} benefits from discard"),
    ("source_tags", "mill",        "payoff_tags", "mill",        InteractionType.FEEDS,    "{a} mills cards → {b} benefits from graveyard"),
    ("source_tags", "token",       "broad_tags",  "pump",        InteractionType.FEEDS,    "{a} creates tokens → {b} pumps the team"),
    ("source_tags", "lifegain",    "broad_tags",  "draw",        InteractionType.FEEDS,    "{a} gains life → {b} draws on life gain"),
    ("broad_tags",  "discard",     "broad_tags",  "reanimation", InteractionType.FEEDS,    "{a} fills graveyard → {b} reanimates from it"),
    ("source_tags", "etb",         "broad_tags",  "bounce",      InteractionType.FEEDS,    "{a} has ETB value → {b} bounces to replay ETB"),
    # ── TRIGGERS ─────────────────────────────────────────────────────────────
    ("source_tags", "token",       "payoff_tags", "token",       InteractionType.TRIGGERS, "{a} creates tokens → {b}'s token-creation trigger fires"),
    # ── ENABLES ──────────────────────────────────────────────────────────────
    ("broad_tags",  "ramp",        "broad_tags",  "wipe",        InteractionType.ENABLES,  "{a} ramps mana → {b} expensive wipe becomes castable"),
    ("broad_tags",  "ramp",        "broad_tags",  "reanimation", InteractionType.ENABLES,  "{a} ramps mana → {b} reanimation spell becomes castable"),
    ("broad_tags",  "ramp",        "broad_tags",  "pump",        InteractionType.ENABLES,  "{a} produces mana → {b} activated pump ability"),
    ("broad_tags",  "protection",  "broad_tags",  "tribal",      InteractionType.ENABLES,  "{a} protects key piece → {b} tribal engine survives"),
    ("broad_tags",  "tutor",       "broad_tags",  "draw",        InteractionType.ENABLES,  "{a} tutors → {b} draw engine found reliably"),
    ("broad_tags",  "protection",  "source_tags", "lifegain",    InteractionType.ENABLES,  "{a} protects → {b} lifegain engine survives removal"),
    # ── AMPLIFIES ────────────────────────────────────────────────────────────
    ("source_tags", "token",       "broad_tags",  "wipe",        InteractionType.AMPLIFIES, "Tokens → sacrifice synergy: {a} creates fodder for {b}"),
    ("broad_tags",  "pump",        "broad_tags",  "tribal",      InteractionType.AMPLIFIES, "Tribal anthem: {a} pump stacks with {b} tribal bonus"),
    ("source_tags", "pump",        "source_tags", "pump",        InteractionType.AMPLIFIES, "{a} + {b} both add counters — outputs stack"),
    # ── PROTECTS ─────────────────────────────────────────────────────────────
    ("broad_tags",  "protection",  "broad_tags",  "removal",     InteractionType.PROTECTS, "{a} protects key creatures → {b} removal suite operates safely"),
    ("broad_tags",  "counter",     "broad_tags",  "protection",  InteractionType.PROTECTS, "{a} counters removal → {b} protected threat survives"),
    ("broad_tags",  "bounce",      "broad_tags",  "counter",     InteractionType.PROTECTS, "{a} bounces threats → {b} backup counter coverage"),
    # ── SACRIFICE / ARISTOCRATS ──────────────────────────────────────────────
    ("source_tags", "sacrifice",   "payoff_tags", "sacrifice",   InteractionType.FEEDS,    "{a} provides sac outlet → {b} fires death trigger"),
    ("source_tags", "token",       "payoff_tags", "sacrifice",   InteractionType.FEEDS,    "{a} makes tokens → {b} sacrifice outlet has fuel"),
    ("broad_tags",  "sacrifice",   "broad_tags",  "lifegain",    InteractionType.TRIGGERS, "{a} death triggers → {b} life gain on creature death"),
    ("broad_tags",  "sacrifice",   "broad_tags",  "draw",        InteractionType.TRIGGERS, "{a} sacrifice or death → {b} card draw on death"),
    # ── ENERGY ───────────────────────────────────────────────────────────────
    ("source_tags", "energy",      "payoff_tags", "energy",      InteractionType.FEEDS,    "{a} produces energy → {b} spends energy counters"),
    ("source_tags", "energy",      "broad_tags",  "pump",        InteractionType.FEEDS,    "{a} produces energy → {b} activated pump uses energy"),
    # ── STORM / SPELL COUNT ──────────────────────────────────────────────────
    ("source_tags", "storm_count", "payoff_tags", "storm_count", InteractionType.AMPLIFIES, "{a} generates/extends spell chain → {b} scales with spell count"),
    ("broad_tags",  "ramp",        "source_tags", "storm_count", InteractionType.ENABLES,  "{a} ritual/ramp → {b} storm chain becomes viable"),
    # ── ENCHANTRESS ──────────────────────────────────────────────────────────
    ("source_tags", "enchantress", "payoff_tags", "enchantress", InteractionType.TRIGGERS, "{a} is an enchantment → {b} enchantment-cast draw trigger fires"),
    ("broad_tags",  "tutor",       "source_tags", "enchantress", InteractionType.ENABLES,  "{a} tutors enchantments → {b} enchantress engine found reliably"),
    # ── BLINK / ETB ABUSE ────────────────────────────────────────────────────
    ("source_tags", "blink",       "payoff_tags", "etb",         InteractionType.AMPLIFIES, "{a} blinks → {b} ETB fires again on re-entry"),
    ("source_tags", "blink",       "broad_tags",  "etb",         InteractionType.AMPLIFIES, "{a} blinks → {b} ETB fires repeatedly"),
    ("broad_tags",  "bounce",      "payoff_tags", "etb",         InteractionType.FEEDS,    "{a} bounces → {b} ETB replays on recast"),
]

# ─── Role classification constants ───────────────────────────────────────────
ROLE_TAGS: Set[str] = {"wipe", "counter", "tutor", "reanimation", "removal", "draw", "bounce"}

ORACLE_KEYWORDS: Set[str] = {
    "flying", "lifelink", "deathtouch", "first strike", "double strike",
    "vigilance", "trample", "haste", "menace", "reach", "indestructible",
}

DEP_PATTERNS: List[Tuple[str, int, str]] = [
    (r"\benchant\b",                                           1, "Aura — needs enchantment target"),
    (r"\bequip\b",                                             1, "Equipment — needs a creature to equip"),
    (r"\bfortify\b",                                           1, "Fortification — needs a land"),
    (r"sacrifice another",                                     1, "Needs another permanent to sacrifice"),
    (r"sacrifice a (creature|permanent)",                      1, "Needs a creature to sacrifice"),
    (r"tap another .{0,20}you control",                       1, "Needs another tapped permanent"),
    (r"if you control (a|an)\b",                              1, "Conditional on board presence"),
    (r"if you have \d+ or more life",                         1, "Conditional on life total"),
    (r"(target|another) creature you control",                 1, "Needs a creature target you control"),
    (r"whenever .{0,30} you control .{0,30}(attacks|blocks)", 1, "Needs attacking/blocking creatures"),
    (r"activated ability of .{0,30} you control",             1, "Needs specific activated ability"),
    (r"for each other .{0,20}you control",                    1, "Scales with other permanents"),
]

INTERACTION_TAGS: Set[str] = {"removal", "counter", "wipe", "bounce", "protection"}
SUPPORT_TAGS: Set[str] = {"draw", "scry", "ramp", "tutor", "loot"}
CORE_ENGINE_TAGS: Set[str] = {
    "lifegain", "token", "sacrifice", "etb", "mill", "discard",
    "energy", "enchantress", "pump", "drain",
}

# ─── Oracle payoff bridge patterns ───────────────────────────────────────────
# Each tuple: (regex_pattern, mechanic_tag, bridge_label)
PAYOFF_BRIDGE_PATTERNS: List[Tuple[str, str, str]] = [
    (r"whenever you gain life.*each opponent loses",              "lifegain", "drain-payoff"),
    (r"target opponent loses x life.*amount of life you gained", "lifegain", "burst-payoff"),
    (r"whenever you gain life.*put.*counter",                    "lifegain", "counter-payoff"),
    (r"whenever you gain life.*draw",                            "lifegain", "draw-payoff"),
    (r"create a food token",                                     "lifegain", "food-enabler"),
    (r"sacrifice.*food.*gain",                                   "lifegain", "food-sac-gain"),
    (r"whenever .{0,30} attacks.*you gain \d+ life",             "lifegain", "attack-lifegain"),
    (r"whenever a (creature|bat|vampire|cleric) .{0,20}you control (enters|attacks|dies).*gain",
                                                                 "lifegain", "tribe-lifegain"),
]


# ═══════════════════════════════════════════════════════════════════════════════
# Directional oracle-text patterns — extracted from search_cards.py
# ═══════════════════════════════════════════════════════════════════════════════
# mechanic → {source: [...], payoff: [...]}
# source = card PRODUCES this resource
# payoff = card REACTS TO / CONSUMES this resource

DIRECTIONAL_PATTERNS: Dict[str, Dict[str, List[str]]] = {
    "lifegain": {
        "source": [
            r"lifelink",
            r"you gain \d+ life",
            r"gains? \d+ life",
            r"gain life equal",
            r"you may gain \d+ life",
        ],
        "payoff": [
            r"whenever you gain life",
            r"each time you gain life",
            r"whenever (a player |you |)gains? life",
            r"if you (have |)gained life",
            r"for each (1 |one )?life you (gained|gain)",
        ],
    },
    "token": {
        "source": [
            r"create[sd]? [a\d]",
            r"put[s]? .{0,20}token",
            r"creates? \d+ token",
            r"creates? a .{0,20}token",
        ],
        "payoff": [
            r"whenever (a |another |you create a? )token",
            r"for each token",
            r"tokens (you control |)get",
            r"whenever you create",
        ],
    },
    "draw": {
        "source": [
            r"draw[s]? (a|[2-9]|\d+) card",
            r"draw cards? equal",
            r"you may draw",
        ],
        "payoff": [
            r"whenever you draw",
            r"each time you draw",
            r"if you (have |)drawn",
            r"for each card (drawn|you draw)",
        ],
    },
    "etb": {
        "source": [
            r"when .{0,40} enters(?: the battlefield)?",
        ],
        "payoff": [
            r"whenever (a |another )creature enters",
            r"whenever .{0,30} enters the battlefield under your control",
            r"each time a creature enters",
        ],
    },
    "pump": {
        "source": [
            r"put[s]? [a\d].{0,10}\+1/\+1 counter",
            r"put[s]? [a\d].{0,10}\+\d/\+\d counter",
            r"gets? \+\d/\+\d until",
        ],
        "payoff": [
            r"for each \+1/\+1 counter",
            r"whenever .{0,20}\+1/\+1 counter (is )?placed",
            r"number of \+1/\+1 counter",
            r"with .{0,10}\+1/\+1 counter",
        ],
    },
    "discard": {
        "source": [
            r"discard[s]? (a|[2-9]|\d+) card",
            r"each player discards",
            r"target player discards",
        ],
        "payoff": [
            r"whenever (you |a player |an opponent )discards",
            r"for each card discarded",
        ],
    },
    "mill": {
        "source": [
            r"mill[s]? \d+",
            r"put[s]? .{0,10}top .{0,10}of .{0,20}library .{0,10}graveyard",
        ],
        "payoff": [
            r"whenever .{0,20}card .{0,20}put into .{0,20}graveyard from",
            r"for each card in (your |their |a )?graveyard",
            r"whenever a (creature |card )?card .{0,20}graveyard",
        ],
    },
    "sacrifice": {
        "source": [
            r"sacrifice (a|another|any number of) (creature|permanent|artifact|land)",
            r"\{[^}]+\}(?:,)? sacrifice (a|another)",
            r": sacrifice",
        ],
        "payoff": [
            r"whenever (a|another) creature (you control )?dies",
            r"whenever you sacrifice (a|another)",
            r"each creature that dies",
            r"whenever a creature dies",
        ],
    },
    "energy": {
        "source": [
            r"you get \{E",
            r"gets? \{E",
            r"opponent gets? \{E",
        ],
        "payoff": [
            r"pay \{E+\}",
            r"you have (\d+|at least) or more \{E",
            r"remove.*\{E.*from",
        ],
    },
    "storm_count": {
        "source": [
            r"copy (this spell|it) for each (other )?spell",
            r"\bstorm\b",
            r"cast (another|a second|an additional)",
            r"you may cast (it|a copy) without paying",
        ],
        "payoff": [
            r"for each (instant or sorcery|other spell|spell) (you've )?cast this turn",
            r"number of (instants?|sorceries|spells).*cast this turn",
            r"spells? you cast this turn",
        ],
    },
    "enchantress": {
        "source": [
            r"\btype\b.*enchantment",  # is an enchantment (type line check done separately)
            r"create.*enchantment token",
            r"enchant (creature|permanent|player|land)",
        ],
        "payoff": [
            r"whenever you cast an enchantment",
            r"whenever an enchantment enters",
            r"\bconstellation\b",
            r"for each enchantment you control",
        ],
    },
    "blink": {
        "source": [
            r"exile (target|another|it).{0,50}(then return|return it).{0,50}battlefield",
            r"\bflicker\b",
            r"phase out",
        ],
        "payoff": [
            r"whenever .{0,40} enters the battlefield",
            r"when .{0,40} enters the battlefield",
            r"\betb\b",
        ],
    },
}


# ═══════════════════════════════════════════════════════════════════════════════
# Preset threshold configurations
# ═══════════════════════════════════════════════════════════════════════════════

DECK_THRESHOLDS = ThresholdConfig(
    min_avg_density=0.25,
    min_engine_avg_density=0.40,
    max_isolated_frac=0.12,
    max_true_isolated_engine=2,
    min_hub_density=0.50,
    min_hub_count=2,
    max_support_ratio=0.45,
    mode_label="deck (role-aware)",
)

POOL_THRESHOLDS = ThresholdConfig(
    min_avg_density=0.20,
    min_engine_avg_density=0.30,
    max_isolated_frac=0.15,
    max_true_isolated_engine=3,
    min_hub_density=0.40,
    min_hub_count=2,
    max_support_ratio=0.55,
    mode_label="pool (loose)",
)
