"""Baris atas jendela: identitas aplikasi di kiri, tombol aksi utama di kanan.

Kenapa modul ini terpisah? Karena penyusunannya menentukan *keserataan* logo
dengan teks nama. Kesalahan yang pernah terjadi: logo diberi `rowspan=2` sedang
teks nama hanya menempati baris pertama, sehingga keduanya terpusat pada sumbu
vertikal yang berbeda dan logo terlihat meleset ke bawah.

Di sini logo, nama, dan tagline diletakkan pada **satu baris grid yang sama**
tanpa `rowspan`, jadi Tk memusatkan semuanya terhadap satu sumbu yang sama.
Semua tombol juga sebaris, sehingga tidak ada lagi dua baris tombol yang
bertumpuk.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Callable, Optional, Sequence

from .branding import (
    APP_NAME,
    APP_TAGLINE,
    SHOW_NAME_WITH_LOGO,
    find_logo,
    find_wordmark,
    load_logo,
    load_wordmark,
)

# (label, command, style)
Action = tuple[str, Callable[[], None], str]


class HeaderBar(ttk.Frame):
    """Baris atas: logo + nama (kiri), tombol aksi utama (kanan)."""

    def __init__(self, master: tk.Misc, actions: Sequence[Action] = (),
                 tagline: Optional[str] = APP_TAGLINE) -> None:
        super().__init__(master, style="App.TFrame", padding=(14, 9, 14, 9))

        self.brand = ttk.Frame(self, style="App.TFrame")

        # --- identitas -----------------------------------------------------
        self.logo_photo: Optional[tk.PhotoImage] = None
        self.uses_wordmark = False

        wordmark_path = find_wordmark()
        logo_path = find_logo()

        # Wordmark sudah memuat nama, jadi logo bujur sangkar diabaikan dan
        # teks nama tidak digambar supaya nama tidak tampil dua kali.
        if wordmark_path:
            self.logo_photo = load_wordmark(self, wordmark_path)
            self.uses_wordmark = self.logo_photo is not None

        if self.logo_photo is not None:
            label = ttk.Label(self.brand, image=self.logo_photo, style="App.TLabel")
            label.image = self.logo_photo  # type: ignore[attr-defined]
            # `anchor="n"`: logo menempel pada baris **nama**, bukan ke tengah
            # blok dua baris. Kalau dibiarkan `center`, pack akan menengahkan
            # logo pada keseluruhan blok (nama + tagline) sehingga logo
            # terlihat meleset ke bawah dari tulisan nama.
            label.pack(side="left", anchor="n", padx=(0, 10))
        elif logo_path:
            self.logo_photo = load_logo(self, logo_path)
            if self.logo_photo is not None:
                label = ttk.Label(self.brand, image=self.logo_photo, style="App.TLabel")
                label.image = self.logo_photo  # type: ignore[attr-defined]
                label.pack(side="left", anchor="n", padx=(0, 10))

        show_name = self.logo_photo is None or (SHOW_NAME_WITH_LOGO and not self.uses_wordmark)

        if show_name:
            texts = ttk.Frame(self.brand, style="App.TFrame")
            texts.pack(side="left", anchor="n")
            ttk.Label(texts, text=APP_NAME, style="Title.TLabel").pack(anchor="w")
            if tagline:
                ttk.Label(texts, text=tagline, style="HeaderTag.TLabel").pack(anchor="w")

        # --- tombol aksi ---------------------------------------------------
        # Tombol dipasang lebih dulu dari sisi kanan supaya ruang kosong
        # tersisa menjadi milik blok identitas di kiri.
        self.action_buttons: list[ttk.Button] = []
        for label_text, command, style in actions:
            button = ttk.Button(self, text=label_text, width=0, command=command, style=style)
            button.pack(side="right", padx=(6, 0))
            self.action_buttons.append(button)

        # Identitas mengisi sisa ruang; logo, nama, dan tagline ada di dalam
        # satu baris sehingga semuanya terpusat pada satu sumbu vertikal.
        self.brand.pack(side="left", fill="y")
