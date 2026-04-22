"""Auto-build logic for MTG deck construction.

Extracts the auto-build algorithm (land analysis, Karsten mana base,
card utilities, CSV manipulation) from the GUI into a reusable module.

The main entry point is :func:`auto_build_decklist`, which takes a
candidate pool CSV and produces a complete 60-card decklist with
sideboard, using synergy scores and Karsten mana-base math.
"""
from __future__ import annotations

import csv
import difflib
import io
import re
import sys
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable

__all__ = [
    # constants
    "COLOR_ORDER",
    "MANA_NAMES",
    "SCORE_SORT_KEYS",
    "BASIC_FOR_COLOR",
    "SUBTYPE_COLOR",
    "TAP_ALWAYS",
    "TAP_CONDITIONAL",
    "TAP_NEVER",
    # functions
    "normalize_colors",
    "sort_and_rewrite_csv",
    "merge_scores_into_candidate_pool",
    "auto_build_decklist",
]

# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────
COLOR_ORDER = "WUBRG"

MANA_NAMES: dict[str, str] = {
    "W": "White", "U": "Blue", "B": "Black", "R": "Red", "G": "Green",
}

SCORE_SORT_KEYS: list[str] = [
    "synergy_density", "engine_density", "weighted_score",
    "engine_score", "role_breadth", "synergy_score",
    "oracle_interactions",
]

_KARSTEN: dict[tuple[int, int], int] = {
    (1, 1): 14, (1, 2): 13, (1, 3): 12, (1, 4): 11, (1, 5): 11,
    (2, 2): 18, (2, 3): 16, (2, 4): 15, (2, 5): 14,
    (3, 3): 22, (3, 4): 20, (3, 5): 18,
}

BASIC_FOR_COLOR: dict[str, str] = {
    "W": "Plains", "U": "Island", "B": "Swamp",
    "R": "Mountain", "G": "Forest",
}
SUBTYPE_COLOR: dict[str, str] = {
    "Plains": "W", "Island": "U", "Swamp": "B",
    "Mountain": "R", "Forest": "G",
}

TAP_ALWAYS      = "always"
TAP_CONDITIONAL = "conditional"
TAP_NEVER       = "never"

_COLOR_WORDS: dict[str, str] = {
    "white": "W", "blue": "U", "black": "B", "red": "R", "green": "G",
}

_GENERIC_NOUNS: set[str] = {
    "creature", "creatures", "permanent", "permanents", "land", "lands",
    "spell", "spells", "token", "tokens", "nontoken", "artifact", "artifacts",
    "enchantment", "enchantments", "player", "opponent", "card", "cards",
    "source", "type", "ability", "counter", "life", "mana", "damage",
    "graveyard", "library", "hand", "battlefield", "stack", "exile",
    "color", "controller", "owner", "target", "chosen", "other",
}

_TRIBAL_LAND_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"whenever (?:a|an|another) (\w+) enters", re.IGNORECASE),
    re.compile(r"whenever (?:a|an|another) (\w+) attacks", re.IGNORECASE),
    re.compile(r"whenever (?:a|an|another) (\w+) dies", re.IGNORECASE),
    re.compile(r"whenever (?:a|an|another) (\w+) you control", re.IGNORECASE),
    re.compile(r"(\w+)s? you control get", re.IGNORECASE),
    re.compile(r"(\w+)s? you control have", re.IGNORECASE),
    re.compile(r"target (\w+) gets", re.IGNORECASE),
    re.compile(r"each (\w+) you control", re.IGNORECASE),
    re.compile(r"number of (\w+)s? you control", re.IGNORECASE),
    re.compile(r"another (\w+) enters", re.IGNORECASE),
    re.compile(r"(\w+)s? you control gain", re.IGNORECASE),
    re.compile(r"sacrifice (?:a|an) (\w+)", re.IGNORECASE),
    re.compile(r"tap an untapped (\w+) you control", re.IGNORECASE),
    # Spell/card type references (catches Bucolic Ranch, etc.)
    re.compile(r"cast (?:a|an) (\w+) spell", re.IGNORECASE),
    re.compile(r"(?:a|an|it's a) (\w+) card", re.IGNORECASE),
    re.compile(r"spend this mana only to cast (?:a|an) (\w+)", re.IGNORECASE),
    re.compile(r"search .{0,30} for .{0,10}(\w+) card", re.IGNORECASE),
]


# ─────────────────────────────────────────────────────────────────────────────
# Default log callback — prints to stderr when no GUI callback is provided
# ─────────────────────────────────────────────────────────────────────────────
def _default_log(message: str, level: str) -> None:
    """Fallback logger that writes to *stderr*."""
    prefix = {"info": "INFO", "warn": "WARN", "error": "ERR ", "success": " OK "}
    tag = prefix.get(level, "    ")
    print("[%s] %s" % (tag, message), file=sys.stderr)


# ─────────────────────────────────────────────────────────────────────────────
# Pure helpers
# ─────────────────────────────────────────────────────────────────────────────
def normalize_colors(raw: str) -> str:
    """Normalize a color string to canonical WUBRG order."""
    seen = dict.fromkeys(c for c in raw.upper() if c in COLOR_ORDER)
    return "".join(c for c in COLOR_ORDER if c in seen)


def _safe_float(val: object) -> float:
    try:
        return float(str(val).strip().rstrip("%"))
    except (ValueError, TypeError):
        return -1.0


def _sort_key(row: dict) -> tuple:
    return tuple(-_safe_float(row.get(c, "0")) for c in SCORE_SORT_KEYS)


def _is_land_card(row: dict) -> bool:
    front = row.get("type_line", "").split("//")[0].strip()
    main_part = front.split("\u2014")[0].strip()
    return "Land" in main_part.split()


def _card_type_group(row: dict) -> str:
    front = row.get("type_line", "").split("//")[0].lower()
    if "creature" in front:      return "Creatures"
    if "planeswalker" in front:  return "Planeswalkers"
    if "instant" in front:       return "Instants"
    if "sorcery" in front:       return "Sorceries"
    if "enchantment" in front:   return "Enchantments"
    if "artifact" in front:      return "Artifacts"
    return "Other Spells"


def _resolve_card_name(
    query: str,
    by_name: dict[str, dict],
) -> tuple[dict | None, str, str]:
    """Fuzzy card-name matching against a *by_name* lookup dict.

    Returns ``(row_or_None, resolved_name, match_status)``.
    """
    key = query.lower().strip()
    if key in by_name:
        return by_name[key], by_name[key].get("name", query).strip(), "exact"
    all_keys = list(by_name.keys())
    close = difflib.get_close_matches(key, all_keys, n=1, cutoff=0.72)
    if close:
        row = by_name[close[0]]
        return row, row.get("name", close[0]).strip(), "fuzzy:" + row.get("name", "")
    if len(key) >= 5:
        for pk, row in by_name.items():
            pn = row.get("name", "").strip()
            if key in pk or pk in key:
                return row, pn, "substr:" + pn
    return None, query, "not_found"


# ─────────────────────────────────────────────────────────────────────────────
# Land analysis: color detection + tap state + tribal dead check
# ─────────────────────────────────────────────────────────────────────────────
def _detect_land_colors(row: dict) -> set[str]:
    """Which WUBRG colors can this land produce for UNRESTRICTED use?

    Three layers of defense against fake 5-color lands:
      1. "spend this mana only" anywhere in oracle → subtypes only
      2. {T}: Add {C}  +  "any color" anywhere    → colorless utility land
         (Bucolic Ranch, Eclipsed Realms, Captivating Cave, Unknown Shores)
      3. Per-line parsing skips costed / restricted abilities
      4. No oracle → produced_mana capped at ≤ 2 colors
    """
    colors: set[str] = set()

    # ── 1) Basic land subtypes — always reliable ────────────────────
    tl = row.get("type_line", "")
    if "\u2014" in tl:
        subtypes = tl.split("\u2014", 1)[1]
    elif " - " in tl:
        subtypes = tl.split(" - ", 1)[1]
    else:
        subtypes = ""
    for subtype, color in SUBTYPE_COLOR.items():
        if re.search(r"\b" + re.escape(subtype) + r"\b", subtypes):
            colors.add(color)

    oracle = (row.get("oracle_text", "") or "").strip()
    ol = oracle.lower() if oracle else ""

    # ── 2) Nuclear: "spend this mana only" anywhere → subtypes only ─
    if ol and "spend this mana only" in ol:
        return colors

    # ── 3) Heuristic: {T}: Add {C}  +  "any color" = utility junk ──
    #    Every real 5-color land (City of Brass, Mana Confluence) taps
    #    directly for any color — it does NOT also have "{T}: Add {C}".
    #    Lands that have BOTH are always restricted/costed utility:
    #      Bucolic Ranch, Eclipsed Realms, Captivating Cave,
    #      Unknown Shores, Shimmering Grotto, etc.
    #    Skip only if no basic subtypes already found.
    if ol and not colors:
        has_free_colorless = bool(
            re.search(r"\{t\}[^:]*:\s*add\s*\{c\}", ol))
        has_any_color = bool(
            re.search(r"\badd\b.{0,30}\bany\b.{0,15}\bcolor\b", ol))
        if has_free_colorless and has_any_color:
            return set()

    # ── 4) Per-line oracle parsing ──────────────────────────────────
    if oracle:
        for line in oracle.split("\n"):
            ll = line.lower().strip()
            if "add" not in ll:
                continue
            if "spend this mana only" in ll:
                continue
            if ":" in ll:
                cost_part = ll.split(":")[0]
                if re.search(r"\{\d+\}", cost_part):
                    continue

            for seg in re.findall(r"add\b(.{1,60})", ll):
                for c in re.findall(r"\{([wubrg])\}", seg):
                    colors.add(c.upper())
                if re.search(r"\bany\b.{0,15}\bcolor\b", seg):
                    colors.update("WUBRG")
                if re.search(r"\bany type\b", seg):
                    colors.update("WUBRG")
                if re.search(
                        r"\b(chosen color|color of your choice)\b", seg):
                    colors.update("WUBRG")
                for word, code in _COLOR_WORDS.items():
                    if re.search(r"\b" + word + r"\b", seg):
                        colors.add(code)

        return colors

    # ── 5) No oracle — conservative produced_mana, cap ≤ 2 colors ──
    pm = str(row.get("produced_mana", "") or "").upper()
    if pm:
        pm_colors = {c for c in "WUBRG" if c in pm}
        if len(pm_colors) <= 2:
            colors.update(pm_colors)

    return colors


def _enters_tapped(row: dict) -> str:
    """Returns TAP_NEVER, TAP_CONDITIONAL, or TAP_ALWAYS."""
    oracle = row.get("oracle_text", "").lower()
    if not oracle.strip():
        return TAP_NEVER
    has_etb_tapped = ("enters the battlefield tapped" in oracle
                      or "enters tapped" in oracle)
    if not has_etb_tapped:
        return TAP_NEVER
    conditional_patterns = [
        "unless you control", "unless you pay", "you may pay",
        "you may reveal", "if you control two or fewer",
        "if you control fewer", "if you control a ",
        "if an opponent controls", "you may sacrifice",
        "if you don't, it enters",
    ]
    for pat in conditional_patterns:
        if pat in oracle:
            return TAP_CONDITIONAL
    return TAP_ALWAYS


def _land_is_acceptable(
    produced: set[str],
    active_set: set[str],
    tap_state: str,
) -> bool:
    """Reject lands where a basic is strictly better."""
    if not produced:
        return False
    relevant = produced & active_set
    if not relevant:
        return False
    off_colors = produced - active_set
    if off_colors and len(relevant) < 2:
        return False
    if tap_state == TAP_ALWAYS and len(relevant) < 2:
        return False
    if tap_state == TAP_ALWAYS and off_colors:
        return False
    return True


def _land_has_dead_tribal(row: dict, deck_subtypes: set[str]) -> bool:
    """Does this land reference a creature type the deck doesn't have?

    Returns True = dead tribal (reject). False = fine to keep.
    """
    oracle = row.get("oracle_text", "")
    if not oracle:
        return False

    referenced_types: set[str] = set()
    for pat in _TRIBAL_LAND_PATTERNS:
        for m in pat.finditer(oracle):
            word = m.group(1).lower().rstrip("s")
            if word not in _GENERIC_NOUNS and len(word) >= 3:
                referenced_types.add(word)

    if not referenced_types:
        return False

    deck_lower = {s.lower().rstrip("s") for s in deck_subtypes}
    for ref in referenced_types:
        if ref in deck_lower:
            return False

    return True


def _count_pips(mana_cost: str) -> dict[str, int]:
    pips = {c: 0 for c in "WUBRG"}
    for m in re.findall(r"\{([WUBRG])\}", mana_cost, re.IGNORECASE):
        pips[m.upper()] += 1
    return pips


def _karsten_required(pips: int, turn: int) -> int:
    pips = min(pips, 3)
    turn = max(1, min(turn, 5))
    return _KARSTEN.get((pips, turn), 11)


# ─────────────────────────────────────────────────────────────────────────────
# CSV sorting + merging
# ─────────────────────────────────────────────────────────────────────────────
def sort_and_rewrite_csv(filepath: Path) -> tuple[bool, int]:
    """Sort a CSV file by synergy score columns in-place.

    Returns ``(changed, row_count)``.
    """
    if not filepath.exists():
        return False, 0
    text = filepath.read_text(encoding="utf-8")
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        return False, 0
    if not any(c in reader.fieldnames for c in SCORE_SORT_KEYS):
        return False, 0
    rows = list(reader)
    if not rows:
        return False, 0
    rows.sort(key=_sort_key)
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=reader.fieldnames,
                       extrasaction="ignore", lineterminator="\n")
    w.writeheader()
    w.writerows(rows)
    filepath.write_text(buf.getvalue(), encoding="utf-8")
    return True, len(rows)


def merge_scores_into_candidate_pool(deck_dir: str) -> tuple[bool, int]:
    """Merge synergy scores from ``top_200.csv`` into ``candidate_pool.csv``.

    Returns ``(changed, row_count)``.
    """
    pool_path = Path(deck_dir) / "candidate_pool.csv"
    top_path  = Path(deck_dir) / "top_200.csv"
    if not pool_path.exists() or not top_path.exists():
        return False, 0
    scores: dict[str, dict[str, str]] = {}
    top_text = top_path.read_text(encoding="utf-8")
    tr = csv.DictReader(io.StringIO(top_text))
    tf = list(tr.fieldnames or [])
    sc = [c for c in SCORE_SORT_KEYS if c in tf]
    if not sc:
        return False, 0
    for row in tr:
        n = row.get("name", "").strip()
        if n:
            scores[n] = {c: row.get(c, "") for c in sc}
    pt = pool_path.read_text(encoding="utf-8")
    pr = csv.DictReader(io.StringIO(pt))
    pf = list(pr.fieldnames or [])
    pool_rows = list(pr)
    if not pool_rows:
        return False, 0
    nc = [c for c in sc if c not in pf]
    mf = pf + nc
    for row in pool_rows:
        n = row.get("name", "").strip()
        cs = scores.get(n, {})
        for c in sc:
            v = cs.get(c, "")
            if c in nc:
                row[c] = v
            elif c in pf and not row.get(c):
                row[c] = v
    pool_rows.sort(key=_sort_key)
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=mf, extrasaction="ignore",
                       lineterminator="\n")
    w.writeheader()
    w.writerows(pool_rows)
    pool_path.write_text(buf.getvalue(), encoding="utf-8")
    return True, len(pool_rows)


# ─────────────────────────────────────────────────────────────────────────────
# AUTO-BUILD DECKLIST
# ─────────────────────────────────────────────────────────────────────────────
def auto_build_decklist(
    deck_dir: str,
    colors: str,
    focus_cards: list[str] | None = None,
    *,
    log: Callable[[str, str], None] | None = None,
) -> tuple[bool, str, list[tuple[str, str]]]:
    """Build a complete decklist from a candidate pool CSV.

    Parameters
    ----------
    deck_dir:
        Path to the deck directory containing ``candidate_pool.csv``.
    colors:
        WUBRG color identity string (e.g. ``"WU"``).
    focus_cards:
        Optional list of card names to lock into the mainboard.
    log:
        Optional ``(message, level)`` callback where *level* is one of
        ``"info"``, ``"warn"``, ``"error"``, ``"success"``.  Falls back
        to printing on *stderr* when *None*.

    Returns
    -------
    tuple[bool, str, list[tuple[str, str]]]
        ``(success, summary_or_error, focus_log)`` where *focus_log* is
        a list of ``(message, level)`` pairs for the GUI to display.
    """
    if log is None:
        log = _default_log

    focus_log: list[tuple[str, str]] = []
    pool_path = Path(deck_dir) / "candidate_pool.csv"

    if not pool_path.exists():
        return False, "candidate_pool.csv not found", focus_log

    with open(pool_path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            return False, "Empty CSV", focus_log
        has_scores = any(c in reader.fieldnames for c in SCORE_SORT_KEYS)
        rows = list(reader)

    if len(rows) < 10:
        return False, "Only %d candidates" % len(rows), focus_log
    if not has_scores:
        return False, "No synergy scores yet", focus_log

    by_name: dict[str, dict] = {}
    for r in rows:
        n = r.get("name", "").strip()
        if n:
            by_name[n.lower()] = r

    pool_lands = [r for r in rows if _is_land_card(r)]
    nonlands   = [r for r in rows if not _is_land_card(r)]

    if not nonlands:
        return False, "No nonland cards", focus_log

    sample = nonlands[:min(30, len(nonlands))]
    avg_cmc = (sum(_safe_float(r.get("cmc", "0")) for r in sample)
               / max(1, len(sample)))
    n_lands    = 22 if avg_cmc < 2.3 else 26 if avg_cmc > 3.5 else 24
    n_nonlands = 60 - n_lands

    def _copies_for(r: dict, *, is_focus: bool = False) -> int:
        """Determine copy count based on CMC, Legendary status, and rarity.

        Focus cards use the same logic as regular cards — the "focus"
        aspect means guaranteed inclusion, not a fixed quantity.
        """
        cmc = _safe_float(r.get("cmc", "0"))
        leg = "Legendary" in r.get("type_line", "")
        rarity = r.get("rarity", "").lower()
        if cmc >= 6:        return 1
        if leg:             return 2
        if cmc >= 5:        return 2
        if cmc >= 4:        return 3
        # CMC 0-3: scale by rarity (mythics/rares are often build-arounds)
        if rarity == "mythic":
            return 2
        if rarity == "rare":
            return 3
        return 4

    def _copy_reason(r: dict, copies: int, *, is_focus: bool = False) -> str:
        parts: list[str] = []
        if is_focus:
            parts.append("Focus")
        cmc = _safe_float(r.get("cmc", "0"))
        if "Legendary" in r.get("type_line", "") and copies <= 2:
            parts.append("Legendary")
        if cmc >= 5:
            parts.append("CMC %d" % int(cmc))
        rarity = r.get("rarity", "").lower()
        if rarity in ("mythic", "rare") and copies <= 3 and cmc < 4:
            parts.append(rarity.title())
        return " + ".join(parts)

    # ══════════════════════════════════════════════════════════════════
    # PHASE 1: Lock focus cards — guaranteed inclusion, qty by CMC/rarity
    # ══════════════════════════════════════════════════════════════════
    mainboard: list[tuple[int, str, dict]] = []
    used: set[str] = set()
    slots = 0
    focus_land_names: list[str] = []

    if focus_cards:
        focus_log.append(("Focus Card Resolution:", "info"))
        for fc in focus_cards:
            fc_clean = fc.strip()
            if not fc_clean:
                continue
            row, resolved, status = _resolve_card_name(fc_clean, by_name)
            if row is None:
                focus_log.append(
                    ("  \u2717 %s -- NOT FOUND" % fc_clean, "error"))
                continue
            if resolved.lower() in used:
                focus_log.append(
                    ("  \u2713 %s -- duplicate" % fc_clean, "info"))
                continue
            if _is_land_card(row):
                focus_land_names.append(resolved)
                mt = status.split(":")[0] if ":" in status else status
                if status == "exact":
                    focus_log.append(
                        ("  \u2713 %s -- locked as land" % resolved,
                         "success"))
                else:
                    focus_log.append(
                        ("  \u2713 \"%s\" -> %s (%s) -- locked as land"
                         % (fc_clean, resolved, mt), "warn"))
                continue
            copies = min(_copies_for(row, is_focus=True), n_nonlands - slots)
            if copies <= 0:
                focus_log.append(
                    ("  \u26a0 %s -- no slots" % resolved, "warn"))
                continue
            mainboard.append((copies, resolved, row))
            used.add(resolved.lower())
            slots += copies
            reason = _copy_reason(row, copies, is_focus=True)
            rs = " (%s)" % reason if reason else ""
            mt = status.split(":")[0] if ":" in status else status
            if status == "exact":
                focus_log.append(
                    ("  \u2713 %s -> %dx%s" % (resolved, copies, rs),
                     "success"))
            else:
                focus_log.append(
                    ("  \u2713 \"%s\" -> %s (%s) -> %dx%s"
                     % (fc_clean, resolved, mt, copies, rs), "warn"))
        focus_log.append(("", "info"))

    # ══════════════════════════════════════════════════════════════════
    # PHASE 2: Fill nonlands by score (non-focus uses CMC scaling)
    # ══════════════════════════════════════════════════════════════════
    for r in nonlands:
        if slots >= n_nonlands:
            break
        name = r.get("name", "").strip()
        if not name or name.lower() in used:
            continue
        copies = min(_copies_for(r, is_focus=False), n_nonlands - slots)
        if copies <= 0:
            break
        mainboard.append((copies, name, r))
        used.add(name.lower())
        slots += copies

    # ══════════════════════════════════════════════════════════════════
    # PHASE 3: Colour analysis
    # ══════════════════════════════════════════════════════════════════
    total_pips: dict[str, int] = {c: 0 for c in "WUBRG"}
    hardest: dict[str, tuple[int, int]] = {}

    for copies, _, r in mainboard:
        mc = r.get("mana_cost", "")
        cmc = max(1, int(_safe_float(r.get("cmc", "1"))))
        pips = _count_pips(mc)
        for c in "WUBRG":
            if pips[c] > 0:
                total_pips[c] += pips[c] * copies
                prev = hardest.get(c, (0, 99))
                if pips[c] > prev[0] or (pips[c] == prev[0]
                                          and cmc < prev[1]):
                    hardest[c] = (pips[c], cmc)

    active_colors = [c for c in "WUBRG"
                     if c in colors.upper() and total_pips.get(c, 0) > 0]
    if not active_colors:
        active_colors = [c for c in "WUBRG" if c in colors.upper()]
    if not active_colors:
        active_colors = ["W"]
    active_set = set(active_colors)

    min_sources: dict[str, int] = {}
    for c in active_colors:
        if c in hardest:
            p, t = hardest[c]
            min_sources[c] = _karsten_required(p, t)
        else:
            min_sources[c] = 10

    # ══════════════════════════════════════════════════════════════════
    # PHASE 4: Mana base
    # ══════════════════════════════════════════════════════════════════
    csrc: dict[str, int] = {c: 0 for c in "WUBRG"}
    land_picks: list[tuple[int, str, set[str]]] = []
    land_used: set[str] = set()
    land_slots = 0

    max_tapped_slots = 2 if avg_cmc < 2.5 else 4
    tapped_slots_used = 0

    # ── Gather creature subtypes for tribal land check ───────────────
    deck_subtypes: set[str] = set()
    for _, _, r in mainboard:
        tl = r.get("type_line", "")
        if "\u2014" in tl:
            sub_part = tl.split("\u2014", 1)[1]
        elif " - " in tl:
            sub_part = tl.split(" - ", 1)[1]
        else:
            sub_part = ""
        for word in sub_part.split():
            cleaned = word.strip(",").strip()
            if cleaned and len(cleaned) >= 3:
                deck_subtypes.add(cleaned)

    untapped_candidates: list[tuple[dict, set[str], str]] = []
    tapped_candidates: list[tuple[dict, set[str], str]] = []
    rej_colorless: list[str] = []
    rej_offid: list[str] = []
    rej_tapped: list[str] = []
    rej_tribal: list[str] = []

    for r in pool_lands:
        name = r.get("name", "").strip()
        tl = r.get("type_line", "")
        if not name or "Basic" in tl:
            continue

        produced = _detect_land_colors(r)
        tap = _enters_tapped(r)

        pm = str(r.get("produced_mana", "") or "").upper()
        if pm and not any(c in pm for c in "WUBRG"):
            rej_colorless.append(name)
            continue

        if not _land_is_acceptable(produced, active_set, tap):
            relevant = produced & active_set
            off = produced - active_set
            if not produced or not relevant:
                rej_colorless.append(name)
            elif tap == TAP_ALWAYS:
                rej_tapped.append("%s [%s, tapped]" % (
                    name, "+".join(sorted(relevant))))
            else:
                rej_offid.append("%s [%s, off:%s]" % (
                    name, "+".join(sorted(relevant)),
                    "+".join(sorted(off))))
            continue

        # Dead tribal check: land's only upside is a tribe trigger
        # the deck can't use. A basic is strictly better.
        if _land_has_dead_tribal(r, deck_subtypes):
            rej_tribal.append(name)
            continue

        relevant = produced & active_set

        if tap == TAP_ALWAYS:
            tapped_candidates.append((r, relevant, tap))
        else:
            untapped_candidates.append((r, relevant, tap))

    if rej_colorless:
        focus_log.append(
            ("  Rejected %d colorless: %s%s"
             % (len(rej_colorless), ", ".join(rej_colorless[:4]),
                "..." if len(rej_colorless) > 4 else ""),
             "info"))
    if rej_offid:
        focus_log.append(
            ("  Rejected %d off-identity: %s%s"
             % (len(rej_offid), ", ".join(rej_offid[:3]),
                "..." if len(rej_offid) > 3 else ""),
             "info"))
    if rej_tapped:
        focus_log.append(
            ("  Rejected %d tapped mono/off-id: %s%s"
             % (len(rej_tapped), ", ".join(rej_tapped[:3]),
                "..." if len(rej_tapped) > 3 else ""),
             "info"))
    if rej_tribal:
        focus_log.append(
            ("  Rejected %d dead tribal: %s%s"
             % (len(rej_tribal), ", ".join(rej_tribal[:4]),
                "..." if len(rej_tribal) > 4 else ""),
             "warn"))

    # 4a) Focus lands
    for fname in focus_land_names:
        if land_slots >= n_lands:
            break
        row = by_name.get(fname.lower())
        if not row or fname.lower() in land_used:
            continue
        produced = _detect_land_colors(row)
        tap = _enters_tapped(row)
        if not _land_is_acceptable(produced, active_set, tap):
            focus_log.append(
                ("  \u26a0 %s REJECTED (makes %s, deck is %s, tap=%s)"
                 % (fname,
                    "+".join(sorted(produced)) or "colorless",
                    "+".join(sorted(active_colors)), tap),
                 "error"))
            continue
        if _land_has_dead_tribal(row, deck_subtypes):
            focus_log.append(
                ("  \u26a0 %s REJECTED (dead tribal ability)" % fname,
                 "error"))
            continue
        relevant = produced & active_set
        copies = min(4, n_lands - land_slots)
        if tap == TAP_ALWAYS:
            copies = min(copies, max_tapped_slots - tapped_slots_used)
            if copies <= 0:
                focus_log.append(
                    ("  \u26a0 %s REJECTED (tapped budget full: %d/%d)"
                     % (fname, tapped_slots_used, max_tapped_slots),
                     "error"))
                continue
            tapped_slots_used += copies
        if copies <= 0:
            break
        land_picks.append((copies, fname, relevant))
        land_used.add(fname.lower())
        land_slots += copies
        for c in relevant:
            csrc[c] += copies

    # 4b) Scoring
    def _land_score(info: tuple[dict, set[str], str]) -> float:
        r, rel, tap = info
        s = 0.0
        if tap == TAP_NEVER:
            s += 1000.0
        elif tap == TAP_CONDITIONAL:
            s += 500.0
        s += len(rel) * 50.0
        for c in rel:
            gap = max(0, min_sources.get(c, 0) - csrc.get(c, 0))
            if gap > 0:
                s += gap * 10.0
        produced = _detect_land_colors(r)
        off = len(produced - active_set)
        s -= off * 30.0
        s += _safe_float(r.get("weighted_score", "0")) * 0.001
        return s

    untapped_candidates.sort(key=_land_score, reverse=True)
    tapped_candidates.sort(key=_land_score, reverse=True)

    # 4c) PASS 1: untapped/conditional only
    max_nb = n_lands // 2

    for r, relevant, tap in untapped_candidates:
        if land_slots >= max_nb:
            break
        name = r.get("name", "").strip()
        if not name or name.lower() in land_used:
            continue
        has_gap = any(csrc.get(c, 0) < min_sources.get(c, 0)
                      for c in relevant)
        if not has_gap and len(relevant) < 2:
            continue
        copies = min(4, max_nb - land_slots)
        if copies <= 0:
            break
        produced = _detect_land_colors(r)
        tap2 = _enters_tapped(r)
        if not _land_is_acceptable(produced, active_set, tap2):
            continue
        land_picks.append((copies, name, relevant))
        land_used.add(name.lower())
        land_slots += copies
        for c in relevant:
            csrc[c] += copies

    # 4d) PASS 2: tapped ONLY if Karsten gaps remain
    karsten_met = all(csrc.get(c, 0) >= min_sources.get(c, 0)
                      for c in active_colors)

    if not karsten_met and tapped_slots_used < max_tapped_slots:
        for r, relevant, tap in tapped_candidates:
            if land_slots >= max_nb:
                break
            if tapped_slots_used >= max_tapped_slots:
                break
            name = r.get("name", "").strip()
            if not name or name.lower() in land_used:
                continue
            has_gap = any(csrc.get(c, 0) < min_sources.get(c, 0)
                          for c in relevant)
            if not has_gap:
                continue
            copies = min(4, max_nb - land_slots)
            copies = min(copies, max_tapped_slots - tapped_slots_used)
            if copies <= 0:
                break
            produced = _detect_land_colors(r)
            tap2 = _enters_tapped(r)
            if not _land_is_acceptable(produced, active_set, tap2):
                continue
            land_picks.append((copies, name, relevant))
            land_used.add(name.lower())
            land_slots += copies
            tapped_slots_used += copies
            for c in relevant:
                csrc[c] += copies
            focus_log.append(
                ("  \u26a0 %s: %dx tapped (gap-fill, %d/%d tapped budget)"
                 % (name, copies, tapped_slots_used, max_tapped_slots),
                 "warn"))

    # 4e) Basics
    remaining = n_lands - land_slots
    basic_alloc: list[tuple[int, str]] = []

    if remaining > 0:
        gaps = {c: max(0, min_sources.get(c, 0) - csrc.get(c, 0))
                for c in active_colors}
        total_gap = sum(gaps.values())

        if total_gap == 0:
            total_p = max(1, sum(total_pips.get(c, 0)
                                 for c in active_colors))
            allocated = 0
            for i, c in enumerate(active_colors):
                if i == len(active_colors) - 1:
                    n = remaining - allocated
                else:
                    n = max(1, round(remaining * total_pips.get(c, 1)
                                     / total_p))
                n = max(0, min(n, remaining - allocated))
                if n > 0:
                    basic_alloc.append((n, BASIC_FOR_COLOR[c]))
                    csrc[c] += n
                    allocated += n
            if allocated < remaining and basic_alloc:
                on, oname = basic_alloc[0]
                basic_alloc[0] = (on + remaining - allocated, oname)
        else:
            allocated = 0
            gc = [c for c in active_colors if gaps.get(c, 0) > 0]
            for i, c in enumerate(gc):
                if i == len(gc) - 1:
                    n = remaining - allocated
                else:
                    n = max(1, round(remaining * gaps[c]
                                     / max(1, total_gap)))
                n = max(1, min(n, remaining - allocated))
                if n > 0:
                    basic_alloc.append((n, BASIC_FOR_COLOR[c]))
                    csrc[c] += n
                    allocated += n
            if allocated < remaining:
                left = remaining - allocated
                best = max(active_colors,
                           key=lambda c: total_pips.get(c, 0))
                found = False
                for idx, (bn, bname) in enumerate(basic_alloc):
                    if bname == BASIC_FOR_COLOR[best]:
                        basic_alloc[idx] = (bn + left, bname)
                        found = True
                        break
                if not found:
                    basic_alloc.append((left, BASIC_FOR_COLOR[best]))
                csrc[best] += left

    # ══════════════════════════════════════════════════════════════════
    # PHASE 5: Sideboard
    # ══════════════════════════════════════════════════════════════════
    sideboard: list[tuple[int, str]] = []
    sb_slots = 0
    for r in nonlands:
        if sb_slots >= 15:
            break
        name = r.get("name", "").strip()
        if not name or name.lower() in used:
            continue
        copies = min(3, 15 - sb_slots)
        sideboard.append((copies, name))
        used.add(name.lower())
        sb_slots += copies

    # ══════════════════════════════════════════════════════════════════
    # PHASE 6: Write output
    # ══════════════════════════════════════════════════════════════════
    type_groups: dict[str, list[tuple[int, str]]] = {}
    for copies, name, r in mainboard:
        grp = _card_type_group(r)
        type_groups.setdefault(grp, []).append((copies, name))

    TYPE_ORDER = ["Creatures", "Instants", "Sorceries", "Enchantments",
                  "Artifacts", "Planeswalkers", "Other Spells"]

    nb_ct = sum(c for c, _, _ in land_picks)
    ba_ct = sum(c for c, _ in basic_alloc)
    main_total = slots + nb_ct + ba_ct
    top3 = ", ".join(n for _, n, _ in mainboard[:3])

    fp = sum(1 for m, cl in focus_log
             if cl in ("success", "warn")
             and ("\u2192" in m or "locked" in m))
    ff = sum(1 for m, cl in focus_log if cl == "error")

    lines = [
        "// Auto-generated decklist (%d main + %d sb)" % (main_total, sb_slots),
        "// Top synergy: %s" % top3,
        "// Avg CMC %.1f -> %d lands (%d nonbasic + %d basic)"
        % (avg_cmc, n_lands, nb_ct, ba_ct),
        "// Tapped budget: %d/%d slots used" % (tapped_slots_used, max_tapped_slots),
    ]
    if focus_cards:
        lines.append("// Focus: %d locked, %d not found" % (fp, ff))
        for m, cl in focus_log:
            if m.startswith("  "):
                lines.append("// %s" % m.strip())
    lines.append("//")
    lines.append("// Mana base (Karsten):")
    all_ok = True
    for c in active_colors:
        need = min_sources.get(c, 0)
        have = csrc.get(c, 0)
        ok = have >= need
        if not ok:
            all_ok = False
        tag = "OK" if ok else "SHORT %d" % (need - have)
        lines.append("//   %s (%s): %d/%d  [%s]"
                      % (MANA_NAMES.get(c, c), c, have, need, tag))
    if all_ok:
        lines.append("//   ALL COLORS OK")

    lines.append("//")
    lines.append("// Land picks:")
    for copies, name, rel in land_picks:
        row = by_name.get(name.lower(), {})
        tap = _enters_tapped(row)
        if tap == TAP_NEVER:
            tap_tag = ""
        elif tap == TAP_CONDITIONAL:
            tap_tag = " [COND]"
        else:
            tap_tag = " [TAPPED]"
        lines.append("//   %dx %s (%s)%s" % (
            copies, name, "+".join(sorted(rel)), tap_tag))
    for copies, name in basic_alloc:
        lines.append("//   %dx %s (basic, untapped)" % (copies, name))

    lines.extend(["// Review before tournament use", "", "Deck"])

    for grp in TYPE_ORDER:
        cards = type_groups.get(grp, [])
        if cards:
            lines.append("// %s" % grp)
            for copies, name in cards:
                lines.append("%d %s" % (copies, name))
            lines.append("")

    lines.append("// Lands")
    for copies, name, _ in land_picks:
        lines.append("%d %s" % (copies, name))
    for copies, name in basic_alloc:
        lines.append("%d %s" % (copies, name))
    lines.append("")
    lines.append("Sideboard")
    for copies, name in sideboard:
        lines.append("%d %s" % (copies, name))
    lines.append("")

    (Path(deck_dir) / "decklist.txt").write_text(
        "\n".join(lines), encoding="utf-8")

    shorts: list[str] = []
    for c in active_colors:
        if csrc.get(c, 0) < min_sources.get(c, 0):
            shorts.append("%s (%d/%d)" % (
                MANA_NAMES.get(c, c), csrc[c], min_sources[c]))
    fn = ""
    if focus_cards:
        fn = " | Focus: %d locked" % fp
        if ff:
            fn += ", %d MISSING" % ff
    mn = (" | Mana: Karsten OK" if not shorts
          else " | MANA WARN: %s" % ", ".join(shorts))

    summary = ("%d main + %d sb | CMC %.1f | %d lands (%dnb+%db) "
               "tapped:%d/%d%s%s"
               % (main_total, sb_slots, avg_cmc, n_lands, nb_ct, ba_ct,
                  tapped_slots_used, max_tapped_slots, fn, mn))
    return True, summary, focus_log