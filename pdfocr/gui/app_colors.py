"""Design system: warna, spacing, tipografi, radius, shadow untuk SelfPDF.

Semua nilai terpusat di sini agar konsisten di seluruh aplikasi.
Mendukung light & dark mode (dark default).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

ThemeName = Literal["dark", "light"]


@dataclass(frozen=True)
class ColorPalette:
    # Background layers
    bg: str              # Window background
    bg_raised: str       # Card/panel background
    bg_sunken: str       # Input/well background
    bg_hover: str        # Hover state
    bg_active: str       # Pressed/active state
    bg_selected: str     # Selection background

    # Borders
    border: str          # Default border
    border_focus: str    # Focused input border
    border_subtle: str   # Subtle divider

    # Text
    fg: str              # Primary text
    fg_muted: str        # Secondary/muted text
    fg_subtle: str       # Very subtle text (placeholders)
    fg_inverse: str      # Text on accent backgrounds

    # Semantic
    accent: str          # Primary action color
    accent_hover: str
    accent_active: str
    success: str
    success_bg: str
    warning: str
    warning_bg: str
    error: str
    error_bg: str

    # Overlay
    overlay: str         # Modal backdrop
    shadow: str          # Shadow color (rgba-like hex)

    # Scrollbar
    scrollbar_track: str
    scrollbar_thumb: str
    scrollbar_thumb_hover: str


DARK = ColorPalette(
    bg="#181a1f",
    bg_raised="#1e2026",
    bg_sunken="#252830",
    bg_hover="#2a2e36",
    bg_active="#323842",
    bg_selected="#1f6feb",
    border="#2d3139",
    border_focus="#1f6feb",
    border_subtle="#282c34",
    fg="#e6edf3",
    fg_muted="#8b949e",
    fg_subtle="#6a737d",
    fg_inverse="#ffffff",
    accent="#1f6feb",
    accent_hover="#388bfd",
    accent_active="#0960d0",
    success="#3fb950",
    success_bg="#1c2d1f",
    warning="#d29922",
    warning_bg="#332800",
    error="#ff7b72",
    error_bg="#3d1212",
    overlay="#000000cc",
    shadow="#00000080",
    scrollbar_track="#181a1f",
    scrollbar_thumb="#3a3f47",
    scrollbar_thumb_hover="#4a4f58",
)

LIGHT = ColorPalette(
    bg="#f6f8fa",
    bg_raised="#ffffff",
    bg_sunken="#f3f4f6",
    bg_hover="#eaeef2",
    bg_active="#d0d7de",
    bg_selected="#0969da",
    border="#d0d7de",
    border_focus="#0969da",
    border_subtle="#d8dee4",
    fg="#24292f",
    fg_muted="#656d76",
    fg_subtle="#8b949e",
    fg_inverse="#ffffff",
    accent="#0969da",
    accent_hover="#0969da",
    accent_active="#0550ae",
    success="#2da44e",
    success_bg="#dafbe1",
    warning="#9a6700",
    warning_bg="#fff8c5",
    error="#cf222e",
    error_bg="#ffebe9",
    overlay="#00000080",
    shadow="#00000020",
    scrollbar_track="#f6f8fa",
    scrollbar_thumb="#c2c8cc",
    scrollbar_thumb_hover="#a0a7ad",
)

# Current active theme (mutable at runtime)
_current_theme = DARK


def get_theme() -> ColorPalette:
    return _current_theme


def set_theme(name: ThemeName) -> None:
    global _current_theme
    _current_theme = DARK if name == "dark" else LIGHT


def toggle_theme() -> ThemeName:
    """Toggle between dark and light, return new theme name."""
    if _current_theme is DARK:
        set_theme("light")
        return "light"
    else:
        set_theme("dark")
        return "dark"


# Legacy constants for backward compatibility (will be removed)
BG = DARK.bg
BG_PANEL = DARK.bg_raised
FG = DARK.fg
FG_DIM = DARK.fg_muted
ACCENT = DARK.accent
OK = DARK.success
WARN = DARK.warning
ERROR = "#ff7b72"
DIALOG_BG = DIALOG_BG = DARK.bg_raised


# ── Spacing system (8px base) ─────────────────────────────────────────
SPACE_1 = 4
SPACE_2 = 8
SPACE_3 = 12
SPACE_4 = 16
SPACE_5 = 24
SPACE_6 = 32
SPACE_7 = 40
SPACE_8 = 48

# ── Border radius ──────────────────────────────────────────────────────
RADIUS_SM = 4
RADIUS_MD = 8
RADIUS_LG = 12
RADIUS_XL = 16
RADIUS_FULL = 9999

# ── Shadows (css-like: offset-y, blur, spread, color) ─────────────────
SHADOW_SM = (0, 1, 2, 0, "#00000030")
SHADOW_MD = (0, 4, 8, -2, "#00000040")
SHADOW_LG = (0, 12, 24, -4, "#00000050")

# ── Typography ─────────────────────────────────────────────────────────
FONT_FAMILY = "system"  # "system" -> TkDefaultFont, atau "Segoe UI" / "SF Pro" / "Inter"
FONT_MONO = "TkFixedFont"

FONT_SIZE_XS = 10
FONT_SIZE_SM = 11
FONT_SIZE_BASE = 12
FONT_SIZE_LG = 13
FONT_SIZE_XL = 15
FONT_SIZE_2XL = 18
FONT_SIZE_3XL = 22
FONT_SIZE_4XL = 28

FONT_WEIGHT_NORMAL = "normal"
FONT_WEIGHT_MEDIUM = "bold"
FONT_WEIGHT_SEMIBOLD = "bold"

# ── Animation durations (ms) ───────────────────────────────────────────
ANIM_FAST = 100
ANIM_NORMAL = 180
ANIM_SLOW = 280

# ── Z-index layers ─────────────────────────────────────────────────────
Z_BASE = 0
Z_DROPDOWN = 100
Z_TOOLTIP = 200
Z_TOAST = 300
Z_MODAL = 400
Z_POPOVER = 500

# ── Component constants ────────────────────────────────────────────────
THUMB_HEIGHT = 190
THUMB_MIN_WIDTH = 140
THUMB_MAX_WIDTH = 220
THUMB_PAD = 8
TOOLBAR_HEIGHT = 48
SIDEBAR_WIDTH = 360
SIDEBAR_MIN_WIDTH = 320
HEADER_HEIGHT = 56
STATUSBAR_HEIGHT = 28
MENU_HEIGHT = 36
TOAST_DURATION = 4000

DROP_FONT = ("TkDefaultFont", 10)

# Latar dialog mengikuti panel agar menapak dengan jendela utama.
DIALOG_BG = BG
