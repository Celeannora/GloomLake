from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPTS_DIR  = PROJECT_ROOT / "scripts"
DB_PATH      = PROJECT_ROOT / "assets" / "data" / "cards.db"

FORMATS = ["Standard", "Modern", "Commander", "Pioneer", "Pauper", "Vintage", "Legacy", "Brawl"]
