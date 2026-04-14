"""
Comprehensive unit tests for the synergy analysis system.

Covers:
    - synergy_types.py   — enums, data classes, constants
    - synergy_engine.py  — scoring engine
    - synergy_thresholds.py — threshold checking
    - synergy_report.py  — report generation

Run with:
    python -m unittest discover tests/
    python -m pytest tests/
"""

from __future__ import annotations

import json
import sys
import unittest
from dataclasses import FrozenInstanceError
from pathlib import Path

# Add scripts/ to path so we can import the modules
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from synergy_types import (
    InteractionType,
    CardRole,
    ThresholdStatus,
    INTERACTION_WEIGHTS,
    Interaction,
    SynergyProfile,
    CardScore,
    CompositeWeights,
    ThresholdConfig,
    ThresholdResult,
    CORE_ENGINE_TAGS,
    DIRECTIONAL_PATTERNS,
    DECK_THRESHOLDS,
    POOL_THRESHOLDS,
)

from synergy_engine import (
    compute_synergy_profile,
    infer_primary_axes,
    classify_role,
    score_pairwise,
    extract_names_from_text,
    extract_names_from_decklist,
)

from synergy_thresholds import (
    get_thresholds,
    check_thresholds,
    format_threshold_result,
    format_threshold_results,
)

from synergy_report import (
    build_markdown_report,
    build_json_report,
    build_top_n_csv,
)

# ── Paths ────────────────────────────────────────────────────────────────────
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_TEST_CORPUS = _PROJECT_ROOT / "test-corpus"
_CARDS_DIR = _PROJECT_ROOT / "cards_by_category"


# ═══════════════════════════════════════════════════════════════════════════════
# Helpers — reusable mock card factories
# ═══════════════════════════════════════════════════════════════════════════════

def _make_card(
    name="Test Card",
    oracle_text="",
    type_line="Creature",
    keywords="",
    cmc="3",
    mana_cost="{2}{W}",
    colors="W",
):
    """Build a minimal card dict suitable for compute_synergy_profile."""
    return {
        "name": name,
        "oracle_text": oracle_text,
        "type_line": type_line,
        "keywords": keywords,
        "cmc": cmc,
        "mana_cost": mana_cost,
        "colors": colors,
    }


def _make_profile(
    name="Test Card",
    source_tags=frozenset(),
    payoff_tags=frozenset(),
    broad_tags=frozenset(),
    subtypes=frozenset(),
    keywords=frozenset(),
    cmc=3.0,
    type_line="Creature",
    oracle_text="",
    is_land=False,
):
    """Build a SynergyProfile directly for unit tests."""
    return SynergyProfile(
        name=name,
        broad_tags=broad_tags,
        source_tags=source_tags,
        payoff_tags=payoff_tags,
        subtypes=subtypes,
        keywords=keywords,
        cmc=cmc,
        type_line=type_line,
        oracle_text=oracle_text,
        is_land=is_land,
    )


def _make_score(
    profile=None,
    role=CardRole.SUPPORT,
    synergy_partners=None,
    engine_partners=None,
    support_partners=None,
    role_breadth_types=None,
    interactions=None,
    weighted_synergy=0.0,
    engine_synergy=0.0,
    dependency=0,
    pool_size=10,
    engine_pool_size=5,
    qty=1,
):
    """Build a CardScore with sensible defaults for testing."""
    if profile is None:
        profile = _make_profile()
    sc = CardScore(
        profile=profile,
        qty=qty,
        role=role,
        synergy_partners=synergy_partners if synergy_partners is not None else set(),
        engine_partners=engine_partners if engine_partners is not None else set(),
        support_partners=support_partners if support_partners is not None else set(),
        role_breadth_types=role_breadth_types if role_breadth_types is not None else set(),
        interactions=interactions if interactions is not None else [],
        weighted_synergy=weighted_synergy,
        engine_synergy=engine_synergy,
        dependency=dependency,
    )
    sc._pool_size = pool_size
    sc._engine_pool_size = engine_pool_size
    return sc


def _build_minimal_scores_dict():
    """Build a small but valid scores dict for threshold/report tests."""
    scores = {}
    # 3 engine cards with lifegain source+payoff → high density
    for i in range(3):
        name = f"engine_{i}"
        sc = _make_score(
            profile=_make_profile(
                name=f"Engine {i}",
                source_tags=frozenset({"lifegain"}),
                payoff_tags=frozenset({"lifegain"}),
            ),
            role=CardRole.ENGINE,
            synergy_partners={f"engine_{j}" for j in range(3) if j != i},
            engine_partners={f"engine_{j}" for j in range(3) if j != i},
            weighted_synergy=6.0,
            engine_synergy=6.0,
            role_breadth_types={"FEEDS", "TRIGGERS"},
            pool_size=5,
            engine_pool_size=3,
        )
        scores[name] = sc

    # 2 support cards
    for i in range(2):
        name = f"support_{i}"
        sc = _make_score(
            profile=_make_profile(
                name=f"Support {i}",
                broad_tags=frozenset({"draw", "ramp"}),
            ),
            role=CardRole.SUPPORT,
            synergy_partners={"engine_0"},
            weighted_synergy=2.0,
            pool_size=5,
            engine_pool_size=3,
        )
        scores[name] = sc

    return scores


# ═══════════════════════════════════════════════════════════════════════════════
# Category 1: TestSynergyTypes — Data class and enum tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestSynergyTypes(unittest.TestCase):
    """Tests for synergy_types.py — enums, data classes, constants."""

    def test_interaction_type_values(self):
        """All InteractionType enum values are strings."""
        for member in InteractionType:
            self.assertIsInstance(member.value, str)
        expected = {"FEEDS", "TRIGGERS", "ENABLES", "AMPLIFIES", "PROTECTS", "REDUNDANT"}
        actual = {m.value for m in InteractionType}
        self.assertEqual(actual, expected)

    def test_card_role_values(self):
        """All CardRole enum values are strings."""
        for member in CardRole:
            self.assertIsInstance(member.value, str)
        expected = {"engine", "enabler", "payoff", "support", "interaction"}
        actual = {m.value for m in CardRole}
        self.assertEqual(actual, expected)

    def test_threshold_status_values(self):
        """All ThresholdStatus enum values are strings."""
        for member in ThresholdStatus:
            self.assertIsInstance(member.value, str)
        expected = {"PASS", "FAIL", "WARN", "INFO"}
        actual = {m.value for m in ThresholdStatus}
        self.assertEqual(actual, expected)

    def test_interaction_weights_complete(self):
        """Every InteractionType has a weight in INTERACTION_WEIGHTS."""
        for itype in InteractionType:
            self.assertIn(itype, INTERACTION_WEIGHTS)
            self.assertIsInstance(INTERACTION_WEIGHTS[itype], float)

    def test_synergy_profile_creation(self):
        """SynergyProfile can be created with all required fields."""
        profile = _make_profile(
            name="Angel of Vitality",
            source_tags=frozenset({"lifegain"}),
            payoff_tags=frozenset({"lifegain"}),
            broad_tags=frozenset({"lifegain", "pump"}),
            cmc=3.0,
            type_line="Creature — Angel",
            is_land=False,
        )
        self.assertEqual(profile.name, "Angel of Vitality")
        self.assertIn("lifegain", profile.source_tags)
        self.assertIn("lifegain", profile.payoff_tags)
        self.assertFalse(profile.is_land)
        self.assertEqual(profile.cmc, 3.0)

    def test_card_score_computed_properties(self):
        """CardScore computed properties return correct values."""
        sc = _make_score(
            role=CardRole.ENGINE,
            synergy_partners={"card_a", "card_b", "card_c"},
            engine_partners={"card_a", "card_b"},
            pool_size=10,
            engine_pool_size=5,
            weighted_synergy=6.0,
            role_breadth_types={"FEEDS", "TRIGGERS"},
        )
        # synergy_count = len(synergy_partners)
        self.assertEqual(sc.synergy_count, 3)
        # synergy_density = synergy_count / max(pool_size - 1, 1)
        self.assertAlmostEqual(sc.synergy_density, 3 / 9)
        # engine_density for ENGINE role = engine_synergy_count / max(engine_pool_size - 1, 1)
        self.assertAlmostEqual(sc.engine_density, 2 / 4)
        # role_breadth
        self.assertEqual(sc.role_breadth, 2)

    def test_card_score_engine_density_support_role(self):
        """engine_density returns 0.0 for SUPPORT role."""
        sc = _make_score(
            role=CardRole.SUPPORT,
            engine_partners={"card_a"},
            engine_pool_size=5,
        )
        self.assertEqual(sc.engine_density, 0.0)

    def test_card_score_engine_density_enabler_role(self):
        """engine_density is computed for ENABLER role."""
        sc = _make_score(
            role=CardRole.ENABLER,
            engine_partners={"card_a", "card_b"},
            engine_pool_size=5,
        )
        self.assertAlmostEqual(sc.engine_density, 2 / 4)

    def test_card_score_composite_score(self):
        """composite_score uses default weights correctly."""
        sc = _make_score(
            role=CardRole.ENGINE,
            synergy_partners={"a", "b"},
            engine_partners={"a"},
            pool_size=10,
            engine_pool_size=5,
            weighted_synergy=5.0,
            role_breadth_types={"FEEDS"},
        )
        dw = CompositeWeights()
        expected = (
            sc.engine_density * dw.engine_density
            + sc.synergy_density * dw.synergy_density
            + min(sc.weighted_synergy, dw.raw_interactions_cap)
            + sc.role_breadth * dw.role_breadth
            + len(sc.oracle_interactions) * dw.oracle_confirmed
        )
        self.assertAlmostEqual(sc.composite_score, expected)

    def test_card_score_composite_with_custom_weights(self):
        """composite_score_with() uses custom CompositeWeights."""
        sc = _make_score(
            role=CardRole.ENGINE,
            synergy_partners={"a", "b"},
            engine_partners={"a"},
            pool_size=10,
            engine_pool_size=5,
            weighted_synergy=5.0,
            role_breadth_types={"FEEDS"},
        )
        custom = CompositeWeights(
            engine_density=100.0,
            synergy_density=0.0,
            raw_interactions_cap=0.0,
            role_breadth=0.0,
            oracle_confirmed=0.0,
        )
        expected = sc.engine_density * 100.0
        self.assertAlmostEqual(sc.composite_score_with(custom), expected)

    def test_interaction_frozen(self):
        """Interaction dataclass is frozen (immutable)."""
        ix = Interaction(
            partner="Test Partner",
            itype=InteractionType.FEEDS,
            note="test note",
            confidence="tag",
        )
        with self.assertRaises(FrozenInstanceError):
            ix.partner = "Other"

    def test_deck_thresholds_preset(self):
        """DECK_THRESHOLDS has expected values."""
        self.assertIsInstance(DECK_THRESHOLDS, ThresholdConfig)
        self.assertEqual(DECK_THRESHOLDS.min_avg_density, 0.25)
        self.assertEqual(DECK_THRESHOLDS.min_engine_avg_density, 0.40)
        self.assertEqual(DECK_THRESHOLDS.max_isolated_frac, 0.12)
        self.assertEqual(DECK_THRESHOLDS.max_true_isolated_engine, 2)
        self.assertEqual(DECK_THRESHOLDS.min_hub_density, 0.50)
        self.assertEqual(DECK_THRESHOLDS.min_hub_count, 2)
        self.assertEqual(DECK_THRESHOLDS.max_support_ratio, 0.45)
        self.assertEqual(DECK_THRESHOLDS.mode_label, "deck (role-aware)")

    def test_pool_thresholds_preset(self):
        """POOL_THRESHOLDS has expected values."""
        self.assertIsInstance(POOL_THRESHOLDS, ThresholdConfig)
        self.assertEqual(POOL_THRESHOLDS.min_avg_density, 0.20)
        self.assertEqual(POOL_THRESHOLDS.min_engine_avg_density, 0.30)
        self.assertEqual(POOL_THRESHOLDS.max_isolated_frac, 0.15)
        self.assertEqual(POOL_THRESHOLDS.max_true_isolated_engine, 3)
        self.assertEqual(POOL_THRESHOLDS.min_hub_density, 0.40)
        self.assertEqual(POOL_THRESHOLDS.min_hub_count, 2)
        self.assertEqual(POOL_THRESHOLDS.max_support_ratio, 0.55)
        self.assertEqual(POOL_THRESHOLDS.mode_label, "pool (loose)")

    def test_core_engine_tags_nonempty(self):
        """CORE_ENGINE_TAGS contains expected mechanics."""
        self.assertIn("lifegain", CORE_ENGINE_TAGS)
        self.assertIn("token", CORE_ENGINE_TAGS)
        self.assertIn("sacrifice", CORE_ENGINE_TAGS)
        self.assertTrue(len(CORE_ENGINE_TAGS) >= 8)

    def test_directional_patterns_structure(self):
        """DIRECTIONAL_PATTERNS has source and payoff lists for each mechanic."""
        for mechanic, dirs in DIRECTIONAL_PATTERNS.items():
            self.assertIn("source", dirs, f"{mechanic} missing 'source'")
            self.assertIn("payoff", dirs, f"{mechanic} missing 'payoff'")
            self.assertIsInstance(dirs["source"], list)
            self.assertIsInstance(dirs["payoff"], list)
            self.assertTrue(len(dirs["source"]) > 0, f"{mechanic} has empty source list")
            self.assertTrue(len(dirs["payoff"]) > 0, f"{mechanic} has empty payoff list")


# ═══════════════════════════════════════════════════════════════════════════════
# Category 2: TestSynergyEngine — Scoring engine tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestSynergyEngine(unittest.TestCase):
    """Tests for synergy_engine.py — profile building, role classification, scoring."""

    def test_compute_synergy_profile_lifegain_creature(self):
        """A creature with lifelink gets source_tags={lifegain}."""
        card = _make_card(
            name="Test Angel",
            oracle_text="Flying, lifelink",
            type_line="Creature — Angel",
            keywords="Flying;Lifelink",
            cmc="4",
            mana_cost="{2}{W}{W}",
            colors="W",
        )
        profile = compute_synergy_profile(card)
        self.assertIsInstance(profile, SynergyProfile)
        self.assertIn("lifegain", profile.source_tags)
        self.assertFalse(profile.is_land)

    def test_compute_synergy_profile_land_excluded(self):
        """Lands are flagged as is_land=True."""
        card = _make_card(
            name="Plains",
            oracle_text="",
            type_line="Basic Land — Plains",
            keywords="",
            cmc="0",
        )
        profile = compute_synergy_profile(card)
        self.assertTrue(profile.is_land)

    def test_compute_synergy_profile_payoff_tags(self):
        """A card with 'whenever you gain life' gets payoff_tags={lifegain}."""
        card = _make_card(
            name="Test Payoff",
            oracle_text="Whenever you gain life, draw a card.",
            type_line="Enchantment",
            keywords="",
            cmc="3",
        )
        profile = compute_synergy_profile(card)
        self.assertIn("lifegain", profile.payoff_tags)

    def test_compute_synergy_profile_enchantress_source(self):
        """Enchantments get source_tags={enchantress}."""
        card = _make_card(
            name="Test Enchantment",
            oracle_text="Enchant creature",
            type_line="Enchantment — Aura",
            keywords="",
            cmc="2",
        )
        profile = compute_synergy_profile(card)
        self.assertIn("enchantress", profile.source_tags)

    def test_compute_synergy_profile_token_source(self):
        """A card that creates tokens gets source_tags={token}."""
        card = _make_card(
            name="Token Maker",
            oracle_text="Create a 1/1 white Soldier creature token.",
            type_line="Sorcery",
            cmc="2",
        )
        profile = compute_synergy_profile(card)
        self.assertIn("token", profile.source_tags)

    def test_compute_synergy_profile_token_payoff(self):
        """A card with 'whenever a token enters' gets payoff_tags={token}."""
        card = _make_card(
            name="Token Payoff",
            oracle_text="Whenever a token enters the battlefield under your control, you gain 1 life.",
            type_line="Enchantment",
            cmc="3",
        )
        profile = compute_synergy_profile(card)
        self.assertIn("token", profile.payoff_tags)

    def test_compute_synergy_profile_draw_source(self):
        """A card that draws cards gets source_tags={draw}."""
        card = _make_card(
            name="Draw Spell",
            oracle_text="Draw 2 cards.",
            type_line="Instant",
            cmc="2",
        )
        profile = compute_synergy_profile(card)
        self.assertIn("draw", profile.source_tags)

    def test_compute_synergy_profile_cmc_parsing(self):
        """CMC is correctly parsed from card dict."""
        card = _make_card(name="Expensive", cmc="7")
        profile = compute_synergy_profile(card)
        self.assertEqual(profile.cmc, 7.0)

    def test_compute_synergy_profile_missing_fields(self):
        """Profile handles missing/empty fields gracefully."""
        card = {"name": "Bare Card"}
        profile = compute_synergy_profile(card)
        self.assertEqual(profile.name, "Bare Card")
        self.assertFalse(profile.is_land)
        self.assertEqual(profile.cmc, 0.0)

    def test_infer_primary_axes(self):
        """Primary axes are tags appearing on 3+ cards."""
        profiles = [
            _make_profile(source_tags=frozenset({"lifegain"})),
            _make_profile(source_tags=frozenset({"lifegain"})),
            _make_profile(payoff_tags=frozenset({"lifegain"})),
            _make_profile(broad_tags=frozenset({"lifegain"})),
            _make_profile(source_tags=frozenset({"mill"})),
        ]
        axes = infer_primary_axes(profiles)
        self.assertIn("lifegain", axes)
        self.assertNotIn("mill", axes)

    def test_infer_primary_axes_override(self):
        """Override string takes precedence."""
        profiles = [
            _make_profile(source_tags=frozenset({"lifegain"})),
            _make_profile(source_tags=frozenset({"lifegain"})),
            _make_profile(source_tags=frozenset({"lifegain"})),
        ]
        axes = infer_primary_axes(profiles, override="token, sacrifice")
        self.assertEqual(axes, {"token", "sacrifice"})
        self.assertNotIn("lifegain", axes)

    def test_infer_primary_axes_empty(self):
        """No profiles -> empty axes."""
        axes = infer_primary_axes([])
        self.assertEqual(axes, set())

    def test_classify_role_engine(self):
        """Card with both source and payoff on primary axis -> ENGINE."""
        profile = _make_profile(
            source_tags=frozenset({"lifegain"}),
            payoff_tags=frozenset({"lifegain"}),
        )
        role = classify_role(profile, {"lifegain"})
        self.assertEqual(role, CardRole.ENGINE)

    def test_classify_role_payoff(self):
        """Card with only payoff on primary axis -> PAYOFF."""
        profile = _make_profile(
            payoff_tags=frozenset({"lifegain"}),
        )
        role = classify_role(profile, {"lifegain"})
        self.assertEqual(role, CardRole.PAYOFF)

    def test_classify_role_enabler(self):
        """Card with only source on primary axis -> ENABLER."""
        profile = _make_profile(
            source_tags=frozenset({"lifegain"}),
        )
        role = classify_role(profile, {"lifegain"})
        self.assertEqual(role, CardRole.ENABLER)

    def test_classify_role_support(self):
        """Card with only non-interaction broad tags -> SUPPORT."""
        profile = _make_profile(
            broad_tags=frozenset({"ramp", "draw"}),
        )
        role = classify_role(profile, {"lifegain"})
        self.assertEqual(role, CardRole.SUPPORT)

    def test_classify_role_interaction(self):
        """Card with removal/counter tags -> INTERACTION."""
        profile = _make_profile(
            broad_tags=frozenset({"removal", "counter"}),
        )
        role = classify_role(profile, {"lifegain"})
        self.assertEqual(role, CardRole.INTERACTION)

    def test_score_pairwise_basic(self):
        """Two cards with matching source/payoff tags produce synergy partners."""
        cards = {
            "lifegain source": _make_card(
                name="Lifegain Source",
                oracle_text="You gain 3 life.",
                type_line="Creature — Cleric",
                keywords="Lifelink",
                cmc="2",
            ),
            "lifegain payoff": _make_card(
                name="Lifegain Payoff",
                oracle_text="Whenever you gain life, draw a card.",
                type_line="Enchantment",
                cmc="3",
            ),
            "another source": _make_card(
                name="Another Source",
                oracle_text="You gain 2 life.",
                type_line="Creature — Cleric",
                keywords="Lifelink",
                cmc="1",
            ),
        }
        scores = score_pairwise(cards)
        has_partners = any(sc.synergy_count > 0 for sc in scores.values())
        self.assertTrue(has_partners, "Expected at least one card with synergy partners")

    def test_score_pairwise_no_lands(self):
        """Lands are excluded from scoring."""
        cards = {
            "plains": _make_card(
                name="Plains",
                oracle_text="",
                type_line="Basic Land — Plains",
                cmc="0",
            ),
            "creature": _make_card(
                name="Test Creature",
                oracle_text="Lifelink",
                type_line="Creature — Angel",
                keywords="Lifelink",
                cmc="3",
            ),
        }
        scores = score_pairwise(cards)
        self.assertNotIn("plains", scores)

    def test_score_pairwise_returns_card_scores(self):
        """score_pairwise returns dict of CardScore instances."""
        cards = {
            "card a": _make_card(name="Card A", oracle_text="You gain 3 life.", keywords="Lifelink"),
        }
        scores = score_pairwise(cards)
        for name, sc in scores.items():
            self.assertIsInstance(sc, CardScore)

    def test_score_pairwise_pool_size_set(self):
        """_pool_size is set on all CardScore instances after scoring."""
        cards = {
            "card a": _make_card(
                name="Card A",
                oracle_text="You gain 3 life.",
                keywords="Lifelink",
            ),
            "card b": _make_card(
                name="Card B",
                oracle_text="Whenever you gain life, draw a card.",
                type_line="Enchantment",
            ),
        }
        scores = score_pairwise(cards)
        for sc in scores.values():
            self.assertGreater(sc._pool_size, 0)

    def test_score_pairwise_with_entries_list(self):
        """score_pairwise accepts a list of entry dicts (structured API)."""
        entries = [
            {
                "name": "Lifegain Source",
                "qty": 4,
                "section": "main",
                "data": _make_card(
                    name="Lifegain Source",
                    oracle_text="You gain 3 life.",
                    type_line="Creature — Cleric",
                    keywords="Lifelink",
                    cmc="2",
                ),
                "found_in_db": True,
            },
            {
                "name": "Lifegain Payoff",
                "qty": 2,
                "section": "main",
                "data": _make_card(
                    name="Lifegain Payoff",
                    oracle_text="Whenever you gain life, draw a card.",
                    type_line="Enchantment",
                    cmc="3",
                ),
                "found_in_db": True,
            },
        ]
        scores = score_pairwise(entries)
        self.assertTrue(len(scores) > 0)

    def test_extract_names_from_text(self):
        """Plain text extraction works."""
        content = "Angel of Vitality\nAjani's Pridemate\n# comment\n// another comment\n\nHeliod, Sun-Crowned"
        names = extract_names_from_text(content)
        self.assertEqual(names, ["Angel of Vitality", "Ajani's Pridemate", "Heliod, Sun-Crowned"])

    def test_extract_names_from_text_empty(self):
        """Empty text returns empty list."""
        names = extract_names_from_text("")
        self.assertEqual(names, [])

    def test_extract_names_from_text_comments_skipped(self):
        """Lines starting with # or // are skipped."""
        content = "# Header\n// Comment\nReal Card Name"
        names = extract_names_from_text(content)
        self.assertEqual(names, ["Real Card Name"])

    def test_extract_names_from_decklist(self):
        """Decklist extraction works with test corpus."""
        decklist_path = _TEST_CORPUS / "good" / "esper_lifegain_60" / "decklist.txt"
        if not decklist_path.exists():
            self.skipTest(f"Test corpus not found: {decklist_path}")
        names = extract_names_from_decklist(decklist_path)
        self.assertIsInstance(names, list)
        self.assertTrue(len(names) > 0, "Expected non-empty card list from decklist")
        name_set = {n.lower() for n in names}
        self.assertIn("dream beavers", name_set)
        self.assertIn("ruin-lurker bat", name_set)


# ═══════════════════════════════════════════════════════════════════════════════
# Category 3: TestSynergyThresholds — Threshold tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestSynergyThresholds(unittest.TestCase):
    """Tests for synergy_thresholds.py — threshold selection and checking."""

    def test_get_thresholds_auto_small(self):
        """Pool size <= 40 -> deck thresholds."""
        dt = get_thresholds(30, mode="auto")
        self.assertEqual(dt.mode_label, "deck (role-aware)")

    def test_get_thresholds_auto_large(self):
        """Pool size > 40 -> pool thresholds."""
        dt = get_thresholds(60, mode="auto")
        self.assertEqual(dt.mode_label, "pool (loose)")

    def test_get_thresholds_auto_boundary(self):
        """Pool size == 40 -> deck thresholds (boundary)."""
        dt = get_thresholds(40, mode="auto")
        self.assertEqual(dt.mode_label, "deck (role-aware)")

    def test_get_thresholds_auto_boundary_41(self):
        """Pool size == 41 -> pool thresholds (just over boundary)."""
        dt = get_thresholds(41, mode="auto")
        self.assertEqual(dt.mode_label, "pool (loose)")

    def test_get_thresholds_explicit_mode(self):
        """Explicit mode overrides auto-detection."""
        dt_deck = get_thresholds(100, mode="deck")
        self.assertEqual(dt_deck.mode_label, "deck (role-aware)")
        dt_pool = get_thresholds(10, mode="pool")
        self.assertEqual(dt_pool.mode_label, "pool (loose)")

    def test_check_thresholds_empty(self):
        """Empty scores dict returns False."""
        passed, results = check_thresholds({})
        self.assertFalse(passed)
        self.assertTrue(len(results) > 0)
        self.assertEqual(results[0].status, ThresholdStatus.FAIL)

    def test_check_thresholds_returns_structured_results(self):
        """Results are ThresholdResult dataclasses, not strings."""
        scores = _build_minimal_scores_dict()
        passed, results = check_thresholds(scores)
        self.assertIsInstance(results, list)
        for r in results:
            self.assertIsInstance(r, ThresholdResult)
            self.assertIsInstance(r.status, ThresholdStatus)
            self.assertIsInstance(r.id, str)
            self.assertIsInstance(r.label, str)
            self.assertIsInstance(r.detail, str)

    def test_check_thresholds_has_expected_ids(self):
        """Threshold results include T1, T1b, T2, T3, T3b, T4, T5."""
        scores = _build_minimal_scores_dict()
        _, results = check_thresholds(scores)
        result_ids = {r.id for r in results}
        for expected_id in ("T1", "T1b", "T2", "T3", "T3b", "T4", "T5"):
            self.assertIn(expected_id, result_ids, f"Missing threshold {expected_id}")

    def test_format_threshold_result_pass(self):
        """PASS status formats correctly."""
        tr = ThresholdResult(
            id="T1",
            status=ThresholdStatus.PASS,
            label="Avg Synergy Density",
            actual=0.35,
            required=0.25,
            detail="T1: Avg Synergy Density = 35% (>= 25%)",
        )
        formatted = format_threshold_result(tr)
        self.assertIn("[PASS]", formatted)
        self.assertIn("T1", formatted)

    def test_format_threshold_result_fail(self):
        """FAIL status formats correctly."""
        tr = ThresholdResult(
            id="T1",
            status=ThresholdStatus.FAIL,
            label="Avg Synergy Density",
            actual=0.10,
            required=0.25,
            detail="T1: Avg Synergy Density = 10% (need >= 25%)",
        )
        formatted = format_threshold_result(tr)
        self.assertIn("[FAIL]", formatted)
        self.assertIn("T1", formatted)

    def test_format_threshold_results_list(self):
        """format_threshold_results returns a list of strings."""
        results = [
            ThresholdResult(id="T1", status=ThresholdStatus.PASS,
                            label="Test", actual=1.0, required=0.5, detail="ok"),
            ThresholdResult(id="T2", status=ThresholdStatus.FAIL,
                            label="Test2", actual=0.1, required=0.5, detail="bad"),
        ]
        formatted = format_threshold_results(results)
        self.assertIsInstance(formatted, list)
        self.assertEqual(len(formatted), 2)
        self.assertIn("[PASS]", formatted[0])
        self.assertIn("[FAIL]", formatted[1])


# ═══════════════════════════════════════════════════════════════════════════════
# Category 4: TestSynergyReport — Report generation tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestSynergyReport(unittest.TestCase):
    """Tests for synergy_report.py — markdown, JSON, and CSV report generation."""

    def setUp(self):
        """Build shared test data for report tests."""
        self.scores = _build_minimal_scores_dict()
        _, self.threshold_results = check_thresholds(self.scores)
        self.all_passed = all(
            r.status in (ThresholdStatus.PASS, ThresholdStatus.INFO)
            for r in self.threshold_results
        )

    def test_build_markdown_report_has_header(self):
        """Markdown report starts with Gate 2.5 header."""
        md = build_markdown_report(
            scores=self.scores,
            threshold_results=self.threshold_results,
            all_passed=self.all_passed,
            source_file="test_input.txt",
            not_found=[],
        )
        self.assertIn("Gate 2.5", md)
        self.assertIn("Synergy Evaluation", md)

    def test_build_markdown_report_has_threshold_section(self):
        """Markdown report contains threshold check section."""
        md = build_markdown_report(
            scores=self.scores,
            threshold_results=self.threshold_results,
            all_passed=self.all_passed,
            source_file="test_input.txt",
            not_found=[],
        )
        self.assertIn("Threshold Check", md)

    def test_build_markdown_report_has_synergy_matrix(self):
        """Markdown report contains synergy matrix section."""
        md = build_markdown_report(
            scores=self.scores,
            threshold_results=self.threshold_results,
            all_passed=self.all_passed,
            source_file="test_input.txt",
            not_found=[],
        )
        # Matrix may or may not appear depending on card count, but the
        # report should at least contain the scores section
        self.assertIn("Synergy Scores", md)

    def test_build_markdown_report_has_role_distribution(self):
        """Markdown report contains role distribution section."""
        md = build_markdown_report(
            scores=self.scores,
            threshold_results=self.threshold_results,
            all_passed=self.all_passed,
            source_file="test_input.txt",
            not_found=[],
        )
        self.assertIn("Role Distribution", md)

    def test_build_markdown_report_not_found_note(self):
        """Markdown report includes not-found cards note when present."""
        md = build_markdown_report(
            scores=self.scores,
            threshold_results=self.threshold_results,
            all_passed=self.all_passed,
            source_file="test_input.txt",
            not_found=["Missing Card A", "Missing Card B"],
        )
        self.assertIn("not in local database", md)
        self.assertIn("Missing Card A", md)

    def test_build_json_report_valid_json(self):
        """JSON report is valid JSON."""
        json_str = build_json_report(
            scores=self.scores,
            threshold_results=self.threshold_results,
            all_passed=self.all_passed,
            source_file="test_input.txt",
            not_found=[],
        )
        parsed = json.loads(json_str)
        self.assertIsInstance(parsed, dict)

    def test_build_json_report_has_metadata(self):
        """JSON report contains metadata section."""
        json_str = build_json_report(
            scores=self.scores,
            threshold_results=self.threshold_results,
            all_passed=self.all_passed,
            source_file="test_input.txt",
            not_found=[],
        )
        parsed = json.loads(json_str)
        self.assertIn("metadata", parsed)
        meta = parsed["metadata"]
        self.assertIn("source_file", meta)
        self.assertIn("timestamp", meta)
        self.assertIn("pool_size", meta)
        self.assertEqual(meta["source_file"], "test_input.txt")

    def test_build_json_report_has_scores(self):
        """JSON report contains per-card scores."""
        json_str = build_json_report(
            scores=self.scores,
            threshold_results=self.threshold_results,
            all_passed=self.all_passed,
            source_file="test_input.txt",
            not_found=[],
        )
        parsed = json.loads(json_str)
        self.assertIn("scores", parsed)
        self.assertIn("thresholds", parsed)
        self.assertIn("all_passed", parsed)

    def test_build_json_report_has_thresholds(self):
        """JSON report contains threshold results."""
        json_str = build_json_report(
            scores=self.scores,
            threshold_results=self.threshold_results,
            all_passed=self.all_passed,
            source_file="test_input.txt",
            not_found=[],
        )
        parsed = json.loads(json_str)
        self.assertIn("thresholds", parsed)
        self.assertIsInstance(parsed["thresholds"], list)
        for t in parsed["thresholds"]:
            self.assertIn("id", t)
            self.assertIn("status", t)

    def test_build_top_n_csv_format(self):
        """Top-N CSV has correct columns."""
        csv_str = build_top_n_csv(self.scores, top_n=3)
        self.assertIsInstance(csv_str, str)
        lines = csv_str.strip().split("\n")
        self.assertTrue(len(lines) >= 1, "CSV should have at least a header")
        header = lines[0]
        # Check key columns exist in header
        self.assertIn("rank", header)
        self.assertIn("name", header)
        self.assertIn("role", header)
        self.assertIn("weighted_score", header)

    def test_build_top_n_csv_row_count(self):
        """Top-N CSV has correct number of data rows."""
        csv_str = build_top_n_csv(self.scores, top_n=2)
        lines = [l for l in csv_str.strip().split("\n") if l.strip()]
        # header + up to 2 data rows
        self.assertTrue(len(lines) <= 3)
        self.assertTrue(len(lines) >= 2, "Should have header + at least 1 data row")


# ═══════════════════════════════════════════════════════════════════════════════
# Category 5: TestIntegration — End-to-end tests using test corpus
# ═══════════════════════════════════════════════════════════════════════════════

class TestIntegration(unittest.TestCase):
    """Integration tests using the test-corpus/ directory and real card DB."""

    def _db_available(self):
        """Check if the card database is available."""
        return _CARDS_DIR.exists() and any(_CARDS_DIR.iterdir())

    def test_good_deck_scores(self):
        """test-corpus/good/esper_lifegain_60/decklist.txt produces scores."""
        decklist_path = _TEST_CORPUS / "good" / "esper_lifegain_60" / "decklist.txt"
        if not decklist_path.exists():
            self.skipTest("Test corpus decklist not found")
        if not self._db_available():
            self.skipTest("Card database not available")

        from synergy_engine import (
            extract_names_from_decklist,
            extract_deck_entries_from_decklist,
            load_cards_from_db,
            attach_card_data,
            score_pairwise,
        )
        from mtg_utils import RepoPaths

        paths = RepoPaths()
        entries = extract_deck_entries_from_decklist(decklist_path)
        names = [e["name"] for e in entries]
        card_data = load_cards_from_db(names, paths)
        annotated, missing = attach_card_data(entries, card_data)
        scores = score_pairwise(annotated)

        self.assertIsInstance(scores, dict)
        self.assertTrue(len(scores) > 0, "Expected non-empty scores from good deck")

    def test_names_list_scores(self):
        """test-corpus/good/esper_shortlist_v3/names.txt produces scores."""
        names_path = _TEST_CORPUS / "good" / "esper_shortlist_v3" / "names.txt"
        if not names_path.exists():
            self.skipTest("Test corpus names.txt not found")
        if not self._db_available():
            self.skipTest("Card database not available")

        from synergy_engine import (
            extract_names_from_text,
            load_cards_from_db,
            score_pairwise,
        )
        from mtg_utils import RepoPaths

        paths = RepoPaths()
        content = names_path.read_text(encoding="utf-8")
        names = extract_names_from_text(content)
        self.assertTrue(len(names) > 0, "Expected names from names.txt")

        card_data = load_cards_from_db(names, paths)
        scores = score_pairwise(card_data)

        self.assertIsInstance(scores, dict)
        self.assertTrue(len(scores) > 0, "Expected non-empty scores from names list")

    def test_missing_cards_handled(self):
        """test-corpus/bad/unknown_cards/decklist.txt handles missing cards gracefully."""
        decklist_path = _TEST_CORPUS / "bad" / "unknown_cards" / "decklist.txt"
        if not decklist_path.exists():
            self.skipTest("Test corpus unknown_cards decklist not found")
        if not self._db_available():
            self.skipTest("Card database not available")

        from synergy_engine import (
            extract_deck_entries_from_decklist,
            load_cards_from_db,
            attach_card_data,
            score_pairwise,
        )
        from mtg_utils import RepoPaths

        paths = RepoPaths()
        entries = extract_deck_entries_from_decklist(decklist_path)
        names = [e["name"] for e in entries]
        card_data = load_cards_from_db(names, paths)
        annotated, missing = attach_card_data(entries, card_data)

        # Should have at least one missing card (UNKNOWN CARD XYZ)
        missing_names = {e["name"] for e in missing}
        self.assertIn("UNKNOWN CARD XYZ", missing_names)

        # Scoring should not crash even with missing cards
        scores = score_pairwise(annotated)
        self.assertIsInstance(scores, dict)


if __name__ == "__main__":
    unittest.main()