#!/usr/bin/env python3
"""
Deck Scaffold Generator — GUI (PySide6)

Design:  Professional dark dashboard with mana-master icons
Icons:   C:/Temp/mana-master  (TTF font + SVG)
Usage:   python scaffold_gui_qt.py
Requires:  pip install PySide6
"""

import json
import math
import os
import platform
import re
import subprocess
import sys
import traceback
from dataclasses import dataclass, field
from pathlib import Path

from PySide6.QtCore import (Qt, QThread, Signal, QTimer, QSize, QPointF,
                             QRectF)
from PySide6.QtGui import (QFont, QFontDatabase, QColor, QPainter, QPen,
                            QBrush, QIcon, QPixmap, QPalette, QAction,
                            QTextCharFormat, QTextCursor)
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QGridLayout, QTabWidget, QScrollArea, QFrame, QLabel, QPushButton,
    QLineEdit, QTextEdit, QPlainTextEdit, QCheckBox, QComboBox,
    QFileDialog, QSplitter, QSizePolicy, QToolTip, QGraphicsDropShadowEffect,
)

# ─────────────────────────────────────────────────────────────────────────────
# Scripts path setup  
# ─────────────────────────────────────────────────────────────────────────────
_scripts_dir = Path(__file__).resolve().parent / "scripts"
_cli_dir = _scripts_dir / "cli"
sys.path.insert(0, str(_scripts_dir))
sys.path.insert(0, str(_cli_dir))

import importlib.util
import sys

# Helper to import from scripts/cli
def _import_from_cli(module_name, *names):
    spec = importlib.util.spec_from_file_location(
        module_name, 
        _cli_dir / f"{module_name}.py"
    )
    if not spec:
        raise ImportError(f"Module {module_name} not found in {_cli_dir}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    
    # Import specific names
    imported = []
    for name in names:
        if hasattr(module, name):
            globals()[name] = getattr(module, name)
            imported.append(name)
        else:
            print(f"Warning: {name} not found in {module_name}")
    
    # Also add module to globals for whole-module imports
    globals()[module_name] = module
    return imported

# Import from scripts/cli
try:
    # First try direct import with absolute path
    import sys
    cli_path = str(Path(__file__).parent / "scripts" / "cli")
    if cli_path not in sys.path:
        sys.path.insert(0, cli_path)
    
    from generate_deck_scaffold import (
        ALL_CREATURE_TYPES,
        ARCHETYPE_QUERIES,
        sanitize_folder_name,
    )

except ImportError as e:
    print(f"Warning: Could not import generate_deck_scaffold: {e}")
    print("Using placeholders...")
    ALL_CREATURE_TYPES = []
    ARCHETYPE_QUERIES = {}
    def sanitize_folder_name(name):
        return "".join(c for c in name if c.isalnum() or c in " -_").strip()

# Import RepoPaths from mtg_utils
try:
    from scripts.utils.mtg_utils import RepoPaths
except ImportError:
    try:
        from mtg_utils import RepoPaths
    except ImportError:
        print("Warning: mtg_utils module not found, using minimal RepoPaths stub")
        class RepoPaths:
            def __init__(self):
                self.root = Path(__file__).parent
                self.cards_by_category = self.root / "cards_by_category"

try:
    # Try importing autobuild from cli directory
    from autobuild import (
        auto_build_decklist,
        merge_scores_into_candidate_pool,
        normalize_colors,
        sort_and_rewrite_csv,
        COLOR_ORDER,
        MANA_NAMES,
    )

except ImportError as e:
    try:
        # Try importing from utils directory
        from scripts.utils.auto_build import *

    except ImportError:
        print(f"Warning: auto_build module not available: {e}")
        print("Using stubs...")
        def auto_build_decklist(*args, **kwargs):
            return (False, "auto_build module not available", [])
        merge_scores_into_candidate_pool = lambda x: None
        normalize_colors = lambda x: x
        def sort_and_rewrite_csv(*args, **kwargs):
            return None

# Import card lookup modules (if available)
try:
    from scripts.utils.card_lookup import CardLookupService
    from scripts.analysis.card_analysis import analyze_card_data
    CARD_LOOKUP_AVAILABLE = True
except ImportError as e:
    CARD_LOOKUP_AVAILABLE = False
    CardLookupService = None
    analyze_card_data = None

# ─────────────────────────────────────────────────────────────────────────────
# Mana icon font discovery
# ─────────────────────────────────────────────────────────────────────────────
_MANA_FONT_PATH: Path | None = None
_MANA_SVG_DIR: Path | None = None
for _base_str in [
    os.environ.get("MANA_ICON_DIR", ""),
    str(Path(__file__).resolve().parent / "assets" / "mana"),
    str(Path("C:/Temp/mana-master")),
    str(Path(__file__).resolve().parent.parent / "mana-master"),
]:
    if not _base_str:
        continue
    _base = Path(_base_str)
    _font = _base / "fonts" / "mana.ttf"
    _svg = _base / "svg"
    if _font.exists() and not _MANA_FONT_PATH:
        _MANA_FONT_PATH = _font
    if _svg.is_dir() and not _MANA_SVG_DIR:
        _MANA_SVG_DIR = _svg
    if _MANA_FONT_PATH and _MANA_SVG_DIR:
        break

# ─────────────────────────────────────────────────────────────────────────────
# Mana font character map (Unicode PUA)
# ─────────────────────────────────────────────────────────────────────────────
IC: dict[str, str] = {
    # Mana colours
    "W": "\ue600", "U": "\ue601", "B": "\ue602",
    "R": "\ue603", "G": "\ue604",
    # Card types
    "artifact": "\ue61e", "creature": "\ue61f",
    "enchantment": "\ue620", "instant": "\ue621",
    "land": "\ue622", "planeswalker": "\ue623",
    "sorcery": "\ue624", "token": "\ue96d",
    # Abilities
    "haste": "\ue953", "trample": "\ue964", "flying": "\ue952",
    "deathtouch": "\ue94b", "menace": "\ue95d", "flash": "\ue951",
    "counter": "\ue954", "removal": "\uea69", "wipe": "\ue9a7",
    "bounce": "\ue965", "protection": "\ue954", "draw": "\ue948",
    "ramp": "\ue622", "tutor": "\ue94f", "mill": "\ue940",
    "etb": "\ue966", "lifegain": "\uea4b", "pump": "\ue93d",
    "ward": "\ue992", "prowess": "\ue982", "proliferate": "\ue981",
    "landfall": "\ue988", "infect": "\uea73",
    # Counters / misc
    "counter_skull": "\ue940", "counter_shield": "\ue9c3",
    "power": "\ue921", "toughness": "\ue922",
    "colorpie": "\ue9f0", "multiple": "\ue925",
    # Guilds
    "guild_azorius": "\ue90c", "guild_boros": "\ue90d",
    "guild_dimir": "\ue90e", "guild_golgari": "\ue90f",
    "guild_gruul": "\ue910", "guild_izzet": "\ue911",
    "guild_orzhov": "\ue912", "guild_rakdos": "\ue913",
    "guild_selesnya": "\ue914", "guild_simic": "\ue915",
    # Clans
    "clan_abzan": "\ue916", "clan_jeskai": "\ue917",
    "clan_mardu": "\ue918", "clan_sultai": "\ue919",
    "clan_temur": "\ue91a",
}

# ─────────────────────────────────────────────────────────────────────────────
# Palette
# ─────────────────────────────────────────────────────────────────────────────
APP_TITLE = "MTG Deck Scaffold Generator"
BG           = "#0d0f18"
CARD_BG      = "#12141f"
CARD_BORDER  = "#1e2040"
SURFACE      = "#181a28"
SURFACE_ALT  = "#222438"
BORDER       = "#282a42"
ACCENT       = "#c9a227"
ACCENT_HOVER = "#b08d1f"
ACCENT_DIM   = "#1f1c10"
ACCENT_2     = "#9b7ddb"
ACCENT_2_HOVER = "#8568c4"
ACCENT_2_DIM = "#1c1630"
TEXT         = "#e8eaf0"
TEXT_DIM     = "#8b95a8"
TEXT_MUTED   = "#5e6d82"
SUCCESS      = "#34d399"
ERROR        = "#f87171"
WARNING      = "#fbbf24"
INFO_BLUE    = "#60a5fa"
DIVIDER      = "#1a1c30"

MANA_COLORS = {
    "W": {"bg": "#e8e4d4", "fg": "#1a1a1a", "dim": "#1e1d18",
           "glow": "#e8e4d4", "icon_fg": "#e0dcc8"},
    "U": {"bg": "#4a80b8", "fg": "#ffffff", "dim": "#111828",
           "glow": "#4a80b8", "icon_fg": "#7eafe0"},
    "B": {"bg": "#6d6088", "fg": "#e0d4ee", "dim": "#181420",
           "glow": "#6d6088", "icon_fg": "#b0a4c8"},
    "R": {"bg": "#c0544c", "fg": "#ffffff", "dim": "#1e1010",
           "glow": "#c0544c", "icon_fg": "#e09090"},
    "G": {"bg": "#4a9060", "fg": "#ffffff", "dim": "#101e16",
           "glow": "#4a9060", "icon_fg": "#78c890"},
}

# ─────────────────────────────────────────────────────────────────────────────
# Game data constants
# ─────────────────────────────────────────────────────────────────────────────
ARCHETYPE_GROUPS: dict[str, dict[str, str]] = {
    "Aggro": {
        "aggro": "Fast creatures, low curve, win by turn 5",
        "burn": "Direct damage spells to face and creatures",
        "prowess": "Noncreature spells trigger creature buffs",
        "infect": "Poison counters as alternate win condition",
    },
    "Midrange": {
        "midrange": "Efficient threats at every mana cost",
        "tempo": "Cheap threats + disruption to stay ahead",
        "blink": "Exile and return creatures to reuse ETB effects",
        "lifegain": "Life gain triggers and drain payoffs",
    },
    "Control": {
        "control": "Counter, remove, wipe — win late with few threats",
        "stax": "Tax and lock effects to slow opponents",
        "superfriends": "Multiple planeswalkers as win conditions",
    },
    "Combo": {
        "combo": "Assemble specific card combinations to win",
        "storm": "Chain cheap spells for a big payoff spell",
        "extra_turns": "Take additional turns to close out the game",
    },
    "Graveyard": {
        "graveyard": "Use the graveyard as a resource",
        "reanimation": "Put big creatures in graveyard, bring them back",
        "flashback": "Cast spells from graveyard for value",
        "madness": "Discard cards to cast them at reduced cost",
        "self_mill": "Mill yourself for graveyard synergies",
        "opp_mill": "Mill opponent's library as win condition",
    },
    "Permanents": {
        "tokens": "Create creature tokens and buff them",
        "aristocrats": "Sacrifice creatures for value and drain",
        "enchantress": "Enchantment-heavy with draw triggers",
        "equipment": "Equip creatures with powerful gear",
        "artifacts": "Artifact synergies and metalcraft",
        "vehicles": "Crew vehicles with small creatures",
        "voltron": "Stack auras/equipment on one big threat",
    },
    "Ramp & Lands": {
        "ramp": "Accelerate mana to cast big spells early",
        "landfall": "Trigger abilities when lands enter",
        "lands": "Land-based strategies and utility lands",
        "domain": "Reward controlling all 5 basic land types",
        "eldrazi": "Colorless Eldrazi creatures with big effects",
        "energy": "Generate and spend energy counters",
        "proliferate": "Add counters to permanents and players",
    },
}

_LBL = {"opp_mill": "Opp Mill", "self_mill": "Self Mill"}
ARCH_LABEL = {k: _LBL.get(k, k.replace("_", " ").title())
              for g in ARCHETYPE_GROUPS.values() for k in g}

TAG_CATEGORIES: dict[str, dict[str, str]] = {
    "Offensive": {
        "haste": "Creatures can attack the turn they enter",
        "trample": "Excess combat damage carries over",
        "pump": "Buff creature power/toughness",
        "flying": "Creatures with flying",
        "deathtouch": "Any damage is lethal",
        "menace": "Can only be blocked by two+",
    },
    "Defensive": {
        "counter": "Counterspells and ability-counter",
        "removal": "Destroy, exile, damage removal",
        "wipe": "Board wipes",
        "bounce": "Return permanents to hand",
        "protection": "Hexproof, indestructible, ward",
        "flash": "Cards with flash",
    },
    "Utility": {
        "draw": "Card draw and selection",
        "ramp": "Mana acceleration",
        "tutor": "Search library for a card",
        "mill": "Cards from library to graveyard",
        "etb": "Enter-the-battlefield triggers",
        "lifegain": "Life gain triggers and payoffs",
    },
}

ALL_TAGS = [t for cats in TAG_CATEGORIES.values() for t in cats]

ARCHETYPE_TAG_MAP: dict[str, list[str]] = {
    "aggro": ["haste", "trample", "pump"],
    "burn": ["removal", "haste"],
    "prowess": ["draw", "pump"],
    "midrange": ["removal", "draw"],
    "tempo": ["bounce", "counter", "flash"],
    "blink": ["etb", "bounce"],
    "lifegain": ["lifegain", "draw"],
    "control": ["counter", "removal", "wipe", "draw"],
    "stax": ["protection"],
    "superfriends": ["protection", "wipe"],
    "combo": ["tutor", "draw"],
    "storm": ["draw", "ramp"],
    "extra_turns": ["draw", "counter"],
    "graveyard": ["mill"],
    "reanimation": ["mill", "tutor"],
    "flashback": ["mill", "draw"],
    "madness": ["draw"],
    "self_mill": ["mill"],
    "opp_mill": ["mill"],
    "tokens": ["pump"],
    "aristocrats": ["draw"],
    "enchantress": ["draw", "protection"],
    "equipment": ["pump"],
    "artifacts": ["draw", "ramp"],
    "vehicles": ["haste"],
    "voltron": ["pump", "protection"],
    "ramp": ["ramp", "draw"],
    "landfall": ["ramp"],
    "lands": ["ramp"],
    "domain": ["ramp"],
    "eldrazi": ["ramp"],
    "energy": ["draw", "pump"],
    "proliferate": ["pump"],
    "infect": ["pump", "trample"],
}

GUILD_NAMES = {
    frozenset("W"): "Mono-White", frozenset("U"): "Mono-Blue",
    frozenset("B"): "Mono-Black", frozenset("R"): "Mono-Red",
    frozenset("G"): "Mono-Green",
    frozenset("WU"): "Azorius", frozenset("WB"): "Orzhov",
    frozenset("UB"): "Dimir", frozenset("UR"): "Izzet",
    frozenset("BR"): "Rakdos", frozenset("BG"): "Golgari",
    frozenset("RG"): "Gruul", frozenset("RW"): "Boros",
    frozenset("GW"): "Selesnya", frozenset("GU"): "Simic",
    frozenset("WUB"): "Esper", frozenset("UBR"): "Grixis",
    frozenset("BRG"): "Jund", frozenset("RGW"): "Naya",
    frozenset("GWU"): "Bant",
    frozenset("WBG"): "Abzan", frozenset("WUR"): "Jeskai",
    frozenset("UBG"): "Sultai", frozenset("URG"): "Temur",
    frozenset("BRW"): "Mardu",
    frozenset("WUBRG"): "Five-Color",
}

GUILD_PRESETS: dict[str, str] = {
    "Azorius": "WU", "Dimir": "UB", "Rakdos": "BR",
    "Gruul": "RG", "Selesnya": "GW", "Orzhov": "WB",
    "Izzet": "UR", "Golgari": "BG", "Boros": "RW", "Simic": "GU",
    "Esper": "WUB", "Grixis": "UBR", "Jund": "BRG",
    "Naya": "RGW", "Bant": "GWU",
    "Abzan": "WBG", "Jeskai": "WUR", "Sultai": "UBG",
    "Mardu": "BRW", "Temur": "URG",
}

GUILD_ICON_MAP: dict[str, str] = {
    "Azorius": "guild_azorius", "Boros": "guild_boros",
    "Dimir": "guild_dimir", "Golgari": "guild_golgari",
    "Gruul": "guild_gruul", "Izzet": "guild_izzet",
    "Orzhov": "guild_orzhov", "Rakdos": "guild_rakdos",
    "Selesnya": "guild_selesnya", "Simic": "guild_simic",
    "Abzan": "clan_abzan", "Jeskai": "clan_jeskai",
    "Mardu": "clan_mardu", "Sultai": "clan_sultai",
    "Temur": "clan_temur",
    "Bant": "multiple", "Esper": "multiple",
    "Grixis": "multiple", "Jund": "multiple", "Naya": "multiple",
    "Mono-White": "W", "Mono-Blue": "U", "Mono-Black": "B",
    "Mono-Red": "R", "Mono-Green": "G",
    "Five-Color": "colorpie",
}

ARCHETYPE_GROUP_ICONS = {
    "Aggro": "haste", "Midrange": "creature", "Control": "instant",
    "Combo": "sorcery", "Graveyard": "counter_skull",
    "Permanents": "enchantment", "Ramp & Lands": "land",
}

TAG_CAT_ICONS = {
    "Offensive": "power", "Defensive": "counter_shield", "Utility": "draw",
}

SCAFFOLD_FILES = ["session.md", "candidate_pool.csv", "decklist.txt",
                  "analysis.md", "sideboard_guide.md"]
SETTINGS_EXT = ".scaffold.json"

# ─────────────────────────────────────────────────────────────────────────────
# Pure helpers
# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class RunResult:
    success: bool
    output: str
    synergy_output: str | None = None
    source: str = "scaffold"
    deck_dir: str | None = None
    files_found: list[str] = field(default_factory=list)
    auto_build_msg: str | None = None
    focus_log: list[tuple[str, str]] = field(default_factory=list)

_LEVEL_COLOR = {"info": TEXT_DIM, "warn": WARNING, "error": ERROR,
                "success": SUCCESS}

def filter_tribes(query: str) -> list[str]:
    q = query.strip().lower()
    return [t for t in ALL_CREATURE_TYPES if q in t.lower()] if q else []

def _extract_deck_dir(output: str) -> str | None:
    for line in output.splitlines():
        if "Output:" in line:
            return line.split("Output:")[-1].strip().rstrip("/\\").strip()
    return None

def _verify_files(deck_dir: str) -> list[str]:
    d = Path(deck_dir)
    found = [f for f in SCAFFOLD_FILES if (d / f).exists()]
    for extra in ["synergy_report.md", "top_200.csv"]:
        if (d / extra).exists() and extra not in found:
            found.append(extra)
    return found

def _open_folder(path: str) -> None:
    p = Path(path)
    if not p.exists():
        return
    if platform.system() == "Windows":
        os.startfile(str(p))
    elif platform.system() == "Darwin":
        subprocess.Popen(["open", str(p)])
    else:
        subprocess.Popen(["xdg-open", str(p)])

def generate_deck_name(colors, archetypes, focus_char=""):
    color_key = frozenset(colors)
    color_name = GUILD_NAMES.get(color_key, "".join(sorted(colors)))
    arch_list = sorted(archetypes)
    arch_label = arch_list[0].replace("_", " ").title() if arch_list else ""
    base = f"{color_name} {arch_label}".strip()
    if focus_char and focus_char.strip():
        base += f" \u2014 {focus_char.strip()}"
    return base


# ─────────────────────────────────────────────────────────────────────────────
# QSS Dark Stylesheet
# ─────────────────────────────────────────────────────────────────────────────
DARK_QSS = f"""
QMainWindow, QWidget#central {{
    background-color: {BG};
}}
QTabWidget::pane {{
    border: none;
    background-color: {BG};
}}
QTabBar::tab {{
    background-color: {SURFACE};
    color: {TEXT_MUTED};
    padding: 10px 24px;
    border: none;
    border-bottom: 2px solid transparent;
    font-size: 12px;
    font-weight: bold;
}}
QTabBar::tab:selected {{
    color: {ACCENT};
    border-bottom: 2px solid {ACCENT};
    background-color: {BG};
}}
QTabBar::tab:hover {{
    background-color: {SURFACE_ALT};
    color: {TEXT_DIM};
}}
QScrollArea {{
    border: none;
    background-color: {BG};
}}
QScrollBar:vertical {{
    background-color: {BG};
    width: 8px;
    border: none;
}}
QScrollBar::handle:vertical {{
    background-color: {BORDER};
    border-radius: 4px;
    min-height: 30px;
}}
QScrollBar::handle:vertical:hover {{
    background-color: {TEXT_MUTED};
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0px;
}}
QFrame#card {{
    background-color: {CARD_BG};
    border: 1px solid {CARD_BORDER};
    border-radius: 16px;
}}
QLabel {{
    color: {TEXT};
    background: transparent;
}}
QLabel#muted {{
    color: {TEXT_MUTED};
    font-size: 11px;
}}
QLabel#dim {{
    color: {TEXT_DIM};
}}
QLabel#accent {{
    color: {ACCENT};
    font-weight: bold;
}}
QLabel#section {{
    color: {TEXT};
    font-size: 14px;
    font-weight: bold;
}}
QLabel#badge {{
    color: {ACCENT_2};
    background-color: {ACCENT_2_DIM};
    border-radius: 8px;
    padding: 2px 6px;
    font-size: 10px;
}}
QLineEdit {{
    background-color: {SURFACE};
    color: {TEXT};
    border: 1px solid {BORDER};
    border-radius: 10px;
    padding: 8px 12px;
    font-size: 13px;
}}
QLineEdit:focus {{
    border: 1px solid {ACCENT_2};
}}
QTextEdit, QPlainTextEdit {{
    background-color: {SURFACE};
    color: {TEXT};
    border: 1px solid {BORDER};
    border-radius: 10px;
    padding: 8px;
    font-family: "Cascadia Code", "Consolas", monospace;
    font-size: 12px;
}}
QTextEdit:focus, QPlainTextEdit:focus {{
    border: 1px solid {ACCENT_2};
}}
QPushButton {{
    background-color: transparent;
    color: {TEXT_DIM};
    border: 1px solid {BORDER};
    border-radius: 10px;
    padding: 6px 16px;
    font-size: 12px;
}}
QPushButton:hover {{
    background-color: {SURFACE_ALT};
    color: {TEXT};
}}
QPushButton:pressed {{
    background-color: {BORDER};
}}
QPushButton#primary {{
    background-color: {ACCENT_2};
    color: #ffffff;
    border: none;
    border-radius: 14px;
    padding: 10px 24px;
    font-size: 14px;
    font-weight: bold;
}}
QPushButton#primary:hover {{
    background-color: {ACCENT_2_HOVER};
}}
QPushButton#pill {{
    border-radius: 14px;
    padding: 4px 14px;
    font-size: 11px;
}}
QPushButton#pill:checked, QPushButton#pill[selected="true"] {{
    background-color: {ACCENT_DIM};
    color: {ACCENT};
    border: 1px solid {ACCENT};
}}
QPushButton#mana {{
    border-radius: 24px;
    border: 1px solid {BORDER};
    font-size: 18px;
    font-weight: bold;
}}
QPushButton#mana:checked, QPushButton#mana[selected="true"] {{
    border: 2px solid;
}}
QPushButton#guild_chip {{
    border-radius: 12px;
    padding: 5px 12px;
    font-size: 12px;
    color: {TEXT_DIM};
    border: 1px solid {BORDER};
    background-color: {SURFACE};
}}
QPushButton#guild_chip:hover {{
    background-color: {SURFACE_ALT};
    color: {TEXT};
}}
QCheckBox {{
    color: {TEXT_DIM};
    font-size: 12px;
    spacing: 6px;
}}
QCheckBox::indicator {{
    width: 16px;
    height: 16px;
    border: 1px solid {BORDER};
    border-radius: 4px;
    background-color: {SURFACE};
}}
QCheckBox::indicator:checked {{
    background-color: {ACCENT_2};
    border: 1px solid {ACCENT_2};
    image: none;
}}
QComboBox {{
    background-color: {SURFACE};
    color: {TEXT};
    border: 1px solid {BORDER};
    border-radius: 8px;
    padding: 6px 12px;
    font-size: 12px;
}}
QComboBox::drop-down {{
    border: none;
    width: 24px;
}}
QComboBox QAbstractItemView {{
    background-color: {SURFACE};
    color: {TEXT};
    border: 1px solid {BORDER};
    selection-background-color: {SURFACE_ALT};
}}
QToolTip {{
    background-color: {SURFACE};
    color: {TEXT_DIM};
    border: 1px solid {BORDER};
    border-radius: 6px;
    padding: 6px 10px;
    font-size: 11px;
}}
"""


# ─────────────────────────────────────────────────────────────────────────────
# Mana font loader
# ─────────────────────────────────────────────────────────────────────────────
_mana_font_family: str | None = None

def _load_mana_font() -> str | None:
    """Load mana.ttf into Qt font database. Returns family name or None."""
    global _mana_font_family
    if _mana_font_family is not None:
        return _mana_font_family
    if _MANA_FONT_PATH and _MANA_FONT_PATH.exists():
        fid = QFontDatabase.addApplicationFont(str(_MANA_FONT_PATH))
        if fid >= 0:
            families = QFontDatabase.applicationFontFamilies(fid)
            if families:
                _mana_font_family = families[0]
                return _mana_font_family
    _mana_font_family = ""  # Mark as attempted
    return None

def mana_font(size: int = 16) -> QFont:
    """Get a QFont for mana icons at given pixel size."""
    family = _load_mana_font()
    if family:
        f = QFont(family, size)
        f.setPixelSize(size)
        return f
    return QFont("Segoe UI", size)

def mana_char(key: str) -> str:
    """Get the unicode character for an icon key."""
    return IC.get(key, "?")


# ─────────────────────────────────────────────────────────────────────────────
# Worker thread for background commands
# ─────────────────────────────────────────────────────────────────────────────
class CommandWorker(QThread):
    line_ready = Signal(str, str)
    finished_result = Signal(object)

    def __init__(self, cmd, cwd, env, source="generic",
                 colors="", run_syn=False, auto_build=False,
                 focus_names=None):
        super().__init__()
        self.cmd = cmd; self.cwd = cwd; self.env = env
        self.source = source; self.colors = colors
        self.run_syn = run_syn; self.auto_build = auto_build
        self.focus_names = focus_names or []
        self._proc = None; self._cancelled = False

    def cancel(self):
        self._cancelled = True
        if self._proc and self._proc.poll() is None:
            self._proc.terminate()
            try: self._proc.wait(timeout=5)
            except Exception: self._proc.kill()

    def run(self):
        try:
            ok, out = self._stream()
        except Exception as e:
            ok, out = False, str(e)
        if self.source != "scaffold":
            self.finished_result.emit(RunResult(ok, out, source=self.source))
            return
        deck_dir = syn = ab_msg = None; focus_log = []
        try:
            deck_dir = _extract_deck_dir(out) if ok else None
            if deck_dir:
                dp = Path(deck_dir)
                if not dp.is_absolute():
                    dp = RepoPaths().root / dp
                deck_dir = str(dp)
            if ok and self.run_syn and deck_dir:
                try: syn = self._do_synergy(deck_dir)
                except Exception as e:
                    self.line_ready.emit(f"Synergy: {e}", ERROR)
            if ok and deck_dir:
                try: self._do_sort(deck_dir)
                except Exception: pass
            if ok and self.auto_build and deck_dir:
                try:
                    ab_ok, ab_msg, focus_log = auto_build_decklist(
                        deck_dir, self.colors, self.focus_names)
                    if ab_ok:
                        self.line_ready.emit(
                            "--- Auto-built Decklist " + "-"*28, SUCCESS)
                        for m, lvl in focus_log:
                            if m: self.line_ready.emit(
                                m, _LEVEL_COLOR.get(lvl, TEXT_DIM))
                        self.line_ready.emit(f"  {ab_msg}", SUCCESS)
                    else:
                        ab_msg = None
                except Exception as e:
                    self.line_ready.emit(f"AUTO-BUILD: {e}", ERROR)
                    ab_msg = None
        except Exception as e:
            self.line_ready.emit(f"Post-scaffold: {e}", ERROR)
        files = _verify_files(deck_dir) if deck_dir else []
        self.finished_result.emit(RunResult(
            ok, out, syn, "scaffold", deck_dir, files, ab_msg, focus_log))

    def _stream(self):
        self.line_ready.emit("$ " + " ".join(self.cmd), TEXT_MUTED)
        self._proc = subprocess.Popen(
            self.cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL, text=True,
            encoding="utf-8", errors="replace",
            cwd=self.cwd, env=self.env)
        lines = []
        for line in self._proc.stdout:
            if self._cancelled: break
            lines.append(line)
            s = line.rstrip()
            if s.strip():
                c = (SUCCESS if "[OK]" in s else
                     ERROR if "ERROR" in s else
                     ACCENT if "candidates" in s.lower() else TEXT)
                self.line_ready.emit(s, c)
        self._proc.wait()
        return self._proc.returncode == 0, "".join(lines).strip()

    def _do_synergy(self, deck_dir):
        session = Path(deck_dir) / "session.md"
        if not session.exists(): return None
        self.line_ready.emit("Running synergy\u2026", ACCENT)
        report = Path(deck_dir) / "synergy_report.md"
        subprocess.run(
            [sys.executable, str(_scripts_dir / "synergy_analysis.py"),
             str(session), "--output", str(report), "--top", "200"],
            capture_output=True, text=True, encoding="utf-8",
            errors="replace", stdin=subprocess.DEVNULL,
            cwd=self.cwd, env=self.env, timeout=120)
        return report.read_text(encoding="utf-8").strip() \
            if report.exists() else None

    def _do_sort(self, deck_dir):
        d = Path(deck_dir)
        ok, n = sort_and_rewrite_csv(d / "top_200.csv")
        if ok: self.line_ready.emit(f"  Sorted top_200.csv ({n})", SUCCESS)
        ok2, pn = merge_scores_into_candidate_pool(deck_dir)
        if ok2: self.line_ready.emit(
            f"  Merged scores ({pn} cards)", SUCCESS)


# ─────────────────────────────────────────────────────────────────────────────
# Custom widgets
# ─────────────────────────────────────────────────────────────────────────────
class CardWidget(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("card")
        self._lay = QVBoxLayout(self)
        self._lay.setContentsMargins(0, 0, 0, 8)
        self._lay.setSpacing(0)

    def add_header(self, number, title, hint=""):
        hdr = QWidget()
        hl = QHBoxLayout(hdr)
        hl.setContentsMargins(24, 20, 24, 8 if hint else 16)
        if number:
            badge = QLabel(number)
            badge.setObjectName("badge")
            badge.setFixedSize(28, 22)
            badge.setAlignment(Qt.AlignCenter)
            hl.addWidget(badge)
        lbl = QLabel(title)
        lbl.setObjectName("section")
        hl.addWidget(lbl)
        hl.addStretch()
        self._lay.addWidget(hdr)
        if hint:
            h = QLabel(hint)
            h.setObjectName("muted")
            h.setContentsMargins(24, 0, 24, 8)
            self._lay.addWidget(h)


class CollapsibleCard(CardWidget):
    def __init__(self, number, title, hint="", collapsed=False, parent=None):
        super().__init__(parent)
        hdr = QWidget()
        hl = QHBoxLayout(hdr)
        hl.setContentsMargins(24, 16, 24, 8 if hint else 12)
        badge = QLabel(number)
        badge.setObjectName("badge")
        badge.setFixedSize(28, 22)
        badge.setAlignment(Qt.AlignCenter)
        hl.addWidget(badge)
        lbl = QLabel(title)
        lbl.setObjectName("section")
        hl.addWidget(lbl)
        hl.addStretch()
        self._chev = QPushButton("\u25be" if not collapsed else "\u25b8")
        self._chev.setFixedSize(28, 24)
        self._chev.setStyleSheet(f"border:none;color:{TEXT_MUTED};font-size:14px;")
        self._chev.clicked.connect(self._toggle)
        hl.addWidget(self._chev)
        self._lay.addWidget(hdr)
        self._hint_lbl = None
        if hint:
            self._hint_lbl = QLabel(hint)
            self._hint_lbl.setObjectName("muted")
            self._hint_lbl.setContentsMargins(24, 0, 24, 4)
            self._lay.addWidget(self._hint_lbl)
        self._body = QWidget()
        self._body_lay = QVBoxLayout(self._body)
        self._body_lay.setContentsMargins(0, 0, 0, 0)
        self._body_lay.setSpacing(4)
        self._lay.addWidget(self._body)
        self._expanded = not collapsed
        if collapsed:
            self._body.hide()
            if self._hint_lbl: self._hint_lbl.hide()

    def _toggle(self):
        self._expanded = not self._expanded
        self._body.setVisible(self._expanded)
        if self._hint_lbl: self._hint_lbl.setVisible(self._expanded)
        self._chev.setText("\u25be" if self._expanded else "\u25b8")

    def body_layout(self):
        return self._body_lay


class ManaOrbitalWidget(QWidget):
    color_changed = Signal()
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(320, 240)
        self.selected = set()
        self._btns = {}
        self._guild_name = ""
        self._guild_icon_key = ""
        cx, cy, r, sz = 160, 110, 84, 48
        for i, c in enumerate(COLOR_ORDER):
            angle = math.radians(90 - i * 72)
            x = int(cx + r * math.cos(angle) - sz // 2)
            y = int(cy - r * math.sin(angle) - sz // 2)
            mc = MANA_COLORS[c]
            btn = QPushButton(mana_char(c), self)
            btn.setFont(mana_font(22))
            btn.setFixedSize(sz, sz)
            btn.move(x, y)
            btn.setToolTip(MANA_NAMES[c])
            btn.setStyleSheet(self._btn_ss(mc, False))
            btn.clicked.connect(lambda ck=False, col=c: self._toggle(col))
            self._btns[c] = btn

    def _btn_ss(self, mc, sel):
        if sel:
            return (f"QPushButton{{background:{mc['bg']};color:{mc['fg']};"
                    f"border:2px solid {mc['glow']};border-radius:24px;}}")
        return (f"QPushButton{{background:{mc['dim']};color:{mc['icon_fg']};"
                f"border:1px solid {BORDER};border-radius:24px;}}"
                f"QPushButton:hover{{background:{SURFACE_ALT};}}")

    def _toggle(self, c):
        mc = MANA_COLORS[c]
        if c in self.selected:
            self.selected.discard(c)
        else:
            self.selected.add(c)
        self._btns[c].setStyleSheet(
            self._btn_ss(mc, c in self.selected))
        gn = GUILD_NAMES.get(frozenset(self.selected), "")
        self._guild_name = gn
        self._guild_icon_key = GUILD_ICON_MAP.get(gn, "")
        self.update()
        self.color_changed.emit()

    def apply_preset(self, guild):
        colors = GUILD_PRESETS.get(guild, "")
        if not colors: return
        for c in list(self.selected): self._toggle(c)
        for c in colors:
            if c not in self.selected: self._toggle(c)

    def paintEvent(self, event):
        super().paintEvent(event)
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        cx, cy, r = 160, 110, 84
        pen = QPen(QColor(BORDER)); pen.setWidth(1)
        p.setPen(pen)
        p.drawEllipse(QPointF(cx, cy), r + 4, r + 4)
        if self._guild_icon_key and len(self.selected) >= 2:
            ch = IC.get(self._guild_icon_key, "")
            if ch:
                p.setFont(mana_font(26))
                p.setPen(QColor(ACCENT))
                p.drawText(QRectF(cx-16, cy-16, 32, 32), Qt.AlignCenter, ch)
        p.end()

    def guild_name(self): return self._guild_name



# ─────────────────────────────────────────────────────────────────────────────
# Main Application Window
# ─────────────────────────────────────────────────────────────────────────────
class ScaffoldApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_TITLE)
        self.resize(960, 1020)
        self.setMinimumSize(800, 700)
        self._repo = RepoPaths()
        self._worker = None
        self._last_deck_dir = None
        self.selected_archetypes = set()
        self._selected_tags = set()
        self._tribes = []
        self._arch_btns = {}
        self._tag_btns = {}
        
        # Card lookup service
        self._card_lookup = None
        if CARD_LOOKUP_AVAILABLE:
            self._card_lookup = CardLookupService()
            if not self._card_lookup.initialize():
                self._card_lookup = None
        cw = QWidget(); cw.setObjectName("central")
        self.setCentralWidget(cw)
        root = QVBoxLayout(cw)
        root.setContentsMargins(0, 0, 0, 0); root.setSpacing(0)
        self._build_header(root)
        self.tabs = QTabWidget()
        root.addWidget(self.tabs, 1)
        self._build_scaffold_tab()
        self._build_queries_tab()
        self._build_synergy_tab()
        self._build_log(root)
        self._build_footer(root)
        
        # Update database status
        self._update_database_status()

    def _build_header(self, root):
        hdr = QFrame()
        hdr.setStyleSheet(f"QFrame{{background:{CARD_BG};border-bottom:2px solid {ACCENT};}}")
        hdr.setFixedHeight(52)
        hl = QHBoxLayout(hdr); hl.setContentsMargins(24, 0, 24, 0)
        ic = QLabel(mana_char("planeswalker")); ic.setFont(mana_font(18))
        ic.setStyleSheet(f"color:{ACCENT};background:transparent;"); hl.addWidget(ic)
        t = QLabel(APP_TITLE)
        t.setStyleSheet(f"color:{TEXT};font-size:14px;font-weight:bold;background:transparent;")
        hl.addWidget(t); hl.addStretch()
        sb = QPushButton("\u2191 Save"); sb.clicked.connect(self._on_save)
        lb = QPushButton("\u2193 Load"); lb.clicked.connect(self._on_load)
        hl.addWidget(sb); hl.addWidget(lb)
        root.addWidget(hdr)

    def _build_scaffold_tab(self):
        page = QWidget(); scroll = QScrollArea()
        scroll.setWidgetResizable(True); scroll.setWidget(page)
        self.tabs.addTab(scroll, "New Scaffold")
        lay = QVBoxLayout(page)
        lay.setContentsMargins(12, 12, 12, 12); lay.setSpacing(8)
        # Card 1: Focus Cards (NOW THE VERY TOP)
        c1 = CardWidget(); c1.add_header("01", "Focus Cards", "Enter key cards, then click Analyze to auto-fill other sections")
        b1 = QWidget(); tb1 = QVBoxLayout(b1); tb1.setContentsMargins(24, 0, 24, 16)
        self.focus_box = QPlainTextEdit(); self.focus_box.setFixedHeight(80)
        self.focus_box.setPlaceholderText("Enter card names, one per line...\nExamples: Resplendent Angel, Glimpse the Unthinkable, Lightning Bolt"); tb1.addWidget(self.focus_box)
        
        # Add powerful auto-analysis button for focus cards
        analysis_row = QHBoxLayout()
        self.analyze_focus_btn = QPushButton("\U0001F50D Analyze Focus Cards & Auto-Fill All Sections")
        self.analyze_focus_btn.setToolTip("Analyze entered cards using card database to auto-suggest: Colors, Archetypes, Tribal, Tags, Name, and Options"
                                         f"\nDatabase status: {self.database_status_label.text() if hasattr(self, 'database_status_label') else 'Not loaded'}")
        # Connect enhanced analysis if available, otherwise fallback
        if CARD_LOOKUP_AVAILABLE:
            self.analyze_focus_btn.clicked.connect(self._analyze_focus_cards_enhanced)
        else:
            self.analyze_focus_btn.clicked.connect(self._analyze_focus_cards)
        self.analyze_focus_btn.setObjectName("primary")
        self.analyze_focus_btn.setFixedHeight(36)
        analysis_row.addWidget(self.analyze_focus_btn)
        analysis_row.addStretch()
        tb1.addLayout(analysis_row)
        
        c1._lay.addWidget(b1); lay.addWidget(c1)
        
        # Card 2: Mana (was Card 1)
        c2 = CardWidget(); c2.add_header("02", "Mana Colours", "Select colour identity")
        b2 = QWidget(); bl2 = QVBoxLayout(b2); bl2.setContentsMargins(24, 0, 24, 16)
        self.mana_orbital = ManaOrbitalWidget()
        self.mana_orbital.color_changed.connect(self._on_colors)
        bl2.addWidget(self.mana_orbital, alignment=Qt.AlignCenter)
        self._guild_lbl = QLabel(""); self._guild_lbl.setObjectName("accent")
        self._guild_lbl.setAlignment(Qt.AlignCenter); bl2.addWidget(self._guild_lbl)
        nr = QHBoxLayout(); nr.addStretch()
        for c in COLOR_ORDER:
            nl = QLabel(MANA_NAMES[c]); nl.setObjectName("muted")
            nl.setAlignment(Qt.AlignCenter); nl.setFixedWidth(56); nr.addWidget(nl)
        nr.addStretch(); bl2.addLayout(nr)
        dv = QFrame(); dv.setFixedHeight(1); dv.setStyleSheet(f"background:{DIVIDER};")
        bl2.addWidget(dv)
        pl = QLabel("PRESETS"); pl.setObjectName("muted")
        pl.setStyleSheet(f"font-size:10px;font-weight:bold;color:{TEXT_MUTED};")
        bl2.addWidget(pl)
        # Guild presets: 4-col grid, full names, no truncation
        gl = list(GUILD_PRESETS.items())
        pgrid = QGridLayout()
        pgrid.setSpacing(6)
        pgrid.setContentsMargins(0, 4, 0, 0)
        for idx, (name, _) in enumerate(gl):
            b = QPushButton(name)
            b.setObjectName("guild_chip")
            b.setToolTip(f"Select {name} colours")
            b.clicked.connect(
                lambda ck=False, n=name: self.mana_orbital.apply_preset(n))
            pgrid.addWidget(b, idx // 4, idx % 4)
        bl2.addLayout(pgrid)
        c2._lay.addWidget(b2); lay.addWidget(c2)
        # Card 3: Archetype (was Card 2)
        c3 = CardWidget(); c3.add_header("03", "Archetype", "Select one or more")
        b3 = QWidget(); bl3 = QVBoxLayout(b3); bl3.setContentsMargins(24, 0, 24, 16)
        for gn, archs in ARCHETYPE_GROUPS.items():
            gh = QHBoxLayout()
            ik = ARCHETYPE_GROUP_ICONS.get(gn)
            if ik:
                gi = QLabel(mana_char(ik)); gi.setFont(mana_font(13))
                gi.setStyleSheet(f"color:{TEXT_MUTED};background:transparent;"); gh.addWidget(gi)
            gl2 = QLabel(gn.upper()); gl2.setObjectName("muted")
            gl2.setStyleSheet(f"font-size:10px;font-weight:bold;color:{TEXT_MUTED};")
            gh.addWidget(gl2); gh.addStretch(); bl3.addLayout(gh)
            grid = QGridLayout(); grid.setSpacing(4)
            for i, (a, desc) in enumerate(archs.items()):
                lbl = ARCH_LABEL.get(a, a.replace("_"," ").title())
                btn = QPushButton(lbl); btn.setObjectName("pill")
                btn.setToolTip(desc); btn.setFixedHeight(30)
                btn.clicked.connect(lambda ck=False, x=a: self._toggle_arch(x))
                grid.addWidget(btn, i//5, i%5); self._arch_btns[a] = btn
            bl3.addLayout(grid)
        c3._lay.addWidget(b3); lay.addWidget(c3)
# Card 4: Tribal (was Card 3)
        c4 = CardWidget(); c4.add_header("04", "Tribal", "Optional \u2014 creature type synergies")
        b4 = QWidget(); tb4 = QVBoxLayout(b4); tb4.setContentsMargins(24, 0, 24, 16)
        self._tribal_cb = QCheckBox("Enable Tribal")
        self._tribal_cb.toggled.connect(self._on_tribal); tb4.addWidget(self._tribal_cb)
        self._wildcard_cb = QCheckBox("Wildcard Mode"); self._wildcard_cb.hide(); tb4.addWidget(self._wildcard_cb)
        self._tribe_search = QLineEdit(); self._tribe_search.setPlaceholderText("Search creature types...")
        self._tribe_search.setEnabled(False); self._tribe_search.textChanged.connect(self._tribe_changed)
        tb4.addWidget(self._tribe_search)
        self._tribe_res = QWidget(); self._tribe_res_l = QVBoxLayout(self._tribe_res)
        self._tribe_res_l.setContentsMargins(0,0,0,0); self._tribe_res.hide(); tb4.addWidget(self._tribe_res)
        self._tribe_chips = QWidget(); self._tribe_chips_l = QHBoxLayout(self._tribe_chips)
        self._tribe_chips_l.setContentsMargins(0,0,0,0); self._tribe_chips.hide(); tb4.addWidget(self._tribe_chips)
        c4._lay.addWidget(b4); lay.addWidget(c4)
# Card 5: Tags (was Card 4)
        c5 = CardWidget(); c5.add_header("05", "Extra Tags", "Optional search keywords")
        b5 = QWidget(); tb5 = QVBoxLayout(b5); tb5.setContentsMargins(24, 0, 24, 16)
        ab = QPushButton("\u2728 Auto from archetype"); ab.setFixedHeight(28)
        ab.clicked.connect(self._auto_tags); tb5.addWidget(ab, alignment=Qt.AlignLeft)
        for cn, ct in TAG_CATEGORIES.items():
            ch = QHBoxLayout()
            ik = TAG_CAT_ICONS.get(cn)
            if ik:
                ci = QLabel(mana_char(ik)); ci.setFont(mana_font(11))
                ci.setStyleSheet(f"color:{TEXT_MUTED};background:transparent;"); ch.addWidget(ci)
            cl = QLabel(cn.upper()); cl.setObjectName("muted")
            cl.setStyleSheet(f"font-size:10px;font-weight:bold;"); ch.addWidget(cl)
            ch.addStretch(); tb5.addLayout(ch)
            tg = QGridLayout(); tg.setSpacing(4)
            for i, (tag, desc) in enumerate(ct.items()):
                btn = QPushButton(tag); btn.setObjectName("pill")
                btn.setToolTip(desc); btn.setFixedHeight(26)
                btn.clicked.connect(lambda ck=False, t=tag: self._toggle_tag(t))
                tg.addWidget(btn, i//6, i%6); self._tag_btns[tag] = btn
            tb5.addLayout(tg)
        c5._lay.addWidget(b5); lay.addWidget(c5)
        # Card 6: Name (was 6, now 6 because we removed old Card 5)
        c6 = CardWidget(); c6.add_header("06", "Deck Name")
        b6 = QWidget(); bl6 = QVBoxLayout(b6); bl6.setContentsMargins(24, 0, 24, 16)
        self._auto_name = QCheckBox("Auto-generate from Colors + Archetype")
        self._auto_name.setChecked(True); self._auto_name.toggled.connect(self._on_auto_name)
        bl6.addWidget(self._auto_name)
        pr = QHBoxLayout()
        pl2 = QLabel("PREVIEW"); pl2.setObjectName("muted")
        pl2.setStyleSheet(f"font-size:10px;font-weight:bold;"); pr.addWidget(pl2)
        self._name_prev = QLabel("\u2014"); self._name_prev.setObjectName("accent")
        pr.addWidget(self._name_prev); pr.addStretch(); bl6.addLayout(pr)
        self.name_entry = QLineEdit(); self.name_entry.setPlaceholderText("e.g. Orzhov Lifegain")
        self.name_entry.setEnabled(False); self.name_entry.textChanged.connect(self._validate)
        bl6.addWidget(self.name_entry)
        fr = QHBoxLayout()
        fl = QLabel("FOCUS CHARACTER"); fl.setObjectName("muted")
        fl.setStyleSheet(f"font-size:10px;font-weight:bold;"); fr.addWidget(fl)
        self._focus_char = QLineEdit(); self._focus_char.setPlaceholderText("Optional (e.g., Aerith)")
        self._focus_char.textChanged.connect(self._update_name); fr.addWidget(self._focus_char)
        bl6.addLayout(fr); c6._lay.addWidget(b6); lay.addWidget(c6)
        # Card 7: Options (was 7)
        c7 = CardWidget(); c7.add_header("07", "Options")
        b7 = QWidget(); bl7 = QVBoxLayout(b7); bl7.setContentsMargins(24, 0, 24, 16)
        self._skip_q = QCheckBox("Skip queries (offline template)")
        self._run_syn = QCheckBox("Run synergy analysis"); self._run_syn.setChecked(True)
        self._auto_bld = QCheckBox("Auto-build decklist (Karsten)"); self._auto_bld.setChecked(True)
        bl7.addWidget(self._skip_q); bl7.addWidget(self._run_syn); bl7.addWidget(self._auto_bld)
        c7._lay.addWidget(b7); lay.addWidget(c7)
        # Card 8: Output (was 8)
        c8 = CardWidget(); c8.add_header("08", "Output Directory", "Default: Decks/")
        b8 = QWidget(); bl8 = QHBoxLayout(b8); bl8.setContentsMargins(24, 0, 24, 16)
        self.output_entry = QLineEdit(); self.output_entry.setPlaceholderText("Decks/")
        bl8.addWidget(self.output_entry)
        bb = QPushButton("Browse"); bb.clicked.connect(self._browse_out)
        bl8.addWidget(bb); c8._lay.addWidget(b8); lay.addWidget(c8)
        lay.addStretch()

    def _build_queries_tab(self):
        page = QWidget(); scroll = QScrollArea()
        scroll.setWidgetResizable(True); scroll.setWidget(page)
        self.tabs.addTab(scroll, "Run Queries")
        lay = QVBoxLayout(page); lay.setContentsMargins(12,12,12,12)
        card = CardWidget(); card.add_header("", "Run Pending Session Queries",
            "Finds placeholders, runs them, fills results.")
        b = QWidget(); bl = QVBoxLayout(b); bl.setContentsMargins(24,0,24,16)
        r = QHBoxLayout()
        self.rq_entry = QLineEdit(); self.rq_entry.setPlaceholderText("Path to session.md")
        r.addWidget(self.rq_entry)
        bb = QPushButton("Browse"); bb.clicked.connect(self._browse_session)
        r.addWidget(bb); bl.addLayout(r)
        self._rq_force = QCheckBox("Force re-run"); self._rq_dry = QCheckBox("Dry run")
        bl.addWidget(self._rq_force); bl.addWidget(self._rq_dry)
        self.rq_btn = QPushButton("Run Queries"); self.rq_btn.setObjectName("primary")
        self.rq_btn.setFixedWidth(180); self.rq_btn.clicked.connect(self._on_queries)
        bl.addWidget(self.rq_btn); card._lay.addWidget(b); lay.addWidget(card); lay.addStretch()

    def _build_synergy_tab(self):
        page = QWidget(); scroll = QScrollArea()
        scroll.setWidgetResizable(True); scroll.setWidget(page)
        self.tabs.addTab(scroll, "Synergy Analysis")
        lay = QVBoxLayout(page); lay.setContentsMargins(12,12,12,12)
        card = CardWidget(); card.add_header("", "Gate 2.5 \u2014 Synergy Analysis",
            "Scores interactions, checks thresholds.")
        b = QWidget(); bl = QVBoxLayout(b); bl.setContentsMargins(24,0,24,16)
        r1 = QHBoxLayout()
        self.syn_in = QLineEdit(); self.syn_in.setPlaceholderText("session.md or decklist.txt")
        r1.addWidget(self.syn_in)
        b1 = QPushButton("Browse"); b1.clicked.connect(self._browse_syn_in)
        r1.addWidget(b1); bl.addLayout(r1)
        r2 = QHBoxLayout()
        self.syn_out = QLineEdit(); self.syn_out.setPlaceholderText("Output report (optional)")
        r2.addWidget(self.syn_out)
        b2 = QPushButton("Browse"); b2.clicked.connect(self._browse_syn_out)
        r2.addWidget(b2); bl.addLayout(r2)
        r3 = QHBoxLayout(); r3.addWidget(QLabel("Threshold:"))
        self.syn_thresh = QLineEdit("3.0"); self.syn_thresh.setFixedWidth(60); r3.addWidget(self.syn_thresh)
        r3.addWidget(QLabel("Mode:"))
        self._syn_mode = QComboBox(); self._syn_mode.addItems(["auto","pool","deck"])
        self._syn_mode.setFixedWidth(100); r3.addWidget(self._syn_mode); r3.addStretch(); bl.addLayout(r3)
        self.syn_btn = QPushButton("Analyze Synergy"); self.syn_btn.setObjectName("primary")
        self.syn_btn.setFixedWidth(200); self.syn_btn.clicked.connect(self._on_synergy)
        bl.addWidget(self.syn_btn)
        r4 = QHBoxLayout()
        self.regenerate_btn = QPushButton("Regenerate Candidate Pool")
        self.regenerate_btn.setFixedWidth(200)
        self.regenerate_btn.clicked.connect(self._on_regenerate_pool)
        r4.addWidget(self.regenerate_btn)
        self.regenerate_status = QLabel(" (requires synergy scores)")
        self.regenerate_status.setObjectName("muted")
        r4.addWidget(self.regenerate_status)
        r4.addStretch()
        bl.addLayout(r4)
        card._lay.addWidget(b); lay.addWidget(card); lay.addStretch()

    def _build_log(self, root):
        d = QFrame(); d.setFixedHeight(1); d.setStyleSheet(f"background:{DIVIDER};"); root.addWidget(d)
        bar = QWidget(); bar.setFixedHeight(32); bar.setStyleSheet(f"background:{SURFACE};")
        bl = QHBoxLayout(bar); bl.setContentsMargins(8,0,8,0)
        self._log_btn = QPushButton("\u25b6  LOG")
        self._log_btn.setStyleSheet(f"border:none;color:{TEXT_MUTED};font-size:10px;font-weight:bold;")
        self._log_btn.clicked.connect(self._toggle_log); bl.addWidget(self._log_btn)
        self._log_inline = QLabel(""); self._log_inline.setObjectName("muted")
        bl.addWidget(self._log_inline); bl.addStretch(); root.addWidget(bar)
        self._log_box = QPlainTextEdit(); self._log_box.setReadOnly(True); self._log_box.setMaximumHeight(0)
        self._log_box.setStyleSheet(f"background:{BG};color:{TEXT_DIM};border:none;"
            f"font-family:'Cascadia Code','Consolas',monospace;font-size:11px;")
        root.addWidget(self._log_box); self._log_vis = False

    def _build_footer(self, root):
        d = QFrame(); d.setFixedHeight(1); d.setStyleSheet(f"background:{DIVIDER};"); root.addWidget(d)
        ft = QWidget(); ft.setFixedHeight(68); ft.setStyleSheet(f"background:{CARD_BG};")
        fl = QHBoxLayout(ft); fl.setContentsMargins(24,0,24,0)
        lv = QVBoxLayout()
        self._arch_cnt = QLabel("0 selected"); self._arch_cnt.setObjectName("muted"); lv.addWidget(self._arch_cnt)
        self._status = QLabel("\u2460 Select colours."); self._status.setObjectName("dim")
        self._status.setStyleSheet(f"font-size:12px;"); lv.addWidget(self._status)
        
        # Database status label
        self.database_status_label = QLabel("Database: Checking...")
        self.database_status_label.setObjectName("dim")
        self.database_status_label.setStyleSheet(f"font-size:12px;")
        lv.addWidget(self.database_status_label)
        fl.addLayout(lv); fl.addStretch()
        rb = QPushButton("Reset"); rb.setStyleSheet(f"border:none;color:{TEXT_MUTED};")
        rb.clicked.connect(self._reset); fl.addWidget(rb)
        if CARD_LOOKUP_AVAILABLE:
            db_btn = QPushButton("Update DB"); db_btn.setStyleSheet(f"border:none;color:{TEXT_MUTED};")
            db_btn.clicked.connect(self._update_database); fl.addWidget(db_btn)
        self._open_btn = QPushButton("\U0001f4c2 Open"); self._open_btn.setEnabled(False)
        self._open_btn.clicked.connect(self._open_dir); fl.addWidget(self._open_btn)
        self.run_btn = QPushButton("Generate Scaffold  \u203a"); self.run_btn.setObjectName("primary")
        self.run_btn.setFixedSize(220, 46); self.run_btn.clicked.connect(self._on_generate)
        fl.addWidget(self.run_btn); root.addWidget(ft)

    # ── Handlers ─────────────────────────────
    def _on_colors(self):
        self._guild_lbl.setText(self.mana_orbital.guild_name())
        self._update_name(); self._validate()
    def _toggle_arch(self, a):
        btn = self._arch_btns[a]
        if a in self.selected_archetypes:
            self.selected_archetypes.discard(a); btn.setStyleSheet("")
        else:
            self.selected_archetypes.add(a)
            btn.setStyleSheet(f"background:{ACCENT_DIM};color:{ACCENT};border:1px solid {ACCENT};border-radius:14px;")
        self._arch_cnt.setText(f"{len(self.selected_archetypes)} selected")
        self._update_name(); self._validate()
    def _toggle_tag(self, t):
        btn = self._tag_btns[t]
        if t in self._selected_tags:
            self._selected_tags.discard(t); btn.setStyleSheet("")
        else:
            self._selected_tags.add(t)
            btn.setStyleSheet(f"background:{ACCENT_DIM};color:{ACCENT};border:1px solid {ACCENT};border-radius:14px;")
    def _auto_tags(self):
        for t in list(self._selected_tags): self._toggle_tag(t)
        for a in self.selected_archetypes:
            for t in ARCHETYPE_TAG_MAP.get(a, []):
                if t in self._tag_btns and t not in self._selected_tags: self._toggle_tag(t)
    
    def _update_database_status(self):
        """Update database status display."""
        if not self._card_lookup or not self._card_lookup.db_metadata:
            status = "Database: Not loaded"
            color = WARNING
        else:
            age = self._card_lookup.get_database_age()
            total_cards = self._card_lookup.db_metadata.get('total_cards', 0)
            if age is None:
                status = f"Database: Loaded ({total_cards} cards)"
                color = INFO_BLUE
                # Log successful loading
                if hasattr(self, '_log_box'):
                    self._log_box.appendPlainText(f"✓ Card database loaded with {total_cards} cards")
            elif age.days < 7:
                status = f"Database: {age.days} day{'s' if age.days != 1 else ''} old ({total_cards} cards)"
                color = SUCCESS
            elif age.days < 30:
                status = f"Database: {age.days} days old ({total_cards} cards)"
                color = WARNING
            else:
                status = f"Database: {age.days} days old (needs update)"
                color = ERROR

        self.database_status_label.setText(status)
        self.database_status_label.setStyleSheet(f"color: {color};")

    def _update_database(self):
        """Update card database."""
        from PySide6.QtWidgets import QMessageBox, QProgressDialog

        reply = QMessageBox.question(
            self, "Update Card Database",
            "Update the local card database from Scryfall? This may take a few minutes.\n\nProgress will be shown in the log.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.No:
            return

        # Show progress dialog
        progress = QProgressDialog("Updating card database...\nCheck log for details.", "Cancel", 0, 0, self)
        progress.setWindowTitle("Updating Database")
        progress.setWindowModality(Qt.WindowModal)
        progress.setMinimumDuration(0)  # Show immediately
        progress.show()

        # Add to log
        self._log_box.appendPlainText("🔄 Starting database update...")

        # Run update in background
        from threading import Thread

        def run_update():
            try:
                # Log that we're starting
                self._log_box.appendPlainText("📡 Downloading latest card data from Scryfall...")

                success, message = self._card_lookup.update_database()

                # Log completion
                if success:
                    self._log_box.appendPlainText("✅ Database update completed successfully")
                else:
                    self._log_box.appendPlainText(f"❌ Database update failed: {message}")

                return success, message
            except Exception as e:
                error_msg = f"Exception during update: {e}"
                self._log_box.appendPlainText(f"💥 {error_msg}")
                return False, error_msg

        def on_update_complete(success, message):
            progress.close()
            if success:
                QMessageBox.information(self, "Update Complete", "Database updated successfully!")
                self._update_database_status()
                # Clear cache to force reload
                self._card_lookup.cache.clear()
            else:
                QMessageBox.warning(self, "Update Failed", f"Database update failed:\n\n{message}")

        # Simple thread implementation
        import threading
        def update_thread():
            result = run_update()
            # Use QTimer to call back on main thread
            from PySide6.QtCore import QTimer
            QTimer.singleShot(0, lambda: on_update_complete(*result))

        thread = threading.Thread(target=update_thread, daemon=True)
        thread.start()

        # Update progress indicator periodically
        timer = QTimer(self)
        progress_text = [
            "Updating card database...",
            "Updating card database..",
            "Updating card database.",
            "Updating card database..."
        ]
        progress_idx = 0

        def update_progress():
            nonlocal progress_idx
            progress.setLabelText(progress_text[progress_idx % len(progress_text)])
            progress_idx += 1
            progress.setValue(progress.value() + 1)

        timer.timeout.connect(update_progress)
        timer.start(500)
    
    def _analyze_focus_cards_enhanced(self):
        """Enhanced focus card analysis using local card database."""
        focus_text = self.focus_box.toPlainText().strip()
        if not focus_text:
            self._sm("No focus cards entered to analyze.", WARNING)
            return

        cards = [line.strip() for line in focus_text.splitlines() if line.strip()]
        self._sm(f"Analyzing {len(cards)} focus cards using card database...", INFO_BLUE)

        # Attempt lazy re-init in case CWD or the DB file changed since
        # startup. Silent fallback used to happen whenever the GUI was
        # launched from a directory that lacked the DB — see card_lookup.py
        # for the CWD-independent resolution fix.
        if not self._card_lookup and CARD_LOOKUP_AVAILABLE:
            _svc = CardLookupService()
            if _svc.initialize():
                self._card_lookup = _svc

        # Clear existing selections first
        self._reset()

        # Check if card lookup is available
        if not self._card_lookup:
            banner = (
                "\n" + "!" * 70 + "\n"
                "!! CARD DATABASE UNAVAILABLE — falling back to pattern matching.\n"
                "!! Colors will NOT be auto-detected. Archetypes are best-effort\n"
                "!! from card-name tokens only. Expect wrong results.\n"
                "!! Run the database update from the toolbar, or relaunch the\n"
                "!! GUI from the repo root, to enable accurate DB-backed analysis.\n"
                + "!" * 70 + "\n"
            )
            self._log_box.appendPlainText(banner)
            self._sm("Card DB unavailable — fallback mode (see log).", WARNING)
            self._analyze_focus_cards()  # Fall back to original
            return
        else:
            self._log_box.appendPlainText(
                f"Card database loaded: "
                f"{self._card_lookup.db_metadata.get('total_cards', '?')} cards."
            )

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
        """Per-card pattern fallback when a single card is missing from the DB.

        Color guessing from card names is intentionally omitted — it has no
        reliable signal and historically produced bad colors (e.g. mono-Red
        on "Sheltered by Ghosts"). Only extract obvious tribal hints using
        whole-word matching.
        """
        tokens = set(re.findall(r"[a-z][a-z']+", card_name.lower()))
        if "angel" in tokens:
            summary["suggested_archetypes"].add("lifegain")
            if "Angel" not in summary["suggested_tribes"]:
                summary["suggested_tribes"].append("Angel")
            summary["deck_name_hints"].append("Lifegain")

    def _apply_analysis_to_gui(self, summary):
        """Apply analysis results to GUI sections."""
        # Apply colors
        for color in summary["suggested_colors"]:
            if color in COLOR_ORDER and color not in self.mana_orbital.selected:
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
            color_name = GUILD_NAMES.get(color_key, "".join(sorted(summary["suggested_colors"])))

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
        else:
            # Previously the deep pattern-matcher produced a (wrong) name
            # from substring false positives; the tightened matcher can now
            # legitimately return nothing. Tell the user instead of silently
            # leaving stale text in the field.
            missing = []
            if not summary["deck_name_hints"]:
                missing.append("archetype hints")
            if not summary["suggested_colors"]:
                missing.append("colors")
            self._log_box.appendPlainText(
                f"No deck-name suggested (missing: {', '.join(missing)}). "
                "Set --name manually."
            )

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

        self._sm(f"Auto-filled {len(summary['suggested_colors'])} colors, {len(summary['suggested_archetypes'])} archetypes, {len(summary['suggested_tribes'])} tribes, {len(summary['suggested_tags'])} tags", SUCCESS)

        # Update database status
        self._update_database_status()

    # Keep the original method as fallback
    def _analyze_focus_cards(self):
        """Original pattern matching analysis (fallback)."""
        focus_text = self.focus_box.toPlainText().strip()
        if not focus_text:
            self._sm("No focus cards entered to analyze.", WARNING)
            return

        cards = [line.strip() for line in focus_text.splitlines() if line.strip()]
        self._sm(f"Analyzing {len(cards)} focus cards to auto-fill all sections...", INFO_BLUE)

        # Clear existing selections first
        self._reset()

        # Track what we're analyzing
        suggested_colors = set()
        suggested_archetypes = set()
        suggested_tribes = []  # Changed from set() to list for slicing
        suggested_tags = set()
        deck_name_hints = []

        # Analyze each card
        self._log_box.appendPlainText(f"Analyzing {len(cards)} cards:")
        for card in cards:
            card_lower = card.lower()
            self._log_box.appendPlainText(f"  - {card}")

            # 1. COLOR ANALYSIS — DELIBERATELY DISABLED IN FALLBACK MODE.
            #
            # Guessing color identity from card-name substrings is unreliable
            # in principle ("red" ⊂ "sheltered", "blood" ⊂ "Bloodthirsty",
            # etc.) and previously produced wildly wrong results (mono-Red
            # for an Orzhov list). Colors must come from the card database
            # (DB path) or from the user's explicit mana selection.
            #
            # Guilds/shards/wedges are the one narrow exception: matching
            # an explicit whole-word guild name on a card is deliberate.
            _tokens = set(re.findall(r"[a-z][a-z']+", card_lower))
            for _guild, _ci in {
                "esper": ["W", "U", "B"], "bant": ["G", "W", "U"],
                "jund": ["B", "R", "G"],  "naya": ["R", "G", "W"],
                "grixis": ["U", "B", "R"],
                "azorius": ["W", "U"], "dimir": ["U", "B"],
                "rakdos": ["B", "R"], "gruul": ["R", "G"],
                "selesnya": ["W", "G"], "orzhov": ["W", "B"],
                "izzet": ["U", "R"], "golgari": ["B", "G"],
                "boros": ["R", "W"], "simic": ["G", "U"],
            }.items():
                if _guild in _tokens:
                    suggested_colors.update(_ci)

            # 2. ARCHETYPE ANALYSIS — word-boundary matching only.
            #
            # Old code used `pattern in card_lower`, which false-matched
            # "blood" inside "Bloodletter" → aristocrats, "scavenge" inside
            # "Scavenger's" → graveyard, etc. We now require whole-word
            # matches using the pre-tokenized set above.
            archetype_patterns = {
                "lifegain": ["vitality", "healer", "life", "ascendant", "angel", "serra", "lyra"],
                "opp_mill": ["mill", "glimpse", "tome", "archive", "memory"],
                "burn": ["burn", "lightning", "shock", "bolt", "fire", "pyro", "inferno"],
                "control": ["counter", "control", "cancel", "negate", "denial", "dissolve"],
                "ramp": ["ramp", "paradise", "growth", "cultivate", "explore", "harvest"],
                "tokens": ["token", "spawn", "army"],
                "artifacts": ["artifact", "equipment", "forge", "anvil", "hammer", "gear"],
                "enchantress": ["enchantment", "aura", "curse", "binding", "seal"],
                "graveyard": ["graveyard", "zombie", "reanimate", "unearth", "dredge", "scavenge"],
                "infect": ["infect", "poison", "toxic", "phyrexian", "blight"],
                "landfall": ["landfall", "terramorphic", "evolving", "fetch"],
                "blink": ["blink", "flicker", "restoration", "ephemerate"],
                "aristocrats": ["sacrifice", "altar", "crypt", "aristocrat"],
            }

            _card_arch_hits: list[str] = []
            for archetype, patterns in archetype_patterns.items():
                _matched = [p for p in patterns if p in _tokens]
                if _matched:
                    suggested_archetypes.add(archetype)
                    _card_arch_hits.append(f"{archetype}[{','.join(_matched)}]")
                    # Add meaningful hint for deck name
                    if archetype == "lifegain":
                        deck_name_hints.append("Lifegain")
                    elif archetype == "opp_mill":
                        deck_name_hints.append("Mill")
                    elif archetype == "burn":
                        deck_name_hints.append("Burn")
                    elif archetype == "control":
                        deck_name_hints.append("Control")
                    elif archetype == "ramp":
                        deck_name_hints.append("Ramp")
                    elif archetype in ["tokens", "artifacts", "enchantress"]:
                        deck_name_hints.append(archetype.title())

            # 3. TRIBAL ANALYSIS - Expanded
            tribal_patterns = {
                "Angel": ["angel", "seraph", "cherub"],
                "Zombie": ["zombie", "ghoul", "undead", "revenant"],
                "Elf": ["elf", "elves", "elvish"],
                "Goblin": ["goblin", "goblinoid"],
                "Merfolk": ["merfolk", "siren", "triton"],
                "Dragon": ["dragon", "wyrm", "drake"],
                "Vampire": ["vampire", "nosferatu", "bloodsucker"],
                "Human": ["human", "warrior", "soldier", "knight", "cleric", "wizard"],
                "Spirit": ["spirit", "ghost", "phantom", "specter"],
                "Elemental": ["elemental", "golem", "construct"],
                "Beast": ["beast", "wolf", "bear", "lion", "tiger"],
                "Bird": ["bird", "hawk", "eagle", "falcon"],
                "Demon": ["demon", "fiend", "devil"],
                "Sliver": ["sliver"],
                "Myr": ["myr"],
                "Eldrazi": ["eldrazi", "kozilek", "ulamog", "emrakul"]
            }

            _card_tribe_hits: list[str] = []
            for tribe, patterns in tribal_patterns.items():
                _matched = [p for p in patterns if p.lower() in _tokens]
                if _matched:
                    _card_tribe_hits.append(f"{tribe}[{','.join(_matched)}]")
                    if tribe not in suggested_tribes:
                        suggested_tribes.append(tribe)

            # Per-card debug line: exactly which patterns fired on this card.
            # Makes silent under-matching (and any future substring regression)
            # visible without digging through source.
            _summary = []
            if _card_arch_hits:
                _summary.append("arch=" + " ".join(_card_arch_hits))
            if _card_tribe_hits:
                _summary.append("tribes=" + " ".join(_card_tribe_hits))
            self._log_box.appendPlainText(
                f"      hits: {'; '.join(_summary) if _summary else '(none)'}"
            )

        # 4. TAG ANALYSIS based on archetypes
        for arch in suggested_archetypes:
            if arch in ARCHETYPE_TAG_MAP:
                suggested_tags.update(ARCHETYPE_TAG_MAP[arch])

        # 5. APPLY ANALYSIS TO ALL SECTIONS

        # Apply colors (Mana section)
        for color in suggested_colors:
            if color in COLOR_ORDER and color not in self.mana_orbital.selected:
                self.mana_orbital._toggle(color)

        # Apply archetypes
        for arch in suggested_archetypes:
            if arch in self._arch_btns and arch not in self.selected_archetypes:
                self._toggle_arch(arch)

        # Apply tribal if we found tribes
        if suggested_tribes:
            self._tribal_cb.setChecked(True)
            for tribe in suggested_tribes[:3]:  # Limit to 3 tribes
                if tribe not in self._tribes:
                    self._tribes.append(tribe)
            self._refresh_chips()

        # Apply tags
        for tag in suggested_tags:
            if tag in self._tag_btns and tag not in self._selected_tags:
                self._toggle_tag(tag)

        # 6. AUTO-GENERATE DECK NAME
        if deck_name_hints and suggested_colors:
            # Get color name
            color_key = frozenset(suggested_colors)
            color_name = GUILD_NAMES.get(color_key, "".join(sorted(suggested_colors)))

            # Get unique archetype hints
            unique_hints = []
            for hint in deck_name_hints:
                if hint not in unique_hints:
                    unique_hints.append(hint)

            # Build name
            if unique_hints:
                archetype_hint = " ".join(unique_hints[:2])  # Max 2 hints
                suggested_name = f"{color_name} {archetype_hint}"
            else:
                suggested_name = color_name

            # Set the name
            if self._auto_name.isChecked():
                self._name_prev.setText(suggested_name)
            else:
                self.name_entry.setText(suggested_name)

        # 7. AUTO-SET OPTIONS based on analysis
        if suggested_archetypes:
            # If we have complex archetypes, enable synergy analysis
            self._run_syn.setChecked(True)
            # Enable auto-build for most decks
            self._auto_bld.setChecked(True)

        # 8. LOG THE ANALYSIS
        self._log_box.appendPlainText("\n" + "="*60)
        self._log_box.appendPlainText("FOCUS CARD ANALYSIS - AUTO-FILLED ALL SECTIONS")
        self._log_box.appendPlainText("="*60)
        self._log_box.appendPlainText(f"Cards analyzed: {len(cards)}")
        self._log_box.appendPlainText(f"Suggested colors: {', '.join(sorted(suggested_colors)) or 'None detected'}")
        self._log_box.appendPlainText(f"Suggested archetypes: {', '.join(sorted(suggested_archetypes)) or 'None detected'}")
        self._log_box.appendPlainText(f"Suggested tribes: {', '.join(suggested_tribes[:5]) or 'None'}")
        self._log_box.appendPlainText(f"Suggested tags: {', '.join(sorted(suggested_tags)) or 'None'}")
        self._log_box.appendPlainText("")

        self._sm(f"Auto-filled {len(suggested_colors)} colors, {len(suggested_archetypes)} archetypes, {len(suggested_tribes)} tribes, {len(suggested_tags)} tags", SUCCESS)
            
    def _on_tribal(self, on):
        self._tribe_search.setEnabled(on); self._wildcard_cb.setVisible(on)
        if not on: self._tribes.clear(); self._refresh_chips(); self._tribe_res.hide(); self._tribe_search.clear()
        self._validate()
    def _tribe_changed(self, text):
        while self._tribe_res_l.count():
            w = self._tribe_res_l.takeAt(0).widget()
            if w: w.deleteLater()
        q = text.strip()
        if not q: self._tribe_res.hide(); return
        matches = filter_tribes(q); self._tribe_res.show()
        if not matches: self._tribe_res_l.addWidget(QLabel(f"No match for '{q}'")); return
        for t in matches[:10]:
            btn = QPushButton(f"\u2713 {t}" if t in self._tribes else t)
            btn.setStyleSheet(f"text-align:left;padding:4px 8px;"
                f"{'background:'+ACCENT_DIM+';color:'+ACCENT+';' if t in self._tribes else ''}")
            btn.clicked.connect(lambda ck=False, n=t: self._tribe_toggle(n))
            self._tribe_res_l.addWidget(btn)
    def _tribe_toggle(self, n):
        if n in self._tribes: self._tribes.remove(n)
        else: self._tribes.append(n)
        self._refresh_chips(); self._tribe_changed(self._tribe_search.text()); self._validate()
    def _refresh_chips(self):
        while self._tribe_chips_l.count():
            w = self._tribe_chips_l.takeAt(0).widget()
            if w: w.deleteLater()
        if not self._tribes: self._tribe_chips.hide(); return
        self._tribe_chips.show()
        for t in self._tribes:
            b = QPushButton(f"{t} \u00d7"); b.setObjectName("guild_chip")
            b.clicked.connect(lambda ck=False, n=t: self._tribe_toggle(n)); self._tribe_chips_l.addWidget(b)
    def _on_auto_name(self, on):
        self.name_entry.setEnabled(not on); self._update_name(); self._validate()
    def _update_name(self):
        if not self._auto_name.isChecked(): return
        n = generate_deck_name(self.mana_orbital.selected, self.selected_archetypes, self._focus_char.text())
        self._name_prev.setText(n if n else "\u2014"); self.name_entry.setText(n)
    def _get_name(self):
        if self._auto_name.isChecked():
            return generate_deck_name(self.mana_orbital.selected, self.selected_archetypes, self._focus_char.text())
        return self.name_entry.text().strip()
    def _validate(self):
        if not self.mana_orbital.selected: self._sm("\u2460 Select colours."); return False
        if not self.selected_archetypes: self._sm("\u2461 Pick archetypes."); return False
        if self._tribal_cb.isChecked() and not self._tribes: self._sm("\u2462 Tribal \u2014 pick subtype.", WARNING); return False
        if not self._get_name(): self._sm("\u2463 Enter a deck name."); return False
        self._sm("Ready!", SUCCESS); return True
    def _sm(self, msg, color=TEXT_MUTED):
        self._status.setText(msg); self._status.setStyleSheet(f"color:{color};font-size:12px;")
    def _toggle_log(self):
        self._log_vis = not self._log_vis
        self._log_box.setMaximumHeight(220 if self._log_vis else 0)
        self._log_btn.setText("\u25bc  LOG" if self._log_vis else "\u25b6  LOG")
    def _log(self, text, color=TEXT):
        self._log_box.appendPlainText(text)
        if not self._log_vis: self._toggle_log()
        self._log_inline.setText(text.strip()[:90])
        self._log_inline.setStyleSheet(f"color:{color};")
    def _log_clear(self): self._log_box.clear(); self._log_inline.setText("")
    def _reset(self):
        for c in list(self.mana_orbital.selected): self.mana_orbital._toggle(c)
        for a in list(self.selected_archetypes): self._toggle_arch(a)
        for t in list(self._selected_tags): self._toggle_tag(t)
        self._tribes.clear(); self._refresh_chips(); self._tribal_cb.setChecked(False)
        self._auto_name.setChecked(True); self.name_entry.clear()
        self._focus_char.clear(); self.output_entry.clear()
        self._skip_q.setChecked(False); self._run_syn.setChecked(True); self._auto_bld.setChecked(True)
        self._last_deck_dir = None; self._open_btn.setEnabled(False); self._validate()
    def _open_dir(self):
        if self._last_deck_dir: _open_folder(self._last_deck_dir)
    def _browse_out(self):
        d = QFileDialog.getExistingDirectory(self, "Output directory")
        if d: self.output_entry.setText(d)
    def _browse_session(self):
        f, _ = QFileDialog.getOpenFileName(self, "session.md", "", "Markdown (*.md);;All (*)")
        if f: self.rq_entry.setText(f)
    def _browse_syn_in(self):
        f, _ = QFileDialog.getOpenFileName(self, "Input", "", "MD/TXT (*.md *.txt);;All (*)")
        if f: self.syn_in.setText(f)
    def _browse_syn_out(self):
        f, _ = QFileDialog.getSaveFileName(self, "Save report", "", "Markdown (*.md);;All (*)")
        if f: self.syn_out.setText(f)

    # ── Settings ─────────────────────────────
    def _export(self):
        return {"deck_name": self.name_entry.text().strip(),
            "colors": sorted(self.mana_orbital.selected),
            "archetypes": sorted(self.selected_archetypes),
            "tribal_enabled": self._tribal_cb.isChecked(), "tribes": list(self._tribes),
            "tags": sorted(self._selected_tags),
            "focus_cards": [l.strip() for l in self.focus_box.toPlainText().strip().splitlines() if l.strip()],
            "output_dir": self.output_entry.text().strip(),
            "options": {"skip_queries": self._skip_q.isChecked(), "run_synergy": self._run_syn.isChecked(),
                "auto_build": self._auto_bld.isChecked(), "wildcard": self._wildcard_cb.isChecked()},
            "auto_name": self._auto_name.isChecked(), "focus_character": self._focus_char.text().strip()}
    def _import(self, data):
        self._reset()
        for c in data.get("colors", []):
            if c in COLOR_ORDER and c not in self.mana_orbital.selected: self.mana_orbital._toggle(c)
        for a in data.get("archetypes", []):
            if a in self._arch_btns and a not in self.selected_archetypes: self._toggle_arch(a)
        if data.get("tribal_enabled"): self._tribal_cb.setChecked(True)
        for t in data.get("tribes", []):
            if t not in self._tribes: self._tribes.append(t)
        self._refresh_chips()
        for t in data.get("tags", []):
            if t in self._tag_btns and t not in self._selected_tags: self._toggle_tag(t)
        fc = data.get("focus_cards", [])
        if fc: self.focus_box.setPlainText("\n".join(fc))
        self._auto_name.setChecked(data.get("auto_name", True))
        if data.get("focus_character"): self._focus_char.setText(data["focus_character"])
        if not data.get("auto_name", True) and data.get("deck_name"): self.name_entry.setText(data["deck_name"])
        if data.get("output_dir"): self.output_entry.setText(data["output_dir"])
        opts = data.get("options", {})
        self._skip_q.setChecked(opts.get("skip_queries", False))
        self._run_syn.setChecked(opts.get("run_synergy", True))
        self._auto_bld.setChecked(opts.get("auto_build", True))
        self._wildcard_cb.setChecked(opts.get("wildcard", False)); self._validate()
    def _on_save(self):
        data = self._export()
        dn = re.sub(r"[^\w\-]", "_", data.get("deck_name","scaffold") or "scaffold")
        f, _ = QFileDialog.getSaveFileName(self, "Save", f"{dn}{SETTINGS_EXT}",
            f"Scaffold (*{SETTINGS_EXT});;JSON (*.json)")
        if not f: return
        try: Path(f).write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"); self._sm(f"Saved: {Path(f).name}", SUCCESS)
        except Exception as e: self._sm(f"Save failed: {e}", ERROR)
    def _on_load(self):
        f, _ = QFileDialog.getOpenFileName(self, "Load", "", f"Scaffold (*{SETTINGS_EXT});;JSON (*.json)")
        if not f: return
        try: self._import(json.loads(Path(f).read_text(encoding="utf-8"))); self._sm(f"Loaded: {Path(f).name}", SUCCESS)
        except Exception as e: self._sm(f"Load failed: {e}", ERROR)

    # ── Commands ─────────────────────────────
    def _env(self): e = os.environ.copy(); e["PYTHONIOENCODING"] = "utf-8"; return e
    def _on_generate(self):
        if self._worker and self._worker.isRunning(): self._worker.cancel(); self._sm("Cancelled.", WARNING); return
        if not self._validate(): return
        name = self._get_name(); colors = normalize_colors("".join(self.mana_orbital.selected))
        cmd = [sys.executable, str(_scripts_dir/"generate_deck_scaffold.py"), "--name", name, "--colors", colors, "--archetype"]
        cmd.extend(sorted(self.selected_archetypes))
        if self._tribal_cb.isChecked():
            if self._wildcard_cb.isChecked(): cmd.append("--wildcard")
            if self._tribes: cmd.extend(["--tribe"] + self._tribes)
        if self._selected_tags: cmd.extend(["--extra-tags", ",".join(sorted(self._selected_tags))])
        od = self.output_entry.text().strip()
        if od: cmd.extend(["--output-dir", od])
        ft = self.focus_box.toPlainText().strip()
        fn = [l.strip() for l in ft.splitlines() if l.strip()]
        if fn: cmd.extend(["--focus-cards"] + fn)
        if self._skip_q.isChecked(): cmd.append("--skip-queries")
        self._log_clear()
        self._start(cmd, "scaffold", colors=colors, run_syn=self._run_syn.isChecked(),
            auto_build=self._auto_bld.isChecked(), focus_names=fn)
    def _on_queries(self):
        if self._worker and self._worker.isRunning(): self._worker.cancel(); return
        p = self.rq_entry.text().strip()
        if not p: self._sm("Select session.md.", ERROR); return
        cmd = [sys.executable, str(_scripts_dir/"run_session_queries.py"), p]
        if self._rq_force.isChecked(): cmd.append("--force")
        if self._rq_dry.isChecked(): cmd.append("--dry-run")
        self._log_clear(); self._start(cmd, "queries")
    def _on_synergy(self):
        if self._worker and self._worker.isRunning(): self._worker.cancel(); return
        inp = self.syn_in.text().strip()
        if not inp: self._sm("Select input.", ERROR); return
        cmd = [sys.executable, str(_scripts_dir/"synergy_analysis.py"), inp]
        t = self.syn_thresh.text().strip()
        if t and t != "3.0": cmd.extend(["--min-synergy", t])
        m = self._syn_mode.currentText()
        if m and m != "auto": cmd.extend(["--mode", m])
        o = self.syn_out.text().strip()
        if o: cmd.extend(["--output", o])
        # Add primary axis override based on selected archetypes
        if self.selected_archetypes:
            axes = archetype_to_axes(sorted(self.selected_archetypes))
            if axes:
                cmd.extend(["--primary-axis", ",".join(sorted(axes))])
        self._log_clear(); self._start(cmd, "synergy")

    def _on_regenerate_pool(self):
        if self._worker and self._worker.isRunning():
            self._sm("Please wait for current operation to complete.", WARNING)
            return
        if not self._last_deck_dir:
            self._sm("No deck directory available. Generate a scaffold first.", ERROR)
            self.regenerate_status.setText(" (no deck directory)")
            return
        self.regenerate_btn.setEnabled(False)
        self.regenerate_status.setText(" (regenerating...)")
        QApplication.processEvents()
        try:
            deck_dir = self._last_deck_dir
            ok, count = merge_scores_into_candidate_pool(deck_dir)
            if ok:
                self.regenerate_status.setText(f" (merged {count} cards)")
                if self._auto_bld.isChecked():
                    colors = ','.join(sorted(self.mana_orbital.selected))
                    focus_names = [l.strip() for l in self.focus_box.toPlainText().splitlines() if l.strip()]
                    ab_ok, ab_msg, _ = auto_build_decklist(
                        deck_dir, colors, focus_names)
                    if ab_ok:
                        self.regenerate_status.setText(f" (merged {count} cards, decklist rebuilt)")
                        self._sm(f"Candidate pool merged and decklist rebuilt: {ab_msg}", SUCCESS)
                    else:
                        self.regenerate_status.setText(f" (merged {count} cards, build failed: {ab_msg})")
                        self._sm(f"Candidate pool merged but decklist build failed: {ab_msg}", ERROR)
                else:
                    self._sm(f"Candidate pool merged: {count} cards updated.", SUCCESS)
            else:
                self.regenerate_status.setText(" (merge failed)")
                self._sm("Failed to merge scores into candidate pool.", ERROR)
        except Exception as e:
            self.regenerate_status.setText(" (error)")
            self._sm(f"Error during regeneration: {e}", ERROR)
        finally:
            self.regenerate_btn.setEnabled(True)

    def _start(self, cmd, source, **kw):
        self._sm("Running\u2026", ACCENT)
        self.run_btn.setText("Cancel \u2715")
        self.run_btn.setStyleSheet(f"background:{ERROR};color:#fff;border:none;border-radius:14px;font-weight:bold;font-size:14px;")
        self._worker = CommandWorker(cmd, str(self._repo.root), self._env(), source, **kw)
        self._worker.line_ready.connect(self._log)
        self._worker.finished_result.connect(self._done); self._worker.start()
    def _done(self, r):
        self.run_btn.setText("Generate Scaffold  \u203a"); self.run_btn.setStyleSheet("")
        self._worker = None
        if r.source == "scaffold" and r.success: self._show_summary(r)
        if r.synergy_output: self._show_synergy(r.synergy_output)
        if r.success:
            if r.source == "scaffold":
                n = len(r.files_found); nm = Path(r.deck_dir).name if r.deck_dir else "?"
                msg = f"Done \u2014 {n} files in {nm}"
                if r.auto_build_msg: msg += f" | {r.auto_build_msg.split('|')[0].strip()}"
                self._sm(msg, SUCCESS)
                if r.deck_dir and Path(r.deck_dir).exists(): self._last_deck_dir = r.deck_dir; self._open_btn.setEnabled(True)
            else: self._sm("Done.", SUCCESS)
        else: self._sm("Error \u2014 see log.", ERROR)
    def _show_summary(self, r):
        self._log("--- Scaffold Complete " + "-"*30, SUCCESS)
        if r.deck_dir: self._log(f"  Folder: {r.deck_dir}", INFO_BLUE)
        for f in SCAFFOLD_FILES + ["synergy_report.md", "top_200.csv"]:
            if f in r.files_found:
                fp = Path(r.deck_dir)/f if r.deck_dir else None
                sz = f"  ({fp.stat().st_size/1024:.1f} KB)" if fp and fp.exists() else ""
                self._log(f"  \u2713 {f}{sz}", SUCCESS)
            elif f in SCAFFOLD_FILES: self._log(f"  \u2717 {f}  (missing)", ERROR)
    def _show_synergy(self, syn):
        self._log("--- Gate 2.5 Synergy " + "-"*30, ACCENT)
        for line in syn.splitlines():
            c = (ERROR if "[FAIL]" in line else SUCCESS if "[PASS]" in line else
                 INFO_BLUE if "[INFO]" in line else ACCENT if line.startswith(("#","**")) else TEXT)
            self._log(line, c)


def main():
    app = QApplication(sys.argv)
    app.setStyleSheet(DARK_QSS)
    _load_mana_font()
    win = ScaffoldApp()
    win.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
