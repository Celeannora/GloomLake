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

    CREATURE      = "#34d399"
    INSTANT       = "#f87171"
    SORCERY       = "#fbbf24"
    ENCHANTMENT   = "#a78bfa"
    ARTIFACT      = "#94a3b8"
    PLANESWALKER  = "#c084fc"
    LAND          = "#86efac"

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


COLOR_ORDER = "WUBRG"
MANA_NAMES = {c: Colors.MANA[c]["name"] for c in COLOR_ORDER}

THEMES = {
    "dark": Colors,
}
