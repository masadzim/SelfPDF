"""Model dokumen, penggabungan PDF, dan penulisan lapisan teks OCR."""

from __future__ import annotations

import os
from dataclasses import dataclass, field

import pymupdf

from .ocr import DEFAULT_LANG, OcrWord, check_available, group_lines, words_to_text

OCR_DPI = 300

SAVE_SEARCHABLE = "searchable"
SAVE_IMAGE = "image"
SAVE_RAW = "raw"

SAVE_LABELS = {
    SAVE_SEARCHABLE: "Searchable PDF (teks tak terlihat + bisa dicari)",
    SAVE_IMAGE: "Image-only PDF (rata, ukuran besar)",
    SAVE_RAW: "Original (tanpa teks OCR)",
}

HELVETICA = pymupdf.Font("helv")


@dataclass
class PageRef:
    """Satu halaman dalam urutan akhir dokumen."""

    doc_key: str
    src_index: int
    rotation: int = 0
    words: list[OcrWord] | None = None
    ocr_dpi: int = OCR_DPI

    @property
    def is_ocr_done(self) -> bool:
        return self.words is not None


@dataclass
class SourceDoc:
    key: str
    path: str
    doc: pymupdf.Document = field(repr=False)

    @property
    def label(self) -> str:
        return os.path.basename(self.path)


class Project:
    """Kumpulan dokumen sumber + urutan halaman hasil urutan visual user."""

    def __init__(self) -> None:
        self.sources: dict[str, SourceDoc] = {}
        self.pages: list[PageRef] = []
        self._counter = 0

    # ------------------------------------------------------------------ load

    def add_files(self, paths: list[str]) -> tuple[int, list[str]]:
        """Tambahkan PDF ke akhir daftar. Balikan: (jumlah halaman, pesan galat)."""
        added = 0
        errors: list[str] = []
        for path in paths:
            try:
                doc = pymupdf.open(path)
                if doc.page_count == 0:
                    doc.close()
                    errors.append(f"{os.path.basename(path)}: tidak ada halaman")
                    continue
            except Exception as exc:
                errors.append(f"{os.path.basename(path)}: {exc}")
                continue

            self._counter += 1
            key = f"d{self._counter}"
            self.sources[key] = SourceDoc(key, path, doc)
            for index in range(doc.page_count):
                self.pages.append(PageRef(doc_key=key, src_index=index))
            added += doc.page_count

        return added, errors

    def close(self) -> None:
        for source in self.sources.values():
            try:
                source.doc.close()
            except Exception:
                pass
        self.sources.clear()
        self.pages.clear()

    # -------------------------------------------------------------- urutan

    def move(self, old_index: int, new_index: int) -> None:
        if old_index == new_index:
            return
        if not (0 <= old_index < len(self.pages) and 0 <= new_index < len(self.pages)):
            return
        page = self.pages.pop(old_index)
        self.pages.insert(new_index, page)

    def remove(self, index: int) -> None:
        if 0 <= index < len(self.pages):
            del self.pages[index]
        self._prune_sources()

    def remove_many(self, indices: list[int]) -> None:
        doomed = {i for i in indices if 0 <= i < len(self.pages)}
        self.pages = [p for i, p in enumerate(self.pages) if i not in doomed]
        self._prune_sources()

    def duplicate(self, index: int) -> None:
        if not (0 <= index < len(self.pages)):
            return
        original = self.pages[index]
        copy = PageRef(
            doc_key=original.doc_key,
            src_index=original.src_index,
            rotation=original.rotation,
            words=list(original.words) if original.words is not None else None,
            ocr_dpi=original.ocr_dpi,
        )
        self.pages.insert(index + 1, copy)

    def rotate(self, index: int, delta: int) -> None:
        if 0 <= index < len(self.pages):
            self.pages[index].rotation = (self.pages[index].rotation + delta) % 360

    def _prune_sources(self) -> None:
        used = {p.doc_key for p in self.pages}
        for key in list(self.sources):
            if key not in used:
                try:
                    self.sources[key].doc.close()
                except Exception:
                    pass
                del self.sources[key]

    # ----------------------------------------------------------------- view

    def source_label(self, index: int) -> str:
        if 0 <= index < len(self.pages):
            return self.sources[self.pages[index].doc_key].label
        return ""

    def page_at(self, index: int) -> pymupdf.Page:
        """Halaman sumber PyMuPDF untuk index saat ini (untuk render/OCR)."""
        ref = self.pages[index]
        return self.sources[ref.doc_key].doc[ref.src_index]

    def effective_rotation(self, index: int) -> int:
        """Rotasi final = rotasi asli dokumen + rotasi pilihan user."""
        if not (0 <= index < len(self.pages)):
            return 0
        ref = self.pages[index]
        source_page = self.sources[ref.doc_key].doc[ref.src_index]
        return (source_page.rotation + ref.rotation) % 360

    def search_text(self, query: str, limit: int = 200) -> list[tuple[int, str]]:
        """Cari di teks OCR, hasil: [(index halaman, potongan baris), ...]."""
        needle = query.strip().lower()
        if not needle:
            return []
        hits: list[tuple[int, str]] = []
        for index, ref in enumerate(self.pages):
            if not ref.words:
                continue
            for line in group_lines(ref.words):
                text = " ".join(w.text for w in line)
                if needle in text.lower():
                    hits.append((index, text))
                    if len(hits) >= limit:
                        return hits
        return hits

    def page_text(self, index: int) -> str:
        if 0 <= index < len(self.pages):
            ref = self.pages[index]
            if ref.words:
                return words_to_text(ref.words)
        return ""

    # ---------------------------------------------------------------- build

    def build(self, mode: str = SAVE_SEARCHABLE) -> pymupdf.Document:
        """Rakit dokumen sesuai urutan saat ini."""
        out = pymupdf.open()
        if not self.pages:
            return out

        if mode == SAVE_IMAGE:
            return self._build_rasterised()

        for ref in self.pages:
            source = self.sources[ref.doc_key].doc
            out.insert_pdf(source, from_page=ref.src_index, to_page=ref.src_index)
            page = out[-1]

            # Teks OCR disisipkan lebih dulu (koordinat mengikuti orientasi
            # asli hasil render), rotasi baru diterapkan setelahnya agar
            # teks ikut ikut terputar bersama halaman.
            if mode == SAVE_SEARCHABLE and ref.words:
                apply_text_layer(page, ref.words, ref.ocr_dpi)

            total = (page.rotation + ref.rotation) % 360
            if total:
                page.set_rotation(total)

        return out

    def _build_rasterised(self) -> pymupdf.Document:
        out = pymupdf.open()
        for ref in self.pages:
            source = self.sources[ref.doc_key].doc[ref.src_index]
            pixmap = source.get_pixmap(dpi=150, alpha=False)
            new_page = out.new_page(width=pixmap.width, height=pixmap.height)
            new_page.insert_image(new_page.rect, pixmap=pixmap)
            if ref.rotation:
                new_page.set_rotation(ref.rotation)
        return out

    def save(self, path: str, mode: str = SAVE_SEARCHABLE) -> None:
        doc = self.build(mode)
        try:
            if mode == SAVE_IMAGE:
                doc.save(path, deflate=True, deflate_images=True)
            else:
                doc.save(path, garbage=4, deflate=True, clean=True)
        finally:
            doc.close()


def apply_text_layer(
    page: pymupdf.Page,
    words: list[OcrWord],
    dpi: int = OCR_DPI,
    overlay: bool = True,
) -> None:
    """Tulis ulang kata OCR sebagai teks tak terlihat (render_mode 3).

    Kata ditulis per baris agar jumlah panggilan rendah; teksnya dipecah
    dengan spasi sehingga penempatan tetap mengikuti kotak kata asli.
    """
    if not words:
        return

    scale = 72.0 / dpi
    writer = pymupdf.TextWriter(page.rect)

    for line in group_lines(words):
        boxes = [w for w in line]
        if not boxes:
            continue
        top = min(w.y0 for w in boxes) * scale
        bottom = max(w.y1 for w in boxes) * scale
        left = min(w.x0 for w in boxes) * scale
        fontsize = max(1.0, (bottom - top) * 0.82)
        text = " ".join(w.text for w in boxes)
        try:
            writer.append((left, bottom), text, font=HELVETICA, fontsize=fontsize)
        except Exception:
            continue

    writer.write_text(page, render_mode=3, overlay=overlay)


def check_ocr_ready(lang: str = DEFAULT_LANG) -> str:
    return check_available(lang)