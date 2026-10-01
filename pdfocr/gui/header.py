"""Modern Header Bar: app identity + primary actions with tooltips & shortcuts.

Design goals:
- Clean visual hierarchy: logo/wordmark left, primary actions right
- Tooltips with keyboard shortcuts on hover
- Consistent spacing, rounded corners, subtle shadows
- Light/dark theme aware
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Callable, Optional, Sequence

from .branding import (
    APP_NAME,
    APP_TAGLINE,
    find_logo,
    find_wordmark,
    load_logo,
    load_wordmark,
)
from .app_colors import (
    get_theme,
    SPACE_2, SPACE_3, SPACE_4, SPACE_5,
    RADIUS_MD, RADIUS_LG,
    TOOLBAR_HEIGHT,
)

# (label, command, style, shortcut, tooltip)
Action = tuple[str, Callable[[], None], str, str, str]


class ToolTip:
    """Lightweight tooltip with fade-in/out animation."""

    def __init__(self, widget: tk.Widget, text: str, delay: int = 500) -> None:
        self.widget = widget
        self.text = text
        self.delay = delay
        self._tip: tk.Toplevel | None = None
        self._after_id: str | None = None
        self._fade_id: str | None = None
        self._alpha = 0.0
        widget.bind("<Enter>", self._schedule_show, add="+")
        widget.bind("<Leave>", self._schedule_hide, add="+")
        widget.bind("<ButtonPress>", self._schedule_hide, add="+")

    def _schedule_show(self, _event: tk.Event | None = None) -> None:
        self._cancel_hide()
        if self._after_id:
            self.widget.after_cancel(self._after_id)
        self._after_id = self.widget.after(self.delay, self._show)

    def _schedule_hide(self, _event: tk.Event | None = None) -> None:
        self._cancel_show()
        if self._after_id:
            self.widget.after_cancel(self._after_id)
            self._after_id = None
        if self._tip and self._tip.winfo_exists():
            self._fade_out()

    def _cancel_show(self) -> None:
        if self._after_id:
            self.widget.after_cancel(self._after_id)
            self._after_id = None

    def _cancel_hide(self) -> None:
        if self._fade_id:
            self.widget.after_cancel(self._fade_id)
            self._fade_id = None

    def _show(self) -> None:
        if self._tip:
            return
        theme = self.widget._theme if hasattr(self.widget, "_theme") else None
        if theme is None:
            from .app_colors import get_theme
            theme = get_theme()
        tip = tk.Toplevel(self.widget)
        tip.wm_overrideredirect(True)
        tip.wm_attributes("-topmost", True)
        bg = theme.bg_raised
        fg = theme.fg
        tip.configure(bg=bg)
        label = tk.Label(
            tip,
            text=self.text,
            bg=bg,
            fg=theme.fg,
            font=("TkDefaultFont", 9),
            padx=8,
            pady=4,
        )
        label.pack()
        # Position near widget
        x = self.widget.winfo_rootx() + self.widget.winfo_width() // 2
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 6
        tip.geometry(f"+{x - tip.winfo_reqwidth() // 2}+{y}")
        tip.attributes("-alpha", 0.0)
        self._tip = tip
        self._fade_in()

    def _fade_in(self) -> None:
        if not self._tip or not self._tip.winfo_exists():
            return
        alpha = self._tip.attributes("-alpha")
        if alpha < 0.95:
            self._tip.attributes("-alpha", min(1.0, alpha + 0.15))
            self._fade_id = self.widget.after(16, self._fade_in)

    def _fade_out(self) -> None:
        if not self._tip or not self._tip.winfo_exists():
            self._tip = None
            return
        alpha = self._tip.attributes("-alpha")
        if alpha > 0.05:
            self._tip.attributes("-alpha", max(0.0, alpha - 0.2))
            self._fade_id = self.widget.after(16, self._fade_out)
        else:
            self._tip.destroy()
            self._tip = None


class HeaderBar(ttk.Frame):
    """Modern header: logo/wordmark + title + tagline (left), toolbar (right)."""

    def __init__(
        self,
        master: tk.Misc,
        actions: Sequence[Action] = (),
        tagline: str | None = None,
    ) -> None:
        super().__init__(master, style="Header.TFrame")
        self._theme = get_theme()
        self._actions = actions

        # Height fixed
        self.configure(height=TOOLBAR_HEIGHT)
        self.pack_propagate(False)

        # Left: identity block
        identity = ttk.Frame(self, style="Header.TFrame")
        identity.pack(side="left", fill="y", padx=(16, 0))

        # Wordmark or logo + text
        self.logo_photo: tk.PhotoImage | None = None
        self.uses_wordmark = False

        wordmark_path = find_wordmark()
        logo_path = find_logo()

        if wordmark_path:
            self.logo_photo = load_wordmark(self, wordmark_path)
            self.uses_wordmark = self.logo_photo is not None

        if self.logo_photo is not None:
            label = ttk.Label(self, image=self.logo_photo, style="Header.TLabel")
            label.image = self.logo_photo  # type: ignore[attr-defined]
            label.pack(side="left", anchor="n", padx=(0, 12))
        elif logo_path:
            self.logo_photo = load_logo(self, logo_path)
            if self.logo_photo is not None:
                label = ttk.Label(self, image=self.logo_photo, style="Header.TLabel")
                label.image = self.logo_photo  # type: ignore[attr-defined]
                label.pack(side="left", anchor="n", padx=(0, 12))

        show_name = self.logo_photo is None or (self.uses_wordmark is False)

        if show_name:
            texts = ttk.Frame(self, style="Header.TFrame")
            texts.pack(side="left", fill="y", padx=(0, 12))
            ttk.Label(texts, text=APP_NAME, style="Title.TLabel").pack(anchor="w")
            if tagline:
                ttk.Label(texts, text=tagline, style="Tagline.TLabel").pack(anchor="w")

        # Right: toolbar with actions
        toolbar = ttk.Frame(self, style="Header.TFrame")
        toolbar.pack(side="right", fill="y", padx=(0, 16))

        self.action_buttons: list[ttk.Button] = []
        for label_text, command, style, shortcut, tooltip in actions:
            btn = ToolbarButton(
                toolbar,
                text=label_text,
                command=command,
                style=style,
                shortcut=shortcut,
                tooltip=tooltip,
            )
            btn.pack(side="right", padx=(8, 0))
            self.action_buttons.append(btn)

        # Fill remaining space with identity
        identity.pack(fill="y", expand=True, side="left")

    @property
    def brand(self) -> "HeaderBar":
        """Backward compatibility: test expects `header.brand` to access identity."""
        return self


class ToolbarButton(ttk.Button):
    """Modern toolbar button with icon (optional), shortcut hint, and tooltip."""

    def __init__(
        self,
        master: tk.Misc,
        text: str,
        command: Callable[[], None],
        style: str = "Toolbar.TButton",
        shortcut: str = "",
        tooltip: str = "",
        **kwargs,
    ) -> None:
        display = text
        if shortcut:
            display = f"{text}  {shortcut}"
        super().__init__(master, text=display, command=command, style=style, **kwargs)
        self._shortcut = shortcut
        self._tooltip_text = tooltip
        self._tooltip: ToolTip | None = None
        if tooltip:
            self._tooltip = ToolTip(self, f"{tooltip}  ({shortcut})" if shortcut else tooltip)

    def update_theme(self) -> None:
        """Called when theme changes."""
        pass


def setup_header_styles(style: ttk.Style) -> None:
    """Configure header and toolbar styles."""
    theme = get_theme()

    style.configure(
        "Header.TFrame",
        background=theme.bg,
        relief="flat",
        borderwidth=0,
    )

    style.configure(
        "Header.TLabel",
        background=theme.bg,
        foreground=theme.fg,
    )

    style.configure(
        "Title.TLabel",
        background=theme.bg,
        foreground=theme.fg,
        font=("TkDefaultFont", 14, "bold"),
    )

    style.configure(
        "Tagline.TLabel",
        background=theme.bg,
        foreground=theme.fg_muted,
        font=("TkDefaultFont", 10),
    )

    style.configure(
        "Toolbar.TButton",
        background=theme.bg,
        foreground=theme.fg,
        relief="flat",
        borderwidth=0,
        focuscolor=theme.accent,
        font=("TkDefaultFont", 10),
        padding=(12, 8),
    )
    style.map(
        "Toolbar.TButton",
        background=[("active", theme.bg_hover), ("pressed", theme.bg_active), ("disabled", theme.bg)],
        foreground=[("disabled", theme.fg_subtle), ("active", theme.fg)],
    )

    # Primary action button
    style.configure(
        "Primary.TButton",
        background=theme.accent,
        foreground=theme.fg_inverse,
        relief="flat",
        borderwidth=0,
        focuscolor=theme.accent_hover,
        font=("TkDefaultFont", 10, "bold"),
        padding=(16, 8),
    )
    style.map(
        "Primary.TButton",
        background=[("active", theme.accent_hover), ("pressed", theme.accent_active), ("disabled", theme.bg_active)],
        foreground=[("disabled", theme.fg_subtle), ("active", theme.fg_inverse)],
    )

    # Danger/destructive button
    style.configure(
        "Danger.TButton",
        background=theme.error,
        foreground=theme.fg_inverse,
        relief="flat",
        borderwidth=0,
        focuscolor=theme.error,
        font=("TkDefaultFont", 10, "bold"),
        padding=(16, 8),
    )
    style.map(
        "Danger.TButton",
        background=[("active", "#ff9a9a"), ("pressed", "#cc0000"), ("disabled", theme.bg_active)],
        foreground=[("disabled", theme.fg_subtle), ("active", theme.fg_inverse)],
    )

    # Ghost/secondary button
    style.configure(
        "Ghost.TButton",
        background=theme.bg,
        foreground=theme.fg,
        relief="flat",
        borderwidth=1,
        bordercolor=theme.border,
        focuscolor=theme.accent,
        font=("TkDefaultFont", 10),
        padding=(12, 8),
    )
    style.map(
        "Ghost.TButton",
        background=[("active", theme.bg_hover), ("pressed", theme.bg_active), ("disabled", theme.bg)],
        foreground=[("disabled", theme.fg_subtle), ("active", theme.fg)],
        bordercolor=[("active", theme.border_focus), ("focus", theme.border_focus)],
    )

    # Toolbar button with icon
    style.configure(
        "Icon.TButton",
        background=theme.bg,
        foreground=theme.fg,
        relief="flat",
        borderwidth=0,
        focuscolor=theme.accent,
        font=("TkDefaultFont", 10),
        padding=(10, 8),
    )
    style.map(
        "Icon.TButton",
        background=[("active", theme.bg_hover), ("pressed", theme.bg_active)],
        foreground=[("active", theme.fg)],
    )
