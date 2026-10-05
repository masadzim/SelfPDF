"""Kotak hasil dan bantuan membuka folder.

Dulu hasil setiap proses ditampilkan lewat `messagebox`. Popup seperti itu
menutupi jendela utama, dan kalau muncul dari dalam dialog yang punya `grab`,
dialog pilih berkas justru tersembunyi di belakangnya — sumber keluhan "dialog
popup ketimpa".

Kotak hasil sekarang jadi widget biasa di panel samping: pesan, daftar berkas,
dan tombol untuk membuka folder tujuan. Tidak ada popup sama sekali.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tkinter as tk
from tkinter import ttk
from typing import Sequence

from .app_colors import FG, FG_DIM, OK, WARN

ERROR = "#ff7b72"

_TONES = {"info": FG, "ok": OK, "warn": WARN, "error": ERROR}


def reveal_path(path: str) -> bool:
    """Buka folder berisi `path` lewat aplikasi bawaan OS."""
    if not path:
        return False
    folder = path if os.path.isdir(path) else os.path.dirname(os.path.abspath(path))
    if not os.path.isdir(folder):
        return False
    try:
        if sys.platform.startswith("win"):
            command = ["explorer", folder]
        elif sys.platform == "darwin":
            command = ["open", folder]
        else:
            command = ["xdg-open", folder]
        subprocess.Popen(
            command,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        return True
    except Exception:
        return False


class ResultView(ttk.Frame):
    """Kotak hasil yang bisa digulir: judul + isi + tombol buka folder."""

    def __init__(self, master: tk.Misc, height: int = 6) -> None:
        super().__init__(master, style="Panel.TFrame")
        self.columnconfigure(0, weight=1)
        self._outputs: list[str] = []

        self.text = tk.Text(
            self,
            height=height,
            wrap="word",
            bg="#161a21",
            fg=FG,
            insertbackground=FG,
            relief="flat",
            highlightthickness=1,
            highlightbackground="#3a4250",
            font=("TkFixedFont", 9),
            padx=8,
            pady=6,
        )
        self.text.grid(row=0, column=0, sticky="nsew")
        self.text.configure(state="disabled")

        self.open_button = ttk.Button(
            self, text="Buka Folder Hasil", width=0, style="Panel.TButton",
            command=self._open
        )

    def _open(self) -> None:
        for path in self._outputs:
            if reveal_path(path):
                return

    def clear(self) -> None:
        self._outputs = []
        self.grid_remove()
        self._write("", "")

    def show(self, headline: str, body: str = "", tone: str = "info",
             outputs: Sequence[str] = ()) -> None:
        """Tampilkan hasil. `headline` tebal, `body` di bawahnya."""
        self._outputs = list(outputs)
        self._write(headline, body, tone)
        # Kotak hasil disembunyikan sampai ada isi supaya tidak memakan ruang
        # panel kosong; begitu ada pesan, baris ini menampilkannya lagi.
        self.grid()
        if self._outputs:
            self.open_button.grid(row=1, column=0, sticky="w", pady=(6, 0))
        else:
            self.open_button.grid_remove()

    def _write(self, headline: str, body: str, tone: str = "info") -> None:
        color = _TONES.get(tone, FG)
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        if headline:
            self.text.insert("1.0", headline)
            self.text.tag_add("head", "1.0", "1.0 + %d chars" % len(headline))
            self.text.tag_configure("head", foreground=color, font=("TkDefaultFont", 9, "bold"))
        if body:
            self.text.insert("end", "\n" + body)
        if not headline and not body:
            self.text.insert("1.0", "—")
            self.text.tag_configure("head", foreground=FG_DIM, font=("TkFixedFont", 9))
            self.text.tag_add("head", "1.0", "end")
        self.text.see("1.0")
        self.text.configure(state="disabled")
