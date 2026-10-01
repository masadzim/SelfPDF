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

        Skala dihitung dari tinggi halaman sehingga hasilnya persis `height`
        piksel, lalu rotasi diterapkan pada gambar. Halaman yang diputar
        90/270 menjadi lanskap sehingga lebarnya otomatis menyesuaikan.
        """
        total_rotation = (base_rotation + rotation) % 360
        page_height = page.rect.height or 1.0
        scale = height / page_height

        pixmap = page.get_pixmap(matrix=pymupdf.Matrix(scale, scale), alpha=False)
        image = Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples)

        if total_rotation:
            image = image.rotate(-total_rotation, expand=True, fillcolor="#ffffff")
        return image

    def get_page(
        self,
        page: pymupdf.Page,
        doc_key: str,
        src_index: int,
        rotation: int,
        base_rotation: int,
        height: int,
    ) -> ImageTk.PhotoImage:
        key = (doc_key, src_index, rotation, base_rotation, height)
        cached = self._cache.get(key)
        if cached is not None:
            return cached

        image = self.render(page, rotation, base_rotation, height)
        photo = ImageTk.PhotoImage(image, master=tk._default_root)
        photo._source_image = image  # type: ignore[attr-defined]

        if len(self._cache) >= self._max:
            self._cache.clear()
        self._cache[key] = photo
        return photo

    def width_of(self, photo: ImageTk.PhotoImage) -> int:
        return photo.width()