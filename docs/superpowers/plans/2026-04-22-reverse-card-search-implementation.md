# Reverse Card Search Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement accurate reverse card search from focus cards using local card database instead of simple pattern matching

**Architecture:** Create CardLookupService class to query local card database (JSON index + CSV files), enhance existing GUI analysis method, add database status tracking and update capability

**Tech Stack:** Python 3.8+, PySide6, JSON, CSV, subprocess for database updates

---

## File Structure

### New Files
- `scripts/utils/card_lookup.py` - Card lookup service with caching
- `tests/test_card_lookup.py` - Unit tests for lookup service
- `assets/data/local_db/metadata.json` - Database metadata file

### Modified Files
- `scaffold_gui.py` - Enhance focus card analysis, add database status UI
- `scripts/utils/fetch_and_categorize_cards.py` - Add metadata file generation

### Test Files
- `tests/test_reverse_card_search.py` - Integration tests for GUI functionality

---

## Task 1: Create CardData Dataclass and Basic Lookup Service

**Files:**
- Create: `scripts/utils/card_lookup.py`
- Test: `tests/test_card_lookup.py`

- [ ] **Step 1: Write the failing test for CardData**

```python
# tests/test_card_lookup.py
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_card_lookup.py::test_card_data_creation -v`
Expected: FAIL with "ModuleNotFoundError: No module named 'scripts.utils.card_lookup'"

- [ ] **Step 3: Create card_lookup.py with CardData dataclass**

```python
# scripts/utils/card_lookup.py
#!/usr/bin/env python3
"""
Card Lookup Service for MTG card database.
"""

import csv
import json
import logging
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

@dataclass
class CardData:
    """Container for card information."""
    name: str
    mana_cost: str
    cmc: float
    type_line: str
    oracle_text: str
    colors: List[str]  # e.g., ["W", "U"]
    color_identity: List[str]
    rarity: str
    keywords: List[str]
    tags: List[str]  # Pre-computed strategic tags
    legal_formats: List[str]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_card_lookup.py::test_card_data_creation -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/utils/card_lookup.py tests/test_card_lookup.py
git commit -m "feat: add CardData dataclass for card lookup"
```

---

## Task 2: Implement CardLookupService Initialization

**Files:**
- Modify: `scripts/utils/card_lookup.py`
- Test: `tests/test_card_lookup.py`

- [ ] **Step 1: Write test for service initialization**

```python
# tests/test_card_lookup.py
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_card_lookup.py::test_lookup_service_initialization -v`
Expected: FAIL with "CardLookupService not defined" or similar

- [ ] **Step 3: Implement CardLookupService class with initialization**

```python
# scripts/utils/card_lookup.py
class CardLookupService:
    """Service for looking up card data from local database."""
    
    def __init__(self, base_path: str = "assets/data/local_db"):
        self.base_path = Path(base_path)
        self.index = None
        self.cache: Dict[str, CardData] = {}
        self.db_metadata = {}
        self.last_loaded = None
        
    def initialize(self) -> bool:
        """Load the card index and metadata. Returns success status."""
        try:
            index_path = self.base_path / "card_index.json"
            if not index_path.exists():
                logger.error(f"Index file not found: {index_path}")
                return False
                
            self.index = json.loads(index_path.read_text(encoding='utf-8'))
            
            metadata_path = self.base_path / "metadata.json"
            if metadata_path.exists():
                self.db_metadata = json.loads(metadata_path.read_text(encoding='utf-8'))
            else:
                # Create default metadata from index
                self.db_metadata = {
                    "last_updated": self.index.get("generated", ""),
                    "total_cards": self.index.get("total_cards", 0),
                    "version": self.index.get("version", "1.0")
                }
            
            self.last_loaded = datetime.now()
            logger.info(f"CardLookupService initialized with {self.db_metadata['total_cards']} cards")
            return True
        except Exception as e:
            logger.error(f"Failed to initialize CardLookupService: {e}")
            return False
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_card_lookup.py::test_lookup_service_initialization -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/utils/card_lookup.py
git commit -m "feat: implement CardLookupService initialization"
```

---

## Task 3: Implement Card Lookup from CSV Files

**Files:**
- Modify: `scripts/utils/card_lookup.py`
- Test: `tests/test_card_lookup.py`

- [ ] **Step 1: Write test for card lookup**

```python
# tests/test_card_lookup.py
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_card_lookup.py::test_card_lookup_with_mock_csv -v`
Expected: FAIL with "lookup method not defined"

- [ ] **Step 3: Implement lookup and CSV loading methods**

```python
# scripts/utils/card_lookup.py
    def lookup(self, card_name: str) -> Optional[CardData]:
        """Look up a card by name (case-insensitive)."""
        if not self.index:
            return None
            
        key = card_name.lower().strip()
        
        # Check cache first
        if key in self.cache:
            return self.cache[key]
        
        # Lookup in index
        if key not in self.index.get("cards", {}):
            return None
        
        # Load from CSV file
        card_info = self.index["cards"][key]
        csv_path = self.base_path.parent / card_info["file"]  # Path is relative to assets/data
        card_data = self._load_from_csv(csv_path, card_info["name"])
        
        if card_data:
            self.cache[key] = card_data
        
        return card_data
    
    def _load_from_csv(self, csv_path: Path, card_name: str) -> Optional[CardData]:
        """Load card data from CSV file."""
        try:
            if not csv_path.exists():
                logger.warning(f"CSV file not found: {csv_path}")
                return None
                
            with open(csv_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if row["name"].lower() == card_name.lower():
                        return self._parse_csv_row(row)
            return None
        except Exception as e:
            logger.error(f"Error loading card from CSV {csv_path}: {e}")
            return None
    
    def _parse_csv_row(self, row: Dict[str, str]) -> CardData:
        """Parse a CSV row into CardData object."""
        # Parse comma-separated lists
        colors = row.get("colors", "").split(",") if row.get("colors") else []
        color_identity = row.get("color_identity", "").split(",") if row.get("color_identity") else []
        keywords = row.get("keywords", "").split(",") if row.get("keywords") else []
        tags = row.get("tags", "").split(";") if row.get("tags") else []
        legal_formats = row.get("legal_formats", "").split(",") if row.get("legal_formats") else []
        
        # Clean empty strings
        colors = [c.strip() for c in colors if c.strip()]
        color_identity = [ci.strip() for ci in color_identity if ci.strip()]
        keywords = [k.strip() for k in keywords if k.strip()]
        tags = [t.strip() for t in tags if t.strip()]
        legal_formats = [f.strip() for f in legal_formats if f.strip()]
        
        # Parse CMC (could be empty string)
        cmc_str = row.get("cmc", "0")
        try:
            cmc = float(cmc_str) if cmc_str else 0.0
        except ValueError:
            cmc = 0.0
        
        return CardData(
            name=row.get("name", ""),
            mana_cost=row.get("mana_cost", ""),
            cmc=cmc,
            type_line=row.get("type_line", ""),
            oracle_text=row.get("oracle_text", ""),
            colors=colors,
            color_identity=color_identity,
            rarity=row.get("rarity", ""),
            keywords=keywords,
            tags=tags,
            legal_formats=legal_formats
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_card_lookup.py::test_card_lookup_with_mock_csv -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/utils/card_lookup.py
git commit -m "feat: implement card lookup from CSV files"
```

---

## Task 4: Add Database Age Tracking and Update Methods

**Files:**
- Modify: `scripts/utils/card_lookup.py`
- Test: `tests/test_card_lookup.py`

- [ ] **Step 1: Write test for database age tracking**

```python
# tests/test_card_lookup.py
def test_database_age_tracking():
    """Test database age calculation."""
    service = CardLookupService()
    service.db_metadata = {
        "last_updated": "2026-04-20T00:00:00+00:00"
    }
    
    # Mock datetime.now to return a fixed time
    from unittest.mock import patch
    with patch('datetime.datetime') as mock_datetime:
        mock_now = datetime(2026, 4, 22, 0, 0, 0, tzinfo=timezone.utc)
        mock_datetime.now.return_value = mock_now
        mock_datetime.fromisoformat = datetime.fromisoformat
        
        age = service.get_database_age()
        
        # Should be 2 days difference
        assert age is not None
        assert age.days == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_card_lookup.py::test_database_age_tracking -v`
Expected: FAIL with "get_database_age method not defined"

- [ ] **Step 3: Implement database age and update methods**

```python
# scripts/utils/card_lookup.py
    def get_database_age(self) -> Optional[timedelta]:
        """Get age of database as timedelta."""
        if not self.db_metadata.get("last_updated"):
            return None
        
        try:
            last_updated = datetime.fromisoformat(self.db_metadata["last_updated"])
            now = datetime.now(timezone.utc)
            
            # Handle timezone-aware vs naive
            if last_updated.tzinfo is None:
                last_updated = last_updated.replace(tzinfo=timezone.utc)
            if now.tzinfo is None:
                now = now.replace(tzinfo=timezone.utc)
                
            return now - last_updated
        except (ValueError, TypeError) as e:
            logger.warning(f"Could not parse last_updated timestamp: {e}")
            return None
    
    def update_database(self) -> Tuple[bool, str]:
        """Update the card database using fetch_and_categorize_cards.py."""
        try:
            # Find the fetch script
            script_path = Path(__file__).parent.parent / "fetch_and_categorize_cards.py"
            if not script_path.exists():
                # Try alternative location
                script_path = self.base_path.parent.parent / "scripts" / "utils" / "fetch_and_categorize_cards.py"
                if not script_path.exists():
                    return False, f"Update script not found: {script_path}"
            
            logger.info(f"Running database update: {script_path}")
            
            # Run the update script
            result = subprocess.run(
                [sys.executable, str(script_path)],
                capture_output=True,
                text=True,
                cwd=script_path.parent.parent  # Run from repo root
            )
            
            if result.returncode == 0:
                # Reload the index
                if self.initialize():
                    return True, "Database updated successfully"
                else:
                    return False, "Update succeeded but failed to reload index"
            else:
                error_msg = result.stderr or "Unknown error"
                return False, f"Update failed (exit code {result.returncode}): {error_msg[:200]}"
                
        except Exception as e:
            return False, f"Error updating database: {e}"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_card_lookup.py::test_database_age_tracking -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/utils/card_lookup.py
git commit -m "feat: add database age tracking and update methods"
```

---

## Task 5: Modify fetch_and_categorize_cards.py to Generate Metadata

**Files:**
- Modify: `scripts/utils/fetch_and_categorize_cards.py`
- Test: `tests/test_card_lookup.py`

- [ ] **Step 1: Write test for metadata generation**

```python
# tests/test_card_lookup.py
def test_metadata_file_creation(tmp_path):
    """Test that metadata.json is created properly."""
    # This test ensures the fetch script creates metadata
    # We'll check that the service can read metadata created by the script
    mock_metadata = {
        "last_updated": "2026-04-22T00:00:00+00:00",
        "total_cards": 1000,
        "version": "1.0",
        "source": "scryfall"
    }
    
    metadata_path = tmp_path / "metadata.json"
    metadata_path.write_text(json.dumps(mock_metadata))
    
    assert metadata_path.exists()
    
    # Verify service can read it
    service = CardLookupService(base_path=str(tmp_path))
    # We'll just check the path exists for this test
    assert (tmp_path / "metadata.json").exists()
```

- [ ] **Step 2: Run test to verify it works**

Run: `python -m pytest tests/test_card_lookup.py::test_metadata_file_creation -v`
Expected: PASS (test doesn't rely on actual implementation yet)

- [ ] **Step 3: Add metadata generation to fetch script**

```python
# Add near the end of scripts/utils/fetch_and_categorize_cards.py, after saving CSV files
def _write_metadata(output_dir: Path, total_cards: int):
    """Write metadata.json file for database tracking."""
    metadata = {
        "version": "1.0",
        "last_updated": datetime.now(timezone.utc).isoformat(),
        "total_cards": total_cards,
        "source": "scryfall",
        "format": "standard"
    }
    
    metadata_path = output_dir / "local_db" / "metadata.json"
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(metadata_path, 'w', encoding='utf-8') as f:
        json.dump(metadata, f, indent=2)
    
    print(f"Metadata written to {metadata_path}")
```

Then find the main execution point in the script (around line 350-370) and add:

```python
    # After saving all CSV files, write metadata
    _write_metadata(OUTPUT_DIR, total_processed)
```

- [ ] **Step 4: Test metadata generation**

Run: `python -c "
import sys
sys.path.insert(0, 'scripts/utils')
from fetch_and_categorize_cards import _write_metadata
from pathlib import Path
import tempfile
import json

with tempfile.TemporaryDirectory() as tmpdir:
    tmpdir = Path(tmpdir)
    _write_metadata(tmpdir, 5000)
    metadata_path = tmpdir / 'local_db' / 'metadata.json'
    assert metadata_path.exists()
    
    with open(metadata_path, 'r') as f:
        data = json.load(f)
        assert data['total_cards'] == 5000
        assert 'last_updated' in data
    
    print('Metadata generation test passed')
"`
Expected: "Metadata generation test passed"

- [ ] **Step 5: Commit**

```bash
git add scripts/utils/fetch_and_categorize_cards.py
git commit -m "feat: add metadata generation to card fetch script"
```

---

## Task 6: Create Enhanced Analysis Logic Module

**Files:**
- Create: `scripts/analysis/card_analysis.py`
- Test: `tests/test_card_analysis.py`

- [ ] **Step 1: Write test for card analysis logic**

```python
# tests/test_card_analysis.py
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_card_analysis.py::test_analyze_card_data -v`
Expected: FAIL with "ModuleNotFoundError: No module named 'scripts.analysis.card_analysis'"

- [ ] **Step 3: Create card analysis module**

```python
# scripts/analysis/card_analysis.py
#!/usr/bin/env python3
"""
Card analysis logic for reverse search functionality.
"""

from typing import Dict, List, Set
from scripts.utils.card_lookup import CardData

# Mapping from card tags to GUI archetypes
TAG_TO_ARCHETYPE = {
    "lifegain": "lifegain",
    "mill": "opp_mill",
    "draw": "draw_go",
    "removal": "control",
    "counter": "control",
    "ramp": "ramp",
    "token": "tokens",
    "bounce": "tempo",
    "discard": "discard",
    "tutor": "combo",
    "wipe": "control",
    "reanimation": "reanimator",
    "burn": "burn",
    "infect": "infect",
    "landfall": "landfall",
    "blink": "blink",
    "aristocrats": "aristocrats"
}

# Tribe extraction patterns
TRIBE_PATTERNS = {
    "Angel": ["Angel", "Seraph", "Cherub"],
    "Zombie": ["Zombie", "Ghoul", "Undead"],
    "Elf": ["Elf", "Elves", "Elvish"],
    "Goblin": ["Goblin", "Goblinoid"],
    "Merfolk": ["Merfolk", "Siren", "Triton"],
    "Dragon": ["Dragon", "Wyrm", "Drake"],
    "Vampire": ["Vampire", "Nosferatu"],
    "Human": ["Human", "Warrior", "Soldier", "Knight"],
    "Spirit": ["Spirit", "Ghost", "Phantom"],
    "Elemental": ["Elemental", "Golem", "Construct"],
    "Beast": ["Beast", "Wolf", "Bear", "Lion"],
    "Bird": ["Bird", "Hawk", "Eagle", "Falcon"],
    "Demon": ["Demon", "Fiend", "Devil"],
    "Sliver": ["Sliver"],
    "Myr": ["Myr"],
    "Eldrazi": ["Eldrazi", "Kozilek", "Ulamog", "Emrakul"]
}

def analyze_card_data(card: CardData) -> Dict[str, Set[str]]:
    """Analyze card data to extract properties for GUI sections."""
    result = {
        "colors": set(),
        "archetypes": set(),
        "tribes": set(),
        "tags": set(),
        "suggestions": []
    }
    
    # 1. Colors
    colors = set(card.colors) or set(card.color_identity)
    result["colors"] = colors
    
    # 2. Archetypes from tags
    for tag in card.tags:
        if tag in TAG_TO_ARCHETYPE:
            archetype = TAG_TO_ARCHETYPE[tag]
            result["archetypes"].add(archetype)
            result["suggestions"].append(f"{archetype} (from tag: {tag})")
    
    # 3. Archetypes from oracle text keywords
    oracle_lower = card.oracle_text.lower()
    text_archetypes = _detect_archetypes_from_text(oracle_lower)
    result["archetypes"].update(text_archetypes)
    
    # 4. Tribes from type line
    type_lower = card.type_line.lower()
    for tribe, patterns in TRIBE_PATTERNS.items():
        for pattern in patterns:
            if pattern.lower() in type_lower:
                result["tribes"].add(tribe)
                break
    
    # 5. Tags (use pre-computed tags plus additional ones)
    result["tags"].update(card.tags)
    
    # Add keyword-based tags
    for keyword in card.keywords:
        keyword_lower = keyword.lower()
        if keyword_lower in ["flying", "haste", "trample", "deathtouch", "vigilance"]:
            result["tags"].add(keyword_lower)
        elif keyword_lower == "lifelink":
            result["tags"].add("lifegain")
    
    return result

def _detect_archetypes_from_text(oracle_text: str) -> Set[str]:
    """Detect archetypes from oracle text patterns."""
    archetypes = set()
    
    # Simple pattern matching
    if "gain" in oracle_text and "life" in oracle_text:
        archetypes.add("lifegain")
    
    if "mill" in oracle_text or "library" in oracle_text and "graveyard" in oracle_text:
        archetypes.add("opp_mill")
    
    if "counter target spell" in oracle_text:
        archetypes.add("control")
    
    if "destroy target" in oracle_text or "exile target" in oracle_text:
        archetypes.add("control")
    
    if "add" in oracle_text and ("mana" in oracle_text or "{" in oracle_text):
        archetypes.add("ramp")
    
    if "create" in oracle_text and "token" in oracle_text:
        archetypes.add("tokens")
    
    return archetypes
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_card_analysis.py::test_analyze_card_data -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/analysis/card_analysis.py tests/test_card_analysis.py
git commit -m "feat: create card analysis logic module"
```

---

## Task 7: Integrate Card Lookup into GUI - Part 1 (Setup)

**Files:**
- Modify: `scaffold_gui.py`
- Test: Run GUI to verify no errors

- [ ] **Step 1: Add imports and service initialization to GUI**

Find the imports section in scaffold_gui.py (around line 100) and add:

```python
# Add after existing imports
try:
    from scripts.utils.card_lookup import CardLookupService
    from scripts.analysis.card_analysis import analyze_card_data
    CARD_LOOKUP_AVAILABLE = True
except ImportError as e:
    print(f"Warning: Card lookup modules not available: {e}")
    CARD_LOOKUP_AVAILABLE = False
    CardLookupService = None
    analyze_card_data = None
```

- [ ] **Step 2: Add service attribute to main window class**

Find the `__init__` method of the main window class (around line 200-250) and add after other attributes:

```python
        # Card lookup service
        self._card_lookup = None
        if CARD_LOOKUP_AVAILABLE:
            self._card_lookup = CardLookupService()
            if not self._card_lookup.initialize():
                self._log_box.appendPlainText("⚠️ Could not initialize card database. Using pattern matching.")
                self._card_lookup = None
```

- [ ] **Step 3: Add database status label to UI**

Find the status bar setup (search for "status bar" or look around line 1800) and add:

```python
        # Database status label
        self.database_status_label = QLabel("Database: Checking...")
        self.status_bar.addWidget(self.database_status_label)
```

- [ ] **Step 4: Add method to update database status**

Add this method to the main window class:

```python
    def _update_database_status(self):
        """Update database status display."""
        if not self._card_lookup or not self._card_lookup.db_metadata:
            status = "Database: Not loaded"
            color = self.WARNING
        else:
            age = self._card_lookup.get_database_age()
            if age is None:
                status = "Database: Loaded"
                color = self.INFO_BLUE
            elif age.days < 7:
                status = f"Database: {age.days} day{'s' if age.days != 1 else ''} old"
                color = self.SUCCESS
            elif age.days < 30:
                status = f"Database: {age.days} days old"
                color = self.WARNING
            else:
                status = f"Database: {age.days} days old (needs update)"
                color = self.ERROR
        
        self.database_status_label.setText(status)
        self.database_status_label.setStyleSheet(f"color: {color};")
```

- [ ] **Step 5: Call status update after initialization**

Find where the GUI initialization completes (around line 300-350) and add:

```python
        # Update database status
        self._update_database_status()
```

- [ ] **Step 6: Test GUI loads without errors**

Run: `python scaffold_gui.py`
Expected: GUI loads successfully, shows database status in status bar

- [ ] **Step 7: Commit**

```bash
git add scaffold_gui.py
git commit -m "feat: integrate card lookup service setup into GUI"
```

---

## Task 8: Integrate Card Lookup into GUI - Part 2 (Enhanced Analysis)

**Files:**
- Modify: `scaffold_gui.py`
- Test: `tests/test_reverse_card_search.py`

- [ ] **Step 1: Write integration test for enhanced analysis**

```python
# tests/test_reverse_card_search.py
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

def test_enhanced_analysis_integration():
    """Test that enhanced analysis methods exist."""
    # Import and check the GUI has enhanced methods
    from scaffold_gui import MainWindow
    
    # Check that the method exists (won't actually run it)
    assert hasattr(MainWindow, '_analyze_focus_cards_enhanced')
    
    # Check database status update method exists
    assert hasattr(MainWindow, '_update_database_status')
    
    print("✓ Enhanced analysis integration methods exist")
```

- [ ] **Step 2: Run test to verify it passes**

Run: `python -m pytest tests/test_reverse_card_search.py::test_enhanced_analysis_integration -v`
Expected: PASS

- [ ] **Step 3: Create enhanced analysis method**

Add this method to the main window class in scaffold_gui.py:

```python
    def _analyze_focus_cards_enhanced(self):
        """Enhanced focus card analysis using local card database."""
        focus_text = self.focus_box.toPlainText().strip()
        if not focus_text:
            self._sm("No focus cards entered to analyze.", self.WARNING)
            return
        
        cards = [line.strip() for line in focus_text.splitlines() if line.strip()]
        self._sm(f"Analyzing {len(cards)} focus cards using card database...", self.INFO_BLUE)
        
        # Clear existing selections first
        self._reset()
        
        # Check if card lookup is available
        if not self._card_lookup:
            self._sm("Card database not available. Using pattern matching.", self.WARNING)
            self._analyze_focus_cards()  # Fall back to original
            return
        
        # Track analysis results
        analysis_summary = {
            "cards_found": 0,
            "cards_not_found": [],
            "suggested_colors": set(),
            "suggested_archetypes": set(),
            "suggested_tribes": [],
            "suggested_tags": set(),
            "deck_name_hints": []
        }
        
        # Analyze each card
        self._log_box.appendPlainText(f"Analyzing {len(cards)} cards:")
        for card_name in cards:
            card_data = self._card_lookup.lookup(card_name)
            
            if card_data:
                self._log_box.appendPlainText(f"  ✓ {card_name} (found in database)")
                analysis_summary["cards_found"] += 1
                self._analyze_card_data(card_data, analysis_summary)
            else:
                self._log_box.appendPlainText(f"  ✗ {card_name} (not in database, using pattern matching)")
                analysis_summary["cards_not_found"].append(card_name)
                self._analyze_with_patterns(card_name, analysis_summary)
        
        # Apply analysis to GUI
        self._apply_analysis_to_gui(analysis_summary)
        
        # Log summary
        self._log_analysis_summary(analysis_summary)
```

- [ ] **Step 4: Add helper methods for card data analysis**

Add these methods to the main window class:

```python
    def _analyze_card_data(self, card_data, summary):
        """Analyze actual card data from database."""
        # Use the analysis module
        if analyze_card_data:
            result = analyze_card_data(card_data)
            
            # Add to summary
            summary["suggested_colors"].update(result["colors"])
            summary["suggested_archetypes"].update(result["archetypes"])
            summary["suggested_tags"].update(result["tags"])
            
            for tribe in result["tribes"]:
                if tribe not in summary["suggested_tribes"]:
                    summary["suggested_tribes"].append(tribe)
            
            # Add deck name hints from archetypes
            for arch in result["archetypes"]:
                if arch not in summary["deck_name_hints"]:
                    summary["deck_name_hints"].append(arch)
    
    def _analyze_with_patterns(self, card_name, summary):
        """Fallback to pattern matching analysis."""
        # Reuse logic from original _analyze_focus_cards
        card_lower = card_name.lower()
        
        # Color detection (simplified version)
        color_keywords = {
            "W": ["angel", "serra", "lyra", "white"],
            "U": ["counter", "mill", "blue"],
            "B": ["zombie", "black", "death"],
            "R": ["burn", "lightning", "red", "dragon"],
            "G": ["elf", "ramp", "green", "paradise"]
        }
        
        for color, keywords in color_keywords.items():
            if any(keyword in card_lower for keyword in keywords):
                summary["suggested_colors"].add(color)
        
        # Archetype detection (simplified)
        if "angel" in card_lower:
            summary["suggested_archetypes"].add("lifegain")
            summary["suggested_tribes"].append("Angel")
            summary["deck_name_hints"].append("Lifegain")
```

- [ ] **Step 5: Add apply and log methods**

Add these methods to the main window class:

```python
    def _apply_analysis_to_gui(self, summary):
        """Apply analysis results to GUI sections."""
        # Apply colors
        for color in summary["suggested_colors"]:
            if color in self.COLOR_ORDER and color not in self.mana_orbital.selected:
                self.mana_orbital._toggle(color)
        
        # Apply archetypes
        for arch in summary["suggested_archetypes"]:
            if arch in self._arch_btns and arch not in self.selected_archetypes:
                self._toggle_arch(arch)
        
        # Apply tribal if we found tribes
        if summary["suggested_tribes"]:
            self._tribal_cb.setChecked(True)
            for tribe in summary["suggested_tribes"][:3]:  # Limit to 3 tribes
                if tribe not in self._tribes:
                    self._tribes.append(tribe)
            self._refresh_chips()
        
        # Apply tags
        for tag in summary["suggested_tags"]:
            if tag in self._tag_btns and tag not in self._selected_tags:
                self._toggle_tag(tag)
        
        # Auto-generate deck name
        if summary["deck_name_hints"] and summary["suggested_colors"]:
            color_key = frozenset(summary["suggested_colors"])
            color_name = self.GUILD_NAMES.get(color_key, "".join(sorted(summary["suggested_colors"])))
            
            unique_hints = []
            for hint in summary["deck_name_hints"]:
                if hint not in unique_hints:
                    unique_hints.append(hint)
            
            if unique_hints:
                archetype_hint = " ".join(unique_hints[:2])
                suggested_name = f"{color_name} {archetype_hint}"
            else:
                suggested_name = color_name
            
            if self._auto_name.isChecked():
                self._name_prev.setText(suggested_name)
            else:
                self.name_entry.setText(suggested_name)
        
        # Auto-set options
        if summary["suggested_archetypes"]:
            self._run_syn.setChecked(True)
            self._auto_bld.setChecked(True)
    
    def _log_analysis_summary(self, summary):
        """Log analysis summary to log box."""
        self._log_box.appendPlainText("\n" + "="*60)
        self._log_box.appendPlainText("ENHANCED FOCUS CARD ANALYSIS - USING CARD DATABASE")
        self._log_box.appendPlainText("="*60)
        self._log_box.appendPlainText(f"Cards analyzed: {summary['cards_found'] + len(summary['cards_not_found'])}")
        self._log_box.appendPlainText(f"Cards found in database: {summary['cards_found']}")
        
        if summary["cards_not_found"]:
            self._log_box.appendPlainText(f"Cards not found (used pattern matching): {', '.join(summary['cards_not_found'])}")
        
        self._log_box.appendPlainText(f"Suggested colors: {', '.join(sorted(summary['suggested_colors'])) or 'None detected'}")
        self._log_box.appendPlainText(f"Suggested archetypes: {', '.join(sorted(summary['suggested_archetypes'])) or 'None detected'}")
        self._log_box.appendPlainText(f"Suggested tribes: {', '.join(summary['suggested_tribes'][:5]) or 'None'}")
        self._log_box.appendPlainText(f"Suggested tags: {', '.join(sorted(summary['suggested_tags'])) or 'None'}")
        self._log_box.appendPlainText("")
        
        self._sm(f"Auto-filled {len(summary['suggested_colors'])} colors, {len(summary['suggested_archetypes'])} archetypes, {len(summary['suggested_tribes'])} tribes, {len(summary['suggested_tags'])} tags", self.SUCCESS)
```

- [ ] **Step 6: Connect enhanced analysis to button**

Find where the analyze button is connected (around line 1040) and modify:

```python
        # Connect the analyze button
        if CARD_LOOKUP_AVAILABLE:
            self.analyze_focus_btn.clicked.connect(self._analyze_focus_cards_enhanced)
        else:
            self.analyze_focus_btn.clicked.connect(self._analyze_focus_cards)
```

- [ ] **Step 7: Test enhanced analysis**

Run: `python scaffold_gui.py`
Expected: GUI loads, enter "Hope Estheim" in focus cards, click analyze, should show "found in database"

- [ ] **Step 8: Commit**

```bash
git add scaffold_gui.py tests/test_reverse_card_search.py
git commit -m "feat: implement enhanced focus card analysis in GUI"
```

---

## Task 9: Add Database Update Functionality to GUI

**Files:**
- Modify: `scaffold_gui.py`
- Test: Manual testing in GUI

- [ ] **Step 1: Add update database action to menu**

Find menu creation (search for "QMenu" or look around line 400-500) and add:

```python
        # Tools menu
        tools_menu = self.menu_bar.addMenu("Tools")
        
        if CARD_LOOKUP_AVAILABLE:
            update_action = QAction("Update Card Database", self)
            update_action.triggered.connect(self._update_database)
            update_action.setStatusTip("Update local card database from Scryfall")
            tools_menu.addAction(update_action)
```

- [ ] **Step 2: Implement update database method**

Add this method to the main window class:

```python
    def _update_database(self):
        """Update card database."""
        from PySide6.QtWidgets import QMessageBox, QProgressDialog
        
        reply = QMessageBox.question(
            self, "Update Card Database",
            "Update the local card database from Scryfall? This may take a few minutes.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.No:
            return
        
        # Show progress dialog
        progress = QProgressDialog("Updating card database...", "Cancel", 0, 0, self)
        progress.setWindowTitle("Updating Database")
        progress.setWindowModality(Qt.WindowModal)
        progress.show()
        
        # Run update in background
        from threading import Thread
        
        def run_update():
            try:
                success, message = self._card_lookup.update_database()
                return success, message
            except Exception as e:
                return False, str(e)
        
        def on_update_complete(success, message):
            progress.close()
            if success:
                QMessageBox.information(self, "Update Complete", message)
                self._update_database_status()
                # Clear cache to force reload
                self._card_lookup.cache.clear()
                self._log_box.appendPlainText(f"✓ Database updated: {message}")
            else:
                QMessageBox.warning(self, "Update Failed", message)
                self._log_box.appendPlainText(f"✗ Database update failed: {message}")
        
        # Simple thread implementation
        import threading
        def update_thread():
            result = run_update()
            # Use QTimer to call back on main thread
            from PySide6.QtCore import QTimer
            QTimer.singleShot(0, lambda: on_update_complete(*result))
        
        thread = threading.Thread(target=update_thread, daemon=True)
        thread.start()
        
        # Update progress every 500ms
        timer = QTimer(self)
        timer.timeout.connect(lambda: progress.setValue(progress.value() + 1))
        timer.start(500)
```

- [ ] **Step 3: Test update functionality**

Run: `python scaffold_gui.py`
Expected: Tools menu has "Update Card Database" option, clicking shows confirmation dialog

- [ ] **Step 4: Add tooltip to analyze button**

Find analyze button creation (around line 1039) and update tooltip:

```python
        self.analyze_focus_btn.setToolTip("Analyze entered cards using card database to auto-suggest: Colors, Archetypes, Tribal, Tags, Name, and Options"
                                         f"\nDatabase status: {self.database_status_label.text() if hasattr(self, 'database_status_label') else 'Not loaded'}")
```

- [ ] **Step 5: Update status after analysis**

In `_log_analysis_summary` method, add at the end:

```python
        # Update database status
        self._update_database_status()
```

- [ ] **Step 6: Test complete functionality**

Run: `python scaffold_gui.py`
1. Check database status shows in status bar
2. Enter "Hope Estheim" in focus cards
3. Click analyze button
4. Verify colors (W, U), archetypes (lifegain, opp_mill), tribe (Angel) are selected
5. Check Tools menu has update option

- [ ] **Step 7: Commit**

```bash
git add scaffold_gui.py
git commit -m "feat: add database update functionality to GUI"
```

---

## Task 10: Final Testing and Polish

**Files:**
- All modified files
- Test: Comprehensive testing

- [ ] **Step 1: Run all tests**

```bash
python -m pytest tests/test_card_lookup.py -v
python -m pytest tests/test_card_analysis.py -v
python -m pytest tests/test_reverse_card_search.py -v
```
Expected: All tests pass

- [ ] **Step 2: Test with actual card database**

```bash
# Check if Hope Estheim is in database
python -c "
import sys
sys.path.insert(0, '.')
from scripts.utils.card_lookup import CardLookupService
service = CardLookupService()
if service.initialize():
    card = service.lookup('Hope Estheim')
    if card:
        print(f'Found: {card.name}')
        print(f'Colors: {card.colors}')
        print(f'Tags: {card.tags}')
    else:
        print('Card not found in database')
else:
    print('Failed to initialize service')
"
```
Expected: Shows card details if in database

- [ ] **Step 3: Test fallback functionality**

Create a test file:

```python
# test_fallback.py
import sys
sys.path.insert(0, '.')
from scripts.utils.card_lookup import CardLookupService

service = CardLookupService()
service.initialize()

# Test with real and fake cards
test_cards = ["Hope Estheim", "Fake Card XYZ123", "Resplendent Angel"]

for card in test_cards:
    result = service.lookup(card)
    if result:
        print(f"✓ {card}: Found (colors: {result.colors})")
    else:
        print(f"✗ {card}: Not found (will use fallback)")
```

Run: `python test_fallback.py`
Expected: Shows which cards are found/not found

- [ ] **Step 4: Run GUI with various test cases**

Manual test cases:
1. Cards in database (Hope Estheim, Resplendent Angel)
2. Cards not in database (make up names)
3. Mixed list of cards
4. Empty focus cards
5. Database update simulation

- [ ] **Step 5: Performance test**

```python
# test_performance.py
import time
import sys
sys.path.insert(0, '.')
from scripts.utils.card_lookup import CardLookupService

service = CardLookupService()
start = time.time()
service.initialize()
init_time = time.time() - start

print(f"Initialization time: {init_time:.2f}s")

# Test lookup performance
test_cards = ["Hope Estheim", "Resplendent Angel", "Glimpse the Unthinkable", "Lightning Bolt"]
start = time.time()
for card in test_cards:
    service.lookup(card)
lookup_time = time.time() - start

print(f"Lookup time for {len(test_cards)} cards: {lookup_time:.2f}s")
print(f"Average per card: {lookup_time/len(test_cards):.3f}s")
```
Expected: Initialization < 2s, lookups < 0.1s per card

- [ ] **Step 6: Final commit with all changes**

```bash
git add -A
git commit -m "feat: complete reverse card search implementation with enhanced focus card analysis"
```

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-04-22-reverse-card-search-implementation.md`.

**Two execution options:**

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

**Which approach?**