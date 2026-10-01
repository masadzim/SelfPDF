"""Modern Menubar with icons, keyboard shortcuts, and command palette (Ctrl+K).

Design:
- In-window menubar (no native tk.Menu flicker on X11)
- Icons for each menu item
- Keyboard shortcuts displayed
- Searchable command palette (Ctrl+K)
- Consistent styling with header
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Callable, Optional

from .app_colors import (
    get_theme,
    SPACE_2, SPACE_3,
    MENU_HEIGHT,
    DROP_FONT,
)

# Command entry for menu items and command palette
CommandEntry = tuple[str, Callable[[], None], str, str]  # (label, command, shortcut, icon_name)
MenuCommands = list[CommandEntry]


class _Submenu:
    """Wrapper for a dropdown menu."""

    def __init__(self, menu: tk.Menu) -> None:
        self._menu = menu

    def add_command(self, label: str, command: Callable[[], None],
                    shortcut: str = "", icon: str = "") -> "_Submenu":
        def run() -> None:
            try:
                self._menu.unpost()
            except tk.TclError:
                pass
            command()

        display = label
        if shortcut:
            display = f"{label}\t{shortcut}"
        theme = get_theme()
        self._menu.add_command(
            label=display,
            command=run,
            background=theme.bg_raised,
            foreground=theme.fg,
            activebackground=theme.accent,
            activeforeground=theme.fg_inverse,
        )
        return self

    def add_separator(self) -> "_Submenu":
        theme = get_theme()
        self._menu.add_separator(background=theme.bg_raised)
        return self


class MenuButton(ttk.Button):
    """Custom button with dropdown menu (no dropdown arrow indicator - VS Code style)."""

    def __init__(self, master: tk.Misc, text: str, **kwargs) -> None:
        super().__init__(master, text=text, width=0, style="Menubar.TButton", **kwargs)
        self._menu: tk.Menu | None = None
        self.bind("<Enter>", lambda e: self.state(["active"]), add="+")
        self.bind("<Leave>", lambda e: self.state(["!active"]), add="+")
        # Bind click to show menu
        self.bind("<Button-1>", self._show_menu, add="+")

    def _show_menu(self, event: tk.Event) -> None:
        if self._menu:
            try:
                self._menu.tk_popup(event.x_root, event.y_root)
            finally:
                self._menu.grab_release()

    def set_menu(self, menu: tk.Menu) -> None:
        self._menu = menu

    def update_theme(self) -> None:
        """Called when theme changes."""
        pass


class MenuBar(ttk.Frame):
    """Modern in-window menubar with icon support and keyboard shortcuts."""

    def __init__(self, master: tk.Misc) -> None:
        super().__init__(master, style="Menubar.TFrame")
        self._columns = 0
        self._commands: list[tuple[str, Callable[[], None], str, str, str]] = []  # (category, label, cmd, shortcut, icon)
        self._row = ttk.Frame(self, style="Menubar.TFrame", height=MENU_HEIGHT)
        self._row.pack(fill="x")
        self._row.pack_propagate(False)

    def add_menu(self, label: str, gap_before: int = 0) -> _Submenu:
        """Add a menu button with dropdown (VS Code style - no arrow)."""
        holder = ttk.Frame(self._row, style="Menubar.TFrame")
        holder.grid(row=0, column=self._columns, sticky="w",
                    padx=(gap_before if self._columns else 0, 0))
        self._columns += 1

        button = MenuButton(holder, text=label)
        button.pack(side="left", fill="y")

        menu = tk.Menu(
            self,
            tearoff=0,
        )
        button.set_menu(menu)
        return _Submenu(menu)

    def register_command(self, category: str, label: str,
                         command: Callable[[], None],
                         shortcut: str = "", icon: str = "") -> None:
        """Register a command for the command palette (Ctrl+K)."""
        self._commands.append((category, label, command, shortcut, icon))

    def get_all_commands(self) -> list[tuple[str, str, Callable[[], None], str, str]]:
        """Return all registered commands for command palette."""
        return self._commands.copy()


class CommandPalette(tk.Toplevel):
    """Searchable command palette (Ctrl+K) — VS Code style."""

    def __init__(self, master: tk.Misc, commands: list[tuple[str, str, Callable[[], None], str, str]],
                 on_execute: Callable[[Callable[[], None]], None]) -> None:
        super().__init__(master)
        self.title("")
        self.withdraw()
        self.overrideredirect(True)
        self.resizable(False, False)
        self.transient(master)

        self._commands = commands
        self._filtered = commands
        self._on_execute = on_execute
        self._selected_idx = 0

        theme = master._theme if hasattr(master, "_theme") else None
        if theme is None:
            from .app_colors import get_theme
            theme = get_theme()
        self._theme = theme

        self.configure(bg=theme.bg_raised)

        # Container with shadow effect
        container = ttk.Frame(self, style="Palette.TFrame", padding=8)
        container.pack(fill="both", expand=True)

        # Search input
        self.search_var = tk.StringVar()
        self.search_entry = ttk.Entry(
            container,
            textvariable=self.search_var,
            font=("TkDefaultFont", 11),
            style="Palette.TEntry",
        )
        self.search_entry.pack(fill="x", pady=(0, 8))
        self.search_entry.bind("<KeyRelease>", self._on_search)
        self.search_entry.bind("<Down>", self._on_down)
        self.search_entry.bind("<Up>", self._on_up)
        self.search_entry.bind("<Return>", self._on_enter)
        self.search_entry.bind("<Escape>", lambda e: self.hide())

        # Results listbox
        list_frame = ttk.Frame(container, style="Palette.TFrame")
        list_frame.pack(fill="both", expand=True)

        self.listbox = tk.Listbox(
            list_frame,
            bg=theme.bg_sunken,
            fg=theme.fg,
            selectbackground=theme.accent,
            selectforeground=theme.fg_inverse,
            font=("TkDefaultFont", 10),
            relief="flat",
            borderwidth=0,
            highlightthickness=0,
            activestyle="none",
            exportselection=False,
        )
        self.listbox.pack(fill="both", expand=True)
        self.listbox.bind("<Double-Button-1>", lambda e: self._execute_selected())
        self.listbox.bind("<ButtonRelease-1>", lambda e: self._execute_selected())

        self.search_var.trace_add("write", lambda *_: self._filter())

        self.bind("<FocusOut>", lambda e: self.after(100, self._check_focus))

    def _filter(self) -> None:
        query = self.search_var.get().lower()
        if not query:
            self._filtered = self._commands
        else:
            self._filtered = [
                c for c in self._commands
                if query in c[1].lower() or query in c[0].lower() or query in c[3].lower()
            ]
        self._refresh_list()
        self._selected_idx = 0
        self._update_selection()

    def _refresh_list(self) -> None:
        self.listbox.delete(0, tk.END)
        for cat, label, _, shortcut, _ in self._filtered:
            display = f"{label}"
            if cat:
                display = f"[{cat}] {label}"
            if shortcut:
                display += f"  ⌘{shortcut}"  # Use ⌘ for Mac-style, Ctrl for others
            self.listbox.insert(tk.END, display)

    def _update_selection(self) -> None:
        self.listbox.selection_clear(0, tk.END)
        if 0 <= self._selected_idx < self.listbox.size():
            self.listbox.selection_set(self._selected_idx)
            self.listbox.see(self._selected_idx)

    def _on_search(self, _event: tk.Event | None = None) -> None:
        self._filter()

    def _on_down(self, _event: tk.Event) -> None:
        if self._selected_idx < self.listbox.size() - 1:
            self._selected_idx += 1
            self._update_selection()

    def _on_up(self, _event: tk.Event) -> None:
        if self._selected_idx > 0:
            self._selected_idx -= 1
            self._update_selection()

    def _on_enter(self, _event: tk.Event) -> None:
        self._execute_selected()

    def _execute_selected(self) -> None:
        if 0 <= self._selected_idx < len(self._filtered):
            _, _, cmd, _, _ = self._filtered[self._selected_idx]
            self.hide()
            cmd()

    def _check_focus(self) -> None:
        if not self.focus_get() or self.focus_get() == self:
            self.hide()

    def show(self, anchor_widget: tk.Widget | None = None) -> None:
        """Show palette centered on screen or near anchor widget."""
        self.deiconify()
        self.search_var.set("")
        self._filter()
        self._selected_idx = 0
        self._update_selection()

        # Position near top-center of parent
        self.update_idletasks()
        w = 600
        h = 400
        if anchor_widget:
            x = anchor_widget.winfo_rootx() + anchor_widget.winfo_width() // 2 - w // 2
            y = anchor_widget.winfo_rooty() + anchor_widget.winfo_height() + 8
        else:
            x = self.master.winfo_rootx() + self.master.winfo_width() // 2 - w // 2
            y = self.master.winfo_rooty() + 80
        self.geometry(f"{w}x{h}+{x}+{y}")
        self.search_entry.focus_set()

    def hide(self) -> None:
        self.withdraw()


def setup_menubar_styles(style: ttk.Style) -> None:
    """Configure menubar styles."""
    theme = get_theme()

    style.configure(
        "Menubar.TFrame",
        background=theme.bg,
        relief="flat",
        borderwidth=0,
    )
    style.configure(
        "Menubar.TMenubutton",
        background=theme.bg,
        foreground=theme.fg,
        relief="flat",
        borderwidth=0,
        bordercolor=theme.bg,
        lightcolor=theme.bg,
        darkcolor=theme.bg,
        focuscolor=theme.accent,
        font=("TkDefaultFont", 10),
        padding=(14, 6),
        anchor="w",
    )
    style.map(
        "Menubar.TMenubutton",
        background=[("active", theme.bg_hover), ("pressed", theme.bg_active), ("disabled", theme.bg)],
        foreground=[("disabled", theme.fg_subtle), ("active", theme.fg)],
        bordercolor=[("active", theme.bg_hover), ("pressed", theme.bg_active)],
        lightcolor=[("active", theme.bg_hover), ("pressed", theme.bg_active)],
        darkcolor=[("active", theme.bg_hover), ("pressed", theme.bg_active)],
    )

    style.configure(
        "MenubarDivider.TFrame",
        background=theme.border_subtle,
        relief="flat",
        borderwidth=0,
    )

    # Command palette styles
    style.configure(
        "Palette.TFrame",
        background=theme.bg_raised,
        relief="flat",
        borderwidth=1,
        bordercolor=theme.border,
    )
    style.configure(
        "Palette.TEntry",
        fieldbackground=theme.bg_sunken,
        foreground=theme.fg,
        bordercolor=theme.border,
        lightcolor=theme.border_focus,
        darkcolor=theme.border_focus,
        borderwidth=1,
        padding=(10, 8),
    )


def setup_menubar_styles(style: ttk.Style) -> None:
    """Configure menubar styles using current theme."""
    theme = get_theme()

    style.configure(
        "Menubar.TFrame",
        background=theme.bg,
        relief="flat",
        borderwidth=0,
    )
    style.configure(
        "Menubar.TMenubutton",
        background=theme.bg,
        foreground=theme.fg,
        relief="flat",
        borderwidth=0,
        bordercolor=theme.bg,
        lightcolor=theme.bg,
        darkcolor=theme.bg,
        focuscolor=theme.accent,
        font=("TkDefaultFont", 10),
        padding=(14, 6),
        anchor="w",
    )
    style.map(
        "Menubar.TMenubutton",
        background=[("active", theme.bg_hover), ("pressed", theme.bg_active), ("disabled", theme.bg)],
        foreground=[("disabled", theme.fg_subtle), ("active", theme.fg)],
        bordercolor=[("active", theme.bg_hover), ("pressed", theme.bg_active)],
        lightcolor=[("active", theme.bg_hover), ("pressed", theme.bg_active)],
        darkcolor=[("active", theme.bg_hover), ("pressed", theme.bg_active)],
    )

    style.configure(
        "MenubarDivider.TFrame",
        background=theme.border_subtle,
        relief="flat",
        borderwidth=0,
    )

    style.configure(
        "Palette.TFrame",
        background=theme.bg_raised,
        relief="flat",
        borderwidth=1,
        bordercolor=theme.border,
    )
    style.configure(
        "Palette.TEntry",
        fieldbackground=theme.bg_sunken,
        foreground=theme.fg,
        bordercolor=theme.border,
        lightcolor=theme.border_focus,
        darkcolor=theme.border_focus,
        borderwidth=1,
        padding=(10, 8),
    )

    def add_menu(self, label: str, gap_before: int = 0) -> _Submenu:
        """Tambah satu tombol menu + dropdown-nya, Return pembungkus dropdown.

        `ttk.Menubutton` sudah punya binding bawaan untuk membuka dropdown
        pada posisi yang tepat, jadi kita tidak perlu memasang command sendiri.

        `gap_before` menambah jarak di sebelah kiri tombol — dipakai untuk
        memisahkan menu terakhir (mis. Bantuan) dari kelompok lain.
        """
        holder = ttk.Frame(self._row, style="Menubar.TFrame")
        holder.grid(row=0, column=self._columns, sticky="w",
                    padx=(gap_before if self._columns else 0, 0))
        self._columns += 1

        button = ttk.Menubutton(holder, text=label, width=0, style="Menubar.TMenubutton")
        button.pack(side="left", fill="y")

        theme = get_theme()

        menu = tk.Menu(
            self,
            tearoff=0,
            bg=theme.bg_raised,
            fg=theme.fg,
            activebackground=theme.accent,
            activeforeground=theme.fg_inverse,
            activeborderwidth=0,
            borderwidth=0,
            font=DROP_FONT,
        )
        button.configure(menu=menu)
        return _Submenu(menu)


def menubar_divider(master: tk.Misc) -> ttk.Frame:
    """Garis tipis pemisah antara bar menu dan isi jendela.

    Dipaket dengan `side="top"` tepat setelah bar menu dibuat, supaya garisnya
    muncul di bawahnya — bukan menempel di tepi bawah jendela.
    """
    line = ttk.Frame(master, style="MenubarDivider.TFrame", height=1)
    line.pack(fill="x", side="top")
    return line
