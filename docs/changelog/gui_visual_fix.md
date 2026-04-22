# GUI Visual Fix Plan

> **Current**: `wrong.png` — boxy, form-like, spread out, disconnected sections
> **Target**: `right.webp` — Utility Tracker style: orbital icons, clean dark cards, focused app feel
> **Backup**: `scaffold_gui_backup.py`

---

## Problem Analysis (wrong.png)

| Issue | Location | Impact |
|-------|----------|--------|
| Mana icons in boxy rectangular containers | Card 01 | Looks like form buttons, not an app |
| Too much horizontal spread on color buttons | Card 01 | Waste of space, not visually appealing |
| Guild presets are tiny thin-bordered boxes | Card 01 | Hard to read, doesn't feel premium |
| Archetype buttons are flat bordered rectangles | Card 02 | Generic form appearance |
| Section headers too heavy (bold + icon + label) | All cards | Visual clutter |
| Cards have barely visible borders | All cards | Sections don't pop, everything blends |
| Too much vertical scrolling | Overall | Long form feel, not app feel |
| Footer and header are plain | Chrome | Doesn't frame the app well |

## Target Design Language (right.webp — Utility Tracker)

Key elements to adopt:

1. **Circular icon orbit** — Icons arranged in a radial pattern around a centre
2. **Circle-outlined icons** — White outlines on dark, not filled rectangles
3. **Very dark cards** — Deep dark (#1a1a2e) with subtle rounded corners (20px+)
4. **Minimal text** — Less is more, let icons speak
5. **Accent colour** — Lavender/purple for actions, gold for selections
6. **Clean white typography** — Simple, no all-caps headers
7. **Focused layouts** — Each section feels self-contained, not a long scroll form

---

## Fix Plan

### Phase 1: Mana Colour Selector — Orbital Layout

**Current**: 5 circular buttons in a horizontal line
**Target**: 5 mana icons in a **colour-wheel / pentagram** arrangement

```
        W
       / \
      U   G
      |   |
      B - R
```

Implementation:
- Use a `tkinter.Canvas` or positioned `CTkFrame` grid to place icons in a circular pattern
- Centre element: guild icon (when 2+ selected) or colour-pie icon
- Each icon: 44px circle with mana glyph, `circle-outlined` style (transparent fill, coloured ring)
- Selected: filled circle with glow
- Labels below each icon removed — tooltip on hover instead
- Connect icons with subtle lines (like utility tracker orbital rings)

### Phase 2: Guild Presets — Compact Dropdown or Chips

**Current**: Horizontal scrollable row of tiny buttons
**Target**: Replace with:
- Option A: `CTkOptionMenu` dropdown with guild icon preview
- Option B: 2-row grid of small guild icon chips (no scroll)
- Option C: Collapsible section — click "Presets" to expand

Recommendation: **Option B** — 2-row grid, 10 guilds on row 1, 10 shards/wedges on row 2

### Phase 3: Card Styling — Deeper, Rounder

- `CARD_BG`: darken to `#12141f` (deeper than current `#171c28`)
- `corner_radius`: increase to `18` (from 14)
- `border_width`: increase to `1` with `#252840` (slightly more visible)
- Inner padding: increase to `24px` (from 20)
- Card spacing: increase bottom margin

### Phase 4: Archetype Buttons — Pill Style

**Current**: Rectangular bordered buttons in a 5-column grid
**Target**: Rounded pill buttons (`corner_radius=20`) with gradient-like hover
- Unselected: transparent with subtle text
- Selected: accent-dim background with gold text + subtle glow border
- Group headers: smaller, integrated separator — thin line + muted icon

### Phase 5: Tag Buttons — Compact Icon-Only + Label

- Reduce tag buttons to icon + short label
- Make pills more compact (height=26)
- 8-column grid instead of 6

### Phase 6: Typography & Spacing

- Card titles: 15px bold, proper case (not UPPERCASE)
- Hint text: 11px, softer muted colour
- Section labels: 10px caps with icon, thinner weight
- Overall: more vertical whitespace between sections

### Phase 7: Footer — Premium Status Bar

- Background: match header (`CARD_BG`)
- Generate button: larger, more prominent accent with glow effect
- Status text: single line, cleaner layout

### Phase 8: Colour Palette Fine-tune

```python
BG           = "#0d0f18"   # even deeper navy-black
CARD_BG      = "#12141f"   # subtle card elevation
CARD_BORDER  = "#1e2040"   # visible but not harsh
SURFACE      = "#181a28"   # inputs/interactives
SURFACE_ALT  = "#222438"   # hover
BORDER       = "#282a42"   # button borders
ACCENT       = "#c9a227"   # keep gold
ACCENT_2     = "#9b7ddb"   # lavender secondary (actions)
```

---

## Implementation Order

1. ✅ Backup: `scaffold_gui_backup.py`
2. Phase 8 → Palette first (affects everything)
3. Phase 3 → Card styling (structural)
4. Phase 1 → Orbital mana selector (biggest visual impact)
5. Phase 2 → Guild presets redesign
6. Phase 4 → Archetype pills
7. Phase 5 → Tag compact pills
8. Phase 6 → Typography
9. Phase 7 → Footer polish

## Estimated Changes

~300 lines modified across palette, `_build_colors`, `_card`, `_card_header`,
`_build_archetypes`, `_build_tags`, `_build_footer`, widget factories.
