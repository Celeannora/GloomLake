#!/usr/bin/env python3
"""
MTG Card Search Tool — AI-Assisted Deck Building

Replaces manual file-by-file sweeps. Reads every relevant CSV and returns a
filtered candidate pool so AI agents can build from verified data without
holding hundreds of KB of raw CSVs in context.

Usage:
    python scripts/search_cards.py --type creature --colors W --tags lifelink,flying
    python scripts/search_cards.py --type instant --oracle "mill" --colors UB
    python scripts/search_cards.py --type creature --cmc-max 3 --colors WB --tags removal
    python scripts/search_cards.py --name "Sheoldred"
    python scripts/search_cards.py --type land --colors WUB
    python scripts/search_cards.py --type creature --tags lifegain --rarity rare,mythic

Flags:
    --type          Card type(s): creature, instant, sorcery, enchantment, artifact,
                    land, planeswalker, battle, other  (comma-separated for multiple)
    --colors        Color identity filter: W, U, B, R, G, WB, WUB, etc.
                    Use 'C' for colorless. Prefix with '=' for exact match (e.g. =WB)
    --oracle        Substring match in oracle_text (case-insensitive)
    --tags          Strategy tag(s) to filter by (comma-separated)
                    See TAG SYSTEM below for full list
    --name          Substring match in card name (case-insensitive)
    --cmc-max       Maximum converted mana cost (inclusive)
    --cmc-min       Minimum converted mana cost (inclusive)
    --rarity        Rarity filter: common, uncommon, rare, mythic (comma-separated)
    --keywords      MTG keyword filter (comma-separated, e.g. Flying,Lifelink)
    --limit         Max results to return (default: 200)
    --show-tags     Print computed tags for each card in results
    --format        Output format: table (default), csv, names

TAG SYSTEM:
    lifegain        — "you gain" life, lifelink keyword
    mill            — "mill", "put top", "into graveyard from library"
    draw            — "draw a card/cards"
    removal         — "exile target", "destroy target", "deals damage to"
    counter         — "counter target spell/ability"
    ramp            — "add {", "search your library for a land"
    token           — "create a", "token"
    bounce          — "return target", "return up to"
    discard         — "target player discards", "each opponent discards"
    tutor           — "search your library for a card"
    wipe            — "destroy all", "exile all", "deals damage to all"
    protection      — "hexproof", "indestructible", "ward"
    pump            — "+1/+1 counter", "gets +X/+X"
    reanimation     — "return from graveyard", "reanimate"
    etb             — "enters", "when ~ enters the battlefield"
    tribal          — "other [creature subtype]s you control"
    flash           — flash keyword
    haste           — haste keyword
    trample         — trample keyword
    flying          — flying keyword
    deathtouch      — deathtouch keyword
    vigilance       — vigilance keyword
    reach           — reach keyword
    menace          — menace keyword
    scry            — "scry"
    surveil         — "surveil"
    sacrifice       — sac outlets and death-trigger payoffs
    energy          — energy producers and spenders
    storm_count     — spell-count producers and payoffs (Storm keyword)
    enchantress     — enchantment-cast draw/trigger payoffs (Constellation)
    blink           — flicker/exile-and-return effects

Exit codes:
    0  Results found and printed
    1  No results found
    2  Invalid arguments
"""

import argparse
import csv
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

# ---------------------------------------------------------------------------
# Strategic tag rules — (tag_name, list_of_oracle_text_substrings_OR_keywords)
# All matches are case-insensitive. A card gets a tag if ANY substring matches.
# ---------------------------------------------------------------------------
TAG_RULES: List[Tuple[str, List[str]]] = [
    ("lifegain",    ["you gain", "lifelink", "gain life"]),
    ("mill",        ["mill ", "mills ", "put the top", "from the top", "into their graveyard from their library"]),
    ("draw",        ["draw a card", "draw two", "draw three", "draw x", "draw cards"]),
    ("removal",     ["exile target", "destroy target", "deals damage to target", "deals that much damage"]),
    ("counter",     ["counter target spell", "counter that spell", "counter target ability"]),
    ("ramp",        ["add {", "add mana", "search your library for a basic land", "search your library for a land"]),
    ("token",       ["create a ", "create x ", "create two ", "create three ", "token"]),
    ("bounce",      ["return target", "return up to", "return each"]),
    ("discard",     ["discards a card", "discards two", "each opponent discards", "target player discards"]),
    ("tutor",       ["search your library for a card", "search your library for an instant", "search your library for a sorcery"]),
    ("wipe",        ["destroy all", "exile all", "deals damage to all", "deals damage to each"]),
    ("protection",  ["hexproof", "indestructible", "ward {"]),
    ("pump",        ["+1/+1 counter", "gets +", "+x/+x"]),
    ("reanimation", ["return target creature card from your graveyard", "return up to one target creature card from a graveyard"]),
    ("etb",         ["when ~ enters", "when it enters", "enters the battlefield"]),
    ("tribal",      ["other ", "s you control get", "s you control have"]),
    ("scry",        ["scry "]),
    ("surveil",     ["surveil "]),
]

# Keywords that map directly to tags (checked against the `keywords` column)
KEYWORD_TAG_MAP: Dict[str, str] = {
    "flash":       "flash",
    "haste":       "haste",
    "trample":     "trample",
    "flying":      "flying",
    "deathtouch":  "deathtouch",
    "vigilance":   "vigilance",
    "reach":       "reach",
    "menace":      "menace",
    "lifelink":    "lifegain",
    "first strike": "first_strike",
    "double strike": "double_strike",
}

CARD_TYPES = [
    'artifact', 'battle', 'creature', 'enchantment', 'instant',
    'land', 'other', 'planeswalker', 'sorcery',
]

COLOR_ORDER = "WUBRG"


def compute_tags(card: Dict) -> Set[str]:
    """Derive strategic tags from a card's oracle_text and keywords."""
    tags: Set[str] = set()
    oracle = card.get("oracle_text", "").lower()
    kw_raw = card.get("keywords", "").lower()
    keywords_str = card.get("keywords", "").lower()

    for tag, patterns in TAG_RULES:
        if any(p in oracle for p in patterns):
            tags.add(tag)

    for kw, tag in KEYWORD_TAG_MAP.items():
        if kw in kw_raw:
            tags.add(tag)

    # sacrifice tag — sac outlets and death-trigger payoffs
    if re.search(r"sacrifice (a|another|any number of) (creature|permanent|artifact|land)", oracle, re.I):
        tags.add("sacrifice")
    if re.search(r"whenever (a|another) creature (you control )?dies", oracle, re.I):
        tags.add("sacrifice")
    if re.search(r"whenever you sacrifice", oracle, re.I):
        tags.add("sacrifice")

    # energy tag — producers and spenders
    if re.search(r"you get \{E", oracle, re.I) or re.search(r"gets? \{E", oracle, re.I):
        tags.add("energy")
    if re.search(r"pay \{E", oracle, re.I):
        tags.add("energy")

    # storm_count tag — spell-count producers and payoffs
    if re.search(r"\bstorm\b", keywords_str, re.I):  # has Storm keyword
        tags.add("storm_count")
    if re.search(r"for each (instant or sorcery|other spell|spell) (cast this turn|you('ve| have) cast)", oracle, re.I):
        tags.add("storm_count")
    if re.search(r"copy (this spell|it) for each", oracle, re.I):
        tags.add("storm_count")

    # enchantress tag — enchantment draw/trigger payoffs
    if re.search(r"whenever you cast an enchantment", oracle, re.I):
        tags.add("enchantress")
    if re.search(r"whenever an enchantment enters", oracle, re.I):
        tags.add("enchantress")
    if re.search(r"\bconstellation\b", oracle, re.I):
        tags.add("enchantress")

    # blink tag — flicker/exile-and-return effects
    if re.search(r"exile (target|another|it).*then return.*to.*battlefield", oracle, re.I):
        tags.add("blink")
    if re.search(r"\bflicker\b", oracle, re.I):
        tags.add("blink")

    return tags


def normalize_colors(color_str: str) -> Set[str]:
    """Normalize a colors/color_identity CSV column value to a set of letters."""
    if not color_str:
        return set()
    # Scryfall stores as comma-separated: "W,U" or empty for colorless
    return set(c.strip().upper() for c in color_str.split(",") if c.strip())


def color_matches(card: Dict, color_filter: str) -> bool:
    """
    Filter by color identity.
    'C' = colorless only
    Prefix '=' for exact color match; otherwise subset match (deck can play card).
    """
    exact = color_filter.startswith("=")
    colors = color_filter.lstrip("=").upper()

    if colors == "C":
        return normalize_colors(card.get("color_identity", "")) == set()

    wanted = set(colors)
    card_identity = normalize_colors(card.get("color_identity", ""))

    if exact:
        return card_identity == wanted
    else:
        # Card is playable in a deck of these colors if card's identity ⊆ wanted
        return card_identity.issubset(wanted)


def load_cards(
    repo_root: Path,
    types: Optional[List[str]],
) -> List[Dict]:
    """Load all cards of the requested types from the card database directory."""
    from mtg_utils import RepoPaths
    paths = RepoPaths(root=repo_root)
    cards_dir = paths.cards_dir
    if not cards_dir.exists():
        print(f"ERROR: {RepoPaths.CARDS_DIR_NAME}/ not found at {cards_dir}", file=sys.stderr)
        sys.exit(2)

    target_types = types if types else CARD_TYPES
    results: List[Dict] = []
    seen_names: Set[str] = set()

    for card_type in target_types:
        type_dir = cards_dir / card_type
        if not type_dir.exists():
            continue
        for csv_file in sorted(type_dir.glob("*.csv")):
            try:
                with open(csv_file, encoding="utf-8") as f:
                    for row in csv.DictReader(f):
                        name = row.get("name", "").strip()
                        key = name.lower()
                        if key and key not in seen_names:
                            seen_names.add(key)
                            row["_card_type"] = card_type
                            row["_source_file"] = str(
                                csv_file.relative_to(repo_root)
                            )
                            results.append(row)
            except Exception as exc:
                print(f"WARNING: Could not read {csv_file}: {exc}", file=sys.stderr)

    return results


def filter_cards(
    cards: List[Dict],
    *,
    color_filter: Optional[str],
    oracle_filter: Optional[str],
    name_filter: Optional[str],
    subtype_filter: Optional[str],
    tag_filters: Optional[List[str]],
    tags_mode: str = "any",
    cmc_min: Optional[float],
    cmc_max: Optional[float],
    rarities: Optional[List[str]],
    keyword_filters: Optional[List[str]],
    keywords_mode: str = "any",
) -> List[Tuple[Dict, Set[str]]]:
    """Apply all filters and return (card, tags) tuples."""
    results: List[Tuple[Dict, Set[str]]] = []

    for card in cards:
        # Name filter
        if name_filter and name_filter.lower() not in card.get("name", "").lower():
            continue

        # Subtype filter — match creature subtype in type_line
        if subtype_filter:
            type_line = card.get("type_line", "").lower()
            subtype_lower = subtype_filter.lower()
            # Extract creature types from type_line (format: "Legendary Creature — Human Soldier")
            if "creature" in type_line:
                # Check if subtype appears after the em-dash
                if " — " in type_line:
                    subtypes_part = type_line.split(" — ")[-1].strip()
                    if subtype_lower not in subtypes_part:
                        continue
                else:
                    # No subtype found after em-dash
                    continue
            else:
                # Not a creature at all
                continue

        # Oracle text filter (supports regex if pattern contains regex metacharacters)
        if oracle_filter:
            oracle_text = card.get("oracle_text", "").lower()
            pattern = oracle_filter.lower()
            if any(c in pattern for c in '.*+?[](){}|\\^$'):
                # Regex mode
                if not re.search(pattern, oracle_text, re.IGNORECASE):
                    continue
            else:
                # Simple substring mode
                if pattern not in oracle_text:
                    continue

        # Color filter
        if color_filter and not color_matches(card, color_filter):
            continue

        # CMC filters
        try:
            cmc = float(card.get("cmc", 0) or 0)
        except (ValueError, TypeError):
            cmc = 0.0
        if cmc_min is not None and cmc < cmc_min:
            continue
        if cmc_max is not None and cmc > cmc_max:
            continue

        # Rarity filter
        if rarities and card.get("rarity", "").lower() not in rarities:
            continue

        # Keyword filter — OR logic by default; use keywords_mode='all' for AND
        if keyword_filters:
            card_kws = {k.strip().lower() for k in card.get("keywords", "").split(";")}
            if keywords_mode == "all":
                if not all(kf.lower() in card_kws for kf in keyword_filters):
                    continue
            else:
                if not any(kf.lower() in card_kws for kf in keyword_filters):
                    continue

        # Compute tags
        tags = compute_tags(card)

        # Tag filter — OR logic by default; use tags_mode='all' for AND
        if tag_filters:
            if tags_mode == "all":
                if not all(t in tags for t in tag_filters):
                    continue
            else:
                if not any(t in tags for t in tag_filters):
                    continue

        results.append((card, tags))

    return results


def print_table(
    results: List[Tuple[Dict, Set[str]]],
    show_tags: bool,
    limit: int,
    show_power: bool = False,
) -> None:
    """Print results as a readable table."""
    total = len(results)
    shown = results[:limit]

    print(f"\n{'='*80}")
    print(f"  CANDIDATE POOL — {total} cards found (showing {min(total, limit)})")
    print(f"{'='*80}\n")

    for card, tags in shown:
        name = card.get("name", "")
        mana = card.get("mana_cost", "") or "—"
        cmc_raw = card.get("cmc", "0")
        try:
            cmc = int(float(cmc_raw))
        except (ValueError, TypeError):
            cmc = 0
        type_line = card.get("type_line", "")
        rarity = card.get("rarity", "")[0].upper() if card.get("rarity") else "?"
        set_code = card.get("set", "")
        collector = card.get("collector_number", "")
        source = card.get("_source_file", "")

        power_suffix = ""
        if show_power:
            ps = compute_power_score(card)
            power_suffix = f"  [Score: {ps}]"
        print(f"  {name}{power_suffix}")
        print(f"    Mana: {mana}  CMC: {cmc}  [{rarity}] ({set_code}) #{collector}")
        print(f"    Type: {type_line}")

        oracle = card.get("oracle_text", "").replace("\n", " / ")
        if oracle:
            # Wrap oracle text at 70 chars
            words = oracle.split()
            lines = []
            current = []
            length = 0
            for w in words:
                if length + len(w) + 1 > 70:
                    lines.append(" ".join(current))
                    current = [w]
                    length = len(w)
                else:
                    current.append(w)
                    length += len(w) + 1
            if current:
                lines.append(" ".join(current))
            for line in lines:
                print(f"    {line}")

        if show_tags and tags:
            print(f"    Tags: {', '.join(sorted(tags))}")

        print(f"    Source: {source}\n")

    if total > limit:
        print(f"  ... {total - limit} more results. Use --limit to show more.\n")

    print(f"{'='*80}")
    print(f"  Total candidates: {total}")
    print(f"{'='*80}\n")


def print_csv(results: List[Tuple[Dict, Set[str]]], limit: int) -> None:
    """Print results as CSV for easy parsing."""
    shown = results[:limit]
    fieldnames = [
        "name", "mana_cost", "cmc", "type_line", "colors", "color_identity",
        "rarity", "set", "collector_number", "keywords", "oracle_text", "_source_file", "_tags"
    ]
    writer = csv.DictWriter(sys.stdout, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    for card, tags in shown:
        row = dict(card)
        row["_tags"] = ";".join(sorted(tags))
        writer.writerow(row)


def print_names(results: List[Tuple[Dict, Set[str]]], limit: int) -> None:
    """Print just card names — useful for quick AI candidate lists."""
    for card, _ in results[:limit]:
        src = card.get("_source_file", "")
        print(f"{card.get('name', '')}  [{src}]")


def compute_power_score(card: dict) -> float:
    """
    Heuristic power score for ranking candidates. Higher = more impactful.
    Not a perfect measure — use alongside synergy analysis.

    Components:
    - stat_efficiency: (power + toughness) / CMC  (creatures only)
    - keyword_value: bonuses for evasion, protection, fast keywords
    - tag_value: bonuses for impactful strategic tags
    - rarity_weight: mythic/rare lean toward competitive staples
    - cmc_penalty: heavy penalty for CMC > 5 (too slow unless payoff is massive)
    """
    cmc = float(card.get("cmc") or 0)
    power_str = card.get("power") or "0"
    tough_str = card.get("toughness") or "0"

    try:
        p = float(power_str) if power_str not in ("*", "X", "?", "∞") else 1.0
        t = float(tough_str) if tough_str not in ("*", "X", "?", "∞") else 1.0
    except (ValueError, TypeError):
        p = t = 0.0

    # Stat efficiency (only meaningful for creatures)
    type_line = (card.get("type_line") or "").lower()
    if "creature" in type_line and cmc > 0:
        stat_score = (p + t) / cmc
    else:
        stat_score = 0.0

    # Keyword bonuses
    keywords_lower = (card.get("keywords") or "").lower()
    kw_vals = {
        "flying": 0.4, "lifelink": 0.4, "deathtouch": 0.5,
        "first strike": 0.3, "double strike": 0.7, "trample": 0.3,
        "haste": 0.45, "indestructible": 0.8, "ward": 0.4,
        "vigilance": 0.25, "flash": 0.45, "menace": 0.25,
        "hexproof": 0.5, "reach": 0.1, "protection": 0.4,
    }
    kw_score = sum(v for k, v in kw_vals.items() if k in keywords_lower)

    # Tag bonuses (high-impact strategic roles)
    tags_str = (card.get("tags") or "").lower()
    tag_vals = {
        "etb": 0.35, "draw": 0.5, "removal": 0.5, "wipe": 0.6,
        "tutor": 0.6, "counter": 0.5, "ramp": 0.45, "reanimation": 0.4,
        "pump": 0.2, "lifegain": 0.2, "protection": 0.3,
    }
    tag_score = sum(v for k, v in tag_vals.items() if k in tags_str)

    # Rarity proxy for competitive relevance
    rarity_bonus = {"mythic": 0.5, "rare": 0.2, "uncommon": 0.1, "common": 0.0}.get(
        (card.get("rarity") or "").lower(), 0.0
    )

    # CMC penalty: starts at cmc=5, grows steeply
    cmc_penalty = max(0.0, (cmc - 4) * 0.3)

    score = stat_score + kw_score + tag_score + rarity_bonus - cmc_penalty
    return round(max(score, 0.0), 2)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Search the MTG Standard card database with strategy-aware filtering.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument("--type", dest="types", help="Card type(s), comma-separated")
    p.add_argument("--colors", help="Color identity filter (e.g. WB, =WB, UB, C)")
    p.add_argument("--oracle", help="Substring match in oracle text")
    p.add_argument("--name", help="Substring match in card name")
    p.add_argument("--subtype", help="Creature subtype filter (e.g. Frog, Angel, Dog)")
    p.add_argument("--tags", help="Strategy tags, comma-separated (e.g. lifegain,draw). OR logic by default.")
    p.add_argument("--tags-mode", choices=["any", "all"], default="any",
                   help="How to match multiple --tags: 'any' (OR, default) or 'all' (AND)")
    p.add_argument("--cmc-max", type=float, help="Max CMC (inclusive)")
    p.add_argument("--cmc-min", type=float, help="Min CMC (inclusive)")
    p.add_argument("--rarity", help="Rarity filter: common,uncommon,rare,mythic")
    p.add_argument("--keywords", help="MTG keyword(s), comma-separated (e.g. Flying,Lifelink). OR logic by default.")
    p.add_argument("--keywords-mode", choices=["any", "all"], default="any",
                   help="How to match multiple --keywords: 'any' (OR, default) or 'all' (AND)")
    p.add_argument("--limit", type=int, default=200, help="Max results (default: 200)")
    p.add_argument("--show-tags", action="store_true", help="Show computed tags per card")
    p.add_argument("--format", choices=["table", "csv", "names"], default="table",
                   help="Output format (default: table)")
    p.add_argument("--legal", metavar="FORMAT",
                   help="Filter to cards legal in format: standard, pioneer, modern, legacy, vintage, all")
    p.add_argument("--ranked", action="store_true",
                   help="Sort output by power score (highest first)")
    p.add_argument("--min-power", type=float, default=None, metavar="SCORE",
                   help="Exclude cards with power score below this threshold")
    return p


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    # Resolve paths
    from mtg_utils import RepoPaths
    paths = RepoPaths()
    repo_root = paths.root

    # Parse type list
    types: Optional[List[str]] = None
    if args.types:
        requested = [t.strip().lower() for t in args.types.split(",")]
        invalid = [t for t in requested if t not in CARD_TYPES]
        if invalid:
            print(f"ERROR: Unknown type(s): {', '.join(invalid)}", file=sys.stderr)
            print(f"Valid types: {', '.join(CARD_TYPES)}", file=sys.stderr)
            sys.exit(2)
        types = requested

    # Parse tag list
    tag_filters: Optional[List[str]] = None
    if args.tags:
        tag_filters = [t.strip().lower() for t in args.tags.split(",")]

    # Parse rarity list
    rarities: Optional[List[str]] = None
    if args.rarity:
        rarities = [r.strip().lower() for r in args.rarity.split(",")]

    # Parse keyword list
    keyword_filters: Optional[List[str]] = None
    if args.keywords:
        keyword_filters = [k.strip() for k in args.keywords.split(",")]

    # Load and filter
    all_cards = load_cards(repo_root, types)

    if not all_cards:
        from mtg_utils import RepoPaths
        print(f"No cards loaded. Check that {RepoPaths.CARDS_DIR_NAME}/ exists and is populated.", file=sys.stderr)
        sys.exit(2)

    # --legal filter: pre-filter cards by format legality
    args_legal = getattr(args, "legal", None)
    if args_legal and args_legal != "all":
        has_legal_col = any("legal_formats" in card for card in all_cards[:10])
        if not has_legal_col:
            print("Note: --legal filter skipped — database lacks legal_formats column.", file=sys.stderr)
            print("Run scripts/fetch_and_categorize_cards.py to rebuild with legality data.", file=sys.stderr)
        else:
            filtered = []
            for card in all_cards:
                legal_formats = card.get("legal_formats", "")
                if not legal_formats:
                    continue
                if args_legal in legal_formats.split(","):
                    filtered.append(card)
            all_cards = filtered

    results = filter_cards(
        all_cards,
        color_filter=args.colors,
        oracle_filter=args.oracle,
        name_filter=args.name,
        subtype_filter=args.subtype,
        tag_filters=tag_filters,
        tags_mode=args.tags_mode,
        cmc_min=args.cmc_min,
        cmc_max=args.cmc_max,
        rarities=rarities,
        keyword_filters=keyword_filters,
        keywords_mode=args.keywords_mode,
    )

    if not results:
        print("\nNo cards matched the given filters.\n", file=sys.stderr)
        sys.exit(1)

    # --min-power filter
    if args.min_power is not None:
        results = [(card, tags) for card, tags in results
                    if compute_power_score(card) >= args.min_power]
        if not results:
            print("\nNo cards matched the given power threshold.\n", file=sys.stderr)
            sys.exit(1)

    # --ranked: sort by power score descending
    if args.ranked:
        results.sort(key=lambda ct: compute_power_score(ct[0]), reverse=True)

    if args.format == "csv":
        print_csv(results, args.limit)
    elif args.format == "names":
        print_names(results, args.limit)
    else:
        print_table(results, show_tags=args.show_tags, limit=args.limit,
                    show_power=args.ranked)

    sys.exit(0)


if __name__ == "__main__":
    main()


# ─── Synergy profile (used exclusively by synergy_analysis.py) ───────────────

import re as _syn_re

# Directional oracle text patterns: mechanic → {source patterns, payoff patterns}
# source = card PRODUCES this resource
# payoff = card REACTS TO / CONSUMES this resource
_DIRECTIONAL: Dict[str, Dict[str, List[str]]] = {
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

_BASIC_TYPES = {
    "plains", "island", "swamp", "mountain", "forest", "basic", "land",
    "enchantment", "artifact", "creature", "instant", "sorcery",
    "planeswalker", "legendary", "snow", "tribal", "battle",
}
_CREATURE_TYPE_RE = _syn_re.compile(
    r"(?:Creature|Legendary Creature)[^—]*—\s*(.+?)(?:\s*//|\s*$)", _syn_re.IGNORECASE
)


def _parse_subtypes(type_line: str) -> Set[str]:
    """Extract creature subtypes from a type line string."""
    m = _CREATURE_TYPE_RE.search(type_line)
    if not m:
        return set()
    raw = m.group(1).strip()
    return {t.strip().lower() for t in raw.split() if t.strip().lower() not in _BASIC_TYPES}


def compute_synergy_profile(card: Dict) -> Dict:
    """
    Return a rich synergy profile for use by synergy_analysis.py.

    Keys:
        broad_tags      set[str]  — existing compute_tags() output (broad, undirected)
        source_tags     set[str]  — mechanics this card PRODUCES/ENABLES
        payoff_tags     set[str]  — mechanics this card REACTS TO / CONSUMES
        subtypes        set[str]  — parsed creature subtypes (lowercase)
        keywords        set[str]  — MTG mechanical keywords (lowercase)
        cmc             float     — converted mana cost
        type_line       str       — raw type line
        oracle_text     str       — oracle text (lowercased)
        is_land         bool      — True if card is a land
        name            str       — card name
    """
    oracle = card.get("oracle_text", "").lower()
    type_line = card.get("type_line", "")
    name = card.get("name", "")

    broad = compute_tags(card)

    source_tags: Set[str] = set()
    payoff_tags: Set[str] = set()
    for mechanic, patterns in _DIRECTIONAL.items():
        for pat in patterns["source"]:
            if _syn_re.search(pat, oracle, _syn_re.IGNORECASE):
                source_tags.add(mechanic)
                break
        for pat in patterns["payoff"]:
            if _syn_re.search(pat, oracle, _syn_re.IGNORECASE):
                payoff_tags.add(mechanic)
                break

    # Lifelink in keywords = definitive lifegain source
    kw_raw = card.get("keywords", "")
    keywords = {k.strip().lower() for k in kw_raw.split(";") if k.strip()}
    if "lifelink" in keywords:
        source_tags.add("lifegain")

    # Enchantments themselves register as enchantress producers
    if "enchantment" in card.get("type_line", "").lower():
        source_tags.add("enchantress")

    subtypes = _parse_subtypes(type_line)

    try:
        cmc = float(card.get("cmc", 0) or 0)
    except (ValueError, TypeError):
        cmc = 0.0

    is_land = "land" in type_line.lower()

    return {
        "broad_tags":  broad,
        "source_tags": source_tags,
        "payoff_tags": payoff_tags,
        "subtypes":    subtypes,
        "keywords":    keywords,
        "cmc":         cmc,
        "type_line":   type_line,
        "oracle_text": oracle,
        "is_land":     is_land,
        "name":        name,
    }
