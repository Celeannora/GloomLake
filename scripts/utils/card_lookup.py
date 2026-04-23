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


class CardLookupService:
    """Service for looking up card data from local database."""

    def __init__(self, base_path: str = "assets/data/local_db"):
        # Resolve repo root from THIS FILE's location, not from CWD.
        # Previous CWD-based discovery silently failed whenever the GUI was
        # launched from a directory that lacked a .git ancestor, which caused
        # the focus-card analyzer to fall back to a buggy name-substring
        # matcher (see scaffold_gui._analyze_focus_cards). Anchoring to the
        # source file makes the service CWD-independent.
        self.repo_root = self._find_repo_root()

        _raw = Path(base_path)
        self.base_path = _raw if _raw.is_absolute() else (self.repo_root / _raw)

        self.index = None
        self.cache: Dict[str, CardData] = {}
        self.db_metadata = {}
        self.last_loaded = None

    def _find_repo_root(self) -> Path:
        """Find the repository root directory.

        Walks up from this file first (stable across CWDs), then falls back
        to walking up from CWD. Final fallback is the structural parent
        (scripts/utils/card_lookup.py -> repo root), validated by probing
        for expected repo contents before accepting it.
        """
        here = Path(__file__).resolve()
        for parent in here.parents:
            if (parent / '.git').exists():
                return parent
        current = Path.cwd()
        for parent in [current] + list(current.parents):
            if (parent / '.git').exists():
                return parent

        # Structural fallback: <root>/scripts/utils/card_lookup.py -> <root>.
        # Validate by probing for either the DB or the scripts/ directory
        # that must exist in a correct checkout. If the probe fails, log a
        # warning but return the candidate anyway — a misconfigured install
        # is still better than ImportError-at-use-time.
        candidate = here.parent.parent.parent
        if (candidate / "assets" / "data" / "local_db").exists():
            return candidate
        if (candidate / "scripts" / "utils" / "card_lookup.py").exists():
            return candidate
        logger.warning(
            "CardLookupService: could not locate repo root; "
            "falling back to %s (no .git, no assets/data/local_db, "
            "no scripts/utils found)", candidate
        )
        return candidate
        
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
    
    def lookup(self, card_name: str) -> Optional[CardData]:
        """Look up a card by name (case-insensitive)."""
        if not self.index:
            logger.warning("CardLookupService: Index not loaded")
            return None

        key = card_name.lower().strip()

        # Check cache first
        if key in self.cache:
            logger.debug(f"CardLookupService: Found {card_name} in cache")
            return self.cache[key]

        # Lookup in index
        if key not in self.index.get("cards", {}):
            logger.debug(f"CardLookupService: {card_name} not found in index")
            return None

        # Load from CSV file
        card_info = self.index["cards"][key]
        # card_info["file"] is a path relative to repo root
        csv_path = self.repo_root / card_info["file"]
        logger.debug(f"CardLookupService: Looking for {card_name} in {csv_path} (repo root: {self.repo_root})")

        card_data = self._load_from_csv(csv_path, card_info["name"])

        if card_data:
            self.cache[key] = card_data
            logger.debug(f"CardLookupService: Successfully loaded {card_name}")
        else:
            logger.warning(f"CardLookupService: Failed to load {card_name} from {csv_path}")

        return card_data
    
    def _load_from_csv(self, csv_path: Path, card_name: str) -> Optional[CardData]:
        """Load card data from CSV file."""
        logger.debug(f"_load_from_csv: Looking for {card_name} in {csv_path}")
        try:
            # Try the path as-is first
            if csv_path.exists():
                actual_path = csv_path
                logger.debug(f"_load_from_csv: File exists at {actual_path}")
            else:
                logger.warning(f"_load_from_csv: File does not exist at {csv_path}")
                # The path might be relative to repo root, try to find it
                # First, try from current directory
                actual_path = Path(csv_path)
                if not actual_path.exists():
                    # Try stripping "assets/data/" prefix if present
                    path_str = str(csv_path)
                    if path_str.startswith("assets/data/") or path_str.startswith("assets\\data\\"):
                        # Try from current directory without the prefix
                        relative_path = Path(*Path(path_str).parts[2:])  # Skip "assets", "data"
                        actual_path = Path("assets/data") / relative_path
                    elif path_str.startswith("cards_by_category/"):
                        # Path is relative to assets/data
                        actual_path = self.base_path.parent / path_str
                    else:
                        # Try treating as relative to assets/data
                        actual_path = self.base_path.parent / path_str
            
            if not actual_path.exists():
                logger.warning(f"CSV file not found: {csv_path} (tried: {actual_path})")
                return None
                
            with open(actual_path, 'r', encoding='utf-8') as f:
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
            # Find the fetch script from repo root
            script_path = self.repo_root / "scripts" / "utils" / "fetch_and_categorize_cards.py"
            if not script_path.exists():
                return False, f"Update script not found: {script_path}"

            logger.info(f"Running database update: {script_path}")

            # Run the update script - don't capture output so progress shows in real-time
            result = subprocess.run(
                [sys.executable, str(script_path)],
                cwd=self.repo_root  # Run from repo root
            )

            if result.returncode == 0:
                # Reload the index
                if self.initialize():
                    return True, "Database updated successfully"
                else:
                    return False, "Update succeeded but failed to reload index"
            else:
                return False, f"Update failed (exit code {result.returncode})"

        except Exception as e:
            return False, f"Error updating database: {e}"