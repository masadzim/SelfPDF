"""Kerangka bersama untuk seluruh tool PDF.

Setiap tool dideskripsikan sebagai `ToolSpec` (metadata + skema parameter),
lalu dijalankan lewat `run_spec` yang menangani pemanggilan, pelaporan progres,
dan hasil. GUI cukup membangun form dari skema tersebut.
"""

from __future__ import annotations

import os
import traceback
from dataclasses import dataclass, field
from typing import Any, Callable, Sequence

import pymupdf

# Jenis input file yang bisa dipilih tool
INPUT_NONE = "none"          # tidak butuh file (mis. tool internal)
INPUT_PDF = "pdf"            # satu PDF
INPUT_PDF_MULTI = "pdf_multi"  # banyak PDF
INPUT_IMAGE = "image"        # banyak gambar (jpg/png/...)
INPUT_IMAGE_ONE = "image_one"
INPUT_OFFICE = "office"      # docx/pptx/xlsx
INPUT_ANY = "any"

FILE_DIALOG = {
    INPUT_PDF: (("PDF", "*.pdf"),),
    INPUT_PDF_MULTI: (("PDF", "*.pdf"),),
    INPUT_IMAGE: (("Gambar", "*.png *.jpg *.jpeg *.tif *.tiff *.bmp *.webp"),),
    INPUT_IMAGE_ONE: (("Gambar", "*.png *.jpg *.jpeg *.tif *.tiff *.bmp *.webp"),),
    INPUT_OFFICE: (
        ("Word", "*.docx *.doc"),
        ("PowerPoint", "*.pptx *.ppt"),
        ("Excel", "*.xlsx *.xls"),
        ("Semua", "*"),
    ),
    INPUT_ANY: (("Semua", "*"),),
}


class ToolError(Exception):
    """Kegagalan yang layak ditampilkan ke pengguna."""


@dataclass
class Param:
    """Satu field parameter pada dialog tool.

    `choices` berisi nilai internal yang dipakai saat proses, sedangkan
    `labels` (opsional) berisi teks yang ditampilkan ke pengguna.
    """

    key: str
    label: str
    kind: str = "text"  # text | int | float | choice | bool | dir | out
    default: Any = ""
    help: str = ""
    choices: Sequence[str] = field(default_factory=tuple)
    labels: Sequence[str] = field(default_factory=tuple)

    def display_choices(self) -> list[str]:
        return list(self.labels) if self.labels else list(self.choices)

    def internal_value(self, displayed: str) -> Any:
        """Terjemahkan teks yang dilihat pengguna ke nilai internal."""
        if self.kind != "choice" or not self.labels:
            return displayed
        try:
            return self.choices[list(self.labels).index(displayed)]
        except ValueError:
            return self.default

    def parse(self, raw: str) -> Any:
        if self.kind == "int":
            try:
                return int(str(raw).strip())
            except ValueError as exc:
                raise ToolError(f"{self.label} harus berupa bilangan bulat.") from exc
        if self.kind == "float":
            try:
                return float(str(raw).strip())
            except ValueError as exc:
                raise ToolError(f"{self.label} harus berupa angka.") from exc
        if self.kind == "bool":
            return str(raw).strip().lower() in ("1", "true", "ya", "yes", "on")
        return str(raw)


def parse_page_range(text: str, page_count: int) -> list[int]:
    """Ubah "1-3, 5, 8-" menjadi daftar indeks halaman (0-based).

    Rentang kosong seperti "8-" berarti sampai halaman terakhir.
    """
    text = (text or "").strip()
    if not text or text.lower() in ("all", "semua", "*"):
        return list(range(page_count))

    wanted: list[int] = []
    for chunk in text.replace(";", ",").split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        try:
            if "-" in chunk:
                start_s, _, end_s = chunk.partition("-")
                start = int(start_s) if start_s.strip() else 1
                end = int(end_s) if end_s.strip() else page_count
            else:
                start = end = int(chunk)
        except ValueError as exc:
            raise ToolError(
                f"Rentang halaman '{chunk}' tidak valid.\n"
                "Contoh yang benar: 1-3, 5, 8- (kosong = semua halaman)."
            ) from exc
        if start < 1:
            start = 1
        if start > end:
            start, end = end, start
        for page in range(start - 1, min(end, page_count)):
            if page not in wanted:
                wanted.append(page)

    if not wanted:
        raise ToolError(
            f"Rentang halaman '{text}' tidak mencakup halaman 1-{page_count}."
        )
    return wanted


@dataclass
class ToolSpec:
    """Deskripsi satu tool yang bisa dipanggil dari menubar."""

    id: str
    label: str
    group: str
    run: Callable[..., "ToolOutcome"]
    description: str = ""
    input_kind: str = INPUT_PDF
    params: Sequence[Param] = field(default_factory=tuple)
    extension: str = ".pdf"
    multi_output: bool = False
    confirm: str = ""

    def open_dialog_title(self) -> str:
        return f"{self.group} — {self.label}"

    def suggested_name(self, first_input: str) -> str:
        base = os.path.splitext(os.path.basename(first_input))[0]
        return f"{base}_{self.id}{self.extension}"


@dataclass
class ToolOutcome:
    """Hasil satu proses tool."""

    output: str = ""
    summary: str = ""
    warnings: list[str] = field(default_factory=list)
    items: list[str] = field(default_factory=list)

    def message(self) -> str:
        parts = []
        if self.summary:
            parts.append(self.summary)
        if self.output:
            parts.append(f"Output: {self.output}")
        if self.items:
            shown = self.items[:6]
            rest = len(self.items) - len(shown)
            parts.append("Dibuat: " + ", ".join(os.path.basename(i) for i in shown))
            if rest > 0:
                parts.append(f"… dan {rest} berkas lain")
        if self.warnings:
            parts.append("Catatan:\n- " + "\n- ".join(self.warnings))
        return "\n\n".join(parts) if parts else "Selesai."


Progress = Callable[[int, str], None]


def report(progress: Progress | None, percent: int, message: str = "") -> None:
    if progress is not None:
        progress(percent, message)


def open_pdf(path: str) -> pymupdf.Document:
    try:
        return pymupdf.open(path)
    except Exception as exc:
        raise ToolError(f"Gagal membuka {os.path.basename(path)}: {exc}") from exc


def save_pdf(doc: pymupdf.Document, out_path: str, metadata: bool = True) -> str:
    directory = os.path.dirname(os.path.abspath(out_path))
    if directory:
        os.makedirs(directory, exist_ok=True)
    try:
        if metadata:
            doc.save(out_path, garbage=4, deflate=True, clean=True)
        else:
            doc.save(out_path, deflate=True)
    except Exception as exc:
        raise ToolError(f"Gagal menyimpan: {exc}") from exc
    finally:
        doc.close()
    return out_path


def require_inputs(paths: Sequence[str], kind: str) -> list[str]:
    if not paths:
        label = {
            INPUT_PDF: "file PDF",
            INPUT_PDF_MULTI: "file PDF",
            INPUT_IMAGE: "gambar",
            INPUT_IMAGE_ONE: "gambar",
            INPUT_OFFICE: "dokumen Office",
            INPUT_ANY: "berkas",
        }.get(kind, "berkas")
        raise ToolError(f"Pilih {label} terlebih dahulu.")
    return [str(p) for p in paths]


def safe_stem(path: str, fallback: str = "output") -> str:
    stem = os.path.splitext(os.path.basename(path))[0].strip()
    cleaned = "".join(c for c in stem if c not in '\\/:*?"<>|').strip()
    return cleaned or fallback


def collect_widgets(doc: pymupdf.Document) -> tuple[list, list]:
    """Kumpulkan `(halaman, widget)` untuk seluruh field AcroForm.

    `Document.widgets()` dihapus di PyMuPDF 1.28. Selain itu `Page.widgets()`
    adalah generator sehingga objek halaman bisa dibuang sebelum widget dipakai,
    lalu PyMuPDF melempar "Annot is not bound to a page". Karena itu list halaman
    ikut dikembalikan dan HARUS ditahan pemanggil selama widget dipakai.
    """
    pages = [doc[index] for index in range(doc.page_count)]
    widgets = [widget for page in pages for widget in page.widgets()]
    return pages, widgets


def iter_widgets(doc: pymupdf.Document):
    """Hasilkan widget AcroForm (versi streaming; lihat `collect_widgets`)."""
    if hasattr(doc, "widgets"):
        try:
            yield from doc.widgets()
            return
        except (AttributeError, TypeError):
            pass
    for index in range(doc.page_count):
        yield from doc[index].widgets()


def run_spec(spec: ToolSpec, inputs: Sequence[str], params: dict[str, Any], out_path: str,
             progress: Progress | None = None) -> ToolOutcome:
    """Jalankan tool dengan penanganan error yang seragam."""
    try:
        require_inputs(inputs, spec.input_kind)
        return spec.run(list(inputs), params, out_path, progress)
    except ToolError:
        raise
    except pymupdf.FileDataError as exc:
        raise ToolError(
            f"PDF rusak atau terenkripsi: {exc}\n\n"
            "Coba menu Security → Repair PDF terlebih dahulu."
        ) from exc
    except PermissionError as exc:
        raise ToolError(f"Tidak punya izin menulis: {exc}") from exc
    except FileNotFoundError as exc:
        raise ToolError(f"Berkas tidak ditemukan: {exc}") from exc
    except Exception as exc:  # noqa: BLE001
        raise ToolError(f"{type(exc).__name__}: {exc}\n\n{traceback.format_exc(limit=3)}") from exc
