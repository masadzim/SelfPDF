"""Menubar yang menyatu dengan jendela.

Kenapa tidak pakai `tk.Menu` sebagai menubar? Pada X11/Xwayland menubar native
menerjemahkan diri menjadi *X window terpisah*. Window terpisah itu punya
latar sendiri, sehingga saat jendela digambar ulang (resize, buka dialog,
redraw thumbnail) area menubar sempat terisi warna tak terdefinisi dan
berkedip hitam. Dropdown di sini dibuat sebagai `tk.Menu` biasa yang hanya
ditempelkan sewaktu dibuka, sehingga tidak ada window menubar yang menetap.

Konsekuensinya: menubar ikut ter-gambar bersama jendela, tidak bisa flicker.

Tata letaknya sengaja **natural width**: setiap tombol selebar labelnya sendiri,
tidak semuanya disamakan dengan label terpanjang (ala VS Code). Meluruskan
tombol ke lebar maksimum itulah yang membuat bar menu terlihat renggang.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from .app_colors import ACCENT, BG, BG_PANEL, FG, FG_DIM

# Tinggi tetap semua tombol menu supaya barisan rata tanpa harus menebak.
MENU_HEIGHT = 30
# Jarak tambahan sebelum menu terakhir supaya tidak menempel dengan yang lain.
TRAILING_GAP = 18

DROP_FONT = ("TkDefaultFont", 10)


def setup_menubar_styles(style: ttk.Style) -> None:
    """Style untuk bar menu (dipanggil sekali dari app)."""
    style.configure(
        "Menubar.TFrame",
        background=BG,
        relief="flat",
        borderwidth=0,
    )
    style.configure(
        "Menubar.TMenubutton",
        background=BG,
        foreground=FG,
        relief="flat",
        borderwidth=0,
        bordercolor=BG,
        lightcolor=BG,
        darkcolor=BG,
        focuscolor=BG,
        font=("TkDefaultFont", 10),
        padding=(13, 4),
        anchor="w",
    )
    style.map(
        "Menubar.TMenubutton",
        background=[("active", BG_PANEL), ("pressed", BG_PANEL)],
        foreground=[("disabled", "#5a6270"), ("active", "#ffffff")],
        bordercolor=[("active", BG_PANEL), ("pressed", BG_PANEL)],
        lightcolor=[("active", BG_PANEL), ("pressed", BG_PANEL)],
        darkcolor=[("active", BG_PANEL), ("pressed", BG_PANEL)],
    )

    # Garis pemisah setebal 1 px di bawah bar menu supaya tidak menyatu dengan
    # isi jendela.
    style.configure(
        "MenubarDivider.TFrame",
        background="#2f3542",
        relief="flat",
        borderwidth=0,
    )


class _Submenu:
    """Pembungkus tipis untuk mengisi satu dropdown."""

    def __init__(self, menu: tk.Menu) -> None:
        self._menu = menu

    def add_command(self, label: str, command) -> "_Submenu":
        def run() -> None:
            # Tutup dulu supaya menu tidak menggantung bila command lambat
            # (mis. menjalankan OCR atau tool PDF).
            try:
                self._menu.unpost()
            except tk.TclError:
                pass
            command()

        self._menu.add_command(
            label=label,
            command=run,
            background=BG_PANEL,
            foreground=FG,
            activebackground=ACCENT,
            activeforeground="#ffffff",
        )
        return self

    def add_separator(self) -> "_Submenu":
        # Separator tidak menerima opsi warna aktif.
        self._menu.add_separator(background=BG_PANEL)
        return self


class MenuBar(ttk.Frame):
    """Bar menu berisi `ttk.Menubutton`, bukan menubar native."""

    def __init__(self, master: tk.Misc) -> None:
        super().__init__(master, style="Menubar.TFrame")
        self._columns = 0
        self._row = ttk.Frame(self, style="Menubar.TFrame", height=MENU_HEIGHT)
        self._row.pack(fill="x")
        # Tinggi dikunci supaya semua tombol menu satu baris, apa pun panjangnya
        # label masing-masing.
        self._row.pack_propagate(False)

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

        menu = tk.Menu(
            self,
            tearoff=0,
            bg=BG_PANEL,
            fg=FG,
            activebackground=ACCENT,
            activeforeground="#ffffff",
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
