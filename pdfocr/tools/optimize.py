"""Optimize PDF: kompres, repair, OCR."""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile

import pymupdf

from ..core import OCR_DPI
from ..ocr import DEFAULT_LANG, check_available, run_ocr
from .base import (
    INPUT_PDF_MULTI,
    Param,
    Progress,
    ToolError,
    ToolOutcome,
    ToolSpec,
    open_pdf,
    report,
    save_pdf,
)

MARGIN = 10.0


# ------------------------------------------------------------------ compress

def compress_pdf(inputs, params, out_path, progress=None) -> ToolOutcome:
    """Kompres dengan render ulang pada DPI lebih rendah.

    Hanya berlaku untuk dokumen hasil scan/gambar. PDF berbasis teks lebih
    baik dikompres dengan `garbage=4, clean=True` tanpa render ulang.
    """
    dpi = int(params.get("dpi", 150))
    quality = int(params.get("quality", 60))
    if not (36 <= dpi <= 1200):
        raise ToolError("DPI harus antara 36 dan 1200.")

    doc = open_pdf(inputs[0])
    try:
        if not doc.is_pdf:
            raise ToolError("Berkas bukan PDF.")

        mode = params.get("mode", "image")
        out = pymupdf.open()
        total = doc.page_count

        if mode == "image":
            for number, page in enumerate(doc, start=1):
                zoom = dpi / 72.0
                pixmap = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), alpha=False)
                rect = page.rect
                target = out.new_page(width=rect.width, height=rect.height)
                target.insert_image(
                    target.rect,
                    stream=pixmap.tobytes("jpeg", jpg_quality=quality),
                )
                report(progress, int(number / total * 100), f"Halaman {number}/{total}")
            save_pdf(out, out_path)
        else:
            # Mode ringan: buang metadata & objek tak terpakai saja.
            out.insert_pdf(doc)
            save_pdf(out, out_path, metadata=False)

        new_bytes = os.path.getsize(out_path)
        original_bytes = os.path.getsize(inputs[0])

        def human(size: int) -> str:
            if size < 1024 * 1024:
                return f"{size / 1024:.0f} KB"
            return f"{size / 1048576:.2f} MB"

        change = (1 - new_bytes / original_bytes) * 100 if original_bytes else 0.0
        if new_bytes >= original_bytes:
            if original_bytes < 100 * 1024:
                note = (
                    f"Ukuran tetap {human(new_bytes)} — berkas ini kecil dan berbasis "
                    "teks, jadi tidak ada yang bisa dikompresi."
                )
            else:
                note = (
                    f"Ukuran tidak berkurang ({human(original_bytes)} → "
                    f"{human(new_bytes)}). Turunkan DPI atau pilih mode ringan."
                )
        else:
            note = (
                f"{human(original_bytes)} → {human(new_bytes)} (hemat {change:.0f}%)."
            )

        return ToolOutcome(output=out_path, summary="Kompresi selesai. " + note)
    finally:
        doc.close()


# -------------------------------------------------------------------- repair

def _gs_rewrite(source: str, out_path: str, preset: str = "prepress") -> tuple[bool, str]:
    """Tulis ulang PDF lewat Ghostscript. Balikan (berhasil, pesan)."""
    gs = shutil.which("gs")
    if not gs:
        return False, "Ghostscript tidak terpasang (sudo apt install ghostscript)."
    cmd = [
        gs,
        "-dBATCH", "-dNOPAUSE", "-dNOOUTERSAVE", "-dQUIET",
        "-dPDFSETTINGS=/" + preset,
        "-sDEVICE=pdfwrite",
        f"-sOutputFile={out_path}",
        f"--permit-file-read={source}",
        source,
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, timeout=600)
    except subprocess.TimeoutExpired:
        return False, "Ghostscript timeout."
    if proc.returncode == 0 and os.path.exists(out_path):
        return True, f"Ghostscript menulis ulang berkas ({preset})."
    return False, proc.stderr.decode(errors="replace")[:400]


def _gs_verify(path: str) -> str:
    """Coba render halaman pertama; pesan status singkat."""
    gs = shutil.which("gs")
    if not gs:
        return "Ghostscript tidak terpasang, verifikasi dilewati."
    try:
        proc = subprocess.run(
            [gs, "-dBATCH", "-dNOPAUSE", "-dQUIET", "-o", os.devnull,
             "-sDEVICE=nullpage", f"--permit-file-read={path}", path],
            capture_output=True, timeout=180,
        )
    except Exception:  # noqa: BLE001
        return "Verifikasi Ghostscript gagal dijalankan."
    if proc.returncode == 0:
        return "Verifikasi Ghostscript: OK."
    return "Ghostscript masih melaporkan masalah pada berkas."


def repair_pdf(inputs, params, out_path, progress=None) -> ToolOutcome:
    """Perbaiki struktur PDF: coba PyMuPDF, lalu Ghostscript sebagai cadangan."""
    notes: list[str] = []
    source = inputs[0]
    repaired_by = "PyMuPDF"

    report(progress, 10, "Mencoba perbaikan internal…")
    try:
        doc = pymupdf.open(source)
    except Exception as exc:  # noqa: BLE001
        doc = None
        notes.append(f"PyMuPDF tidak bisa membuka: {exc}")

    if doc is not None:
        try:
            if doc.is_repaired:
                notes.append("Struktur xref rusak, diperbaiki otomatis.")
            report(progress, 45, "Menulis ulang struktur…")
            clean = pymupdf.open()
            clean.insert_pdf(doc)
            save_pdf(clean, out_path)
        except Exception as exc:  # noqa: BLE001
            notes.append(f"Penulisan ulang PyMuPDF gagal: {exc}")
        finally:
            try:
                doc.close()
            except Exception:
                pass

    if not os.path.exists(out_path) or os.path.getsize(out_path) == 0:
        report(progress, 55, "Mencoba Ghostscript…")
        ok, message = _gs_rewrite(source, out_path)
        if not ok:
            raise ToolError(
                "Berkas rusak berat dan tidak bisa diperbaiki.\n" + message
            )
        repaired_by = "Ghostscript"
        notes.insert(0, "PyMuPDF gagal; Ghostscript dipakai untuk menulis ulang.")

    report(progress, 80, "Memverifikasi hasil…")
    notes.append(_gs_verify(out_path))

    result = pymupdf.open(out_path)
    try:
        total = result.page_count
    finally:
        result.close()

    report(progress, 100)
    return ToolOutcome(
        output=out_path,
        summary=f"Berkas diperbaiki oleh {repaired_by}, {total} halaman.",
        warnings=notes,
    )


# ----------------------------------------------------------------------- ocr

def ocr_pdf(inputs, params, out_path, progress=None) -> ToolOutcome:
    """Tambahkan lapisan teks tak terlihat ke seluruh halaman."""
    lang = params.get("lang", DEFAULT_LANG)
    try:
        check_available(lang)
    except Exception as exc:  # noqa: BLE001
        raise ToolError(str(exc)) from exc

    doc = open_pdf(inputs[0])
    try:
        total = doc.page_count
        words_found = 0
        empty_pages: list[int] = []

        for number, page in enumerate(doc, start=1):
            if page.get_text().strip():
                report(progress, int(number / total * 100), f"Halaman {number}/{total}")
                continue

            words = run_ocr(page, lang=lang, dpi=OCR_DPI)
            words_found += len(words)
            if not words:
                empty_pages.append(number)
            else:
                from ..core import apply_text_layer

                apply_text_layer(page, words, OCR_DPI)

            report(progress, int(number / total * 100), f"Halaman {number}/{total}")

        save_pdf(doc, out_path)

        notes = []
        if empty_pages:
            shown = ", ".join(str(i) for i in empty_pages[:8])
            notes.append(f"{len(empty_pages)} halaman tidak menghasilkan teks: {shown}")
        return ToolOutcome(
            output=out_path,
            summary=f"{total} halaman diproses, {words_found} kata dikenali.",
            warnings=notes,
        )
    finally:
        try:
            doc.close()
        except Exception:
            pass


# ------------------------------------------------------------------ registry

SPECS: list[ToolSpec] = [
    ToolSpec(
        id="compress",
        label="Compress PDF",
        group="Optimize PDF",
        description="Perkecil ukuran PDF dengan menurunkan resolusi gambar.",
        input_kind=INPUT_PDF_MULTI,
        run=compress_pdf,
        params=(
            Param("mode", "Metode", "choice", "image",
                  choices=("image", "light"),
                  labels=("Render ulang (paling kecil, untuk hasil scan)",
                           "Ringan (pertahankan teks & vektor)")),
            Param("dpi", "DPI", "int", "150", help="72–300 untuk hasil scan."),
            Param("quality", "Kualitas JPEG", "int", "60", help="1–95, makin rendah makin kecil."),
        ),
    ),
    ToolSpec(
        id="repair",
        label="Repair PDF",
        group="Optimize PDF",
        description="Perbaiki PDF yang rusak atau tidak bisa dibuka.",
        input_kind=INPUT_PDF_MULTI,
        run=repair_pdf,
    ),
    ToolSpec(
        id="ocr",
        label="OCR PDF",
        group="Optimize PDF",
        description="Tambahkan teks yang bisa dicari ke PDF hasil scan.",
        input_kind=INPUT_PDF_MULTI,
        run=ocr_pdf,
        params=(Param("lang", "Bahasa OCR", "text", DEFAULT_LANG),),
    ),
]
