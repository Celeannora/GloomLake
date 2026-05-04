#!/usr/bin/env python3
"""
MTG Deck Scaffold Generator — GUI (PySide6)
Fully rebuilt with SVG assets, glassmorphism panels, animations,
guild watermarks, keyboard shortcuts, deck history, and rich tooltips.
"""

import json
import os
import re
import sqlite3
import subprocess
import sys
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from pathlib import Path

from PySide6.QtCore import (
    Qt, QThread, Signal, QSize, QPropertyAnimation, QEasingCurve,
    QPoint, QTimer, QRect, QParallelAnimationGroup, QSequentialAnimationGroup,
    QPauseAnimation, QSettings,
)
from PySide6.QtGui import (
    QColor, QIcon, QPixmap, QImage, QFont, QPainter, QPen, QBrush,
    QRadialGradient, QLinearGradient, QCursor, QAction, QKeySequence,
    QFontDatabase, QPainterPath, QTransform,
)
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QGridLayout, QTabWidget, QScrollArea, QFrame, QLabel, QPushButton,
    QLineEdit, QPlainTextEdit, QCheckBox, QComboBox,
    QFileDialog, QSplitter, QSizePolicy, QProgressBar, QTableWidget,
    QTableWidgetItem, QHeaderView, QAbstractItemView, QToolTip,
    QGraphicsDropShadowEffect, QDialog, QTextBrowser, QMenu,
    QMessageBox, QSystemTrayIcon, QStyle, QInputDialog,
)

# ═══════════════════════════════════════════════════════════════════════════════
# Project root & path setup
# ═══════════════════════════════════════════════════════════════════════════════
PROJECT_ROOT = Path(__file__).resolve().parent
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
CLI_DIR = SCRIPTS_DIR / "cli"
sys.path.insert(0, str(SCRIPTS_DIR))
sys.path.insert(0, str(CLI_DIR))
sys.path.insert(0, str(SCRIPTS_DIR / "utils"))
sys.path.insert(0, str(SCRIPTS_DIR / "analysis"))

# Asset paths
SVG_SET_DIR = PROJECT_ROOT / "assets" / "mtg-vectors-main" / "svg" / "set"
SVG_WATERMARK_DIR = PROJECT_ROOT / "assets" / "mtg-vectors-main" / "svg" / "watermark"
DB_PATH = PROJECT_ROOT / "assets" / "data" / "cards.db"

from generate_deck_scaffold import ALL_CREATURE_TYPES, ARCHETYPE_QUERIES, sanitize_folder_name

try:
    from scripts.utils.mtg_utils import RepoPaths
except ImportError:
    class RepoPaths:
        def __init__(self):
            self.root = PROJECT_ROOT
            self.cards_by_category = self.root / "cards_by_category"


# ═══════════════════════════════════════════════════════════════════════════════
# Color System
# ═══════════════════════════════════════════════════════════════════════════════
class Colors:
    BG_DARK       = "#060810"
    BG            = "#0a0d16"
    BG_OVERLAY    = "#0e1120"
    CARD          = "#12162a"
    CARD_HOVER    = "#181e38"
    CARD_BORDER   = "#1e2440"
    SURFACE       = "#151a30"
    SURFACE_ALT   = "#1c2340"
    SURFACE_HOVER = "#222a4a"
    BORDER        = "#263050"
    BORDER_LIGHT  = "#354070"
    ACCENT        = "#e8b830"
    ACCENT_HOVER  = "#f5d060"
    ACCENT_DIM    = "#2a2210"
    ACCENT_2      = "#a855f7"
    ACCENT_2_DIM  = "#201030"
    ACCENT_3      = "#38bdf8"
    ACCENT_4      = "#34d399"
    TEXT          = "#eef0f5"
    TEXT_DIM      = "#8890b0"
    TEXT_MUTED    = "#505878"
    SUCCESS       = "#34d399"
    ERROR         = "#f87171"
    WARNING       = "#fbbf24"
    INFO          = "#60a5fa"

    # Card type colours
    CREATURE      = "#34d399"
    INSTANT       = "#f87171"
    SORCERY       = "#fbbf24"
    ENCHANTMENT   = "#a78bfa"
    ARTIFACT      = "#94a3b8"
    PLANESWALKER  = "#c084fc"
    LAND          = "#86efac"

    # Rarity
    RARITY_COMMON   = "#94a3b8"
    RARITY_UNCOMMON = "#a3a8b8"
    RARITY_RARE     = "#e8b830"
    RARITY_MYTHIC   = "#f97316"

    MANA = {
        "W": {"bg": "#f0e8d0", "fg": "#1a1a1a", "dim": "#1e1c18", "name": "White",  "hex": "#f0e8d0"},
        "U": {"bg": "#3b7dd8", "fg": "#ffffff", "dim": "#0e1828", "name": "Blue",   "hex": "#3b7dd8"},
        "B": {"bg": "#6b5a80", "fg": "#e8daf0", "dim": "#16121e", "name": "Black",  "hex": "#6b5a80"},
        "R": {"bg": "#d04a42", "fg": "#ffffff", "dim": "#1e0e0e", "name": "Red",    "hex": "#d04a42"},
        "G": {"bg": "#3a8a55", "fg": "#ffffff", "dim": "#0e1a12", "name": "Green",  "hex": "#3a8a55"},
    }

    @staticmethod
    def type_color(type_line: str) -> str:
        tl = type_line.lower()
        if "creature" in tl:       return Colors.CREATURE
        if "instant" in tl:        return Colors.INSTANT
        if "sorcery" in tl:        return Colors.SORCERY
        if "enchantment" in tl:    return Colors.ENCHANTMENT
        if "artifact" in tl:       return Colors.ARTIFACT
        if "planeswalker" in tl:   return Colors.PLANESWALKER
        if "land" in tl:           return Colors.LAND
        return Colors.TEXT_DIM

    @staticmethod
    def rarity_color(rarity: str) -> str:
        r = (rarity or "").lower()
        if r == "mythic":    return Colors.RARITY_MYTHIC
        if r == "rare":      return Colors.RARITY_RARE
        if r == "uncommon":  return Colors.RARITY_UNCOMMON
        return Colors.RARITY_COMMON


# ═══════════════════════════════════════════════════════════════════════════════
# SVG Asset Helpers
# ═══════════════════════════════════════════════════════════════════════════════
def _find_svg(subdir: str, name: str) -> Path | None:
    """Search for an SVG file in mtg-vectors-main subdirectory."""
    base = PROJECT_ROOT / "assets" / "mtg-vectors-main" / "svg" / subdir
    if not base.exists():
        return None
    for candidate in [
        base / f"{name}.svg",
        base / f"{name.lower()}.svg",
        base / f"{name.upper()}.svg",
    ]:
        if candidate.exists():
            return candidate
    return None


def _svg_to_icon(path: Path, size: int = 32, fallback_color: str | None = None) -> QIcon:
    """Convert SVG file to QIcon at given size."""
    try:
        image = QImage(str(path))
        if not image.isNull():
            pixmap = QPixmap.fromImage(
                image.scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            )
            return QIcon(pixmap)
    except Exception:
        pass
    return QIcon()


def load_mana_svg_icon(color: str, size: int = 36) -> QIcon:
    """Load mana symbol SVG for a colour — tries ZNE set first, then any set."""
    if color not in "WUBRG":
        return QIcon()
    # Try several set directories
    for set_code in ["ZNE", "ZNR", "M21", "M20", "XLN", "DOM", "GRN", "RNA", "WAR", "ELD"]:
        path = _find_svg(f"set/{set_code}", color)
        if path:
            return _svg_to_icon(path, size)
    return QIcon()


def load_guild_watermark_icon(guild_key: str, size: int = 64) -> QIcon:
    """Load guild/shard watermark SVG.  guild_key like 'dimir','azorius','abzan','esper' etc."""
    path = _find_svg("watermark", guild_key)
    if path:
        return _svg_to_icon(path, size)
    return QIcon()


def load_set_symbol_icon(set_code: str, size: int = 24) -> QIcon:
    """Load a set symbol — uses C.svg (common) from a set directory."""
    path = _find_svg(f"set/{set_code}", "C")
    if path:
        return _svg_to_icon(path, size)
    return QIcon()


# ═══════════════════════════════════════════════════════════════════════════════
# Programmatic fallbacks for mana / type dots (used when SVGs missing)
# ═══════════════════════════════════════════════════════════════════════════════
def create_mana_icon_fallback(color: str, size: int = 36) -> QIcon:
    mc = Colors.MANA.get(color, {})
    bg = mc.get("bg", "#888888")
    fg = mc.get("fg", "#ffffff")
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    gradient = QRadialGradient(size / 2, size / 2, size / 2)
    gradient.setColorAt(0, QColor(bg).lighter(130))
    gradient.setColorAt(1, QColor(bg))
    painter.setPen(QPen(QColor(0, 0, 0, 100), 1.5))
    painter.setBrush(QBrush(gradient))
    m = 2
    painter.drawEllipse(m, m, size - 2 * m, size - 2 * m)
    painter.setPen(QColor(fg))
    painter.setFont(QFont("Segoe UI", int(size * 0.42), QFont.Bold))
    painter.drawText(m, m, size - 2 * m, size - 2 * m, Qt.AlignCenter, color)
    painter.end()
    return QIcon(pixmap)


def create_colorized_svg_icon(color_char: str, size: int = 36) -> QIcon:
    """Try SVG first, fall back to programmatic."""
    icon = load_mana_svg_icon(color_char, size)
    if not icon.isNull():
        return icon
    return create_mana_icon_fallback(color_char, size)


def type_pip_icon(type_line: str, size: int = 12) -> QIcon:
    """Small coloured pip for card type."""
    color = Colors.type_color(type_line)
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setBrush(QBrush(QColor(color)))
    painter.setPen(Qt.NoPen)
    painter.drawEllipse(0, 0, size, size)
    painter.end()
    return QIcon(pixmap)


# ═══════════════════════════════════════════════════════════════════════════════
# Archetype / Tag data
# ═══════════════════════════════════════════════════════════════════════════════
ARCHETYPE_GROUPS = OrderedDict([
    ("Aggro",        {"aggro": "Fast creatures", "burn": "Direct damage", "prowess": "Spell triggers", "infect": "Poison"}),
    ("Midrange",     {"midrange": "Efficient threats", "tempo": "Cheap + disruption", "blink": "ETB value", "lifegain": "Life gain"}),
    ("Control",      {"control": "Counter/remove", "stax": "Tax effects", "superfriends": "Planeswalkers"}),
    ("Combo",        {"combo": "Card combos", "storm": "Chain spells", "extra_turns": "Extra turns"}),
    ("Graveyard",    {"graveyard": "GY resource", "reanimation": "Reanimate", "self_mill": "Self mill", "opp_mill": "Opp mill"}),
    ("Permanents",   {"tokens": "Token creation", "aristocrats": "Sacrifice", "enchantress": "Enchantments", "equipment": "Equipment", "artifacts": "Artifacts", "voltron": "Auras"}),
    ("Ramp & Lands", {"ramp": "Mana ramp", "landfall": "Land drops", "lands": "Land strategy", "domain": "5 basics", "tribal": "Creature types"}),
])

TAG_OPTIONS = OrderedDict([
    ("Offensive", ["haste", "trample", "pump", "flying", "deathtouch", "menace"]),
    ("Defensive", ["counter", "removal", "wipe", "bounce", "protection", "flash"]),
    ("Utility",   ["draw", "ramp", "tutor", "mill", "etb", "lifegain"]),
])

FORMATS = ["Standard", "Modern", "Commander", "Pioneer", "Pauper", "Vintage", "Legacy", "Brawl"]

COLOR_PRESETS = {
    "WU — Azorius":  "WU",  "WB — Orzhov": "WB",  "WR — Boros":  "WR",  "WG — Selesnya": "WG",
    "UB — Dimir":    "UB",  "UR — Izzet":  "UR",  "UG — Simic":  "UG",
    "BR — Rakdos":   "BR",  "BG — Golgari":"BG",
    "RG — Gruul":    "RG",
    "WUB — Esper":   "WUB", "WUR — Jeskai":"WUR", "WUG — Bant":  "WUG",
    "WBR — Mardu":   "WBR", "WBG — Abzan": "WBG",
    "URG — Temur":   "URG", "UBR — Grixis":"UBR", "UBG — Sultai":"UBG",
    "BRG — Jund":    "BRG", "WRG — Naya":  "WRG",
    "5c — WUBRG":    "WUBRG",
}


# ═══════════════════════════════════════════════════════════════════════════════
# Guild detection
# ═══════════════════════════════════════════════════════════════════════════════
def detect_guild(colors_str: str):
    normalized = "".join(dict.fromkeys(c for c in colors_str.upper() if c in "WUBRG"))
    cs = frozenset(normalized)
    guilds = {
        frozenset({"W", "U"}): ("Azorius", "WU"), frozenset({"W", "B"}): ("Orzhov", "WB"),
        frozenset({"W", "R"}): ("Boros", "WR"),   frozenset({"W", "G"}): ("Selesnya", "WG"),
        frozenset({"U", "B"}): ("Dimir", "UB"),   frozenset({"U", "R"}): ("Izzet", "UR"),
        frozenset({"U", "G"}): ("Simic", "UG"),   frozenset({"B", "R"}): ("Rakdos", "BR"),
        frozenset({"B", "G"}): ("Golgari", "BG"), frozenset({"R", "G"}): ("Gruul", "RG"),
    }
    shards = {
        frozenset({"W", "U", "B"}): ("Esper", "WUB"), frozenset({"W", "U", "R"}): ("Jeskai", "WUR"),
        frozenset({"W", "U", "G"}): ("Bant", "WUG"),  frozenset({"W", "B", "R"}): ("Mardu", "WBR"),
        frozenset({"W", "B", "G"}): ("Abzan", "WBG"), frozenset({"U", "R", "G"}): ("Temur", "URG"),
        frozenset({"U", "B", "R"}): ("Grixis", "UBR"),frozenset({"U", "B", "G"}): ("Sultai", "UBG"),
        frozenset({"B", "R", "G"}): ("Jund", "BRG"),  frozenset({"W", "R", "G"}): ("Naya", "WRG"),
    }
    if cs == frozenset({"W", "U", "B", "R", "G"}):
        return "WUBRG", "Five-Color"
    for d in [shards, guilds]:
        if cs in d:
            return d[cs]
    if len(normalized) == 1:
        return normalized, f"Mono-{Colors.MANA.get(normalized, {}).get('name', normalized)}"
    return None, None


# ═══════════════════════════════════════════════════════════════════════════════
# Workers
# ═══════════════════════════════════════════════════════════════════════════════
@dataclass
class RunResult:
    code: int
    output: str
    label: str = ""


class CommandWorker(QThread):
    finished_with_result = Signal(object)

    def __init__(self, cmd, label="", parent=None):
        super().__init__(parent)
        self._cmd = cmd
        self._label = label

    def run(self):
        try:
            proc = subprocess.run(
                self._cmd, capture_output=True, text=True, encoding="utf-8",
                errors="replace", cwd=str(PROJECT_ROOT)
            )
            output = (proc.stdout or "") + (proc.stderr or "")
            self.finished_with_result.emit(
                RunResult(code=proc.returncode, output=output, label=self._label)
            )
        except Exception as exc:
            self.finished_with_result.emit(
                RunResult(code=1, output=str(exc), label=self._label)
            )


class SynergyBuildWorker(QThread):
    finished_with_result = Signal(dict)
    error = Signal(str)

    def __init__(self, colors, archetype, fmt="Standard", parent=None):
        super().__init__(parent)
        self._colors = colors
        self._archetype = archetype
        self._format = fmt

    def run(self):
        try:
            from greedy_synergy_engine import SynergyEngine
            if not DB_PATH.exists():
                self.error.emit(f"Database not found at {DB_PATH}")
                return
            engine = SynergyEngine(DB_PATH)
            try:
                eligible = engine.get_eligible_cards(
                    list(self._colors), self._format, limit=500
                )
                lands = engine.get_lands(list(self._colors), limit=30)
                land_counts = {
                    "Aggro": 20, "Tempo": 21, "Midrange": 23,
                    "Ramp": 25, "Control": 26, "Combo": 23
                }
                result = engine.select_synergistic_deck(
                    eligible, lands, self._archetype, deck_size=60,
                    land_count=land_counts.get(self._archetype, 23)
                )
                analysis = engine.analyze_deck_synergy(result["deck"])
                result["analysis"] = analysis
                result["colors"] = self._colors
                result["archetype"] = self._archetype
                result["format"] = self._format
                self.finished_with_result.emit(result)
            finally:
                engine.close()
        except Exception as exc:
            self.error.emit(str(exc))


# ═══════════════════════════════════════════════════════════════════════════════
# Animated Curve Chart
# ═══════════════════════════════════════════════════════════════════════════════
class CurveChartWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._curve = {}
        self._anim_progress = 0.0
        self._anim = None
        self.setMinimumHeight(150)
        self.setMaximumHeight(190)

    def set_curve(self, curve: dict):
        self._curve = curve
        self._anim_progress = 0.0
        self._anim = QPropertyAnimation(self, b"animProgress")
        self._anim.setDuration(600)
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)
        self._anim.valueChanged.connect(self.update)
        self._anim.start()

    def get_animProgress(self):
        return self._anim_progress

    def set_animProgress(self, v):
        self._anim_progress = v
        self.update()

    animProgress = property(get_animProgress, set_animProgress)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        if not self._curve:
            painter.setPen(QColor(Colors.TEXT_MUTED))
            painter.setFont(QFont("Segoe UI", 10))
            painter.drawText(self.rect(), Qt.AlignCenter, "Build a deck to see the mana curve")
            return

        max_cmc = max(self._curve.keys(), default=7)
        max_count = max(self._curve.values(), default=1)
        if max_count == 0:
            return

        w = self.width()
        h = self.height()
        n_bars = max_cmc + 1
        gap = 6
        total_gap = gap * (n_bars - 1)
        bar_w = max(14, min(42, (w - 40 - total_gap) // n_bars))
        x_start = (w - (bar_w * n_bars + total_gap)) // 2
        y_bottom = h - 26

        for cmc in range(n_bars):
            count = self._curve.get(cmc, 0)
            full_h = int((count / max_count) * (y_bottom - 24)) if max_count else 0
            bar_h = int(full_h * self._anim_progress)
            x = x_start + cmc * (bar_w + gap)
            y = y_bottom - bar_h

            # Gradient bar
            if cmc <= 2:
                c1, c2 = QColor("#34d399"), QColor("#059669")
            elif cmc <= 4:
                c1, c2 = QColor("#e8b830"), QColor("#b89020")
            elif cmc <= 6:
                c1, c2 = QColor("#f87171"), QColor("#dc2626")
            else:
                c1, c2 = QColor("#a855f7"), QColor("#7c3aed")

            if bar_h > 0:
                grad = QLinearGradient(x, y, x, y_bottom)
                grad.setColorAt(0, c1)
                grad.setColorAt(1, c2)
                painter.setBrush(QBrush(grad))
                painter.setPen(QPen(c2.darker(120), 1))
                painter.drawRoundedRect(x, y, bar_w, bar_h, 4, 4)
                # Count atop bar
                painter.setPen(QColor(Colors.TEXT))
                painter.setFont(QFont("Segoe UI", 9, QFont.Bold))
                painter.drawText(x, y - 14, bar_w, 14, Qt.AlignCenter, str(count))

            # CMC label
            painter.setPen(QColor(Colors.TEXT_DIM) if count == 0 else QColor(Colors.TEXT))
            painter.setFont(QFont("Segoe UI", 9))
            painter.drawText(x, y_bottom + 4, bar_w, 18, Qt.AlignCenter, str(cmc))

        painter.end()


# ═══════════════════════════════════════════════════════════════════════════════
# Colour-pie chart widget
# ═══════════════════════════════════════════════════════════════════════════════
class ColorPieWidget(QWidget):
    """Small donut chart showing colour distribution."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self._counts = {}
        self.setMinimumSize(100, 100)
        self.setMaximumSize(160, 160)

    def set_counts(self, counts: dict):
        self._counts = counts
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        if not self._counts or sum(self._counts.values()) == 0:
            painter.setPen(QColor(Colors.TEXT_MUTED))
            painter.setFont(QFont("Segoe UI", 9))
            painter.drawText(self.rect(), Qt.AlignCenter, "No color data")
            return

        total = sum(self._counts.values())
        w = self.width()
        h = self.height()
        side = min(w, h) - 16
        x = (w - side) // 2
        y = (h - side) // 2
        rect = QRect(x, y, side, side)

        start_angle = 90 * 16  # start from top
        order = ["W", "U", "B", "R", "G"]
        for color in order:
            count = self._counts.get(color, 0)
            if count <= 0:
                continue
            span = int(360 * 16 * count / total)
            mc = Colors.MANA.get(color, {})
            painter.setBrush(QBrush(QColor(mc.get("bg", "#888"))))
            painter.setPen(QPen(QColor(Colors.BG), 2))
            painter.drawPie(rect, start_angle, span)
            start_angle += span

        # centre hole for donut look
        painter.setBrush(QBrush(QColor(Colors.BG)))
        painter.drawEllipse(rect.center(), side // 5, side // 5)
        painter.end()


# ═══════════════════════════════════════════════════════════════════════════════
# Summary Card
# ═══════════════════════════════════════════════════════════════════════════════
class SummaryCard(QFrame):
    def __init__(self, label: str, value: str, color: str = Colors.ACCENT, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"""
            QFrame {{
                background: {Colors.SURFACE};
                border: 1px solid {Colors.BORDER};
                border-radius: 10px;
            }}
        """)
        self._color = color
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(2)
        layout.setAlignment(Qt.AlignCenter)

        self.val_label = QLabel(value)
        self.val_label.setStyleSheet(f"color: {color}; font-size: 22px; font-weight: 700; border: none;")
        self.val_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.val_label)

        self.lbl = QLabel(label)
        self.lbl.setStyleSheet(f"color: {Colors.TEXT_DIM}; font-size: 10px; border: none;")
        self.lbl.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.lbl)

    def set_value(self, value: str, color: str | None = None):
        c = color or self._color
        self.val_label.setText(str(value))
        self.val_label.setStyleSheet(f"color: {c}; font-size: 22px; font-weight: 700; border: none;")


# ═══════════════════════════════════════════════════════════════════════════════
# Toast notification queue
# ═══════════════════════════════════════════════════════════════════════════════
class Toast(QFrame):
    def __init__(self, message: str, color: str = Colors.SUCCESS, duration_ms: int = 3500, parent=None):
        super().__init__(parent)
        self.setObjectName("toast")
        self.setStyleSheet(f"""
            #toast {{
                background: {Colors.SURFACE_ALT};
                border: 1px solid {color};
                border-radius: 10px;
            }}
        """)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        icon_lbl = QLabel("●")
        icon_lbl.setStyleSheet(f"color: {color}; font-size: 14px; border: none;")
        layout.addWidget(icon_lbl)
        msg_lbl = QLabel(message)
        msg_lbl.setStyleSheet(f"color: {Colors.TEXT}; font-size: 13px; border: none;")
        layout.addWidget(msg_lbl)

        self._timer = QTimer.singleShot(duration_ms, self._fade_out)

    def _fade_out(self):
        self.deleteLater()


# ═══════════════════════════════════════════════════════════════════════════════
# Deck History entry
# ═══════════════════════════════════════════════════════════════════════════════
@dataclass
class DeckHistoryEntry:
    name: str
    archetype: str
    colors: str
    score: int
    timestamp: str
    deck: list = field(default_factory=list)
    lands: list = field(default_factory=list)
    deck_qty: dict = field(default_factory=dict)
    land_qty: dict = field(default_factory=dict)
    analysis: dict = field(default_factory=dict)


# ═══════════════════════════════════════════════════════════════════════════════
# Glassmorphism Panel
# ═══════════════════════════════════════════════════════════════════════════════
def make_panel(title: str, subtitle: str = "") -> QFrame:
    frame = QFrame()
    frame.setObjectName("glassPanel")
    frame.setStyleSheet(f"""
        #glassPanel {{
            background: {Colors.CARD};
            border: 1px solid {Colors.CARD_BORDER};
            border-radius: 12px;
        }}
    """)
    v = QVBoxLayout(frame)
    v.setContentsMargins(16, 12, 16, 14)
    v.setSpacing(6)

    head = QLabel(title)
    head.setStyleSheet(f"color: {Colors.ACCENT}; font-weight: 700; font-size: 13px; border: none;")
    v.addWidget(head)

    if subtitle:
        sub = QLabel(subtitle)
        sub.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: 11px; border: none; margin-bottom: 2px;")
        v.addWidget(sub)

    return frame


# ═══════════════════════════════════════════════════════════════════════════════
# Main Window
# ═══════════════════════════════════════════════════════════════════════════════
class MainWindow(QMainWindow):
    MAX_HISTORY = 15

    def __init__(self):
        super().__init__()
        self.setWindowTitle("GloomLake — MTG Deck Scaffold Generator")
        self.resize(1400, 920)
        self.setMinimumSize(1024, 680)

        self._workers: list = []
        self._deck_history: list[DeckHistoryEntry] = []
        self._qb_result: dict | None = None
        self._settings = QSettings("GloomLake", "DeckScaffold")

        self._setup_shortcuts()
        self._build_ui()
        self._apply_palette()
        self._restore_settings()

    # ── Keyboard shortcuts ───────────────────────────────────────────────────
    def _setup_shortcuts(self):
        # Ctrl+N: new deck (clear)
        QAction("New Deck", self, shortcut=QKeySequence("Ctrl+N"),
                triggered=lambda: self._on_new_deck()).setShortcutContext(Qt.WindowShortcut)
        # Ctrl+B: quick build
        QAction("Build", self, shortcut=QKeySequence("Ctrl+B"),
                triggered=lambda: self._on_quick_build()).setShortcutContext(Qt.WindowShortcut)
        # Ctrl+E: export
        QAction("Export", self, shortcut=QKeySequence("Ctrl+E"),
                triggered=lambda: self._on_export_decklist()).setShortcutContext(Qt.WindowShortcut)
        # Ctrl+Q: quit
        QAction("Quit", self, shortcut=QKeySequence("Ctrl+Q"),
                triggered=lambda: self.close()).setShortcutContext(Qt.WindowShortcut)
        # F5: refresh/rebuild
        QAction("Refresh", self, shortcut=QKeySequence("F5"),
                triggered=lambda: self._on_quick_build()).setShortcutContext(Qt.WindowShortcut)
        # F11: fullscreen
        QAction("Fullscreen", self, shortcut=QKeySequence("F11"),
                triggered=lambda: self._toggle_fullscreen()).setShortcutContext(Qt.WindowShortcut)
        # Ctrl+Shift+H: show history
        QAction("History", self, shortcut=QKeySequence("Ctrl+Shift+H"),
                triggered=lambda: self._show_history_dialog()).setShortcutContext(Qt.WindowShortcut)

    def _toggle_fullscreen(self):
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()

    # ── UI Construction ──────────────────────────────────────────────────────
    def _build_ui(self):
        central = QWidget(self)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Header ──────────────────────────────────────────────────────────
        root.addWidget(self._build_header())

        # ── Tab widget ──────────────────────────────────────────────────────
        self.tabs = QTabWidget()
        self.tabs.setStyleSheet(f"""
            QTabWidget::pane {{
                border: none;
                background: {Colors.BG};
            }}
            QTabBar::tab {{
                background: {Colors.SURFACE};
                color: {Colors.TEXT_DIM};
                padding: 11px 28px;
                border: 1px solid {Colors.BORDER};
                border-bottom: none;
                border-top-left-radius: 10px;
                border-top-right-radius: 10px;
                margin-right: 3px;
                font-size: 13px;
                font-weight: 600;
            }}
            QTabBar::tab:selected {{
                background: {Colors.CARD};
                color: {Colors.ACCENT};
                border-bottom: 2px solid {Colors.ACCENT};
            }}
            QTabBar::tab:hover:!selected {{
                background: {Colors.SURFACE_ALT};
                color: {Colors.TEXT};
            }}
        """)
        self.tabs.addTab(self._build_scaffold_tab(), "⚒  Scaffold")
        self.tabs.addTab(self._build_quickbuild_tab(), "⚡  Quick Build")
        self.tabs.addTab(self._build_analysis_tab(), "🔍  Deck Analysis")
        self.tabs.addTab(self._build_history_tab(), "📜  History")
        root.addWidget(self.tabs, 1)

        # ── Status bar ──────────────────────────────────────────────────────
        root.addWidget(self._build_status_bar())

        self.setCentralWidget(central)

        # Clock timer
        self._clock_timer = QTimer(self)
        self._clock_timer.timeout.connect(lambda: self.status_time.setText(time.strftime("%H:%M:%S")))
        self._clock_timer.start(1000)

        # Build elapsed timer
        self._build_start_time = 0.0
        self._build_timer = QTimer(self)
        self._build_timer.timeout.connect(self._update_build_elapsed)
        self._build_timer.setInterval(200)

    def _build_header(self) -> QFrame:
        header = QFrame()
        header.setStyleSheet(f"""
            QFrame {{
                background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
                    stop:0 {Colors.BG_OVERLAY}, stop:0.5 {Colors.CARD}, stop:1 {Colors.BG_OVERLAY});
                border-bottom: 1px solid {Colors.BORDER};
            }}
        """)
        header.setFixedHeight(58)
        hl = QHBoxLayout(header)
        hl.setContentsMargins(18, 0, 18, 0)

        # Logo
        title_row = QHBoxLayout()
        title_row.setSpacing(10)
        logo_icon = load_mana_svg_icon("B", 30)
        if logo_icon.isNull():
            logo_icon = load_set_symbol_icon("ZNE", 30)
        if not logo_icon.isNull():
            logo_lbl = QLabel()
            logo_lbl.setPixmap(logo_icon.pixmap(QSize(30, 30)))
            title_row.addWidget(logo_lbl)

        title = QLabel("GloomLake")
        title.setStyleSheet(f"color: {Colors.ACCENT}; font-size: 21px; font-weight: 800; letter-spacing: 1px;")
        title_row.addWidget(title)

        subtitle = QLabel("Deck Scaffold")
        subtitle.setStyleSheet(f"color: {Colors.TEXT_DIM}; font-size: 12px;")
        title_row.addWidget(subtitle)

        hl.addLayout(title_row)
        hl.addStretch(1)

        self.header_stats = QLabel("")
        self.header_stats.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: 11px;")
        hl.addWidget(self.header_stats)
        return header

    def _build_status_bar(self) -> QFrame:
        status = QFrame()
        status.setStyleSheet(f"""
            QFrame {{
                background: {Colors.BG_OVERLAY};
                border-top: 1px solid {Colors.BORDER};
            }}
        """)
        status.setFixedHeight(34)
        sl = QHBoxLayout(status)
        sl.setContentsMargins(14, 0, 14, 0)

        self.status_label = QLabel("Ready")
        self.status_label.setStyleSheet(f"color: {Colors.TEXT_DIM}; font-size: 11px;")
        sl.addWidget(self.status_label)

        self.status_elapsed = QLabel("")
        self.status_elapsed.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: 11px;")
        sl.addWidget(self.status_elapsed)

        sl.addStretch(1)

        self.status_time = QLabel("")
        self.status_time.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: 11px;")
        sl.addWidget(self.status_time)
        return status

    # ── Scaffold Tab ────────────────────────────────────────────────────────
    def _build_scaffold_tab(self) -> QWidget:
        widget = QWidget()
        widget.setStyleSheet(f"background: {Colors.BG};")
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(14)

        splitter = QSplitter(Qt.Horizontal)

        # Left config
        config_scroll = QScrollArea()
        config_scroll.setWidgetResizable(True)
        config_scroll.setMinimumWidth(420)
        config_scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        config_widget = QWidget()
        cl = QVBoxLayout(config_widget)
        cl.setSpacing(12)
        cl.setContentsMargins(0, 0, 10, 0)

        # Deck name
        nf = make_panel("Deck Name", "Name your deck")
        name_row = QHBoxLayout()
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("e.g. Orzhov Lifegain")
        self.name_edit.setStyleSheet(self._input_style())
        name_row.addWidget(self.name_edit, 1)
        random_name_btn = QPushButton("🎲")
        random_name_btn.setFixedWidth(36)
        random_name_btn.setStyleSheet(self._icon_btn_style())
        random_name_btn.setToolTip("Random name suggestion")
        random_name_btn.clicked.connect(self._on_random_name)
        name_row.addWidget(random_name_btn)
        nf.layout().addLayout(name_row)
        cl.addWidget(nf)

        # Color presets
        cf = make_panel("Color Presets", "Quick-select a guild / shard")
        self.color_preset_combo = QComboBox()
        self.color_preset_combo.addItem("— Custom —")
        for label in COLOR_PRESETS:
            self.color_preset_combo.addItem(f"  {label}")
        self.color_preset_combo.setStyleSheet(self._combo_style())
        self.color_preset_combo.currentTextChanged.connect(self._on_color_preset)
        cf.layout().addWidget(self.color_preset_combo)
        cl.addWidget(cf)

        # Mana colours
        mf = make_panel("Mana Colours", "Select your deck's colours")
        self.guild_label = QLabel("Select colours to detect guild")
        self.guild_label.setStyleSheet(f"color: {Colors.ACCENT_2}; font-style: italic; font-size: 12px; border: none;")
        mf.layout().addWidget(self.guild_label)

        # Guild watermark
        self.guild_watermark = QLabel()
        self.guild_watermark.setAlignment(Qt.AlignCenter)
        self.guild_watermark.setFixedHeight(70)
        self.guild_watermark.setStyleSheet("border: none;")
        mf.layout().addWidget(self.guild_watermark)

        mrow = QHBoxLayout()
        mrow.setSpacing(8)
        self.mana_buttons = {}
        for color in "WUBRG":
            btn = QPushButton()
            btn.setCheckable(True)
            btn.setFixedSize(54, 54)
            btn.setIconSize(QSize(36, 36))
            icon = create_colorized_svg_icon(color, 36)
            btn.setIcon(icon)
            btn.setToolTip(f"{Colors.MANA[color]['name']} ({color})")
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: {Colors.MANA[color]['dim']};
                    border: 2px solid {Colors.MANA[color]['bg']};
                    border-radius: 27px;
                }}
                QPushButton:hover {{
                    background: {Colors.MANA[color]['bg']};
                    border: 2px solid {Colors.ACCENT};
                }}
                QPushButton:checked {{
                    background: {Colors.MANA[color]['bg']};
                    border: 3px solid {Colors.ACCENT};
                }}
            """)
            btn.clicked.connect(lambda checked, c=color: self._on_mana_toggled(c))
            self.mana_buttons[color] = btn
            mrow.addWidget(btn)
        mrow.addStretch(1)
        mf.layout().addLayout(mrow)
        cl.addWidget(mf)

        # Archetypes
        af = make_panel("Archetypes", "Choose one or more archetypes")
        self.archetype_checks = {}
        for group_name, archetypes in ARCHETYPE_GROUPS.items():
            gl = QLabel(f"▸ {group_name}")
            gl.setStyleSheet(f"color: {Colors.TEXT}; font-size: 12px; font-weight: 600; margin-top: 6px; border: none;")
            af.layout().addWidget(gl)
            row = QGridLayout()
            row.setSpacing(4)
            col = 0
            for arch_key, arch_desc in archetypes.items():
                label = arch_key.replace("_", " ").title()
                if arch_key == "opp_mill":
                    label = "Opp Mill"
                elif arch_key == "self_mill":
                    label = "Self Mill"
                cb = QCheckBox(label)
                cb.setToolTip(arch_desc)
                cb.setStyleSheet(self._checkbox_style())
                self.archetype_checks[arch_key] = cb
                row.addWidget(cb, 0, col)
                col += 1
                if col >= 3:
                    col = 0
            af.layout().addLayout(row)
        cl.addWidget(af)

        # Tribe
        tf = make_panel("Tribe (optional)", "Focus on a creature type")
        self.tribe_edit = QLineEdit()
        self.tribe_edit.setPlaceholderText("e.g. Angel, Warrior, Zombie")
        self.tribe_edit.setStyleSheet(self._input_style())
        tf.layout().addWidget(self.tribe_edit)
        self.wildcard_cb = QCheckBox("Wildcard mode")
        self.wildcard_cb.setStyleSheet(self._checkbox_style())
        tf.layout().addWidget(self.wildcard_cb)
        cl.addWidget(tf)

        # Tags
        tagf = make_panel("Extra Tags", "Additional themes to include")
        self.tag_checks = {}
        for cat_name, tags in TAG_OPTIONS.items():
            tagf.layout().addWidget(QLabel(f"▸ {cat_name}"))
            row = QHBoxLayout()
            for tag in tags:
                cb = QCheckBox(tag)
                cb.setStyleSheet(self._checkbox_style())
                self.tag_checks[tag] = cb
                row.addWidget(cb)
            row.addStretch(1)
            tagf.layout().addLayout(row)
        cl.addWidget(tagf)

        # Focus cards
        ff = make_panel("Focus Cards (optional)", "Cards you want included")
        self.focus_edit = QLineEdit()
        self.focus_edit.setPlaceholderText("Card names, comma-separated")
        self.focus_edit.setStyleSheet(self._input_style())
        ff.layout().addWidget(self.focus_edit)
        cl.addWidget(ff)

        # Options
        of = make_panel("Options")
        opt_row = QHBoxLayout()
        self.skip_queries_cb = QCheckBox("Skip queries (offline mode)")
        self.skip_queries_cb.setStyleSheet(self._checkbox_style())
        opt_row.addWidget(self.skip_queries_cb)
        opt_row.addStretch(1)
        of.layout().addLayout(opt_row)
        cl.addWidget(of)

        # Generate btn
        self.generate_btn = QPushButton("⚒  Generate Scaffold")
        self.generate_btn.setStyleSheet(self._primary_btn_style())
        self.generate_btn.setCursor(QCursor(Qt.PointingHandCursor))
        self.generate_btn.clicked.connect(self._on_scaffold_generate)
        cl.addWidget(self.generate_btn)
        cl.addStretch(1)

        config_scroll.setWidget(config_widget)
        splitter.addWidget(config_scroll)

        # Right output
        out_widget = QWidget()
        out_widget.setStyleSheet(f"background: {Colors.BG};")
        ol = QVBoxLayout(out_widget)
        ol.setContentsMargins(10, 0, 0, 0)
        ol.setSpacing(8)

        out_header = QHBoxLayout()
        out_header.addWidget(QLabel("Output Log"))
        out_header.addStretch(1)

        copy_btn = QPushButton("📋 Copy")
        copy_btn.setStyleSheet(self._mini_btn_style())
        copy_btn.clicked.connect(self._on_copy_log)
        out_header.addWidget(copy_btn)

        clear_btn = QPushButton("Clear")
        clear_btn.setStyleSheet(self._mini_btn_style())
        clear_btn.clicked.connect(lambda: self.scaffold_log.clear())
        out_header.addWidget(clear_btn)
        ol.addLayout(out_header)

        self.scaffold_log = QPlainTextEdit()
        self.scaffold_log.setReadOnly(True)
        self.scaffold_log.setStyleSheet(self._log_style())
        ol.addWidget(self.scaffold_log, 1)

        splitter.addWidget(out_widget)
        splitter.setSizes([440, 900])
        layout.addWidget(splitter)
        return widget

    # ── Quick Build Tab ─────────────────────────────────────────────────────
    def _build_quickbuild_tab(self) -> QWidget:
        widget = QWidget()
        widget.setStyleSheet(f"background: {Colors.BG};")
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(14)

        splitter = QSplitter(Qt.Horizontal)

        # Left panel
        left_scroll = QScrollArea()
        left_scroll.setWidgetResizable(True)
        left_scroll.setMinimumWidth(400)
        left_scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setSpacing(12)
        ll.setContentsMargins(0, 0, 10, 0)

        # Colors
        cf = make_panel("Colours", "Pick your mana colours")
        self.qb_guild_watermark = QLabel()
        self.qb_guild_watermark.setAlignment(Qt.AlignCenter)
        self.qb_guild_watermark.setFixedHeight(70)
        self.qb_guild_watermark.setStyleSheet("border: none;")
        cf.layout().addWidget(self.qb_guild_watermark)

        color_row = QHBoxLayout()
        color_row.setSpacing(8)
        self.qb_mana_buttons = {}
        for color in "WUBRG":
            btn = QPushButton()
            btn.setCheckable(True)
            btn.setFixedSize(54, 54)
            btn.setIconSize(QSize(36, 36))
            btn.setIcon(create_colorized_svg_icon(color, 36))
            btn.setToolTip(f"{Colors.MANA[color]['name']} ({color})")
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: {Colors.MANA[color]['dim']};
                    border: 2px solid {Colors.MANA[color]['bg']};
                    border-radius: 27px;
                }}
                QPushButton:hover {{
                    background: {Colors.MANA[color]['bg']};
                    border: 2px solid {Colors.ACCENT};
                }}
                QPushButton:checked {{
                    background: {Colors.MANA[color]['bg']};
                    border: 3px solid {Colors.ACCENT};
                }}
            """)
            btn.clicked.connect(lambda checked, c=color: self._update_guild_display(
                "".join(k for k in "WUBRG" if self.qb_mana_buttons.get(k) and self.qb_mana_buttons[k].isChecked()),
                self.qb_guild_label, self.qb_guild_watermark))
            self.qb_mana_buttons[color] = btn
            color_row.addWidget(btn)
        color_row.addStretch(1)
        cf.layout().addLayout(color_row)

        self.qb_guild_label = QLabel("Select colours")
        self.qb_guild_label.setStyleSheet(f"color: {Colors.ACCENT_2}; font-style: italic; font-size: 12px; border: none;")
        cf.layout().addWidget(self.qb_guild_label)
        ll.addWidget(cf)

        # Archetype + Format
        af = make_panel("Archetype & Format", "Choose your strategy and format")
        form_row = QHBoxLayout()
        form_row.addWidget(QLabel("Archetype:"))
        self.qb_archetype_combo = QComboBox()
        self.qb_archetype_combo.addItems(["Aggro", "Midrange", "Control", "Combo", "Tempo", "Ramp"])
        self.qb_archetype_combo.setStyleSheet(self._combo_style())
        form_row.addWidget(self.qb_archetype_combo, 1)

        form_row.addWidget(QLabel("Format:"))
        self.qb_format_combo = QComboBox()
        self.qb_format_combo.addItems(FORMATS)
        self.qb_format_combo.setCurrentText("Standard")
        self.qb_format_combo.setStyleSheet(self._combo_style())
        form_row.addWidget(self.qb_format_combo, 1)
        af.layout().addLayout(form_row)
        ll.addWidget(af)

        # Build button
        build_row = QHBoxLayout()
        self.qb_build_btn = QPushButton("⚡  Build Deck")
        self.qb_build_btn.setStyleSheet(self._primary_btn_style())
        self.qb_build_btn.setCursor(QCursor(Qt.PointingHandCursor))
        self.qb_build_btn.clicked.connect(self._on_quick_build)
        build_row.addWidget(self.qb_build_btn, 1)

        self.qb_validate_btn = QPushButton("✅ Validate")
        self.qb_validate_btn.setStyleSheet(self._secondary_btn_style())
        self.qb_validate_btn.setCursor(QCursor(Qt.PointingHandCursor))
        self.qb_validate_btn.clicked.connect(self._on_validate_deck)
        self.qb_validate_btn.setVisible(False)
        build_row.addWidget(self.qb_validate_btn)
        ll.addLayout(build_row)

        # Progress
        self.qb_progress = QProgressBar()
        self.qb_progress.setVisible(False)
        self.qb_progress.setStyleSheet(f"""
            QProgressBar {{
                background: {Colors.SURFACE};
                border: 1px solid {Colors.BORDER};
                border-radius: 8px;
                text-align: center;
                color: {Colors.TEXT};
                height: 22px;
                font-size: 11px;
            }}
            QProgressBar::chunk {{
                background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
                    stop:0 {Colors.ACCENT}, stop:1 {Colors.ACCENT_2});
                border-radius: 7px;
            }}
        """)
        ll.addWidget(self.qb_progress)

        # Summary cards
        self.summary_row = QHBoxLayout()
        self.summary_row.setSpacing(8)
        self.qb_summary_cards: dict[str, SummaryCard] = {}
        for key, label in [("score", "Score"), ("cards", "Cards"), ("lands", "Lands"),
                           ("creatures", "Creatures"), ("avg_cmc", "Avg CMC")]:
            card = SummaryCard(label, "—")
            self.qb_summary_cards[key] = card
            self.summary_row.addWidget(card)
        ll.addLayout(self.summary_row)

        # Curve chart
        cf2 = make_panel("Mana Curve")
        self.qb_curve = CurveChartWidget()
        cf2.layout().addWidget(self.qb_curve)
        ll.addWidget(cf2)

        # Colour pie
        cpf = make_panel("Colour Distribution")
        self.qb_color_pie = ColorPieWidget()
        cpf.layout().addWidget(self.qb_color_pie, alignment=Qt.AlignCenter)
        ll.addWidget(cpf)

        # Tribes & Keywords
        mk = make_panel("Top Tribes & Keywords")
        self.qb_meta_label = QLabel("")
        self.qb_meta_label.setStyleSheet(f"color: {Colors.TEXT}; font-size: 12px; border: none;")
        self.qb_meta_label.setWordWrap(True)
        mk.layout().addWidget(self.qb_meta_label)
        ll.addWidget(mk)

        # Export + Copy
        export_row = QHBoxLayout()
        self.qb_export_btn = QPushButton("💾  Export Decklist")
        self.qb_export_btn.setVisible(False)
        self.qb_export_btn.setStyleSheet(self._secondary_btn_style())
        self.qb_export_btn.setCursor(QCursor(Qt.PointingHandCursor))
        self.qb_export_btn.clicked.connect(self._on_export_decklist)
        export_row.addWidget(self.qb_export_btn)

        self.qb_copy_btn = QPushButton("📋 Copy to Clipboard")
        self.qb_copy_btn.setVisible(False)
        self.qb_copy_btn.setStyleSheet(self._secondary_btn_style())
        self.qb_copy_btn.setCursor(QCursor(Qt.PointingHandCursor))
        self.qb_copy_btn.clicked.connect(self._on_copy_decklist)
        export_row.addWidget(self.qb_copy_btn)
        ll.addLayout(export_row)

        ll.addStretch(1)
        left_scroll.setWidget(left)
        splitter.addWidget(left_scroll)

        # Right: Deck tables
        right = QWidget()
        right.setStyleSheet(f"background: {Colors.BG};")
        rl = QVBoxLayout(right)
        rl.setContentsMargins(10, 0, 0, 0)
        rl.setSpacing(10)

        # Search bar
        search_row = QHBoxLayout()
        self.qb_search_edit = QLineEdit()
        self.qb_search_edit.setPlaceholderText("🔍  Filter cards (name, type, CMC)...")
        self.qb_search_edit.setStyleSheet(self._input_style())
        self.qb_search_edit.textChanged.connect(self._on_filter_deck_table)
        search_row.addWidget(self.qb_search_edit, 1)

        self.qb_search_label = QLabel("")
        self.qb_search_label.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: 11px;")
        search_row.addWidget(self.qb_search_label)
        rl.addLayout(search_row)

        # Deck table
        deck_header = QHBoxLayout()
        deck_header.addWidget(QLabel("Deck List"))
        self.deck_count_label = QLabel("")
        self.deck_count_label.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: 11px;")
        deck_header.addWidget(self.deck_count_label)
        rl.addLayout(deck_header)

        self.qb_deck_table = QTableWidget()
        self.qb_deck_table.setColumnCount(6)
        self.qb_deck_table.setHorizontalHeaderLabels(["", "Qty", "Card Name", "CMC", "Type", "Rarity"])
        self.qb_deck_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.qb_deck_table.setColumnWidth(0, 14)
        self.qb_deck_table.setColumnWidth(1, 42)
        self.qb_deck_table.setColumnWidth(3, 42)
        self.qb_deck_table.setColumnWidth(5, 60)
        self.qb_deck_table.setStyleSheet(self._table_style())
        self.qb_deck_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.qb_deck_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.qb_deck_table.setAlternatingRowColors(True)
        self.qb_deck_table.verticalHeader().setVisible(False)
        self.qb_deck_table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.qb_deck_table.customContextMenuRequested.connect(self._on_deck_table_context_menu)
        # Click header to sort
        self.qb_deck_table.horizontalHeader().sectionClicked.connect(
            lambda col: self._sort_deck_table(col)
        )
        rl.addWidget(self.qb_deck_table, 3)

        # Lands table
        land_header = QHBoxLayout()
        land_header.addWidget(QLabel("Lands"))
        self.land_count_label = QLabel("")
        self.land_count_label.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: 11px;")
        land_header.addWidget(self.land_count_label)
        rl.addLayout(land_header)

        self.qb_land_table = QTableWidget()
        self.qb_land_table.setColumnCount(5)
        self.qb_land_table.setHorizontalHeaderLabels(["", "Qty", "Card Name", "Colours", "Type"])
        self.qb_land_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.qb_land_table.setColumnWidth(0, 14)
        self.qb_land_table.setColumnWidth(1, 42)
        self.qb_land_table.setStyleSheet(self._table_style())
        self.qb_land_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.qb_land_table.setAlternatingRowColors(True)
        self.qb_land_table.verticalHeader().setVisible(False)
        rl.addWidget(self.qb_land_table, 1)

        splitter.addWidget(right)
        splitter.setSizes([400, 940])
        layout.addWidget(splitter)
        return widget

    # ── Deck Analysis Tab ───────────────────────────────────────────────────
    def _build_analysis_tab(self) -> QWidget:
        widget = QWidget()
        widget.setStyleSheet(f"background: {Colors.BG};")
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        load_row = QHBoxLayout()
        load_row.setSpacing(8)
        self.analysis_path_edit = QLineEdit()
        self.analysis_path_edit.setPlaceholderText("Select a .txt decklist file to analyze...")
        self.analysis_path_edit.setStyleSheet(self._input_style())
        load_row.addWidget(self.analysis_path_edit, 1)

        browse_btn = QPushButton("Browse...")
        browse_btn.setStyleSheet(self._secondary_btn_style())
        browse_btn.setCursor(QCursor(Qt.PointingHandCursor))
        browse_btn.clicked.connect(self._on_browse_decklist)
        load_row.addWidget(browse_btn)

        analyze_btn = QPushButton("🔍  Analyze")
        analyze_btn.setStyleSheet(self._primary_btn_style())
        analyze_btn.setCursor(QCursor(Qt.PointingHandCursor))
        analyze_btn.clicked.connect(self._on_analyze_deck)
        load_row.addWidget(analyze_btn)
        layout.addLayout(load_row)

        self.analysis_results = QPlainTextEdit()
        self.analysis_results.setReadOnly(True)
        self.analysis_results.setStyleSheet(self._log_style())
        layout.addWidget(self.analysis_results, 1)
        return widget

    # ── History Tab ─────────────────────────────────────────────────────────
    def _build_history_tab(self) -> QWidget:
        widget = QWidget()
        widget.setStyleSheet(f"background: {Colors.BG};")
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        header_row = QHBoxLayout()
        header_row.addWidget(QLabel("📜  Deck History"))
        header_row.addStretch(1)
        clear_hist_btn = QPushButton("Clear History")
        clear_hist_btn.setStyleSheet(self._mini_btn_style())
        clear_hist_btn.clicked.connect(self._on_clear_history)
        header_row.addWidget(clear_hist_btn)
        layout.addLayout(header_row)

        self.history_table = QTableWidget()
        self.history_table.setColumnCount(5)
        self.history_table.setHorizontalHeaderLabels(["Name", "Archetype", "Colours", "Score", "Time"])
        self.history_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.history_table.setColumnWidth(1, 100)
        self.history_table.setColumnWidth(2, 80)
        self.history_table.setColumnWidth(3, 60)
        self.history_table.setColumnWidth(4, 100)
        self.history_table.setStyleSheet(self._table_style())
        self.history_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.history_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.history_table.verticalHeader().setVisible(False)
        self.history_table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.history_table.customContextMenuRequested.connect(self._on_history_context_menu)
        self.history_table.doubleClicked.connect(self._on_history_double_click)
        layout.addWidget(self.history_table, 1)
        return widget

    # ── Style helpers ───────────────────────────────────────────────────────
    def _input_style(self) -> str:
        return f"""
            QLineEdit {{
                background: {Colors.SURFACE};
                color: {Colors.TEXT};
                border: 1px solid {Colors.BORDER};
                padding: 9px 12px;
                border-radius: 8px;
                font-size: 13px;
            }}
            QLineEdit:focus {{
                border: 1px solid {Colors.ACCENT};
            }}
            QLineEdit::placeholder {{
                color: {Colors.TEXT_MUTED};
            }}
        """

    def _checkbox_style(self) -> str:
        return f"""
            QCheckBox {{
                color: {Colors.TEXT};
                font-size: 12px;
                spacing: 8px;
            }}
            QCheckBox::indicator {{
                width: 16px;
                height: 16px;
                border-radius: 4px;
                border: 1px solid {Colors.BORDER};
                background: {Colors.SURFACE};
            }}
            QCheckBox::indicator:checked {{
                background: {Colors.ACCENT};
                border: 1px solid {Colors.ACCENT};
            }}
        """

    def _combo_style(self) -> str:
        return f"""
            QComboBox {{
                background: {Colors.SURFACE};
                color: {Colors.TEXT};
                border: 1px solid {Colors.BORDER};
                padding: 9px 12px;
                border-radius: 8px;
                font-size: 13px;
            }}
            QComboBox:hover {{ border: 1px solid {Colors.ACCENT}; }}
            QComboBox::drop-down {{ border: none; width: 30px; }}
            QComboBox QAbstractItemView {{
                background: {Colors.SURFACE};
                color: {Colors.TEXT};
                border: 1px solid {Colors.BORDER};
                selection-background-color: {Colors.SURFACE_ALT};
            }}
        """

    def _primary_btn_style(self) -> str:
        return f"""
            QPushButton {{
                background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
                    stop:0 {Colors.ACCENT}, stop:1 #c89828);
                color: #000;
                font-weight: 700;
                font-size: 14px;
                padding: 12px 22px;
                border-radius: 10px;
                border: none;
            }}
            QPushButton:hover {{
                background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
                    stop:0 {Colors.ACCENT_HOVER}, stop:1 #d8a830);
            }}
            QPushButton:pressed {{
                background: #b08820;
            }}
            QPushButton:disabled {{
                background: {Colors.SURFACE};
                color: {Colors.TEXT_MUTED};
            }}
        """

    def _secondary_btn_style(self) -> str:
        return f"""
            QPushButton {{
                background: {Colors.SURFACE};
                color: {Colors.ACCENT};
                border: 1px solid {Colors.ACCENT};
                padding: 9px 18px;
                border-radius: 8px;
                font-size: 13px;
                font-weight: 600;
            }}
            QPushButton:hover {{
                background: {Colors.ACCENT_DIM};
            }}
        """

    def _mini_btn_style(self) -> str:
        return f"""
            QPushButton {{
                background: transparent;
                color: {Colors.TEXT_MUTED};
                border: 1px solid {Colors.BORDER};
                padding: 5px 14px;
                border-radius: 6px;
                font-size: 11px;
            }}
            QPushButton:hover {{
                color: {Colors.TEXT};
            }}
        """

    def _icon_btn_style(self) -> str:
        return f"""
            QPushButton {{
                background: {Colors.SURFACE};
                color: {Colors.TEXT};
                border: 1px solid {Colors.BORDER};
                border-radius: 8px;
                font-size: 16px;
            }}
            QPushButton:hover {{
                background: {Colors.SURFACE_ALT};
            }}
        """

    def _table_style(self) -> str:
        return f"""
            QTableWidget {{
                background: {Colors.SURFACE};
                color: {Colors.TEXT};
                border: 1px solid {Colors.BORDER};
                gridline-color: {Colors.CARD_BORDER};
                border-radius: 10px;
                font-size: 12px;
                selection-background-color: {Colors.SURFACE_ALT};
            }}
            QHeaderView::section {{
                background: {Colors.SURFACE_ALT};
                color: {Colors.ACCENT};
                padding: 7px 10px;
                border: none;
                border-bottom: 1px solid {Colors.BORDER};
                font-weight: 700;
                font-size: 11px;
            }}
            QTableWidget::item {{
                padding: 5px 8px;
                border-bottom: 1px solid {Colors.CARD_BORDER};
            }}
            QTableWidget::item:selected {{
                background: {Colors.SURFACE_ALT};
                color: {Colors.ACCENT};
            }}
        """

    def _log_style(self) -> str:
        return f"""
            QPlainTextEdit {{
                background: {Colors.SURFACE};
                color: {Colors.TEXT};
                border: 1px solid {Colors.BORDER};
                font-family: 'Cascadia Code', 'Consolas', 'JetBrains Mono', monospace;
                font-size: 12px;
                padding: 14px;
                border-radius: 10px;
            }}
        """

    # ── Utility ─────────────────────────────────────────────────────────────
    def _log(self, widget, msg):
        widget.appendPlainText(msg)
        bar = widget.verticalScrollBar()
        QTimer.singleShot(10, lambda: bar.setValue(bar.maximum()))

    def _set_status(self, msg: str):
        self.status_label.setText(msg)

    def _show_toast(self, msg: str, color: str = Colors.SUCCESS):
        toast = Toast(msg, color, parent=self)
        toast.move(self.width() - toast.sizeHint().width() - 30, 65)
        toast.show()

    def _update_build_elapsed(self):
        if self._build_start_time:
            elapsed = time.time() - self._build_start_time
            self.status_elapsed.setText(f"[{elapsed:.1f}s]")

    # ── Settings ────────────────────────────────────────────────────────────
    def _restore_settings(self):
        # Restore window geometry
        geo = self._settings.value("windowGeometry")
        if geo:
            self.restoreGeometry(geo)
        # Restore last format
        fmt = self._settings.value("lastFormat", "Standard")
        if hasattr(self, 'qb_format_combo'):
            idx = self.qb_format_combo.findText(fmt)
            if idx >= 0:
                self.qb_format_combo.setCurrentIndex(idx)

    def _save_settings(self):
        self._settings.setValue("windowGeometry", self.saveGeometry())
        if hasattr(self, 'qb_format_combo'):
            self._settings.setValue("lastFormat", self.qb_format_combo.currentText())

    def closeEvent(self, event):
        self._save_settings()
        event.accept()

    # ── Scaffold slots ──────────────────────────────────────────────────────
    def _on_color_preset(self, text: str):
        if text.startswith("—"):
            return
        # Extract colors from end: "WU — Azorius" → "WU"
        parts = text.split("—")
        if len(parts) >= 2:
            colors = parts[-1].strip()
        else:
            return
        # Uncheck all
        for c, btn in self.mana_buttons.items():
            btn.setChecked(c in colors)
        self._update_guild_display("".join(c for c in "WUBRG" if c in colors), self.guild_label, self.guild_watermark)

    def _on_mana_toggled(self, color: str):
        colors = "".join(c for c in "WUBRG" if self.mana_buttons[c].isChecked())
        self._update_guild_display(colors, self.guild_label, self.guild_watermark)

    def _update_guild_display(self, colors: str, label: QLabel, watermark_lbl: QLabel):
        if colors:
            code, name = detect_guild(colors)
            label.setText(f"{code} — {name}" if name else colors)
            # Load watermark
            if name:
                guild_key = name.lower().replace(" ", "_")
                icon = load_guild_watermark_icon(guild_key, 64)
                if not icon.isNull():
                    watermark_lbl.setPixmap(icon.pixmap(QSize(64, 64)))
                else:
                    watermark_lbl.clear()
            else:
                watermark_lbl.clear()
        else:
            label.setText("Select colours to detect guild")
            watermark_lbl.clear()

    def _on_random_name(self):
        suggestions = [
            "Eternal Dominion", "Mana Flare", "Shadowborn Rising",
            "Arcane Ascension", "Dreadmaw Stomp", "Fae Bargain",
            "Goblin Shenanigans", "Knight's Oath", "Leyline Shift",
        ]
        import random
        self.name_edit.setText(random.choice(suggestions))

    def _on_scaffold_generate(self):
        name = self.name_edit.text().strip()
        colors = "".join(c for c in "WUBRG" if self.mana_buttons[c].isChecked())
        archetypes = [k for k, cb in self.archetype_checks.items() if cb.isChecked()]
        if not name:
            self._log(self.scaffold_log, "⚠ ERROR: Deck name required."); return
        if not colors:
            self._log(self.scaffold_log, "⚠ ERROR: At least one colour required."); return
        if not archetypes:
            self._log(self.scaffold_log, "⚠ ERROR: At least one archetype required."); return

        cmd = [
            sys.executable,
            str(SCRIPTS_DIR / "generate_deck_scaffold.py"),
            "--name", name,
            "--colors", colors,
            "--archetype"
        ] + archetypes

        tribe = self.tribe_edit.text().strip()
        if tribe:
            for t in tribe.split(","):
                t = t.strip()
                if t:
                    cmd.extend(["--tribe", t])
        if self.wildcard_cb.isChecked():
            cmd.append("--wildcard")
        tags = [t for t, cb in self.tag_checks.items() if cb.isChecked()]
        if tags:
            cmd.extend(["--extra-tags", ",".join(tags)])
        focus = self.focus_edit.text().strip()
        if focus:
            for c in focus.split(","):
                c = c.strip()
                if c:
                    cmd.extend(["--focus-cards", c])
        if self.skip_queries_cb.isChecked():
            cmd.append("--skip-queries")

        self._log(self.scaffold_log, f"$ {' '.join(cmd)}")
        self._set_status(f"Generating scaffold for {name}...")
        self.generate_btn.setEnabled(False)
        worker = CommandWorker(cmd, label="generate", parent=self)
        worker.finished_with_result.connect(self._on_scaffold_done)
        self._workers.append(worker)
        worker.start()

    def _on_scaffold_done(self, result: RunResult):
        self._log(self.scaffold_log, f"--- Done (exit {result.code}) ---")
        for line in result.output.splitlines():
            if line.strip():
                self._log(self.scaffold_log, line.rstrip())
        self.generate_btn.setEnabled(True)
        self._workers = [w for w in self._workers if w.isRunning()]
        if result.code == 0:
            self._set_status("Scaffold generated successfully")
            self._show_toast("Scaffold generated!", Colors.SUCCESS)
        else:
            self._set_status("Scaffold generation failed")
            self._show_toast("Generation failed", Colors.ERROR)

    def _on_copy_log(self):
        QApplication.clipboard().setText(self.scaffold_log.toPlainText())
        self._show_toast("Output copied to clipboard", Colors.INFO)

    # ── Quick Build slots ───────────────────────────────────────────────────
    def _on_quick_build(self):
        colors = "".join(c for c in "WUBRG" if self.qb_mana_buttons[c].isChecked())
        if not colors:
            self._set_status("Select at least one colour")
            self._show_toast("Select colours first", Colors.WARNING)
            return
        archetype = self.qb_archetype_combo.currentText()
        fmt = self.qb_format_combo.currentText()

        self.qb_build_btn.setEnabled(False)
        self.qb_validate_btn.setVisible(False)
        self.qb_progress.setVisible(True)
        self.qb_progress.setRange(0, 0)
        self.qb_export_btn.setVisible(False)
        self.qb_copy_btn.setVisible(False)

        self._set_status(f"Building {archetype} {colors} deck ({fmt})...")
        self._build_start_time = time.time()
        self._build_timer.start()
        self.status_elapsed.setVisible(True)

        for card in self.qb_summary_cards.values():
            card.set_value("...")

        self._qb_worker = SynergyBuildWorker(colors, archetype, fmt, parent=self)
        self._qb_worker.finished_with_result.connect(self._on_quick_build_done)
        self._qb_worker.error.connect(self._on_quick_build_error)
        self._qb_worker.start()

    def _on_quick_build_done(self, result: dict):
        self.qb_build_btn.setEnabled(True)
        self.qb_progress.setVisible(False)
        self._build_timer.stop()
        self.status_elapsed.setVisible(False)
        self._qb_result = result

        analysis = result.get("analysis", {})
        deck = result.get("deck", [])
        lands = result.get("lands", [])
        curve = result.get("curve", {})
        deck_qty = result.get("deck_qty", {})
        land_qty = result.get("land_qty", {})
        total_cards = sum(deck_qty.values())
        total_lands = sum(land_qty.values())
        total_score = min(10, int(analysis.get("total_synergy", 0) / 100) + 3)

        # Compute avg CMC
        cmcs = [int(float(c.get("cmc", 0) or 0)) * deck_qty.get(c.get("name", ""), 1) for c in deck]
        avg_cmc = sum(cmcs) / max(total_cards, 1)

        # Update summary cards
        score_color = Colors.SUCCESS if total_score >= 7 else Colors.WARNING if total_score >= 5 else Colors.ERROR
        self.qb_summary_cards["score"].set_value(f"{total_score}/10", score_color)
        self.qb_summary_cards["cards"].set_value(str(total_cards))
        self.qb_summary_cards["lands"].set_value(str(total_lands))
        self.qb_summary_cards["creatures"].set_value(str(analysis.get("unique_creatures", 0)))
        self.qb_summary_cards["avg_cmc"].set_value(f"{avg_cmc:.1f}")

        # Curves & pie
        self.qb_curve.set_curve(curve)

        # Color pie from analysis
        color_dist = analysis.get("color_distribution", {})
        self.qb_color_pie.set_counts(color_dist)

        # Tribes & keywords
        tribes = analysis.get("top_tribes", [])[:4]
        keywords = analysis.get("top_keywords", [])[:5]
        meta_parts = []
        if tribes:
            meta_parts.append("<b>Tribes:</b> " + ", ".join(f"{t[0]} ({t[1]})" for t in tribes))
        if keywords:
            meta_parts.append("<b>Keywords:</b> " + ", ".join(f"{k[0]} ({k[1]})" for k in keywords))
        self.qb_meta_label.setText("<br>".join(meta_parts))

        # Fill deck table
        self._populate_deck_table(deck, deck_qty)
        self.deck_count_label.setText(f"{len(deck)} unique / {total_cards} total")

        # Fill lands table
        self._populate_land_table(lands, land_qty)
        self.land_count_label.setText(f"{len(lands)} unique / {total_lands} total")

        self.qb_export_btn.setVisible(True)
        self.qb_copy_btn.setVisible(True)
        self.qb_validate_btn.setVisible(True)

        elapsed = time.time() - self._build_start_time if self._build_start_time else 0
        self._set_status(
            f"Built {result.get('archetype','')} {result.get('colors','')} deck "
            f"({total_cards} cards, {total_lands} lands) in {elapsed:.1f}s"
        )
        self._show_toast(f"Deck built — {total_score}/10 synergy", Colors.SUCCESS)

        # Add to history
        entry = DeckHistoryEntry(
            name=f"{result.get('archetype','')}_{result.get('colors','')}_{int(time.time())}",
            archetype=result.get("archetype", ""),
            colors=result.get("colors", ""),
            score=total_score,
            timestamp=time.strftime("%H:%M:%S"),
            deck=deck,
            lands=lands,
            deck_qty=deck_qty,
            land_qty=land_qty,
            analysis=analysis,
        )
        self._deck_history.insert(0, entry)
        if len(self._deck_history) > self.MAX_HISTORY:
            self._deck_history = self._deck_history[:self.MAX_HISTORY]
        self._refresh_history_table()

        # Invalidate filter
        self._full_deck = deck
        self._full_deck_qty = deck_qty
        self._on_filter_deck_table(self.qb_search_edit.text())

    def _populate_deck_table(self, deck: list, deck_qty: dict):
        self.qb_deck_table.setRowCount(0)
        # Group by CMC
        by_cmc: dict[int, list] = {}
        for card in deck:
            cmc = int(float(card.get("cmc", 0) or 0))
            by_cmc.setdefault(cmc, []).append(card)

        row = 0
        for cmc in sorted(by_cmc):
            for card in sorted(by_cmc[cmc], key=lambda c: c.get("name", "")):
                name = card.get("name", "Unknown")
                qty = deck_qty.get(name, 1)
                type_line = card.get("type_line", "")
                rarity = card.get("rarity", "common")

                self.qb_deck_table.insertRow(row)

                # Type pip
                pip_lbl = QLabel()
                pip_lbl.setPixmap(type_pip_icon(type_line, 10).pixmap(QSize(10, 10)))
                pip_lbl.setAlignment(Qt.AlignCenter)
                self.qb_deck_table.setCellWidget(row, 0, pip_lbl)

                self.qb_deck_table.setItem(row, 1, self._make_item(str(qty)))
                name_item = self._make_item(name)
                name_item.setToolTip(
                    f"{name}\n{type_line}\n"
                    f"{card.get('oracle_text', '')[:120]}"
                )
                self.qb_deck_table.setItem(row, 2, name_item)
                self.qb_deck_table.setItem(row, 3, self._make_item(str(cmc)))
                self.qb_deck_table.setItem(row, 4, self._make_item(type_line[:40]))
                rarity_item = self._make_item(rarity.capitalize())
                rarity_item.setForeground(QColor(Colors.rarity_color(rarity)))
                self.qb_deck_table.setItem(row, 5, rarity_item)

                # Rarity-coloured left border highlight
                color = Colors.rarity_color(rarity)
                for c in range(6):
                    it = self.qb_deck_table.item(row, c)
                    if it:
                        it.setData(Qt.UserRole, color)

                row += 1

    def _populate_land_table(self, lands: list, land_qty: dict):
        self.qb_land_table.setRowCount(0)
        for i, land in enumerate(sorted(lands, key=lambda l: l.get("name", ""))):
            name = land.get("name", "Unknown")
            qty = land_qty.get(name, 1)
            type_line = land.get("type_line", "")

            self.qb_land_table.insertRow(i)

            pip_lbl = QLabel()
            pip_lbl.setPixmap(type_pip_icon(type_line, 10).pixmap(QSize(10, 10)))
            pip_lbl.setAlignment(Qt.AlignCenter)
            self.qb_land_table.setCellWidget(i, 0, pip_lbl)

            self.qb_land_table.setItem(i, 1, self._make_item(str(qty)))
            self.qb_land_table.setItem(i, 2, self._make_item(name))
            self.qb_land_table.setItem(i, 3, self._make_item(land.get("colors", "")))
            self.qb_land_table.setItem(i, 4, self._make_item(type_line[:30]))

    def _make_item(self, text: str) -> QTableWidgetItem:
        item = QTableWidgetItem(text)
        item.setForeground(QColor(Colors.TEXT))
        return item

    # ── Filter & Sort ──────────────────────────────────────────────────────
    def _on_filter_deck_table(self, text: str):
        if not hasattr(self, '_full_deck') or not self._full_deck:
            return
        query = text.strip().lower()
        if not query:
            filtered_deck = self._full_deck
            filtered_qty = self._full_deck_qty
        else:
            filtered_deck = [
                c for c in self._full_deck
                if query in c.get("name", "").lower()
                or query in c.get("type_line", "").lower()
                or query == str(int(float(c.get("cmc", 0) or 0)))
            ]
            filtered_qty = {
                k: v for k, v in self._full_deck_qty.items()
                if query in k.lower()
            }

        self._populate_deck_table(filtered_deck, filtered_qty)
        self.qb_search_label.setText(
            f"{len(filtered_deck)} / {len(self._full_deck)} shown"
            if query else ""
        )

    def _sort_deck_table(self, col: int):
        """Toggle sort ascending/descending on column click."""
        order = getattr(self, '_sort_order', Qt.AscendingOrder)
        self._sort_order = Qt.DescendingOrder if order == Qt.AscendingOrder else Qt.AscendingOrder
        self.qb_deck_table.sortItems(col, self._sort_order)

    # ── Context menu on deck table ──────────────────────────────────────────
    def _on_deck_table_context_menu(self, pos):
        menu = QMenu(self)
        copy_action = menu.addAction("📋 Copy card name")
        copy_action.triggered.connect(lambda: self._copy_selected_card())
        menu.exec(self.qb_deck_table.viewport().mapToGlobal(pos))

    def _copy_selected_card(self):
        row = self.qb_deck_table.currentRow()
        if row >= 0:
            item = self.qb_deck_table.item(row, 2)  # name column
            if item:
                QApplication.clipboard().setText(item.text())
                self._show_toast("Card name copied", Colors.INFO)

    # ── Validate deck ──────────────────────────────────────────────────────
    def _on_validate_deck(self):
        if not self._qb_result:
            return
        deck_qty = self._qb_result.get("deck_qty", {})
        land_qty = self._qb_result.get("land_qty", {})
        total = sum(deck_qty.values()) + sum(land_qty.values())
        issues = []
        if total < 60:
            issues.append(f"⚠ Only {total} cards (need 60+)")
        elif total > 60:
            issues.append(f"ℹ {total} cards (> 60 is okay for casual)")
        # Check 4-of limit
        for name, qty in deck_qty.items():
            if qty > 4:
                issues.append(f"⚠ {qty}x {name} exceeds 4-of limit")
        if not issues:
            QMessageBox.information(self, "Deck Valid", f"✅ {total} cards — deck looks valid!")
        else:
            QMessageBox.warning(self, "Deck Issues", "\n".join(issues))

    # ── Export & Copy ──────────────────────────────────────────────────────
    def _on_export_decklist(self):
        if not self._qb_result:
            return
        result = self._qb_result
        name = f"{result.get('archetype','Deck')}_{result.get('colors','')}_{int(time.time())}"
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Decklist", f"{name}.txt", "Text Files (*.txt);;CSV (*.csv);;Arena Format (*.txt)"
        )
        if not path:
            return
        lines = self._format_decklist(result, Path(path).suffix)
        Path(path).write_text("\n".join(lines), encoding="utf-8")
        self._set_status(f"Decklist exported to {path}")
        self._show_toast("Decklist exported!", Colors.SUCCESS)

    def _on_copy_decklist(self):
        if not self._qb_result:
            return
        lines = self._format_decklist(self._qb_result, ".txt")
        QApplication.clipboard().setText("\n".join(lines))
        self._show_toast("Decklist copied to clipboard!", Colors.INFO)

    def _format_decklist(self, result: dict, fmt: str) -> list:
        deck_qty = result.get("deck_qty", {})
        land_qty = result.get("land_qty", {})
        lines = [
            f"// Deck: {result.get('archetype','')} {result.get('colors','')}",
            f"// Format: {result.get('format','Standard')}",
            f"// Synergy: {result.get('analysis',{}).get('total_synergy',0):.0f}",
            "",
        ]
        # Non-lands
        by_cmc = {}
        for card in result.get("deck", []):
            cmc = int(float(card.get("cmc", 0) or 0))
            by_cmc.setdefault(cmc, []).append(card)

        if fmt == ".csv":
            lines = ["Qty,Name,CMC,Type,Rarity"]
            for cmc in sorted(by_cmc):
                for card in sorted(by_cmc[cmc], key=lambda c: c.get("name", "")):
                    name = card.get("name", "Unknown")
                    qty = deck_qty.get(name, 1)
                    lines.append(
                        f'{qty},"{name}",{cmc},"{card.get("type_line","")}","{card.get("rarity","")}"'
                    )
            for land in result.get("lands", []):
                name = land.get("name", "Unknown")
                qty = land_qty.get(name, 1)
                lines.append(
                    f'{qty},"{name}",0,"{land.get("type_line","")}","Land"'
                )
        else:
            # Arena / text format
            for cmc in sorted(by_cmc):
                for card in sorted(by_cmc[cmc], key=lambda c: c.get("name", "")):
                    name = card.get("name", "Unknown")
                    qty = deck_qty.get(name, 1)
                    lines.append(f"{qty} {name}")
            lines.append("")
            for land in result.get("lands", []):
                name = land.get("name", "Unknown")
                qty = land_qty.get(name, 1)
                lines.append(f"{qty} {name}")

        return lines

    # ── Quick Build error handler ───────────────────────────────────────────
    def _on_quick_build_error(self, error_msg: str):
        self.qb_build_btn.setEnabled(True)
        self.qb_progress.setVisible(False)
        self._build_timer.stop()
        self.status_elapsed.setVisible(False)
        self._set_status("Build failed")
        self._show_toast(f"Error: {error_msg}", Colors.ERROR)
        # Offer retry
        retry = QMessageBox.question(
            self, "Build Failed",
            f"Build error:\n{error_msg}\n\nRetry?",
            QMessageBox.Retry | QMessageBox.Cancel
        )
        if retry == QMessageBox.Retry:
            QTimer.singleShot(300, self._on_quick_build)

    # ── Analysis slots ──────────────────────────────────────────────────────
    def _on_browse_decklist(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Open Decklist", "", "Text Files (*.txt);;All Files (*)"
        )
        if path:
            self.analysis_path_edit.setText(path)

    def _on_analyze_deck(self):
        path = self.analysis_path_edit.text().strip()
        if not path or not Path(path).exists():
            self.analysis_results.setPlainText("⚠ ERROR: Select a valid decklist file.")
            self._show_toast("Select a decklist file", Colors.WARNING)
            return

        self._set_status("Analyzing deck...")
        try:
            lines = Path(path).read_text(encoding="utf-8").splitlines()
            card_names = []
            for line in lines:
                line = line.strip()
                if not line or line.startswith("//"):
                    continue
                m = re.match(r'(\d+)\s+(.+)', line)
                if m:
                    qty, name = int(m.group(1)), m.group(2).strip()
                    card_names.extend([name] * qty)
            if not card_names:
                self.analysis_results.setPlainText("No cards found in decklist.")
                return

            if not DB_PATH.exists():
                self.analysis_results.setPlainText("⚠ Card database not found.")
                return

            conn = sqlite3.connect(str(DB_PATH))
            conn.row_factory = sqlite3.Row
            cards = []
            for name in set(card_names):
                cursor = conn.execute(
                    "SELECT * FROM cards WHERE name = ? LIMIT 1", (name,)
                )
                row = cursor.fetchone()
                if row:
                    cards.append(dict(row))
            conn.close()

            if not cards:
                self.analysis_results.setPlainText("No cards found in database.")
                return

            from greedy_synergy_engine import SynergyEngine
            engine = SynergyEngine(DB_PATH)
            analysis = engine.analyze_deck_synergy(cards)
            engine.close()

            avg_cmc = (
                sum(int(float(c.get("cmc", 0) or 0)) for c in cards) / len(cards)
                if cards else 0
            )

            out = [
                "╔" + "═" * 50 + "╗",
                "║          DECK ANALYSIS REPORT                      ║",
                "╚" + "═" * 50 + "╝",
                "",
                f"  Total cards analyzed:  {len(cards)}",
                f"  Synergy score:         {analysis['total_synergy']:.1f}",
                f"  Creatures: {analysis['unique_creatures']:>3}   |  Spells: {analysis['unique_spells']}",
                f"  Avg CMC:   {avg_cmc:>5.2f}",
                "",
                "  ── Top Tribes ──",
            ]
            for tribe, count in analysis["top_tribes"][:10]:
                bar = "█" * min(count, 25)
                out.append(f"    {tribe:<22} {bar} {count}")

            out.append("")
            out.append("  ── Top Keywords ──")
            for kw, count in analysis["top_keywords"][:10]:
                bar = "█" * min(count, 25)
                out.append(f"    {kw:<22} {bar} {count}")

            self.analysis_results.setPlainText("\n".join(out))
            self._set_status(
                f"Analyzed {len(cards)} cards — synergy: {analysis['total_synergy']:.0f}"
            )
            self._show_toast("Analysis complete!", Colors.SUCCESS)

        except Exception as exc:
            self.analysis_results.setPlainText(f"⚠ ERROR: {exc}")
            self._set_status("Analysis failed")
            self._show_toast("Analysis failed", Colors.ERROR)

    # ── History slots ──────────────────────────────────────────────────────
    def _refresh_history_table(self):
        self.history_table.setRowCount(len(self._deck_history))
        for i, entry in enumerate(self._deck_history):
            self.history_table.setItem(i, 0, self._make_item(entry.name))
            self.history_table.setItem(i, 1, self._make_item(entry.archetype))
            self.history_table.setItem(i, 2, self._make_item(entry.colors))
            score_item = self._make_item(str(entry.score))
            score_color = Colors.SUCCESS if entry.score >= 7 else Colors.WARNING if entry.score >= 5 else Colors.ERROR
            score_item.setForeground(QColor(score_color))
            self.history_table.setItem(i, 3, score_item)
            self.history_table.setItem(i, 4, self._make_item(entry.timestamp))

    def _on_history_context_menu(self, pos):
        menu = QMenu(self)
        load_action = menu.addAction("📂 Load this deck")
        load_action.triggered.connect(self._on_history_load)
        delete_action = menu.addAction("🗑 Remove")
        delete_action.triggered.connect(self._on_history_delete)
        menu.exec(self.history_table.viewport().mapToGlobal(pos))

    def _on_history_load(self):
        row = self.history_table.currentRow()
        if 0 <= row < len(self._deck_history):
            entry = self._deck_history[row]
            self._qb_result = {
                "deck": entry.deck,
                "lands": entry.lands,
                "deck_qty": entry.deck_qty,
                "land_qty": entry.land_qty,
                "analysis": entry.analysis,
                "archetype": entry.archetype,
                "colors": entry.colors,
                "curve": entry.analysis.get("curve", {}),
            }
            self._on_quick_build_done(self._qb_result)
            self.tabs.setCurrentIndex(1)  # switch to Quick Build
            self._show_toast(f"Loaded: {entry.name}", Colors.INFO)

    def _on_history_delete(self):
        row = self.history_table.currentRow()
        if 0 <= row < len(self._deck_history):
            del self._deck_history[row]
            self._refresh_history_table()

    def _on_history_double_click(self, index):
        self._on_history_load()

    def _on_clear_history(self):
        self._deck_history.clear()
        self._refresh_history_table()
        self._show_toast("History cleared", Colors.INFO)

    def _show_history_dialog(self):
        self.tabs.setCurrentIndex(3)  # switch to History tab

    # ── New deck ────────────────────────────────────────────────────────────
    def _on_new_deck(self):
        # Clear scaffold form
        self.name_edit.clear()
        self.tribe_edit.clear()
        self.focus_edit.clear()
        for btn in self.mana_buttons.values():
            btn.setChecked(False)
        for cb in self.archetype_checks.values():
            cb.setChecked(False)
        for cb in self.tag_checks.values():
            cb.setChecked(False)
        self.wildcard_cb.setChecked(False)
        self.skip_queries_cb.setChecked(False)
        self.guild_watermark.clear()
        self.guild_label.setText("Select colours to detect guild")
        self.color_preset_combo.setCurrentIndex(0)
        # Clear QB
        for btn in self.qb_mana_buttons.values():
            btn.setChecked(False)
        self.qb_guild_watermark.clear()
        self.qb_guild_label.setText("Select colours")
        self.qb_deck_table.setRowCount(0)
        self.qb_land_table.setRowCount(0)
        self.qb_meta_label.clear()
        self.qb_export_btn.setVisible(False)
        self.qb_copy_btn.setVisible(False)
        self.qb_validate_btn.setVisible(False)
        self.tabs.setCurrentIndex(0)
        self._set_status("New deck — ready")
        self._show_toast("New deck cleared", Colors.INFO)

    # ── Global palette ──────────────────────────────────────────────────────
    def _apply_palette(self):
        self.setStyleSheet(f"""
            QMainWindow {{ background: {Colors.BG}; }}
            QLabel {{ color: {Colors.TEXT}; }}
            QScrollArea {{ border: none; background: transparent; }}
            QSplitter::handle {{
                background: {Colors.BORDER};
                width: 2px;
            }}
            QToolTip {{
                background: {Colors.SURFACE_ALT};
                color: {Colors.TEXT};
                border: 1px solid {Colors.BORDER};
                padding: 6px 10px;
                border-radius: 6px;
                font-size: 12px;
            }}
        """)


# ═══════════════════════════════════════════════════════════════════════════════
# Entry point
# ═══════════════════════════════════════════════════════════════════════════════
def main():
    app = QApplication.instance() or QApplication(sys.argv)
    app.setFont(QFont("Segoe UI", 10))
    app.setApplicationName("GloomLake")
    app.setOrganizationName("GloomLake")

    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())