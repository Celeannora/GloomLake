"""
Synergy Engine — core scoring logic for the MTG-Decks synergy analysis system.

This module contains all card-loading, profile-building, role-classification,
and pairwise-scoring logic extracted from the former monolithic
``synergy_analysis.py`` and ``search_cards.py``.

Architecture position::

    synergy_types.py   ← enums, dataclasses, constants
    synergy_engine.py  ← YOU ARE HERE (scoring engine)
    synergy_report.py  ← threshold checks & markdown output

Public API
----------
- ``load_cards_from_db``          — load card rows from the CSV database
- ``compute_synergy_profile``     — build a rich SynergyProfile for one card
- ``infer_primary_axes``          — detect the deck's primary mechanical axes
- ``classify_role``               — assign a CardRole to a profiled card
- ``score_pairwise``              — single-pass O(n²) pairwise scoring engine
- ``extract_names_from_session``  — pull card names from a session.md file
- ``extract_names_from_decklist`` — pull card names from a decklist.txt
- ``extract_deck_entries_from_decklist`` — structured entries with qty/section
- ``attach_card_data``            — join entries with DB rows
- ``extract_names_from_pools``    — pull card names from pool CSV files
- ``extract_names_from_text``     — pull card names from plain text
"""

from __future__ import annotations

import csv
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Set, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))

from synergy_types import (
    InteractionType,
    CardRole,
    INTERACTION_WEIGHTS,
    Interaction,
    SynergyProfile,
    CardScore,
    CompositeWeights,
    INTERACTION_RULES,
    ROLE_TAGS,
    ORACLE_KEYWORDS,
    DEP_PATTERNS,
    INTERACTION_TAGS,
    SUPPORT_TAGS,
    CORE_ENGINE_TAGS,
    PAYOFF_BRIDGE_PATTERNS,
    DIRECTIONAL_PATTERNS,
)
from mtg_utils import RepoPaths, parse_decklist, CARD_TYPES
from search_cards import compute_tags as _compute_broad_tags

__all__ = [
    "load_cards_from_db",
    "compute_synergy_profile",
    "infer_primary_axes",
    "classify_role",
    "score_pairwise",
    "extract_names_from_session",
    "extract_names_from_decklist",
    "extract_deck_entries_from_decklist",
    "attach_card_data",
    "extract_names_from_pools",
    "extract_names_from_text",
]


# ═══════════════════════════════════════════════════════════════════════════════
# Pre-compiled regex patterns
# ═══════════════════════════════════════════════════════════════════════════════

_GATE3_ROW_RE: re.Pattern[str] = re.compile(
    r"\|\s*(\d+)\s*\|\s*([^|\n]{2,60})\s*\|"
)

_SKIP_HEADERS: frozenset[str] = frozenset({
    "card name", "card", "qty", "quantity", "mana", "source file",
    "set/collector", "role/justification", "role", "color", "total pips",
    "key cards", "required sources", "actual sources", "status",
    "land name", "colors produced", "label", "command",
})

_BASIC_TYPES: frozenset[str] = frozenset({
    "plains", "island", "swamp", "mountain", "forest", "basic", "land",
    "enchantment", "artifact", "creature", "instant", "sorcery",
    "planeswalker", "legendary", "snow", "tribal", "battle",
})

_CREATURE_TYPE_RE: re.Pattern[str] = re.compile(
    r"(?:Creature|Legendary Creature)[^—]*—\s*(.+?)(?:\s*//|\s*$)",
    re.IGNORECASE,
)

# Pre-compile dependency patterns for performance
_COMPILED_DEP_PATTERNS: List[Tuple[re.Pattern[str], int, str]] = [
    (re.compile(pat, re.IGNORECASE), weight, desc)
    for pat, weight, desc in DEP_PATTERNS
]

# Pre-compile directional patterns for performance
_COMPILED_DIRECTIONAL: Dict[str, Dict[str, List[re.Pattern[str]]]] = {}
for _mech, _dirs in DIRECTIONAL_PATTERNS.items():
    _COMPILED_DIRECTIONAL[_mech] = {
        "source": [re.compile(p, re.IGNORECASE) for p in _dirs["source"]],
        "payoff": [re.compile(p, re.IGNORECASE) for p in _dirs["payoff"]],
    }

# Pre-compile payoff bridge patterns
_COMPILED_BRIDGE_PATTERNS: List[Tuple[re.Pattern[str], str, str]] = [
    (re.compile(pat, re.IGNORECASE), axis, label)
    for pat, axis, label in PAYOFF_BRIDGE_PATTERNS
]

# Confidence multipliers for weighted scoring
_CONFIDENCE_MULTIPLIER: Dict[str, float] = {
    "oracle":   1.5,
    "tag":      1.0,
    "inferred": 0.5,
}

# Session-extraction helpers
_NAME_RE: re.Pattern[str] = re.compile(r"^[A-Z][a-zA-Z',\- ]{1,50}$")
_DIGITS_RE: re.Pattern[str] = re.compile(r"^\d+$")
_DASHES_RE: re.Pattern[str] = re.compile(r"^-+$")


# ═══════════════════════════════════════════════════════════════════════════════
# Private helpers
# ═══════════════════════════════════════════════════════════════════════════════

def _cmc_bracket(cmc: float) -> int:
    """Map a converted mana cost to a coarse bracket for redundancy checks."""
    if cmc <= 1:
        return 0
    if cmc <= 3:
        return 1
    if cmc <= 5:
        return 2
    return 3


def _parse_subtypes(type_line: str) -> Set[str]:
    """Extract creature subtypes from a type line string."""
    m = _CREATURE_TYPE_RE.search(type_line)
    if not m:
        return set()
    raw = m.group(1).strip()
    return {
        t.strip().lower()
        for t in raw.split()
        if t.strip().lower() not in _BASIC_TYPES
    }


# ═══════════════════════════════════════════════════════════════════════════════
# Card loading
# ═══════════════════════════════════════════════════════════════════════════════

def load_cards_from_db(
    names: List[str], paths: RepoPaths,
) -> Dict[str, Dict[str, Any]]:
    """Load card data from the CSV database for a list of card names.

    Scans every CSV under ``paths.cards_dir`` and returns a dict keyed by
    *lowercased* card name.  Stops early once every requested name is found.
    """
    target: Dict[str, str] = {n.lower(): n for n in names}
    found: Dict[str, Dict[str, Any]] = {}
    for card_type in CARD_TYPES:
        type_dir = paths.cards_dir / card_type
        if not type_dir.exists():
            continue
        for csv_file in sorted(type_dir.glob("*.csv")):
            try:
                with open(csv_file, encoding="utf-8") as f:
                    for row in csv.DictReader(f):
                        name_lower = row.get("name", "").lower()
                        if name_lower in target and name_lower not in found:
                            found[name_lower] = row
                            if len(found) == len(target):
                                return found
            except Exception as exc:
                print(
                    f"[WARN] Skipped {csv_file.name}: {exc}",
                    file=sys.stderr,
                )
                continue
    return found


# ═══════════════════════════════════════════════════════════════════════════════
# Synergy profile builder
# ═══════════════════════════════════════════════════════════════════════════════

def compute_synergy_profile(card: Dict[str, Any]) -> SynergyProfile:
    """Build a rich :class:`SynergyProfile` from a card dict.

    Moved from ``search_cards.py`` (lines 800-865).  Uses
    :data:`DIRECTIONAL_PATTERNS` from ``synergy_types`` for source/payoff
    classification and :func:`compute_tags` from ``search_cards`` for broad
    tags.

    Returns a :class:`SynergyProfile` dataclass with ``frozenset`` fields
    instead of mutable sets.
    """
    oracle: str = str(card.get("oracle_text", "") or "").lower()
    type_line: str = str(card.get("type_line", "") or "")
    name: str = str(card.get("name", "") or "")

    # Broad (undirected) tags via search_cards.compute_tags
    broad: Set[str] = _compute_broad_tags(card)

    # Directional source / payoff classification
    source_tags: Set[str] = set()
    payoff_tags: Set[str] = set()
    for mechanic, compiled in _COMPILED_DIRECTIONAL.items():
        for pat in compiled["source"]:
            if pat.search(oracle):
                source_tags.add(mechanic)
                break
        for pat in compiled["payoff"]:
            if pat.search(oracle):
                payoff_tags.add(mechanic)
                break

    # Lifelink in keywords = definitive lifegain source
    kw_raw: str = str(card.get("keywords", "") or "")
    keywords: Set[str] = {
        k.strip().lower() for k in kw_raw.split(";") if k.strip()
    }
    if "lifelink" in keywords:
        source_tags.add("lifegain")

    # Enchantments themselves register as enchantress producers
    if "enchantment" in type_line.lower():
        source_tags.add("enchantress")

    subtypes: Set[str] = _parse_subtypes(type_line)

    try:
        cmc = float(card.get("cmc", 0) or 0)
    except (ValueError, TypeError):
        cmc = 0.0

    is_land: bool = "land" in type_line.lower()

    return SynergyProfile(
        name=name,
        broad_tags=frozenset(broad),
        source_tags=frozenset(source_tags),
        payoff_tags=frozenset(payoff_tags),
        subtypes=frozenset(subtypes),
        keywords=frozenset(keywords),
        cmc=cmc,
        type_line=type_line,
        oracle_text=oracle,
        is_land=is_land,
        mana_cost=str(card.get("mana_cost", "") or ""),
        colors=str(
            card.get("colors", card.get("color_identity", "")) or ""
        ),
    )


# ═══════════════════════════════════════════════════════════════════════════════
# Role classification
# ═══════════════════════════════════════════════════════════════════════════════

def infer_primary_axes(
    profiles: List[Any], override: str = "",
) -> Set[str]:
    """Determine the deck's primary mechanical axes.

    If *override* is given (comma-separated string), those axes are used
    directly.  Otherwise, any :data:`CORE_ENGINE_TAGS` tag appearing on >= 3
    cards is considered a primary axis.

    Accepts both ``SynergyProfile`` dataclass instances and legacy dicts.
    """
    if override:
        return {x.strip().lower() for x in override.split(",") if x.strip()}

    counts: Dict[str, int] = {}
    for p in profiles:
        # Support both SynergyProfile dataclass and legacy dict
        if isinstance(p, SynergyProfile):
            tags: Set[str] = (
                set(p.source_tags) | set(p.payoff_tags) | set(p.broad_tags)
            )
        else:
            tags = (
                set(p.get("source_tags", set()))
                | set(p.get("payoff_tags", set()))
                | set(p.get("broad_tags", set()))
            )
        for t in tags & CORE_ENGINE_TAGS:
            counts[t] = counts.get(t, 0) + 1
    return {t for t, c in counts.items() if c >= 3}


def classify_role(
    profile: Any, primary_axes: Set[str],
) -> CardRole:
    """Assign a :class:`CardRole` to a card based on its profile and the
    deck's primary axes.

    Accepts both ``SynergyProfile`` dataclass instances and legacy dicts.
    """
    if isinstance(profile, SynergyProfile):
        src: Set[str] = set(profile.source_tags)
        pay: Set[str] = set(profile.payoff_tags)
        broad: Set[str] = set(profile.broad_tags)
    else:
        src = set(profile.get("source_tags", set()))
        pay = set(profile.get("payoff_tags", set()))
        broad = set(profile.get("broad_tags", set()))

    core = (src | pay | broad) & primary_axes
    if core and src and pay:
        return CardRole.ENGINE
    if pay & primary_axes:
        return CardRole.PAYOFF
    if src & primary_axes:
        return CardRole.ENABLER
    if broad & INTERACTION_TAGS:
        return CardRole.INTERACTION
    return CardRole.SUPPORT


# ═══════════════════════════════════════════════════════════════════════════════
# Pairwise scoring — private helpers
# ═══════════════════════════════════════════════════════════════════════════════

def _apply_weighted(
    scores: Dict[str, CardScore],
    name_a: str,
    name_b: str,
    itype: InteractionType,
    primary_axes: Set[str],
    confidence: str = "tag",
) -> None:
    """Apply weighted synergy score for an interaction between two cards.

    Uses :data:`INTERACTION_WEIGHTS` and a confidence multiplier instead of
    the former hardcoded ``weight = 2.0 if itype in {...} else 1.0``.
    """
    weight: float = INTERACTION_WEIGHTS.get(itype, 1.0)
    conf_mult: float = _CONFIDENCE_MULTIPLIER.get(confidence, 1.0)
    effective: float = weight * conf_mult

    boost_a: float = 1.0 + 0.25 * max(scores[name_a].qty - 1, 0)
    boost_b: float = 1.0 + 0.25 * max(scores[name_b].qty - 1, 0)

    scores[name_a].weighted_synergy += effective * boost_b
    scores[name_b].weighted_synergy += effective * boost_a

    engine_roles = {CardRole.ENGINE, CardRole.ENABLER, CardRole.PAYOFF}
    if (
        scores[name_a].role in engine_roles
        and scores[name_b].role in engine_roles
    ):
        scores[name_a].engine_partners.add(name_b)
        scores[name_b].engine_partners.add(name_a)
        scores[name_a].engine_synergy += effective * boost_b
        scores[name_b].engine_synergy += effective * boost_a
    else:
        scores[name_a].support_partners.add(name_b)
        scores[name_b].support_partners.add(name_a)


def _add_oracle_bridge(
    scores: Dict[str, CardScore],
    payoff_name: str,
    source_name: str,
    note: str,
    primary_axes: Set[str],
) -> None:
    """Record an oracle-confirmed payoff bridge between two cards."""
    if payoff_name not in scores or source_name not in scores:
        return
    scores[payoff_name].interactions.append(Interaction(
        partner=source_name,
        itype=InteractionType.TRIGGERS,
        note=note,
        confidence="oracle",
    ))
    for a, b in [(payoff_name, source_name), (source_name, payoff_name)]:
        scores[a].synergy_partners.add(b)
        scores[a].engine_partners.add(b)
        scores[a].role_breadth_types.add(InteractionType.TRIGGERS.value)

    # Oracle bridges get a strong fixed bonus (confidence = oracle -> 1.5x)
    bridge_weight: float = 3.0
    scores[payoff_name].weighted_synergy += bridge_weight
    scores[source_name].weighted_synergy += bridge_weight
    scores[payoff_name].engine_synergy += bridge_weight
    scores[source_name].engine_synergy += bridge_weight


def _score_tag_interactions(
    scores: Dict[str, CardScore],
    name_a: str,
    pa: SynergyProfile,
    name_b: str,
    pb: SynergyProfile,
    primary_axes: Set[str],
) -> None:
    """Pass 1: Rule-based tag interactions between a pair of cards."""
    for (
        field_a, val_a, field_b, val_b, itype_enum, note_tmpl
    ) in INTERACTION_RULES:
        # Access profile fields by name (broad_tags, source_tags, payoff_tags)
        pa_field_a: frozenset[str] = getattr(pa, field_a)
        pb_field_b: frozenset[str] = getattr(pb, field_b)
        pb_field_a: frozenset[str] = getattr(pb, field_a)
        pa_field_b: frozenset[str] = getattr(pa, field_b)

        # Forward direction: A -> B
        if val_a in pa_field_a and val_b in pb_field_b:
            note = note_tmpl.format(a=name_a, b=name_b)
            scores[name_a].interactions.append(Interaction(
                partner=name_b,
                itype=itype_enum,
                note=note,
                confidence="tag",
            ))
            if itype_enum != InteractionType.REDUNDANT:
                scores[name_a].synergy_partners.add(name_b)
                scores[name_b].synergy_partners.add(name_a)
                scores[name_a].role_breadth_types.add(itype_enum.value)
                scores[name_b].role_breadth_types.add(itype_enum.value)
                _apply_weighted(
                    scores, name_a, name_b, itype_enum, primary_axes,
                    confidence="tag",
                )

        # Reverse direction: B -> A
        if val_a in pb_field_a and val_b in pa_field_b:
            note = note_tmpl.format(a=name_b, b=name_a)
            scores[name_b].interactions.append(Interaction(
                partner=name_a,
                itype=itype_enum,
                note=note,
                confidence="tag",
            ))
            if itype_enum != InteractionType.REDUNDANT:
                scores[name_a].synergy_partners.add(name_b)
                scores[name_b].synergy_partners.add(name_a)
                scores[name_b].role_breadth_types.add(itype_enum.value)
                scores[name_a].role_breadth_types.add(itype_enum.value)
                _apply_weighted(
                    scores, name_b, name_a, itype_enum, primary_axes,
                    confidence="tag",
                )


# ── Pre-computed oracle indices (built once, used in O(n²) loop) ─────────

def _build_oracle_indices(
    profiles: Dict[str, SynergyProfile],
) -> Tuple[
    Dict[str, Set[str]],   # subtype_mentions: card -> subtypes found in oracle
    Dict[str, Set[str]],   # keyword_cares: card -> keywords oracle cares about
]:
    """Pre-compute per-card oracle-text indices for subtype and keyword lookups.

    Instead of running regex on every *pair*, we run it once per *card* and
    store the results.  The pairwise loop then does cheap set-intersection
    lookups.

    Returns
    -------
    subtype_mentions : dict[card_name, set[str]]
        For each card, the set of subtypes (from the entire pool) that appear
        as whole words in that card's oracle text.
    keyword_cares : dict[card_name, set[str]]
        For each card, the set of ORACLE_KEYWORDS that the card's oracle text
        "cares about" (i.e. matches the keyword-care pattern).
    """
    # Collect all unique subtypes across the pool (length >= 3)
    all_subtypes: Set[str] = set()
    for p in profiles.values():
        all_subtypes.update(s for s in p.subtypes if len(s) >= 3)

    # Pre-compile one regex per subtype
    subtype_regexes: Dict[str, re.Pattern[str]] = {
        st: re.compile(r"\b" + re.escape(st) + r"\b")
        for st in all_subtypes
    }

    # Pre-compile one regex per oracle keyword
    keyword_regexes: Dict[str, re.Pattern[str]] = {
        kw: re.compile(
            r"(creature[s]? (with|that (have|has))"
            r"|whenever a .{0,20})"
            + re.escape(kw),
            re.IGNORECASE,
        )
        for kw in ORACLE_KEYWORDS
    }

    subtype_mentions: Dict[str, Set[str]] = {}
    keyword_cares: Dict[str, Set[str]] = {}

    for name, prof in profiles.items():
        oracle = prof.oracle_text
        # Which subtypes does this card's oracle text mention?
        mentioned: Set[str] = set()
        for st, pat in subtype_regexes.items():
            if pat.search(oracle):
                mentioned.add(st)
        subtype_mentions[name] = mentioned

        # Which keywords does this card's oracle text care about?
        cares: Set[str] = set()
        for kw, pat in keyword_regexes.items():
            if pat.search(oracle):
                cares.add(kw)
        keyword_cares[name] = cares

    return subtype_mentions, keyword_cares


def _score_oracle_crossref_indexed(
    scores: Dict[str, CardScore],
    name_a: str,
    pa: SynergyProfile,
    name_b: str,
    pb: SynergyProfile,
    subtype_mentions: Dict[str, Set[str]],
    keyword_cares: Dict[str, Set[str]],
    oracle_seen: Dict[str, Set[str]],
) -> None:
    """Pass 2: Oracle text cross-reference using pre-computed indices.

    Uses *subtype_mentions* and *keyword_cares* (built once by
    :func:`_build_oracle_indices`) instead of running regex per pair.
    *oracle_seen* tracks which (card, partner) oracle-TRIGGERS have already
    been recorded, replacing the expensive linear ``any()`` scan.
    """
    # Check A's subtypes mentioned in B's oracle text
    a_subtypes_in_b = set(pa.subtypes) & subtype_mentions.get(name_b, set())
    if a_subtypes_in_b and name_b not in oracle_seen.get(name_a, set()):
        subtype = next(iter(a_subtypes_in_b))
        note = (
            f"Oracle: {pb.name} references '{subtype}' subtype "
            f"that {pa.name} has"
        )
        scores[name_a].interactions.append(Interaction(
            partner=name_b,
            itype=InteractionType.TRIGGERS,
            note=note,
            confidence="oracle",
        ))
        scores[name_a].synergy_partners.add(name_b)
        scores[name_b].synergy_partners.add(name_a)
        scores[name_a].role_breadth_types.add(InteractionType.TRIGGERS.value)
        scores[name_b].role_breadth_types.add(InteractionType.TRIGGERS.value)
        oracle_seen.setdefault(name_a, set()).add(name_b)

    # Check B's subtypes mentioned in A's oracle text
    b_subtypes_in_a = set(pb.subtypes) & subtype_mentions.get(name_a, set())
    if b_subtypes_in_a and name_a not in oracle_seen.get(name_b, set()):
        subtype = next(iter(b_subtypes_in_a))
        note = (
            f"Oracle: {pa.name} references '{subtype}' subtype "
            f"that {pb.name} has"
        )
        scores[name_b].interactions.append(Interaction(
            partner=name_a,
            itype=InteractionType.TRIGGERS,
            note=note,
            confidence="oracle",
        ))
        scores[name_a].synergy_partners.add(name_b)
        scores[name_b].synergy_partners.add(name_a)
        scores[name_b].role_breadth_types.add(InteractionType.TRIGGERS.value)
        scores[name_a].role_breadth_types.add(InteractionType.TRIGGERS.value)
        oracle_seen.setdefault(name_b, set()).add(name_a)

    # Check A's keywords cared about in B's oracle text
    a_kw_in_b = (pa.keywords & ORACLE_KEYWORDS) & keyword_cares.get(name_b, set())
    if a_kw_in_b and name_b not in oracle_seen.get(name_a, set()):
        kw = next(iter(a_kw_in_b))
        note = (
            f"Oracle: {pb.name} cares about '{kw}' keyword "
            f"that {pa.name} has"
        )
        scores[name_a].interactions.append(Interaction(
            partner=name_b,
            itype=InteractionType.TRIGGERS,
            note=note,
            confidence="oracle",
        ))
        scores[name_a].synergy_partners.add(name_b)
        scores[name_b].synergy_partners.add(name_a)
        scores[name_a].role_breadth_types.add(InteractionType.TRIGGERS.value)
        scores[name_b].role_breadth_types.add(InteractionType.TRIGGERS.value)
        oracle_seen.setdefault(name_a, set()).add(name_b)


def _score_oracle_bridges(
    scores: Dict[str, CardScore],
    name_a: str,
    pa: SynergyProfile,
    name_b: str,
    pb: SynergyProfile,
    primary_axes: Set[str],
) -> None:
    """Pass 2b: Oracle payoff bridges (life-gain drain, food, tribe triggers)."""
    for compiled_pat, axis, label in _COMPILED_BRIDGE_PATTERNS:
        if axis not in primary_axes:
            continue
        b_tags: frozenset[str] = pb.source_tags | pb.payoff_tags | pb.broad_tags
        a_tags: frozenset[str] = pa.source_tags | pa.payoff_tags | pa.broad_tags

        if compiled_pat.search(pa.oracle_text) and axis in b_tags:
            note = (
                f"Oracle payoff bridge [{label}]: {name_a} converts "
                f"{axis} -> payoff; {name_b} produces {axis}"
            )
            _add_oracle_bridge(scores, name_a, name_b, note, primary_axes)
        elif compiled_pat.search(pb.oracle_text) and axis in a_tags:
            note = (
                f"Oracle payoff bridge [{label}]: {name_b} converts "
                f"{axis} -> payoff; {name_a} produces {axis}"
            )
            _add_oracle_bridge(scores, name_b, name_a, note, primary_axes)


def _score_redundancy(
    scores: Dict[str, CardScore],
    name_a: str,
    pa: SynergyProfile,
    name_b: str,
    pb: SynergyProfile,
    seen_redundant: Set[frozenset],
) -> None:
    """Pass 3: CMC-bracket-aware REDUNDANT detection (narrow roles only)."""
    shared_roles: frozenset[str] = pa.broad_tags & pb.broad_tags & ROLE_TAGS
    if shared_roles and _cmc_bracket(pa.cmc) == _cmc_bracket(pb.cmc):
        pair: frozenset[str] = frozenset([name_a, name_b])
        if pair not in seen_redundant:
            seen_redundant.add(pair)
            note = (
                f"Both are {', '.join(shared_roles)} at CMC "
                f"{pa.cmc}/{pb.cmc} (same bracket)"
            )
            scores[name_a].redundant_with.append(name_b)
            scores[name_b].redundant_with.append(name_a)
            scores[name_a].interactions.append(Interaction(
                partner=name_b,
                itype=InteractionType.REDUNDANT,
                note=note,
                confidence="inferred",
            ))
            scores[name_b].interactions.append(Interaction(
                partner=name_a,
                itype=InteractionType.REDUNDANT,
                note=note,
                confidence="inferred",
            ))


# ═══════════════════════════════════════════════════════════════════════════════
# Main scoring function
# ═══════════════════════════════════════════════════════════════════════════════

def score_pairwise(
    cards_or_entries: Any,
    score_mode: str = "role-aware",
    primary_axis: str = "",
) -> Dict[str, CardScore]:
    """Single-pass O(n**2) pairwise scoring engine.

    Accepts either:
    - A ``list`` of entry dicts (with ``name``, ``qty``, ``section``, ``data``,
      ``found_in_db`` keys — as produced by :func:`attach_card_data`), or
    - A ``dict`` mapping lowercased card names to card-data dicts (legacy API).

    Returns a dict mapping lowercased card names to :class:`CardScore`
    dataclass instances.

    All five scoring passes from the original ``synergy_analysis.py`` are
    merged into a single pair iteration (passes 1-3), followed by a per-card
    dependency pass (pass 4).
    """
    profiles: Dict[str, SynergyProfile] = {}
    qty_by_name: Dict[str, int] = {}
    section_by_name: Dict[str, str] = {}

    # -- Build profiles ----------------------------------------------------
    if isinstance(cards_or_entries, list):
        for e in cards_or_entries:
            if not e.get("found_in_db") or not e.get("data"):
                continue
            p = compute_synergy_profile(e["data"])
            if p.is_land:
                continue
            key: str = e["name"].lower()
            profiles[key] = p
            qty_by_name[key] = int(e.get("qty", 1))
            section_by_name[key] = e.get("section", "pool")
    else:
        for name, data in cards_or_entries.items():
            p = compute_synergy_profile(data)
            if p.is_land:
                continue
            profiles[name] = p
            qty_by_name[name] = 1
            section_by_name[name] = "pool"

    # -- Infer primary axes ------------------------------------------------
    primary_axes: Set[str] = infer_primary_axes(
        list(profiles.values()), override=primary_axis,
    )

    # -- Initialize score records ------------------------------------------
    scores: Dict[str, CardScore] = {
        name: CardScore(
            profile=profiles[name],
            qty=qty_by_name.get(name, 1),
            section=section_by_name.get(name, "pool"),
            role=classify_role(profiles[name], primary_axes),
        )
        for name in profiles
    }

    names: List[str] = list(profiles.keys())
    seen_redundant: Set[frozenset] = set()

    # -- Pre-compute oracle indices (O(n) instead of O(n²) regex) ----------
    subtype_mentions, keyword_cares = _build_oracle_indices(profiles)
    oracle_seen: Dict[str, Set[str]] = {}  # dedup tracker for oracle TRIGGERS

    # -- Single-pass pairwise scoring (Passes 1-3 merged) ------------------
    for i, name_a in enumerate(names):
        pa = profiles[name_a]
        for name_b in names[i + 1:]:
            pb = profiles[name_b]

            # Pass 1: Tag interactions
            _score_tag_interactions(
                scores, name_a, pa, name_b, pb, primary_axes,
            )

            # Pass 2: Oracle cross-reference (indexed — no per-pair regex)
            _score_oracle_crossref_indexed(
                scores, name_a, pa, name_b, pb,
                subtype_mentions, keyword_cares, oracle_seen,
            )

            # Pass 2b: Oracle bridges
            _score_oracle_bridges(
                scores, name_a, pa, name_b, pb, primary_axes,
            )

            # Pass 3: Redundancy
            _score_redundancy(
                scores, name_a, pa, name_b, pb, seen_redundant,
            )

    # -- Pass 4: Dependency scoring (per-card, not per-pair) ---------------
    for name, sc in scores.items():
        oracle_text: str = sc.profile.oracle_text
        dep: int = 0
        for compiled_pat, weight, _desc in _COMPILED_DEP_PATTERNS:
            if compiled_pat.search(oracle_text):
                dep += weight
        sc.dependency = min(dep, 4)

    # -- Finalize: set pool-size context on each CardScore -----------------
    all_scored: int = len(scores)
    engine_count: int = sum(
        1
        for s in scores.values()
        if s.role in {CardRole.ENGINE, CardRole.ENABLER, CardRole.PAYOFF}
    )
    for sc in scores.values():
        sc._pool_size = all_scored
        sc._engine_pool_size = engine_count

    return scores


# ═══════════════════════════════════════════════════════════════════════════════
# Input extraction functions
# ═══════════════════════════════════════════════════════════════════════════════

def extract_names_from_session(content: str) -> List[str]:
    """Pull card names from a session.md file.

    Scans Gate 3/5 markdown tables and fenced code blocks for card names.
    """
    names: List[str] = []
    seen: Set[str] = set()

    def _add(name: str) -> None:
        key = name.lower().strip()
        if key and key not in seen and len(key) >= 3:
            seen.add(key)
            names.append(name.strip())

    gate_sections = re.split(r"# GATE [35][^#]*", content)
    for section in gate_sections[1:]:
        for line in section.splitlines():
            if not line.startswith("|"):
                continue
            parts = [p.strip() for p in line.split("|") if p.strip()]
            if len(parts) < 3:
                continue
            qty_cell = parts[0]
            name_cell = parts[1] if len(parts) > 1 else ""
            if name_cell.lower() in _SKIP_HEADERS:
                continue
            if _DASHES_RE.match(name_cell):
                continue
            if not name_cell:
                continue
            if qty_cell and not _DIGITS_RE.match(qty_cell.strip()):
                continue
            if _NAME_RE.match(name_cell):
                _add(name_cell)

    code_blocks = re.findall(r"```[^\n]*\n(.*?)```", content, re.DOTALL)
    for block in code_blocks:
        lines = block.splitlines()
        for line in lines[1:]:
            if not line.strip() or line.startswith("#") or line.startswith("-"):
                continue
            parts = line.split(",")
            if parts:
                candidate = parts[0].strip().strip('"')
                if (
                    candidate
                    and candidate.lower() not in _SKIP_HEADERS
                    and _NAME_RE.match(candidate)
                ):
                    _add(candidate)

    return names


def extract_names_from_decklist(path: Path) -> List[str]:
    """Pull card names from a decklist.txt (main + sideboard)."""
    main, side = parse_decklist(path)
    return [name for _, name in main + side]


def extract_deck_entries_from_decklist(
    path: Path, include_sideboard: bool = False,
) -> List[Dict[str, Any]]:
    """Return structured entry dicts with qty and section from a decklist."""
    main, side = parse_decklist(path)
    entries: List[Dict[str, Any]] = [
        {"name": name, "qty": qty, "section": "main"}
        for qty, name in main
    ]
    if include_sideboard:
        entries += [
            {"name": name, "qty": qty, "section": "side"}
            for qty, name in side
        ]
    return entries


def attach_card_data(
    entries: List[Dict[str, Any]],
    card_data: Dict[str, Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Join entry dicts with card-data rows from the database.

    Returns ``(annotated, missing)`` where *annotated* has a ``data`` key
    and a ``found_in_db`` flag, and *missing* lists entries not found.
    """
    annotated: List[Dict[str, Any]] = []
    missing: List[Dict[str, Any]] = []
    for e in entries:
        row: Dict[str, Any] = dict(e)
        data = card_data.get(e["name"].lower())
        if data:
            row["data"] = data
            row["found_in_db"] = True
        else:
            row["data"] = None
            row["found_in_db"] = False
            missing.append(row)
        annotated.append(row)
    return annotated, missing


def extract_names_from_pools(input_path: Path) -> List[str]:
    """Pull card names from pool CSV files under a deck directory."""
    if input_path.is_file():
        pools_dir = input_path.parent / "pools"
    elif (input_path / "pools").exists():
        pools_dir = input_path / "pools"
    else:
        pools_dir = input_path

    names: List[str] = []
    seen: Set[str] = set()
    for pool_file in sorted(pools_dir.glob("pool_*.csv")):
        try:
            file_content = pool_file.read_text(encoding="utf-8")
            for line in file_content.splitlines():
                if line.startswith("#") or not line.strip():
                    continue
                parts = line.split(",")
                if not parts:
                    continue
                candidate = parts[0].strip().strip('"')
                if (
                    candidate
                    and candidate.lower() not in _SKIP_HEADERS
                    and candidate.lower() not in seen
                ):
                    seen.add(candidate.lower())
                    names.append(candidate)
        except Exception:
            continue
    return names


def extract_names_from_text(content: str) -> List[str]:
    """Pull card names from plain text (one name per line)."""
    names: List[str] = []
    for line in content.splitlines():
        line = line.strip()
        if line and not line.startswith("#") and not line.startswith("//"):
            names.append(line)
    return names