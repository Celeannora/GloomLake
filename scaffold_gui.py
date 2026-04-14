#!/usr/bin/env python3
"""
Deck Scaffold Generator — GUI (customtkinter)

Usage:  python scaffold_gui.py
Requires:  pip install customtkinter
"""

import json
import os
import platform
import re
import subprocess
import sys
import threading
import tkinter as tk
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from tkinter import filedialog

try:
    import customtkinter as ctk
except ImportError:
    print("customtkinter is not installed. Run:  pip install customtkinter")
    sys.exit(1)

_scripts_dir = Path(__file__).resolve().parent / "scripts"
sys.path.insert(0, str(_scripts_dir))
from generate_deck_scaffold import (
    ALL_CREATURE_TYPES,
    ARCHETYPE_QUERIES,
    sanitize_folder_name,
)
from mtg_utils import RepoPaths
from auto_build import (
    auto_build_decklist,
    merge_scores_into_candidate_pool,
    normalize_colors,
    sort_and_rewrite_csv,
    COLOR_ORDER,
    MANA_NAMES,
)

# ─────────────────────────────────────────────────────────────────────────────
# Palette
# ─────────────────────────────────────────────────────────────────────────────
APP_TITLE = "MTG Deck Scaffold Generator"
WIN_W, WIN_H = 860, 940

ACCENT       = "#c9a227"
ACCENT_HOVER = "#a8871e"
BG           = "#0c0c0c"
CARD_BG      = "#141414"
CARD_BORDER  = "#1e1e1e"
SURFACE      = "#1a1a1a"
SURFACE_ALT  = "#222222"
BORDER       = "#333333"
TEXT         = "#e8e8e8"
TEXT_DIM     = "#999999"
TEXT_MUTED   = "#666666"
SUCCESS      = "#4ade80"
ERROR        = "#f87171"
WARNING      = "#fb923c"
INFO_BLUE    = "#60a5fa"

MANA_COLORS = {
    "W": {"bg": "#f9f4e0", "fg": "#1a1a1a", "dim": "#48443a", "label": "W"},
    "U": {"bg": "#1177cc", "fg": "#ffffff", "dim": "#1e3550", "label": "U"},
    "B": {"bg": "#5c3d6e", "fg": "#e0d4ee", "dim": "#2a1e32", "label": "B"},
    "R": {"bg": "#d42e2e", "fg": "#ffffff", "dim": "#501f1f", "label": "R"},
    "G": {"bg": "#1f944a", "fg": "#ffffff", "dim": "#1e3828", "label": "G"},
}

# ─────────────────────────────────────────────────────────────────────────────
# Archetype groups with descriptions (tribal removed — now standalone card)
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
        "reanimation": "Put big creatures in graveyard, bring them back cheap",
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
        "landfall": "Trigger abilities when lands enter the battlefield",
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

# ─────────────────────────────────────────────────────────────────────────────
# Tag categories and archetype-to-tag mapping
# ─────────────────────────────────────────────────────────────────────────────
TAG_CATEGORIES: dict[str, dict[str, str]] = {
    "Offensive": {
        "haste":      "Creatures can attack the turn they enter",
        "trample":    "Excess combat damage carries over to the player",
        "pump":       "Spells and abilities that buff creature power/toughness",
        "flying":     "Creatures with flying or that grant flying",
        "deathtouch": "Any damage from this creature is lethal",
        "menace":     "Can only be blocked by two or more creatures",
    },
    "Defensive": {
        "counter":    "Counterspells and ability-counter effects",
        "removal":    "Destroy, exile, or damage-based creature removal",
        "wipe":       "Board wipes that clear multiple permanents at once",
        "bounce":     "Return permanents to hand (tempo plays)",
        "protection": "Hexproof, indestructible, ward, and shields",
        "flash":      "Cards with flash or that grant flash",
    },
    "Utility": {
        "draw":       "Card draw and card selection (scry, surveil)",
        "ramp":       "Mana acceleration — extra lands or mana rocks",
        "tutor":      "Search your library for a specific card",
        "mill":       "Put cards from a library into the graveyard",
        "etb":        "Enter-the-battlefield triggered abilities",
        "lifegain":   "Gain life triggers and life-total payoffs",
    },
}

ALL_TAGS = [tag for tags in TAG_CATEGORIES.values() for tag in tags]
TAG_DESCRIPTIONS: dict[str, str] = {
    tag: desc for cat in TAG_CATEGORIES.values() for tag, desc in cat.items()
}

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
}

# ─────────────────────────────────────────────────────────────────────────────
# Guild / shard / wedge name mapping for auto-generated deck names
# ─────────────────────────────────────────────────────────────────────────────
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

SCAFFOLD_FILES = ["session.md", "candidate_pool.csv", "decklist.txt",
                  "analysis.md", "sideboard_guide.md"]

GRID_COLS = 5
INNER_PAD = 16

SETTINGS_EXT = ".scaffold.json"


# ─────────────────────────────────────────────────────────────────────────────
# Tooltip for archetype hover descriptions
# ─────────────────────────────────────────────────────────────────────────────
class Tooltip:
    """Hover tooltip for archetype buttons."""
    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.tip_window = None
        widget.bind("<Enter>", self._show)
        widget.bind("<Leave>", self._hide)

    def _show(self, event=None):
        try:
            bbox = self.widget.bbox("insert")
        except Exception:
            bbox = None
        if bbox:
            x, y = bbox[0], bbox[1]
        else:
            x, y = 0, 0
        x += self.widget.winfo_rootx() + 25
        y += self.widget.winfo_rooty() + 25
        self.tip_window = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{x}+{y}")
        label = tk.Label(tw, text=self.text, justify='left',
                        background="#2b2b2b", foreground="#e0e0e0",
                        relief='solid', borderwidth=1,
                        font=("Segoe UI", 10))
        label.pack(ipadx=6, ipady=3)

    def _hide(self, event=None):
        if self.tip_window:
            self.tip_window.destroy()
            self.tip_window = None


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


# ─────────────────────────────────────────────────────────────────────────────
# Pure helpers (GUI-only; auto-build helpers live in auto_build.py)
# ─────────────────────────────────────────────────────────────────────────────
_LEVEL_COLOR = {
    "info": TEXT_DIM,
    "warn": WARNING,
    "error": ERROR,
    "success": SUCCESS,
}


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
    """Auto-generate a deck name from selected colors and archetypes."""
    color_key = frozenset(colors)
    color_name = GUILD_NAMES.get(color_key, "".join(sorted(colors)))
    arch_list = sorted(archetypes)
    arch_label = arch_list[0].replace("_", " ").title() if arch_list else ""
    base = f"{color_name} {arch_label}".strip()
    if focus_char and focus_char.strip():
        base += f" \u2014 {focus_char.strip()}"
    return base


# ─────────────────────────────────────────────────────────────────────────────
# Fonts
# ─────────────────────────────────────────────────────────────────────────────
_F_BODY = _F_SMALL = _F_BOLD = _F_MONO = None
_F_TITLE = _F_SECTION = _F_HINT = None


def _init_fonts():
    global _F_BODY, _F_SMALL, _F_BOLD, _F_MONO, _F_TITLE, _F_SECTION, _F_HINT
    _F_BODY    = ctk.CTkFont(size=13)
    _F_SMALL   = ctk.CTkFont(size=11)
    _F_BOLD    = ctk.CTkFont(size=13, weight="bold")
    _F_MONO    = ctk.CTkFont(family="Courier New", size=11)
    _F_TITLE   = ctk.CTkFont(size=17, weight="bold")
    _F_SECTION = ctk.CTkFont(size=14, weight="bold")
    _F_HINT    = ctk.CTkFont(size=11)


def w_entry(parent, placeholder="", **kw):
    d = dict(fg_color=SURFACE, border_color=BORDER, text_color=TEXT,
             placeholder_text_color=TEXT_MUTED, font=_F_BODY,
             height=38, corner_radius=8)
    d.update(kw)
    return ctk.CTkEntry(parent, placeholder_text=placeholder, **d)


def w_button(parent, text, command=None, *, primary=False, **kw):
    if primary:
        d = dict(fg_color=ACCENT, hover_color=ACCENT_HOVER, text_color=BG,
                 font=_F_BOLD, height=40, corner_radius=8)
    else:
        d = dict(fg_color=SURFACE_ALT, hover_color=BORDER, text_color=TEXT_DIM,
                 font=ctk.CTkFont(size=12), height=36, corner_radius=8)
    d.update(kw)
    return ctk.CTkButton(parent, text=text, command=command, **d)


def w_check(parent, text, variable, **kw):
    d = dict(font=ctk.CTkFont(size=12), text_color=TEXT_DIM,
             fg_color=ACCENT, hover_color=ACCENT_HOVER,
             border_color=BORDER, checkmark_color="#FFFFFF")
    d.update(kw)
    return ctk.CTkCheckBox(parent, text=text, variable=variable, **d)


def w_label(parent, text, *, muted=False, hint=False, bold=False, **kw):
    if bold:    font, color = _F_BOLD, TEXT
    elif hint:  font, color = _F_HINT, TEXT_MUTED
    elif muted: font, color = _F_SMALL, TEXT_DIM
    else:       font, color = _F_BODY, TEXT
    d = dict(font=font, text_color=color)
    d.update(kw)
    return ctk.CTkLabel(parent, text=text, **d)


# ─────────────────────────────────────────────────────────────────────────────
# Application
# ─────────────────────────────────────────────────────────────────────────────
class ScaffoldApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("dark-blue")
        _init_fonts()
        self.title(APP_TITLE)
        self.geometry("%dx%d" % (WIN_W, WIN_H))
        self.minsize(760, 700)
        self.configure(fg_color=BG)
        self._repo = RepoPaths()
        self.selected_colors = set()
        self.selected_archetypes = set()
        self._selected_tags = set()
        self._tribes = []
        self.tribal_enabled_var = ctk.BooleanVar(value=False)
        self.wildcard_var     = ctk.BooleanVar(value=False)
        self.skip_queries_var = ctk.BooleanVar(value=False)
        self.run_synergy_var  = ctk.BooleanVar(value=True)
        self.auto_build_var   = ctk.BooleanVar(value=True)
        self.auto_name_var    = ctk.BooleanVar(value=True)
        self.tribe_var        = ctk.StringVar()
        self.focus_char_var   = ctk.StringVar()
        self._active_proc = None
        self._active_btn = None
        self._active_btn_text = ""
        self._running = False
        self._was_cancelled = False
        self._last_deck_dir = None
        self._tribe_search_job = None
        self._build_ui()

    # ── Settings export / import ──────────────────────────────────────────

    def _export_settings(self):
        return {
            "deck_name": self.name_entry.get().strip(),
            "colors": sorted(self.selected_colors),
            "archetypes": sorted(self.selected_archetypes),
            "tribal_enabled": self.tribal_enabled_var.get(),
            "tribes": list(self._tribes),
            "tags": sorted(self._selected_tags),
            "focus_cards": [l.strip() for l in
                            self.focus_box.get("1.0", "end").strip()
                            .splitlines() if l.strip()],
            "output_dir": self.output_entry.get().strip(),
            "options": {
                "skip_queries": self.skip_queries_var.get(),
                "run_synergy": self.run_synergy_var.get(),
                "auto_build": self.auto_build_var.get(),
                "wildcard": self.wildcard_var.get(),
            },
            "auto_name": self.auto_name_var.get(),
            "focus_character": self.focus_char_var.get().strip(),
        }

    def _import_settings(self, data):
        self._reset_form()
        for c in data.get("colors", []):
            if c in COLOR_ORDER and c not in self.selected_colors:
                self._toggle_color(c)
        for a in data.get("archetypes", []):
            if a in self._arch_btns and a not in self.selected_archetypes:
                self._toggle_arch(a)
        tribal_on = data.get("tribal_enabled", False)
        if tribal_on and not self.tribal_enabled_var.get():
            self.tribal_enabled_var.set(True)
            self._on_tribal_toggle()
        for t in data.get("tribes", []):
            if t not in self._tribes:
                self._tribes.append(t)
        self._refresh_tribe_chips()
        for t in data.get("tags", []):
            if t in self._tag_btns and t not in self._selected_tags:
                self._toggle_tag(t)
        fc = data.get("focus_cards", [])
        if fc:
            self.focus_box.insert("1.0", "\n".join(fc))
        auto_name = data.get("auto_name", True)
        self.auto_name_var.set(auto_name)
        focus_char = data.get("focus_character", "")
        if focus_char:
            self.focus_char_var.set(focus_char)
        self._on_auto_name_toggle()
        if not auto_name:
            name = data.get("deck_name", "")
            if name:
                self.name_entry.configure(state="normal")
                self.name_entry.delete(0, "end")
                self.name_entry.insert(0, name)
        od = data.get("output_dir", "")
        if od:
            self.output_entry.insert(0, od)
        opts = data.get("options", {})
        self.skip_queries_var.set(opts.get("skip_queries", False))
        self.run_synergy_var.set(opts.get("run_synergy", True))
        self.auto_build_var.set(opts.get("auto_build", True))
        self.wildcard_var.set(opts.get("wildcard", False))
        self._validate_live()

    def _on_save_settings(self):
        data = self._export_settings()
        dn = data.get("deck_name", "scaffold") or "scaffold"
        dn = re.sub(r"[^\w\-]", "_", dn)
        f = filedialog.asksaveasfilename(
            title="Save scaffold settings",
            defaultextension=SETTINGS_EXT,
            initialfile="%s%s" % (dn, SETTINGS_EXT),
            filetypes=[("Scaffold Settings", "*" + SETTINGS_EXT),
                       ("JSON", "*.json"), ("All", "*.*")])
        if not f:
            return
        try:
            Path(f).write_text(json.dumps(data, indent=2, ensure_ascii=False),
                               encoding="utf-8")
            self._sm("Settings saved: %s" % Path(f).name, SUCCESS)
        except Exception as e:
            self._sm("Save failed: %s" % e, ERROR)

    def _on_load_settings(self):
        f = filedialog.askopenfilename(
            title="Load scaffold settings",
            filetypes=[("Scaffold Settings", "*" + SETTINGS_EXT),
                       ("JSON", "*.json"), ("All", "*.*")])
        if not f:
            return
        try:
            data = json.loads(Path(f).read_text(encoding="utf-8"))
            self._import_settings(data)
            self._sm("Loaded: %s" % Path(f).name, SUCCESS)
        except Exception as e:
            self._sm("Load failed: %s" % e, ERROR)

    # ── UI construction ───────────────────────────────────────────────────

    def _build_ui(self):
        hdr = ctk.CTkFrame(self, fg_color=SURFACE, corner_radius=0, height=56)
        hdr.pack(fill="x"); hdr.pack_propagate(False)
        ctk.CTkLabel(hdr, text="\u2726  " + APP_TITLE, font=_F_TITLE,
                     text_color=ACCENT).pack(side="left", padx=24, pady=14)
        w_button(hdr, "\u2193 Load", self._on_load_settings,
                 width=70, height=30).pack(side="right", padx=(4, 20), pady=13)
        w_button(hdr, "\u2191 Save", self._on_save_settings,
                 width=70, height=30).pack(side="right", padx=0, pady=13)
        self.tabs = ctk.CTkTabview(self, fg_color=BG,
            segmented_button_fg_color=SURFACE,
            segmented_button_selected_color=ACCENT,
            segmented_button_selected_hover_color=ACCENT_HOVER,
            segmented_button_unselected_color=SURFACE,
            segmented_button_unselected_hover_color=SURFACE_ALT,
            text_color=TEXT, text_color_disabled=TEXT_MUTED)
        self.tabs.pack(fill="both", expand=True)
        self.tabs.add("New Scaffold")
        self.tabs.add("Run Queries")
        self.tabs.add("Synergy Analysis")
        self._build_scaffold_tab()
        self._build_queries_tab()
        self._build_synergy_tab()
        self._build_log_panel()
        self._build_footer()

    def _card(self, parent):
        c = ctk.CTkFrame(parent, fg_color=CARD_BG, corner_radius=14,
                          border_color=CARD_BORDER, border_width=1)
        c.pack(fill="x", padx=10, pady=(0, 10))
        return c

    def _card_header(self, card, number, title, hint=""):
        row = ctk.CTkFrame(card, fg_color="transparent")
        row.pack(fill="x", padx=INNER_PAD, pady=(14, 2 if hint else 10))
        ctk.CTkLabel(row, text=number,
                     font=ctk.CTkFont(size=12, weight="bold"),
                     text_color=BG, fg_color=ACCENT,
                     corner_radius=13, width=26, height=26
                     ).pack(side="left", padx=(0, 10))
        ctk.CTkLabel(row, text=title, font=_F_SECTION,
                     text_color=TEXT).pack(side="left")
        if hint:
            w_label(card, hint, hint=True).pack(
                anchor="w", padx=INNER_PAD, pady=(0, 8))

    def _build_scaffold_tab(self):
        tab = self.tabs.tab("New Scaffold")
        self.scroll = ctk.CTkScrollableFrame(
            tab, fg_color=BG, scrollbar_button_color=BORDER,
            scrollbar_button_hover_color=ACCENT)
        self.scroll.pack(fill="both", expand=True)

        # Card 1: Mana Colours
        c1 = self._card(self.scroll)
        self._card_header(c1, "1", "Mana Colours", "Select colour identity")
        self._build_colors(c1)

        # Card 2: Archetype
        c2 = self._card(self.scroll)
        self._card_header(c2, "2", "Archetype", "Select one or more")
        self._build_archetypes(c2)

        # Card 3: Tribal (standalone)
        c3 = self._card(self.scroll)
        self._card_header(c3, "3", "Tribal",
                          "Optional \u2014 enable for creature type synergies")
        self._build_tribal_card(c3)

        # Card 4: Extra Tags
        c4 = self._card(self.scroll)
        self._card_header(c4, "4", "Extra Tags", "Optional search keywords")
        self._build_tags(c4)

        # Card 5: Focus Cards
        c5 = self._card(self.scroll)
        self._card_header(
            c5, "5", "Focus Cards",
            "Cards listed here are guaranteed inclusion. "
            "Quantity determined by synergy analysis. One card per line.")
        self.focus_box = ctk.CTkTextbox(
            c5, fg_color=SURFACE, border_color=BORDER, text_color=TEXT,
            font=ctk.CTkFont(family="Courier New", size=12),
            border_width=1, corner_radius=8, height=80, wrap="word")
        self.focus_box.pack(fill="x", padx=INNER_PAD, pady=(0, 14))

        # Card 6: Deck Name (with auto-generate)
        c6 = self._card(self.scroll)
        self._card_header(c6, "6", "Deck Name")
        self._build_deck_name(c6)

        # Card 7: Options
        c7 = self._card(self.scroll)
        self._card_header(c7, "7", "Options")
        self._build_options(c7)

        # Card 8: Output Directory
        c8 = self._card(self.scroll)
        self._card_header(c8, "8", "Output Directory", "Default: Decks/")
        self._build_output(c8)

    # ── Card 1: Mana Colours ─────────────────────────────────────────────

    def _build_colors(self, p):
        f = ctk.CTkFrame(p, fg_color="transparent")
        f.pack(fill="x", padx=INNER_PAD, pady=(0, 14))
        self._color_btns = {}
        for c in COLOR_ORDER:
            mc = MANA_COLORS[c]
            btn = ctk.CTkButton(
                f, text="%s\n%s" % (mc["label"], MANA_NAMES[c]),
                width=118, height=62, corner_radius=12,
                fg_color=mc["dim"], hover_color=mc["bg"], text_color=mc["fg"],
                border_color=CARD_BORDER, border_width=2,
                font=ctk.CTkFont(size=13, weight="bold"),
                command=lambda col=c: self._toggle_color(col))
            btn.pack(side="left", padx=(0, 8))
            self._color_btns[c] = btn

    def _toggle_color(self, c):
        btn, mc = self._color_btns[c], MANA_COLORS[c]
        if c in self.selected_colors:
            self.selected_colors.discard(c)
            btn.configure(fg_color=mc["dim"], border_color=CARD_BORDER,
                          border_width=2)
        else:
            self.selected_colors.add(c)
            btn.configure(fg_color=mc["bg"], border_color=ACCENT,
                          border_width=3)
        self._update_auto_name()
        self._validate_live()

    def _build_archetypes(self, p):
        ct = ctk.CTkFrame(p, fg_color="transparent")
        ct.pack(fill="x", padx=INNER_PAD, pady=(0, 14))
        self._arch_btns = {}
        self._arch_tooltips = {}
        for gn, archs in ARCHETYPE_GROUPS.items():
            h = ctk.CTkFrame(ct, fg_color="transparent")
            h.pack(fill="x", pady=(8, 4))
            ctk.CTkFrame(h, fg_color=ACCENT, width=3, height=14,
                         corner_radius=1).pack(side="left", padx=(0, 8))
            ctk.CTkLabel(h, text=gn, font=ctk.CTkFont(size=11, weight="bold"),
                         text_color=TEXT_DIM).pack(side="left")
            g = ctk.CTkFrame(ct, fg_color="transparent")
            g.pack(fill="x")
            for col in range(GRID_COLS):
                g.columnconfigure(col, weight=1, uniform="a")
            for i, (a, desc) in enumerate(archs.items()):
                lbl = ARCH_LABEL.get(a, a.replace("_", " ").title())
                btn = ctk.CTkButton(
                    g, text=lbl, height=34, corner_radius=8,
                    fg_color=SURFACE, hover_color=SURFACE_ALT,
                    text_color=TEXT_DIM, border_color=BORDER, border_width=1,
                    font=ctk.CTkFont(size=12),
                    command=lambda x=a: self._toggle_arch(x))
                btn.grid(row=i // GRID_COLS, column=i % GRID_COLS,
                         padx=3, pady=3, sticky="ew")
                self._arch_btns[a] = btn
                self._arch_tooltips[a] = Tooltip(btn, desc)

    def _toggle_arch(self, arch):
        btn = self._arch_btns[arch]
        if arch in self.selected_archetypes:
            self.selected_archetypes.discard(arch)
            btn.configure(fg_color=SURFACE, text_color=TEXT_DIM,
                          border_color=BORDER, border_width=1)
        else:
            self.selected_archetypes.add(arch)
            btn.configure(fg_color=ACCENT, text_color=BG,
                          border_color=ACCENT, border_width=1)
        if hasattr(self, '_arch_count'):
            self._arch_count.configure(
                text="%d selected" % len(self.selected_archetypes))
        self._update_auto_name()
        self._validate_live()

    def _build_tribal_card(self, p):
        top = ctk.CTkFrame(p, fg_color="transparent")
        top.pack(fill="x", padx=INNER_PAD, pady=(0, 6))
        self._tribal_enable_cb = w_check(
            top, "Enable Tribal", self.tribal_enabled_var)
        self._tribal_enable_cb.pack(side="left")
        self._tribal_enable_cb.configure(command=self._on_tribal_toggle)
        self._wildcard_cb = w_check(
            top, "Wildcard Mode", self.wildcard_var, fg_color=WARNING)
        self._wildcard_cb.pack(side="left", padx=(20, 0))
        self._tribe_search_entry = w_entry(p, "Search creature types...",
                                           state="disabled")
        self._tribe_search_entry.configure(textvariable=self.tribe_var)
        self._tribe_search_entry.pack(fill="x", padx=INNER_PAD, pady=(0, 4))
        self.tribe_var.trace_add("write", self._tribe_debounce)
        self._tribe_results = ctk.CTkFrame(p, fg_color=SURFACE,
                                           corner_radius=8)
        self._tribe_results_visible = False
        self._tribe_chips = ctk.CTkFrame(p, fg_color="transparent")
        self._tribe_chips_visible = False
        self._tribe_widgets = [self._tribe_search_entry]
        self._wildcard_cb.pack_forget()
        self._on_tribal_toggle()

    def _on_tribal_toggle(self):
        enabled = self.tribal_enabled_var.get()
        for w in self._tribe_widgets:
            w.configure(state="normal" if enabled else "disabled")
        if enabled:
            self._wildcard_cb.pack(side="left", padx=(20, 0))
        else:
            self._wildcard_cb.pack_forget()
            self.wildcard_var.set(False)
            self._tribes.clear()
            self._refresh_tribe_chips()
            self._hide_tribe_results()
            self.tribe_var.set("")
        self._validate_live()

    def _show_tribe_results(self):
        if not self._tribe_results_visible:
            self._tribe_results.pack(fill="x", padx=INNER_PAD)
            self._tribe_results_visible = True

    def _hide_tribe_results(self):
        if self._tribe_results_visible:
            self._tribe_results.pack_forget()
            self._tribe_results_visible = False

    def _show_tribe_chips(self):
        if not self._tribe_chips_visible:
            self._tribe_chips.pack(fill="x", padx=INNER_PAD, pady=(4, 14))
            self._tribe_chips_visible = True

    def _hide_tribe_chips(self):
        if self._tribe_chips_visible:
            self._tribe_chips.pack_forget()
            self._tribe_chips_visible = False

    def _tribe_debounce(self, *_):
        if self._tribe_search_job:
            self.after_cancel(self._tribe_search_job)
        self._tribe_search_job = self.after(200, self._tribe_search)

    def _tribe_search(self):
        self._tribe_search_job = None
        for w in self._tribe_results.winfo_children():
            w.destroy()
        q = self.tribe_var.get().strip()
        if not q:
            self._hide_tribe_results()
            return
        matches = filter_tribes(q)
        if not matches:
            self._show_tribe_results()
            w_label(self._tribe_results, "No match for '%s'" % q,
                    hint=True).pack(anchor="w", padx=8, pady=4)
            return
        self._show_tribe_results()
        for t in matches[:10]:
            already = t in self._tribes
            ctk.CTkButton(
                self._tribe_results,
                text=("\u2713 " + t) if already else t,
                fg_color=ACCENT if already else "transparent",
                hover_color=SURFACE_ALT,
                text_color=BG if already else TEXT_DIM,
                font=ctk.CTkFont(size=12), anchor="w",
                height=28, corner_radius=6,
                command=lambda n=t: self._tribe_toggle(n)
            ).pack(fill="x", padx=4, pady=1)
        if len(matches) > 10:
            w_label(self._tribe_results, "+%d more" % (len(matches) - 10),
                    hint=True).pack(anchor="w", padx=8, pady=(2, 4))

    def _tribe_toggle(self, name):
        if name in self._tribes:
            self._tribes.remove(name)
        else:
            self._tribes.append(name)
        self._refresh_tribe_chips()
        self._tribe_search()
        self._validate_live()

    def _refresh_tribe_chips(self):
        for w in self._tribe_chips.winfo_children():
            w.destroy()
        if not self._tribes:
            self._hide_tribe_chips()
            return
        self._show_tribe_chips()
        for t in self._tribes:
            chip = ctk.CTkFrame(self._tribe_chips, fg_color=SURFACE_ALT,
                                corner_radius=14)
            chip.pack(side="left", padx=(0, 6), pady=2)
            ctk.CTkLabel(chip, text=t, font=ctk.CTkFont(size=12),
                         text_color=TEXT).pack(side="left", padx=(10, 2),
                                              pady=4)
            ctk.CTkButton(
                chip, text="\u00d7", width=24, height=24,
                fg_color="transparent", hover_color=BORDER,
                text_color=TEXT_MUTED,
                font=ctk.CTkFont(size=14, weight="bold"),
                corner_radius=12,
                command=lambda n=t: self._tribe_toggle(n)
            ).pack(side="left", padx=(0, 4))

    def _build_tags(self, p):
        auto_row = ctk.CTkFrame(p, fg_color="transparent")
        auto_row.pack(fill="x", padx=INNER_PAD, pady=(0, 8))
        w_button(auto_row, "\u2728 Auto-select from archetype",
                 self._auto_select_tags, width=240).pack(side="left")
        self._tag_btns = {}
        self._tag_tooltips = {}
        for cat_name, cat_tags in TAG_CATEGORIES.items():
            cat_hdr = ctk.CTkFrame(p, fg_color="transparent")
            cat_hdr.pack(fill="x", padx=INNER_PAD, pady=(4, 2))
            ctk.CTkLabel(cat_hdr, text=cat_name,
                         font=ctk.CTkFont(size=10, weight="bold"),
                         text_color=TEXT_MUTED).pack(side="left")
            f = ctk.CTkFrame(p, fg_color="transparent")
            f.pack(fill="x", padx=INNER_PAD, pady=(0, 4))
            for col in range(6):
                f.columnconfigure(col, weight=1, uniform="tag")
            for i, (tag, desc) in enumerate(cat_tags.items()):
                btn = ctk.CTkButton(
                    f, text=tag, height=30, corner_radius=15,
                    fg_color=SURFACE, hover_color=SURFACE_ALT,
                    text_color=TEXT_MUTED, border_color=BORDER, border_width=1,
                    font=ctk.CTkFont(size=11),
                    command=lambda t=tag: self._toggle_tag(t))
                btn.grid(row=i // 6, column=i % 6, padx=3, pady=3,
                         sticky="ew")
                self._tag_btns[tag] = btn
                self._tag_tooltips[tag] = Tooltip(btn, desc)
        ctk.CTkFrame(p, fg_color="transparent", height=6).pack()

    def _toggle_tag(self, tag):
        btn = self._tag_btns[tag]
        if tag in self._selected_tags:
            self._selected_tags.discard(tag)
            btn.configure(fg_color=SURFACE, text_color=TEXT_MUTED,
                          border_color=BORDER)
        else:
            self._selected_tags.add(tag)
            btn.configure(fg_color=ACCENT, text_color=BG, border_color=ACCENT)

    def _auto_select_tags(self):
        for t in list(self._selected_tags):
            self._toggle_tag(t)
        new_tags = set()
        for arch in self.selected_archetypes:
            for tag in ARCHETYPE_TAG_MAP.get(arch, []):
                new_tags.add(tag)
        for tag in new_tags:
            if tag in self._tag_btns and tag not in self._selected_tags:
                self._toggle_tag(tag)

    def _build_deck_name(self, p):
        auto_row = ctk.CTkFrame(p, fg_color="transparent")
        auto_row.pack(fill="x", padx=INNER_PAD, pady=(0, 6))
        self._auto_name_cb = w_check(
            auto_row, "Auto-generate from Colors + Archetype",
            self.auto_name_var)
        self._auto_name_cb.configure(command=self._on_auto_name_toggle)
        self._auto_name_cb.pack(side="left")
        self._name_preview_frame = ctk.CTkFrame(p, fg_color="transparent")
        self._name_preview_frame.pack(fill="x", padx=INNER_PAD, pady=(0, 4))
        ctk.CTkLabel(self._name_preview_frame, text="Preview:",
                     font=_F_SMALL, text_color=TEXT_MUTED
                     ).pack(side="left", padx=(0, 6))
        self._name_preview = ctk.CTkLabel(
            self._name_preview_frame, text="",
            font=_F_BOLD, text_color=ACCENT)
        self._name_preview.pack(side="left")
        self.name_entry = w_entry(p, "e.g. Orzhov Lifegain")
        self.name_entry.pack(fill="x", padx=INNER_PAD, pady=(0, 6))
        self.name_entry.bind("<KeyRelease>", lambda _: self._validate_live())
        fc_row = ctk.CTkFrame(p, fg_color="transparent")
        fc_row.pack(fill="x", padx=INNER_PAD, pady=(0, 14))
        ctk.CTkLabel(fc_row, text="Focus Character:",
                     font=_F_SMALL, text_color=TEXT_DIM
                     ).pack(side="left", padx=(0, 8))
        self._focus_char_entry = w_entry(
            fc_row, "Optional focus character (e.g., Aerith)",
            textvariable=self.focus_char_var)
        self._focus_char_entry.pack(side="left", fill="x", expand=True)
        self.focus_char_var.trace_add("write",
                                      lambda *_: self._update_auto_name())
        self._on_auto_name_toggle()

    def _on_auto_name_toggle(self):
        auto = self.auto_name_var.get()
        if auto:
            self.name_entry.configure(state="disabled")
            self._name_preview_frame.pack(fill="x", padx=INNER_PAD,
                                          pady=(0, 4))
            self._update_auto_name()
        else:
            self.name_entry.configure(state="normal")
            self._name_preview_frame.pack_forget()
        self._validate_live()

    def _update_auto_name(self):
        if not self.auto_name_var.get():
            return
        name = generate_deck_name(
            self.selected_colors, self.selected_archetypes,
            self.focus_char_var.get())
        self._name_preview.configure(
            text=name if name else "(select colors & archetype)")
        self.name_entry.configure(state="normal")
        self.name_entry.delete(0, "end")
        if name:
            self.name_entry.insert(0, name)
        self.name_entry.configure(state="disabled")

    def _get_deck_name(self):
        if self.auto_name_var.get():
            return generate_deck_name(
                self.selected_colors, self.selected_archetypes,
                self.focus_char_var.get())
        return self.name_entry.get().strip()

    def _build_options(self, p):
        f = ctk.CTkFrame(p, fg_color="transparent")
        f.pack(fill="x", padx=INNER_PAD, pady=(0, 14))
        for v, t, kw in [
            (self.skip_queries_var, "Skip queries (offline template)", {}),
            (self.run_synergy_var, "Run synergy analysis after scaffold", {}),
            (self.auto_build_var,
             "Auto-build decklist (Karsten mana base)", {}),
        ]:
            w_check(f, t, v, **kw).pack(anchor="w", pady=3)

    def _build_output(self, p):
        r = ctk.CTkFrame(p, fg_color="transparent")
        r.pack(fill="x", padx=INNER_PAD, pady=(0, 14))
        self.output_entry = w_entry(r, "Decks/")
        self.output_entry.pack(side="left", fill="x", expand=True,
                               padx=(0, 8))
        w_button(r, "Browse", self._browse_output, width=80).pack(
            side="left")

    def _build_queries_tab(self):
        tab = self.tabs.tab("Run Queries")
        f = ctk.CTkScrollableFrame(tab, fg_color=BG,
                                   scrollbar_button_color=BORDER)
        f.pack(fill="both", expand=True)
        card = ctk.CTkFrame(f, fg_color=CARD_BG, corner_radius=14,
                            border_color=CARD_BORDER, border_width=1)
        card.pack(fill="x", padx=10, pady=10)
        w_label(card, "Run Pending Session Queries", bold=True,
                text_color=ACCENT).pack(anchor="w", padx=INNER_PAD,
                                        pady=(14, 2))
        w_label(card, "Finds placeholders, runs them, fills results.",
                hint=True, wraplength=700, justify="left"
                ).pack(anchor="w", padx=INNER_PAD, pady=(0, 12))
        r = ctk.CTkFrame(card, fg_color="transparent")
        r.pack(fill="x", padx=INNER_PAD, pady=(0, 8))
        self.rq_entry = w_entry(r, "Path to session.md")
        self.rq_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))
        w_button(r, "Browse", self._browse_session, width=80).pack(
            side="left")
        self.rq_force = ctk.BooleanVar(value=False)
        self.rq_dryrun = ctk.BooleanVar(value=False)
        o = ctk.CTkFrame(card, fg_color="transparent")
        o.pack(anchor="w", padx=INNER_PAD, pady=(0, 12))
        w_check(o, "Force re-run", self.rq_force).pack(anchor="w", pady=2)
        w_check(o, "Dry run", self.rq_dryrun).pack(anchor="w", pady=2)
        self.rq_btn = w_button(card, "Run Queries", self._on_run_queries,
                               primary=True, width=160)
        self.rq_btn.pack(anchor="w", padx=INNER_PAD, pady=(0, 14))

    def _build_synergy_tab(self):
        tab = self.tabs.tab("Synergy Analysis")
        f = ctk.CTkScrollableFrame(tab, fg_color=BG,
                                   scrollbar_button_color=BORDER)
        f.pack(fill="both", expand=True)
        card = ctk.CTkFrame(f, fg_color=CARD_BG, corner_radius=14,
                            border_color=CARD_BORDER, border_width=1)
        card.pack(fill="x", padx=10, pady=10)
        w_label(card, "Gate 2.5 -- Synergy Analysis", bold=True,
                text_color=ACCENT).pack(anchor="w", padx=INNER_PAD,
                                        pady=(14, 2))
        w_label(card, "Scores interactions, checks thresholds.",
                hint=True, wraplength=700, justify="left"
                ).pack(anchor="w", padx=INNER_PAD, pady=(0, 12))
        r1 = ctk.CTkFrame(card, fg_color="transparent")
        r1.pack(fill="x", padx=INNER_PAD, pady=(0, 8))
        self.syn_in = w_entry(r1, "session.md or decklist.txt")
        self.syn_in.pack(side="left", fill="x", expand=True, padx=(0, 8))
        w_button(r1, "Browse", self._browse_syn_in, width=80).pack(
            side="left")
        r2 = ctk.CTkFrame(card, fg_color="transparent")
        r2.pack(fill="x", padx=INNER_PAD, pady=(0, 8))
        self.syn_out = w_entry(r2, "Output report (optional)")
        self.syn_out.pack(side="left", fill="x", expand=True, padx=(0, 8))
        w_button(r2, "Browse", self._browse_syn_out, width=80).pack(
            side="left")
        sr = ctk.CTkFrame(card, fg_color="transparent")
        sr.pack(anchor="w", padx=INNER_PAD, pady=(0, 12))
        w_label(sr, "Threshold:").pack(side="left", padx=(0, 4))
        self.syn_thresh = ctk.CTkEntry(
            sr, width=60, fg_color=SURFACE, border_color=BORDER,
            text_color=TEXT, font=_F_BODY, height=32, corner_radius=6)
        self.syn_thresh.insert(0, "3.0")
        self.syn_thresh.pack(side="left", padx=(0, 16))
        w_label(sr, "Mode:").pack(side="left", padx=(0, 4))
        self._syn_mode = ctk.StringVar(value="auto")
        ctk.CTkOptionMenu(
            sr, values=["auto", "pool", "deck"],
            variable=self._syn_mode, width=100, height=32,
            fg_color=SURFACE, button_color=ACCENT,
            button_hover_color=ACCENT_HOVER,
            dropdown_fg_color=SURFACE, dropdown_hover_color=SURFACE_ALT,
            text_color=TEXT, dropdown_text_color=TEXT,
            font=ctk.CTkFont(size=12), corner_radius=6).pack(side="left")
        self.syn_btn = w_button(card, "Analyze Synergy", self._on_synergy,
                                primary=True, width=180)
        self.syn_btn.pack(anchor="w", padx=INNER_PAD, pady=(0, 14))

    def _build_log_panel(self):
        self._log_visible = False
        self._log_tags = set()
        bar = ctk.CTkFrame(self, fg_color=SURFACE, corner_radius=0, height=34)
        bar.pack(fill="x"); bar.pack_propagate(False)
        self._log_toggle = ctk.CTkButton(
            bar, text="\u25b6  Log",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color=TEXT_MUTED, fg_color="transparent",
            hover_color=BORDER, anchor="w", height=34, corner_radius=0,
            command=self._toggle_log)
        self._log_toggle.pack(side="left", fill="y", padx=8)
        self._log_inline = w_label(bar, "", hint=True)
        self._log_inline.pack(side="left", padx=4)
        self._log_frame = ctk.CTkFrame(
            self, fg_color=SURFACE, corner_radius=0, height=0)
        self._log_frame.pack(fill="x"); self._log_frame.pack_propagate(False)
        self._log_box = ctk.CTkTextbox(
            self._log_frame, fg_color=SURFACE, text_color=TEXT,
            font=_F_MONO, border_width=0, corner_radius=0,
            wrap="word", state="disabled")
        self._log_box.pack(fill="both", expand=True)

    def _toggle_log(self):
        self._log_visible = not self._log_visible
        self._log_frame.configure(height=220 if self._log_visible else 0)
        self._log_toggle.configure(
            text=("\u25bc  Log" if self._log_visible else "\u25b6  Log"))

    def _log_tag_for(self, color):
        tag = "c_%s" % color.replace("#", "")
        if tag not in self._log_tags:
            try:
                self._log_box._textbox.tag_configure(tag, foreground=color)
            except Exception:
                pass
            self._log_tags.add(tag)
        return tag

    def _log(self, text, color=TEXT):
        tag = self._log_tag_for(color)
        line = text if text.endswith("\n") else text + "\n"
        self._log_box.configure(state="normal")
        s = self._log_box.index("end-1c")
        self._log_box.insert("end", line)
        e = self._log_box.index("end-1c")
        try:
            self._log_box._textbox.tag_add(tag, s, e)
        except Exception:
            pass
        self._log_box.see("end")
        self._log_box.configure(state="disabled")
        if not self._log_visible:
            self._toggle_log()
        self._log_inline.configure(text=text.strip()[:90], text_color=color)

    def _log_clear(self):
        self._log_box.configure(state="normal")
        self._log_box.delete("1.0", "end")
        self._log_box.configure(state="disabled")
        self._log_inline.configure(text="")

    def _build_footer(self):
        ctk.CTkFrame(self, height=1, fg_color=BORDER,
                      corner_radius=0).pack(fill="x")
        ft = ctk.CTkFrame(self, fg_color=SURFACE, corner_radius=0, height=72)
        ft.pack(fill="x", side="bottom"); ft.pack_propagate(False)
        left = ctk.CTkFrame(ft, fg_color="transparent")
        left.pack(side="left", padx=20, fill="y")
        self._arch_count = ctk.CTkLabel(
            left, text="0 selected",
            font=ctk.CTkFont(size=12), text_color=TEXT_MUTED)
        self._arch_count.pack(anchor="w", pady=(10, 0))
        self.status = ctk.CTkLabel(
            left, text="\u2460 Select colours.",
            font=ctk.CTkFont(size=12), text_color=TEXT_MUTED,
            wraplength=400, justify="left")
        self.status.pack(anchor="w", pady=(2, 0))
        right = ctk.CTkFrame(ft, fg_color="transparent")
        right.pack(side="right", padx=20, fill="y")
        self.run_btn = ctk.CTkButton(
            right, text="Generate Scaffold",
            width=200, height=44, corner_radius=10,
            fg_color=ACCENT, hover_color=ACCENT_HOVER, text_color=BG,
            font=ctk.CTkFont(size=14, weight="bold"),
            command=self._on_generate)
        self.run_btn.pack(side="right", pady=14)
        self._open_btn = w_button(
            right, "\U0001f4c2 Open", self._open_folder_btn,
            width=90, state="disabled")
        self._open_btn.pack(side="right", padx=(0, 8), pady=14)
        w_button(right, "Reset", self._reset_form, width=60,
                 fg_color="transparent", text_color=TEXT_MUTED
                 ).pack(side="right", padx=(0, 8), pady=14)

    def _validate_live(self):
        if not self.selected_colors:
            self._sm("\u2460 Select colours.", TEXT_MUTED); return False
        if not self.selected_archetypes:
            self._sm("\u2461 Pick archetypes.", TEXT_MUTED); return False
        if self.tribal_enabled_var.get() and not self._tribes:
            self._sm("\u2462 Tribal \u2014 pick subtype.", WARNING); return False
        name = self._get_deck_name()
        if not name:
            self._sm("\u2463 Enter a deck name.", TEXT_MUTED); return False
        self._sm("Ready!", SUCCESS); return True

    def _sm(self, msg, color=TEXT_MUTED):
        if hasattr(self, 'status'):
            self.status.configure(text=msg, text_color=color)

    def _reset_form(self):
        for c in list(self.selected_colors): self._toggle_color(c)
        for a in list(self.selected_archetypes): self._toggle_arch(a)
        for t in list(self._selected_tags): self._toggle_tag(t)
        self._tribes.clear(); self._refresh_tribe_chips()
        if self._tribe_results_visible:
            for w in self._tribe_results.winfo_children(): w.destroy()
            self._hide_tribe_results()
        self.tribal_enabled_var.set(False)
        self._on_tribal_toggle()
        self.focus_box.delete("1.0", "end")
        self.auto_name_var.set(True)
        self._on_auto_name_toggle()
        self.name_entry.configure(state="normal")
        self.name_entry.delete(0, "end")
        self.name_entry.configure(state="disabled")
        self.focus_char_var.set("")
        self.output_entry.delete(0, "end")
        self.skip_queries_var.set(False)
        self.run_synergy_var.set(True)
        self.auto_build_var.set(True)
        self.wildcard_var.set(False)
        self._last_deck_dir = None
        self._open_btn.configure(state="disabled")
        self._validate_live()

    def _open_folder_btn(self):
        if self._last_deck_dir:
            _open_folder(self._last_deck_dir)

    def _browse_output(self):
        d = filedialog.askdirectory(title="Output directory")
        if d:
            self.output_entry.delete(0, "end")
            self.output_entry.insert(0, d)

    def _browse_session(self):
        f = filedialog.askopenfilename(
            title="session.md",
            filetypes=[("Markdown", "*.md"), ("All", "*.*")])
        if f:
            self.rq_entry.delete(0, "end")
            self.rq_entry.insert(0, f)

    def _browse_syn_in(self):
        f = filedialog.askopenfilename(
            title="Input",
            filetypes=[("MD/TXT", "*.md *.txt"), ("All", "*.*")])
        if f:
            self.syn_in.delete(0, "end")
            self.syn_in.insert(0, f)

    def _browse_syn_out(self):
        f = filedialog.asksaveasfilename(
            title="Save report", defaultextension=".md",
            filetypes=[("Markdown", "*.md"), ("All", "*.*")])
        if f:
            self.syn_out.delete(0, "end")
            self.syn_out.insert(0, f)

    def _guard(self, btn):
        if not self._running: return False
        if self._active_btn is btn: self._cancel(); return True
        self._sm("Already running.", WARNING); return True

    def _start(self, btn, label):
        self._running = True
        self._was_cancelled = False
        self._active_btn = btn
        self._active_btn_text = label
        btn.configure(state="normal", text="Cancel \u2715",
                      fg_color=ERROR, hover_color="#dc2626")
        self._sm("Running...", ACCENT)
        self._log_clear()

    def _finish(self):
        if not self._running: return
        if self._active_btn:
            self._active_btn.configure(
                state="normal", text=self._active_btn_text,
                fg_color=ACCENT, hover_color=ACCENT_HOVER)
        self._active_proc = None
        self._running = False

    def _cancel(self):
        self._was_cancelled = True
        if self._active_proc and self._active_proc.poll() is None:
            self._active_proc.terminate()
            try: self._active_proc.wait(timeout=5)
            except Exception: self._active_proc.kill()
        self._finish()
        self._sm("Cancelled.", WARNING)
        self._log("Cancelled.", WARNING)

    def _env(self):
        e = os.environ.copy()
        e["PYTHONIOENCODING"] = "utf-8"
        return e

    def _on_generate(self):
        if self._guard(self.run_btn): return
        if not self._validate_live(): return
        name = self._get_deck_name()
        colors = normalize_colors("".join(self.selected_colors))
        cmd = [sys.executable,
               str(_scripts_dir / "generate_deck_scaffold.py"),
               "--name", name, "--colors", colors, "--archetype"]
        cmd.extend(sorted(self.selected_archetypes))
        if self.tribal_enabled_var.get():
            if self.wildcard_var.get():
                cmd.append("--wildcard")
            if self._tribes:
                cmd.append("--tribe")
                cmd.extend(self._tribes)
        if self._selected_tags:
            cmd.extend(["--extra-tags",
                        ",".join(sorted(self._selected_tags))])
        od = self.output_entry.get().strip()
        if od:
            cmd.extend(["--output-dir", od])
        ft = self.focus_box.get("1.0", "end").strip()
        fn = [l.strip() for l in ft.splitlines() if l.strip()]
        if fn:
            cmd.append("--focus-cards")
            cmd.extend(fn)
        if self.skip_queries_var.get():
            cmd.append("--skip-queries")
        rs = self.run_synergy_var.get()
        ab = self.auto_build_var.get()
        self._start(self.run_btn, "Generate Scaffold")
        threading.Thread(
            target=self._bg_scaffold,
            args=(cmd, colors, rs, ab, fn),
            daemon=True).start()

    def _on_run_queries(self):
        if self._guard(self.rq_btn): return
        p = self.rq_entry.get().strip()
        if not p:
            self._sm("Select session.md.", ERROR); return
        cmd = [sys.executable,
               str(_scripts_dir / "run_session_queries.py"), p]
        if self.rq_force.get(): cmd.append("--force")
        if self.rq_dryrun.get(): cmd.append("--dry-run")
        self._start(self.rq_btn, "Run Queries")
        threading.Thread(
            target=self._bg_generic, args=(cmd, "queries"),
            daemon=True).start()

    def _on_synergy(self):
        if self._guard(self.syn_btn): return
        inp = self.syn_in.get().strip()
        if not inp:
            self._sm("Select input.", ERROR); return
        cmd = [sys.executable,
               str(_scripts_dir / "synergy_analysis.py"), inp]
        t = self.syn_thresh.get().strip()
        if t and t != "3.0":
            cmd.extend(["--min-synergy", t])
        m = self._syn_mode.get()
        if m and m != "auto":
            cmd.extend(["--mode", m])
        o = self.syn_out.get().strip()
        if o:
            cmd.extend(["--output", o])
        self._start(self.syn_btn, "Analyze Synergy")
        threading.Thread(
            target=self._bg_generic, args=(cmd, "synergy"),
            daemon=True).start()

    def _stream(self, cmd):
        self.after(0, self._log, "$ " + " ".join(cmd), TEXT_MUTED)
        proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL, text=True,
            encoding="utf-8", errors="replace",
            cwd=str(self._repo.root), env=self._env())
        self._active_proc = proc
        lines = []
        for line in proc.stdout:
            lines.append(line)
            s = line.rstrip()
            if s.strip():
                c = (SUCCESS if "[OK]" in s else
                     ERROR if "ERROR" in s else
                     ACCENT if "candidates" in s.lower() else TEXT)
                self.after(0, self._log, s, c)
        proc.wait()
        return proc.returncode == 0, "".join(lines).strip()

    def _bg_generic(self, cmd, source):
        try:
            ok, out = self._stream(cmd)
        except Exception as e:
            ok, out = False, str(e)
        self.after(0, self._done, RunResult(ok, out, source=source))

    def _bg_scaffold(self, cmd, colors, run_syn, auto_build, focus_names):
        try:
            ok, out = self._stream(cmd)
        except Exception as e:
            ok, out = False, str(e)
        deck_dir = None; syn = None; ab_msg = None; focus_log = []
        try:
            deck_dir = _extract_deck_dir(out) if ok else None
            if deck_dir:
                dp = Path(deck_dir)
                if not dp.is_absolute():
                    dp = self._repo.root / dp
                deck_dir = str(dp)
            if ok and run_syn and deck_dir:
                try:
                    syn = self._bg_synergy(deck_dir)
                except Exception as e:
                    self.after(0, self._log,
                               "Synergy crashed: %s" % e, ERROR)
                    self.after(0, self._log, traceback.format_exc(), ERROR)
            if ok and deck_dir:
                try:
                    self._bg_sort(deck_dir)
                except Exception as e:
                    self.after(0, self._log,
                               "Sort crashed: %s" % e, ERROR)
            if ok and auto_build and deck_dir:
                try:
                    ab_ok, ab_msg, focus_log = auto_build_decklist(
                        deck_dir, colors, focus_names)
                    if ab_ok:
                        self.after(0, self._log, "", TEXT)
                        self.after(0, self._log,
                                   "--- Auto-built Decklist " + "-" * 28,
                                   SUCCESS)
                        for m, lvl in focus_log:
                            if m:
                                self.after(0, self._log, m,
                                           _LEVEL_COLOR.get(lvl, TEXT_DIM))
                        self.after(0, self._log, "  %s" % ab_msg, SUCCESS)
                    else:
                        self.after(0, self._log,
                                   "  Auto-build skipped: %s" % ab_msg,
                                   TEXT_DIM)
                        ab_msg = None
                except Exception as e:
                    self.after(0, self._log,
                               "AUTO-BUILD CRASHED: %s" % e, ERROR)
                    self.after(0, self._log, traceback.format_exc(), ERROR)
                    ab_msg = None
        except Exception as e:
            self.after(0, self._log,
                       "Post-scaffold error: %s" % e, ERROR)
            self.after(0, self._log, traceback.format_exc(), ERROR)
        files = _verify_files(deck_dir) if deck_dir else []
        self.after(0, self._done,
                   RunResult(ok, out, syn, "scaffold", deck_dir, files,
                             ab_msg, focus_log))

    def _bg_synergy(self, deck_dir):
        session = Path(deck_dir) / "session.md"
        if not session.exists():
            return None
        self.after(0, self._log, "\nRunning synergy analysis...", ACCENT)
        report = Path(deck_dir) / "synergy_report.md"
        cmd = [sys.executable,
               str(_scripts_dir / "synergy_analysis.py"),
               str(session), "--output", str(report), "--top", "200"]
        try:
            subprocess.run(
                cmd, capture_output=True, text=True,
                encoding="utf-8", errors="replace",
                stdin=subprocess.DEVNULL,
                cwd=str(self._repo.root), env=self._env(), timeout=120)
            if report.exists():
                return report.read_text(encoding="utf-8").strip()
            return None
        except Exception as e:
            return "Synergy failed: %s" % e

    def _bg_sort(self, deck_dir):
        d = Path(deck_dir)
        ok, n = sort_and_rewrite_csv(d / "top_200.csv")
        if ok:
            self.after(0, self._log,
                       "  Sorted top_200.csv (%d rows)" % n, SUCCESS)
        ok2, pn = merge_scores_into_candidate_pool(deck_dir)
        if ok2:
            self.after(0, self._log,
                       "  Merged scores into candidate_pool.csv (%d cards)"
                       % pn, SUCCESS)

    def _done(self, r):
        was = self._was_cancelled
        self._was_cancelled = False
        self._finish()
        if was:
            return
        if r.source == "scaffold" and r.success:
            self._show_summary(r)
        if r.synergy_output:
            self._show_synergy(r.synergy_output)
        if r.success:
            if r.source == "scaffold":
                n = len(r.files_found)
                nm = Path(r.deck_dir).name if r.deck_dir else "?"
                msg = "Done -- %d files in %s" % (n, nm)
                if r.auto_build_msg:
                    msg += " | %s" % r.auto_build_msg.split("|")[0].strip()
                self._sm(msg, SUCCESS)
                if r.deck_dir and Path(r.deck_dir).exists():
                    self._last_deck_dir = r.deck_dir
                    self._open_btn.configure(state="normal")
            else:
                self._sm("Done.", SUCCESS)
        else:
            self._sm("Error -- see log.", ERROR)

    def _show_summary(self, r):
        self._log("", TEXT)
        self._log("--- Scaffold Complete " + "-" * 30, SUCCESS)
        if r.deck_dir:
            self._log("  Folder: %s" % r.deck_dir, INFO_BLUE)
        af = SCAFFOLD_FILES + ["synergy_report.md", "top_200.csv"]
        for f in af:
            if f in r.files_found:
                fp = Path(r.deck_dir) / f if r.deck_dir else None
                sz = ""
                if fp and fp.exists():
                    sz = "  (%.1f KB)" % (fp.stat().st_size / 1024)
                self._log("  \u2713 %s%s" % (f, sz), SUCCESS)
            elif f in SCAFFOLD_FILES:
                self._log("  \u2717 %s  (missing)" % f, ERROR)

    def _show_synergy(self, syn):
        self._log("", TEXT)
        self._log("--- Gate 2.5 Synergy " + "-" * 30, ACCENT)
        self._log("  (Deck feedback, not an error)", TEXT_MUTED)
        for line in syn.splitlines():
            c = (ERROR if "[FAIL]" in line else
                 SUCCESS if "[PASS]" in line else
                 INFO_BLUE if "[INFO]" in line else
                 ACCENT if line.startswith(("#", "**")) else TEXT)
            self._log(line, c)


def main():
    ScaffoldApp().mainloop()


if __name__ == "__main__":
    main()
