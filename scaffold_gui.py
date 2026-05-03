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

# ---------------------------------------------------------------------------
# Scripts path setup
# ---------------------------------------------------------------------------
_scripts_dir = Path(__file__).resolve().parent / "scripts"
_cli_dir = _scripts_dir / "cli"
sys.path.insert(0, str(_scripts_dir))
sys.path.insert(0, str(_cli_dir))
# Also insert utils so direct module imports resolve
sys.path.insert(0, str(_scripts_dir / "utils"))
sys.path.insert(0, str(_scripts_dir / "analysis"))

import importlib.util


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
    imported = []
    for name in names:
        if hasattr(module, name):
            globals()[name] = getattr(module, name)
            imported.append(name)
        else:
            print(f"Warning: {name} not found in {module_name}")
    globals()[module_name] = module
    return imported


# --- generate_deck_scaffold imports ---
try:
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
    ALL_CREATURE_TYPES = []
    ARCHETYPE_QUERIES = {}

    def sanitize_folder_name(name):
        return "".join(c for c in name if c.isalnum() or c in " -_").strip()


# --- RepoPaths ---
try:
    from scripts.utils.mtg_utils import RepoPaths
except ImportError:
    try:
        from mtg_utils import RepoPaths
    except ImportError:
        print("Warning: mtg_utils not found, using stub")

        class RepoPaths:
            def __init__(self):
                self.root = Path(__file__).parent
                self.cards_by_category = self.root / "cards_by_category"


# --- auto_build imports (FIX 2: correct module is scripts/utils/auto_build.py) ---
try:
    # FIX 2: auto_build lives in scripts/utils/auto_build.py
    _utils_path = str(Path(__file__).parent / "scripts" / "utils")
    if _utils_path not in sys.path:
        sys.path.insert(0, _utils_path)
    from auto_build import (
        auto_build_decklist,
        merge_scores_into_candidate_pool,
        normalize_colors,
        sort_and_rewrite_csv,
        COLOR_ORDER,
        MANA_NAMES,
    )
except ImportError as e:
    try:
        # FIX 3: retry with explicit path injection
        _utils_path2 = str(Path(__file__).parent / "scripts" / "utils")
        if _utils_path2 not in sys.path:
            sys.path.insert(0, _utils_path2)
        from auto_build import (
            auto_build_decklist,
            merge_scores_into_candidate_pool,
            normalize_colors,
            sort_and_rewrite_csv,
            COLOR_ORDER,
            MANA_NAMES,
        )
    except ImportError:
        print(f"Warning: auto_build module not available: {e}")
        print("Using stubs...")

        def auto_build_decklist(*args, **kwargs):
            return (False, "auto_build module not available", [])

        merge_scores_into_candidate_pool = lambda x: None
        normalize_colors = lambda x: x

        def sort_and_rewrite_csv(*args, **kwargs):
            return None

        # FIX 4: Ensure COLOR_ORDER and MANA_NAMES are ALWAYS defined
        COLOR_ORDER = "WUBRG"
        MANA_NAMES = {"W": "White", "U": "Blue", "B": "Black", "R": "Red", "G": "Green"}


# --- card lookup ---
try:
    from scripts.utils.card_lookup import CardLookupService
    from scripts.analysis.card_analysis import analyze_card_data
    CARD_LOOKUP_AVAILABLE = True
except ImportError:
    CARD_LOOKUP_AVAILABLE = False
    CardLookupService = None
    analyze_card_data = None


# ---------------------------------------------------------------------------
# Mana icon font discovery
# ---------------------------------------------------------------------------
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
    # FIX 1: Check flat layout (assets/mana/mana.ttf) BEFORE nested fonts/ subdir
    _font = _base / "mana.ttf"
    if not _font.exists():
        _font = _base / "fonts" / "mana.ttf"
    _svg = _base / "svg"
    if _font.exists() and not _MANA_FONT_PATH:
        _MANA_FONT_PATH = _font
    if _svg.is_dir() and not _MANA_SVG_DIR:
        _MANA_SVG_DIR = _svg
    if _MANA_FONT_PATH and _MANA_SVG_DIR:
        break


# ---------------------------------------------------------------------------
# Mana font character map (Unicode PUA)
# ---------------------------------------------------------------------------
IC: dict[str, str] = {
    "W": "\ue600", "U": "\ue601", "B": "\ue602",
    "R": "\ue603", "G": "\ue604",
    "artifact": "\ue61e", "creature": "\ue61f",
    "enchantment": "\ue620", "instant": "\ue621",
    "land": "\ue622", "planeswalker": "\ue623",
    "sorcery": "\ue624", "token": "\ue96d",
    "haste": "\ue953", "trample": "\ue964", "flying": "\ue952",
    "deathtouch": "\ue94b", "menace": "\ue95d", "flash": "\ue951",
    "counter": "\ue954", "removal": "\uea69", "wipe": "\ue9a7",
    "bounce": "\ue965", "protection": "\ue954", "draw": "\ue948",
    "ramp": "\ue622", "tutor": "\ue94f", "mill": "\ue940",
    "etb": "\ue966", "lifegain": "\uea4b", "pump": "\ue93d",
    "ward": "\ue992", "prowess": "\ue982", "proliferate": "\ue981",
    "landfall": "\ue988", "infect": "\uea73",
    "counter_skull": "\ue940", "counter_shield": "\ue9c3",
    "power": "\ue921", "toughness": "\ue922",
    "colorpie": "\ue9f0", "multiple": "\ue925",
    "guild_azorius": "\ue90c", "guild_boros": "\ue90d",
    "guild_dimir": "\ue90e", "guild_golgari": "\ue90f",
    "guild_gruul": "\ue910", "guild_izzet": "\ue911",
    "guild_orzhov": "\ue912", "guild_rakdos": "\ue913",
    "guild_selesnya": "\ue914", "guild_simic": "\ue915",
    "clan_abzan": "\ue916", "clan_jeskai": "\ue917",
    "clan_mardu": "\ue918", "clan_sultai": "\ue919",
    "clan_temur": "\ue91a",
}


# ---------------------------------------------------------------------------
# Palette
# ---------------------------------------------------------------------------
APP_TITLE    = "MTG Deck Scaffold Generator"
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


# ---------------------------------------------------------------------------
# Game data constants  (kept verbatim from original)
# ---------------------------------------------------------------------------
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
    frozenset("WU"): "Azorius",   frozenset("WB"): "Orzhov",
    frozenset("WR"): "Boros",     frozenset("WG"): "Selesnya",
    frozenset("UB"): "Dimir",     frozenset("UR"): "Izzet",
    frozenset("UG"): "Simic",     frozenset("BR"): "Rakdos",
    frozenset("BG"): "Golgari",   frozenset("RG"): "Gruul",
    frozenset("WUB"): "Esper",    frozenset("WUR"): "Jeskai",
    frozenset("WUG"): "Bant",     frozenset("WBR"): "Mardu",
    frozenset("WBG"): "Abzan",    frozenset("WRG"): "Naya",
    frozenset("UBR"): "Grixis",   frozenset("UBG"): "Sultai",
    frozenset("URG"): "Temur",    frozenset("BRG"): "Jund",
    frozenset("WUBR"): "Non-Green", frozenset("WUBG"): "Non-Red",
    frozenset("WURG"): "Non-Black", frozenset("WBRG"): "Non-Blue",
    frozenset("UBRG"): "Non-White",
    frozenset("WUBRG"): "Five-Color",
}


# ---------------------------------------------------------------------------
# FIX 8: archetype_to_axes — called in _on_synergy but never previously defined
# ---------------------------------------------------------------------------
def archetype_to_axes(archetypes: list[str]) -> list[str]:
    """Map selected archetypes to synergy analysis primary axes."""
    _MAP: dict[str, list[str]] = {
        "aggro":        ["haste", "pump", "trample"],
        "burn":         ["removal", "haste"],
        "prowess":      ["draw", "pump"],
        "infect":       ["pump", "trample"],
        "midrange":     ["removal", "draw"],
        "tempo":        ["bounce", "counter", "flash"],
        "blink":        ["etb", "bounce"],
        "lifegain":     ["lifegain", "draw"],
        "control":      ["counter", "removal", "wipe", "draw"],
        "stax":         ["protection"],
        "superfriends": ["protection", "wipe"],
        "combo":        ["tutor", "draw"],
        "storm":        ["draw", "ramp"],
        "extra_turns":  ["draw", "counter"],
        "graveyard":    ["mill"],
        "reanimation":  ["mill", "tutor"],
        "flashback":    ["mill", "draw"],
        "madness":      ["draw"],
        "self_mill":    ["mill"],
        "opp_mill":     ["mill"],
        "tokens":       ["pump"],
        "aristocrats":  ["draw"],
        "enchantress":  ["draw", "protection"],
        "equipment":    ["pump"],
        "artifacts":    ["draw", "ramp"],
        "vehicles":     ["haste"],
        "voltron":      ["pump", "protection"],
        "ramp":         ["ramp", "draw"],
        "landfall":     ["ramp"],
        "lands":        ["ramp"],
        "domain":       ["ramp"],
        "eldrazi":      ["ramp"],
        "energy":       ["draw", "pump"],
        "proliferate":  ["pump"],
    }
    axes: set[str] = set()
    for arch in archetypes:
        axes.update(_MAP.get(arch, []))
    return sorted(axes)


# ---------------------------------------------------------------------------
# Subprocess helpers — all paths anchored to scripts/{cli,utils,analysis}.
# These centralise the "FIX 5/6/7" path-correction so any future caller goes
# through one place.
# ---------------------------------------------------------------------------
def _run_generate_scaffold(args: list[str]) -> tuple[int, str]:
    """Invoke scripts/cli/generate_deck_scaffold.py (FIX 5)."""
    cmd = [sys.executable, str(_cli_dir / "generate_deck_scaffold.py"), *args]
    return _run_subprocess(cmd)


def _run_session_queries(deck_path: str) -> tuple[int, str]:
    """Invoke scripts/utils/run_session_queries.py (FIX 6)."""
    cmd = [sys.executable, str(_scripts_dir / "utils" / "run_session_queries.py"), deck_path]
    return _run_subprocess(cmd)


def _run_synergy_analysis(*args: str) -> tuple[int, str]:
    """Invoke scripts/analysis/synergy_analysis.py (FIX 7a/b)."""
    cmd = [sys.executable, str(_scripts_dir / "analysis" / "synergy_analysis.py"), *args]
    return _run_subprocess(cmd)


def _run_subprocess(cmd: list[str]) -> tuple[int, str]:
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=str(Path(__file__).resolve().parent),
        )
        return proc.returncode, (proc.stdout or "") + (proc.stderr or "")
    except FileNotFoundError as exc:
        return 127, f"Command not found: {exc}"
    except Exception as exc:  # pragma: no cover
        return 1, f"Subprocess error: {exc!r}\n{traceback.format_exc()}"


# ---------------------------------------------------------------------------
# Mana font registration helper
# ---------------------------------------------------------------------------
def _register_mana_font() -> str | None:
    """Register the mana TTF font with QFontDatabase if available.

    Returns the registered family name, or None if registration failed/no font.
    """
    if not _MANA_FONT_PATH:
        return None
    try:
        font_id = QFontDatabase.addApplicationFont(str(_MANA_FONT_PATH))
        if font_id < 0:
            return None
        families = QFontDatabase.applicationFontFamilies(font_id)
        return families[0] if families else None
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Result of a background subprocess
# ---------------------------------------------------------------------------
@dataclass
class RunResult:
    code: int
    output: str
    label: str = ""


# ---------------------------------------------------------------------------
# CommandWorker — runs a subprocess off the GUI thread
# ---------------------------------------------------------------------------
class CommandWorker(QThread):
    finished_with_result = Signal(object)  # RunResult

    def __init__(self, cmd: list[str], label: str = "", parent=None):
        super().__init__(parent)
        self._cmd = cmd
        self._label = label

    def run(self) -> None:  # noqa: D401
        code, output = _run_subprocess(self._cmd)
        self.finished_with_result.emit(RunResult(code=code, output=output, label=self._label))


# ---------------------------------------------------------------------------
# MainWindow — minimal dashboard that exposes the recovery-scope features.
# Full widget set (mana selectors, archetype cards, etc.) will be re-added in
# a follow-up; this window keeps the public entry-points working today.
# ---------------------------------------------------------------------------
class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(APP_TITLE)
        self.resize(1100, 720)
        self._mana_family = _register_mana_font()
        self._workers: list[CommandWorker] = []
        self._build_ui()
        self._apply_palette()

    # ── UI ----------------------------------------------------------------
    def _build_ui(self) -> None:
        central = QWidget(self)
        root = QVBoxLayout(central)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)

        title = QLabel(APP_TITLE)
        title.setStyleSheet(f"color: {ACCENT}; font-size: 22px; font-weight: 600;")
        root.addWidget(title)

        subtitle = QLabel(
            "Recovery build — core actions are wired; full widget set returns in a follow-up."
        )
        subtitle.setStyleSheet(f"color: {TEXT_DIM}; font-size: 12px;")
        root.addWidget(subtitle)

        # Generate Scaffold panel ----------------------------------------
        gen_panel = self._panel("Generate Deck Scaffold")
        gen_layout = gen_panel.layout()

        row = QHBoxLayout()
        row.addWidget(QLabel("Archetype:"))
        self.archetype_combo = QComboBox()
        self.archetype_combo.addItems(sorted(ARCH_LABEL.keys()))
        row.addWidget(self.archetype_combo, 1)
        gen_layout.addLayout(row)

        row2 = QHBoxLayout()
        row2.addWidget(QLabel("Colors (e.g. WU):"))
        self.colors_edit = QLineEdit()
        self.colors_edit.setPlaceholderText("WUBRG subset")
        row2.addWidget(self.colors_edit, 1)
        gen_layout.addLayout(row2)

        row3 = QHBoxLayout()
        row3.addWidget(QLabel("Output dir:"))
        self.outdir_edit = QLineEdit()
        self.outdir_edit.setPlaceholderText("Decks/MyDeck")
        row3.addWidget(self.outdir_edit, 1)
        browse = QPushButton("Browse…")
        browse.clicked.connect(self._on_browse_outdir)
        row3.addWidget(browse)
        gen_layout.addLayout(row3)

        gen_btn_row = QHBoxLayout()
        self.generate_btn = QPushButton("Generate Scaffold")
        self.generate_btn.clicked.connect(self._on_generate)
        gen_btn_row.addWidget(self.generate_btn)

        self.session_btn = QPushButton("Run Session Queries")
        self.session_btn.clicked.connect(self._on_session)
        gen_btn_row.addWidget(self.session_btn)

        self.synergy_btn = QPushButton("Synergy Analysis")
        self.synergy_btn.clicked.connect(self._on_synergy)
        gen_btn_row.addWidget(self.synergy_btn)
        gen_btn_row.addStretch(1)
        gen_layout.addLayout(gen_btn_row)

        root.addWidget(gen_panel)

        # Output panel ----------------------------------------------------
        out_panel = self._panel("Output")
        self.log_box = QPlainTextEdit()
        self.log_box.setReadOnly(True)
        self.log_box.setStyleSheet(
            f"background:{SURFACE}; color:{TEXT}; border:1px solid {BORDER}; "
            f"font-family: monospace;"
        )
        out_panel.layout().addWidget(self.log_box)
        root.addWidget(out_panel, 1)

        self.setCentralWidget(central)

    def _panel(self, title: str) -> QFrame:
        frame = QFrame()
        frame.setStyleSheet(
            f"QFrame {{ background:{CARD_BG}; border:1px solid {CARD_BORDER}; border-radius:8px; }}"
        )
        v = QVBoxLayout(frame)
        v.setContentsMargins(14, 12, 14, 12)
        v.setSpacing(8)
        head = QLabel(title)
        head.setStyleSheet(f"color:{TEXT}; font-weight:600; font-size:14px; border:none;")
        v.addWidget(head)
        return frame

    def _apply_palette(self) -> None:
        self.setStyleSheet(
            f"QMainWindow {{ background:{BG}; }} "
            f"QLabel {{ color:{TEXT}; }} "
            f"QLineEdit, QComboBox {{ background:{SURFACE}; color:{TEXT}; "
            f"border:1px solid {BORDER}; padding:4px; border-radius:4px; }} "
            f"QPushButton {{ background:{ACCENT_DIM}; color:{ACCENT}; "
            f"border:1px solid {ACCENT}; padding:6px 12px; border-radius:4px; }} "
            f"QPushButton:hover {{ background:{ACCENT}; color:#000; }}"
        )

    # ── Event handlers ----------------------------------------------------
    def _log(self, msg: str) -> None:
        self.log_box.appendPlainText(msg)

    def _on_browse_outdir(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Choose output directory")
        if path:
            self.outdir_edit.setText(path)

    def _on_generate(self) -> None:
        archetype = self.archetype_combo.currentText().strip()
        colors = self.colors_edit.text().strip().upper()
        outdir = self.outdir_edit.text().strip()
        if not archetype or not colors or not outdir:
            self._log("Generate: archetype, colors, and output dir are all required.")
            return
        # FIX 5: subprocess uses scripts/cli/
        cmd = [
            sys.executable,
            str(_cli_dir / "generate_deck_scaffold.py"),
            "--archetype", archetype,
            "--colors", colors,
            "--out", outdir,
        ]
        self._spawn(cmd, label=f"generate_deck_scaffold {archetype}/{colors}")

    def _on_session(self) -> None:
        outdir = self.outdir_edit.text().strip()
        if not outdir:
            self._log("Session: output dir is required.")
            return
        # FIX 6: scripts/utils/run_session_queries.py
        cmd = [
            sys.executable,
            str(_scripts_dir / "utils" / "run_session_queries.py"),
            outdir,
        ]
        self._spawn(cmd, label="run_session_queries")

    def _on_synergy(self) -> None:
        outdir = self.outdir_edit.text().strip()
        if not outdir:
            self._log("Synergy: output dir is required.")
            return
        decklist = str(Path(outdir) / "decklist.txt")
        # FIX 7a/b: scripts/analysis/synergy_analysis.py
        cmd = [
            sys.executable,
            str(_scripts_dir / "analysis" / "synergy_analysis.py"),
            decklist,
            "--mode", "deck",
            "--format", "decklist",
        ]
        self._spawn(cmd, label="synergy_analysis")

    def _spawn(self, cmd: list[str], label: str) -> None:
        self._log(f"$ {' '.join(cmd)}")
        worker = CommandWorker(cmd, label=label, parent=self)
        worker.finished_with_result.connect(self._on_worker_done)
        self._workers.append(worker)
        worker.start()

    def _on_worker_done(self, result: RunResult) -> None:
        self._log(f"--- {result.label} (exit {result.code}) ---")
        if result.output:
            self._log(result.output.rstrip())
        self._workers = [w for w in self._workers if w.isRunning()]


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def main() -> int:
    """Launch the GUI. Returns the Qt exit code."""
    app = QApplication.instance() or QApplication(sys.argv)
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())

