"""Tests for card analysis logic."""
from scripts.analysis.card_analysis import analyze_card_data
from scripts.utils.card_lookup import CardData


def test_analyze_card_data():
    """Test analysis of card data to extract properties."""
    card = CardData(
        name="Hope Estheim",
        mana_cost="{W}{U}",
        cmc=2.0,
        type_line="Creature — Angel",
        oracle_text="When ~ enters the battlefield, you gain 2 life and target opponent mills 3 cards.",
        colors=["W", "U"],
        color_identity=["W", "U"],
        rarity="Rare",
        keywords=["Flying", "Lifelink"],
        tags=["lifegain", "mill", "flying"],
        legal_formats=["Standard", "Modern"]
    )
    
    result = analyze_card_data(card)
    
    assert result["colors"] == {"W", "U"}
    assert "lifegain" in result["archetypes"]
    assert "opp_mill" in result["archetypes"]
    assert "Angel" in result["tribes"]
    assert "flying" in result["tags"]