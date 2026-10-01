"""Model dokumen, penggabungan PDF, dan penulisan lapisan teks OCR."""

from __future__ import annotations

import os
from dataclasses import dataclass, field

import pymupdf

from .ocr import DEFAULT_LANG, OcrWord, check_available, group_lines, words_to_text

OCR_DPI = 300

# Halaman gambar disalin pada 72 DPI (1 piksel = 1 poin) agar geometri
# halaman hasil sama persis dengan `page.rect` dokumen gambar pymupdf.
IMAGE_PAGE_DPI = 72

# Jenis berkas yang bisa dimasukkan lewat satu tombol insert. PDF dan gambar
# bisa dirender jadi halaman (jadi thumbnail di preview), sedangkan Office dan
# HTML tidak — keduanya hanya disimpan sebagai daftar berkas.
KIND_PDF = "pdf"
KIND_IMAGE = "image"
KIND_OFFICE = "office"
KIND_HTML = "html"
KIND_OTHER = "other"

KIND_LABELS = {
    KIND_PDF: "PDF",
    KIND_IMAGE: "Gambar",
    KIND_OFFICE: "Office",
    KIND_HTML: "HTML",
    KIND_OTHER: "Berkas",
}

_EXT_KIND = {
    ".pdf": KIND_PDF,
    ".png": KIND_IMAGE, ".jpg": KIND_IMAGE, ".jpeg": KIND_IMAGE,
    ".tif": KIND_IMAGE, ".tiff": KIND_IMAGE, ".bmp": KIND_IMAGE, ".webp": KIND_IMAGE,
    ".doc": KIND_OFFICE, ".docx": KIND_OFFICE,
    ".ppt": KIND_OFFICE, ".pptx": KIND_OFFICE,
    ".xls": KIND_OFFICE, ".xlsx": KIND_OFFICE,
    ".html": KIND_HTML, ".htm": KIND_HTML,
}

# Jenis yang bisa dibuka pymupdf sehingga muncul sebagai halaman di preview.
RENDERABLE_KINDS = (KIND_PDF, KIND_IMAGE)


def kind_of(path: str) -> str:
    """Tentukan jenis berkas dari ekstensinya."""
    return _EXT_KIND.get(os.path.splitext(path)[1].lower(), KIND_OTHER)

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
    kind: str = KIND_PDF

    @property
    def label(self) -> str:
        return os.path.basename(self.path)


class Project:
    """Berkas yang sudah dimasukkan + urutan halaman hasil urutan visual user.

    `files` adalah **sumber tunggal**: semua tool membaca dari sini, jadi satu
    tombol insert berlaku untuk semua pekerjaan. Halaman di `pages` hanya
    turunan dari berkas yang bisa dirender (PDF & gambar); Office/HTML tetap
    ada di `files` tanpa halaman.
    """

    def __init__(self) -> None:
        self.files: list[str] = []
        self.sources: dict[str, SourceDoc] = {}
        self.pages: list[PageRef] = []
        self._counter = 0

    # ------------------------------------------------------------------ load

    def add_files(self, paths: list[str]) -> tuple[int, list[str]]:
        """Tambahkan berkas. Balikan: (jumlah halaman baru, pesan galat).

        PDF dan gambar ikut jadi halaman (muncul sebagai thumbnail di preview).
        Office dan HTML hanya tercatat sebagai berkas; pymupdf tidak bisa
        merendernya sehingga tidak punya halaman.
        """
        added_pages = 0
        errors: list[str] = []

        for path in paths:
            if not os.path.isfile(path):
                errors.append(f"{os.path.basename(path)}: berkas tidak ditemukan")
                continue

            kind = kind_of(path)
            if kind in RENDERABLE_KINDS:
                try:
                    doc = pymupdf.open(path)
                    if doc.page_count == 0:
                        doc.close()
                        errors.append(f"{os.path.basename(path)}: tidak ada halaman")
                        continue
                except Exception as exc:
                    errors.append(f"{os.path.basename(path)}: {exc}")
                    continue

                self.files.append(path)
                self._counter += 1
                key = f"d{self._counter}"
                self.sources[key] = SourceDoc(key, path, doc, kind=kind)
                for index in range(doc.page_count):
                    self.pages.append(PageRef(doc_key=key, src_index=index))
                added_pages += doc.page_count
            else:
                # Tidak bisa dirender, tapi tetap input yang sah untuk tool
                # konversi (WORD/EXCEL/HTML to PDF).
                self.files.append(path)

        return added_pages, errors

    def inputs_for(self, input_kind: str) -> list[str]:
        """Berkas dari `files` yang cocok dengan `input_kind` sebuah tool."""
        if input_kind in ("pdf_multi", "pdf"):
            wanted = (KIND_PDF,)
        elif input_kind in ("image", "image_one"):
            wanted = (KIND_IMAGE,)
        elif input_kind == "office":
            wanted = (KIND_OFFICE,)
        elif input_kind == "any":
            wanted = (KIND_HTML, KIND_OTHER)
        else:
            return []

        return [p for p in self.files if kind_of(p) in wanted]

    def kinds_present(self) -> set[str]:
        return {kind_of(p) for p in self.files}

    def close(self) -> None:
        for source in self.sources.values():
            try:
                source.doc.close()
            except Exception:
                pass
        self.sources.clear()
        self.pages.clear()
        self.files.clear()

    def remove_file(self, path: str) -> None:
        """Keluarkan satu berkas dan semua halamannya dari proyek."""
        if path not in self.files:
            return
        self.files.remove(path)
        doomed = [key for key, src in self.sources.items() if src.path == path]
        self.pages = [p for p in self.pages if p.doc_key not in doomed]
        for key in doomed:
            try:
                self.sources[key].doc.close()
            except Exception:
                pass
            del self.sources[key]

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
            page = self._copy_page(out, ref)

            # Teks OCR disisipkan lebih dulu (koordinat mengikuti orientasi
            # asli hasil render), rotasi baru diterapkan setelahnya agar
            # teks ikut ikut terputar bersama halaman.
            if mode == SAVE_SEARCHABLE and ref.words:
                apply_text_layer(page, ref.words, ref.ocr_dpi)

            total = (page.rotation + ref.rotation) % 360
            if total:
                page.set_rotation(total)

        return out

    def _copy_page(self, out: pymupdf.Document, ref: PageRef) -> pymupdf.Page:
        """Salin satu halaman sumber ke dokumen keluaran, kembalikan halamannya.

        Berkas gambar dibuka pymupdf sebagai dokumen non-PDF, jadi tidak bisa
        disalin lewat `insert_pdf`. Halaman gambar dirender dengan ukuran
        persis `page.rect` sumber (72 DPI = 1 piksel per poin) supaya skala
        yang dipakai `apply_text_layer` — `72 / ocr_dpi` dari koordinat
        render 300 DPI — tetap placing-nya pas di halaman hasil.
        """
        source = self.sources[ref.doc_key].doc
        if source.is_pdf:
            out.insert_pdf(source, from_page=ref.src_index, to_page=ref.src_index)
            return out[-1]

        source_page = source[ref.src_index]
        pixmap = source_page.get_pixmap(dpi=IMAGE_PAGE_DPI, alpha=False)
        page = out.new_page(width=pixmap.width, height=pixmap.height)
        page.insert_image(page.rect, pixmap=pixmap)
        return page

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