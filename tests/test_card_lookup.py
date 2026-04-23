"""Tests for card lookup service."""
import json
from pathlib import Path
from scripts.utils.card_lookup import CardData, CardLookupService


def test_card_data_creation():
    """Test CardData dataclass creation."""
    card = CardData(
        name="Test Card",
        mana_cost="{W}{U}",
        cmc=2.0,
        type_line="Creature — Angel",
        oracle_text="When ~ enters the battlefield, you gain 2 life.",
        colors=["W", "U"],
        color_identity=["W", "U"],
        rarity="Rare",
        keywords=["Flying", "Lifelink"],
        tags=["lifegain", "flying"],
        legal_formats=["Standard", "Modern"]
    )
    
    assert card.name == "Test Card"
    assert card.cmc == 2.0
    assert card.colors == ["W", "U"]
    assert "lifegain" in card.tags


def test_lookup_service_initialization(tmp_path):
    """Test CardLookupService initialization with mock index."""
    # Create mock index file
    mock_index = {
        "version": "1.0",
        "generated": "2026-04-22T00:00:00+00:00",
        "total_cards": 10,
        "cards": {
            "test card": {
                "name": "Test Card",
                "type": "creature",
                "file": "creature/creature_t.csv",
                "mana_cost": "{W}{U}",
                "type_line": "Creature — Angel"
            }
        }
    }
    
    index_path = tmp_path / "card_index.json"
    index_path.write_text(json.dumps(mock_index))
    
    # Initialize service
    service = CardLookupService(base_path=str(tmp_path))
    result = service.initialize()
    
    assert result is True
    assert service.index is not None
    assert len(service.index["cards"]) == 1


def test_card_lookup_with_mock_csv(tmp_path):
    """Test looking up a card with mock CSV data."""
    # Create mock index
    mock_index = {
        "version": "1.0",
        "generated": "2026-04-22T00:00:00+00:00",
        "total_cards": 1,
        "cards": {
            "hope estheim": {
                "name": "Hope Estheim",
                "type": "creature",
                "file": "creature/creature_h.csv",
                "mana_cost": "{W}{U}",
                "type_line": "Creature — Angel"
            }
        }
    }
    
    index_path = tmp_path / "card_index.json"
    index_path.write_text(json.dumps(mock_index))
    
    # Create mock CSV file
    csv_dir = tmp_path / "creature"
    csv_dir.mkdir(parents=True)
    csv_path = csv_dir / "creature_h.csv"
    
    csv_data = """name,mana_cost,cmc,type_line,oracle_text,colors,color_identity,rarity,keywords,tags,legal_formats
Hope Estheim,{W}{U},2.0,Creature — Angel,"When ~ enters the battlefield, you gain 2 life.","W,U","W,U",Rare,"Flying,Lifelink","lifegain;mill;flying","Standard,Modern"
"""
    csv_path.write_text(csv_data)
    
    # Test lookup
    service = CardLookupService(base_path=str(tmp_path))
    service.initialize()
    card = service.lookup("Hope Estheim")
    
    assert card is not None
    assert card.name == "Hope Estheim"
    assert card.colors == ["W", "U"]
    assert "lifegain" in card.tags
    assert "mill" in card.tags


def test_database_age_tracking():
    """Test database age calculation."""
    from unittest.mock import patch
    from datetime import datetime, timezone
    
    service = CardLookupService()
    service.db_metadata = {
        "last_updated": "2026-04-20T00:00:00+00:00"
    }
    
    # Mock datetime.now to return a fixed time
    mock_now = datetime(2026, 4, 22, 0, 0, 0, tzinfo=timezone.utc)
    with patch('scripts.utils.card_lookup.datetime') as mock_datetime:
        mock_datetime.now.return_value = mock_now
        mock_datetime.fromisoformat = datetime.fromisoformat
        
        age = service.get_database_age()
        
        # Should be 2 days difference
        assert age is not None
        assert age.days == 2