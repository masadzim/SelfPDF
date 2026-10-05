"""Cache thumbnail halaman.

Thumbnail di-cache berdasarkan identitas halaman yang stabil
(doc_key + src_index), bukan berdasarkan posisinya di grid, sehingga tetap
benar setelah pengguna mengurutkan ulang halaman.
"""

from __future__ import annotations

import tkinter as tk

import pymupdf
from PIL import Image, ImageTk

THUMB_DPI = 72


class ThumbCache:
    """Menyimpan thumbnail siap pakai untuk widget Tk."""

    def __init__(self, max_entries: int = 600) -> None:
        self._cache: dict[tuple, ImageTk.PhotoImage] = {}
        self._max = max_entries

    def clear(self) -> None:
        self._cache.clear()

    def drop_source(self, doc_key: str) -> None:
        for key in [k for k in self._cache if k[0] == doc_key]:
            del self._cache[key]

    @staticmethod
    def render(
        page: pymupdf.Page,
        rotation: int,
        base_rotation: int,
        height: int,
    ) -> Image.Image:
        """Render satu halaman menjadi thumbnail setinggi `height` piksel.

        `page.get_pixmap()` sudah menerapkan rotasi `/Rotate` milik dokumen
        (dan `page.rect` juga sudah memantulkannya), sehingga **hanya** rotasi
        pilihan user yang perlu dirotasi lagi di atas gambar. `base_rotation`
        sengaja tidak dipakai di sini — menghitungnya lagi akan memutar
        thumbnail dua kali dan membuat halaman ber-/Rotate 90 tampil portrait.
        """
        page_height = page.rect.height or 1.0
        scale = height / page_height

        pixmap = page.get_pixmap(matrix=pymupdf.Matrix(scale, scale), alpha=False)
        image = Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples)

        if rotation:
            image = image.rotate(-rotation, expand=True, fillcolor="#ffffff")
        return image

    def get_page(
        self,
        page: pymupdf.Page,
        doc_key: str,
        src_index: int,
        rotation: int,
        base_rotation: int,
        height: int,
        master: tk.Misc | None = None,
    ) -> ImageTk.PhotoImage:
        key = (doc_key, src_index, rotation, base_rotation, height)
        cached = self._cache.get(key)
        if cached is not None:
            return cached

        image = self.render(page, rotation, base_rotation, height)
        # `master` eksplisit supaya tidak bergantung pada global
        # `tk._default_root`, yang belum tentu ada saat pemanggil bukan GUI utama.
        photo = ImageTk.PhotoImage(image, master=master or tk._default_root)
        photo._source_image = image  # type: ignore[attr-defined]

        # Saat penuh, buang entri tertua (FIFO) satu per satu, bukan
        # `clear()` sekaligus — membersihkan semuanya membuat seluruh
        # thumbnail di-render ulang setiap kali proyek besar di-refresh.
        while len(self._cache) >= self._max and self._cache:
            self._cache.pop(next(iter(self._cache)))
        self._cache[key] = photo
        return photo

    def width_of(self, photo: ImageTk.PhotoImage) -> int:
        return photo.width()