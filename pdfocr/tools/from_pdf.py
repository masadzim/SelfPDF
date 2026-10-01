"""Convert From PDF: JPG, Word, PowerPoint, Excel, PDF/A."""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile

import pymupdf

from .base import (
    INPUT_PDF_MULTI,
    Param,
    Progress,
    ToolError,
    ToolOutcome,
    ToolSpec,
    open_pdf,
    report,
    safe_stem,
    save_pdf,
)

PDFA_PROFILE = "/usr/share/color/icc/ghostscript/srgb.icc"

# Lokasi PDFA_def.ps bawaan Ghostscript (PDF/A butuh file definisi ini;
# ICC saja tidak cukup).
GS_DEF_CANDIDATES = (
    "/usr/share/ghostscript/*/lib/PDFA_def.ps",
    "/usr/local/share/ghostscript/*/lib/PDFA_def.ps",
    "/usr/lib/ghostscript/*/lib/PDFA_def.ps",
)


def _find_gs_pdfa_def() -> str | None:
    import glob

    for pattern in GS_DEF_CANDIDATES:
        hits = sorted(glob.glob(pattern))
        if hits:
            return hits[-1]
    return None


# ------------------------------------------------------------------ pdf to jpg

def pdf_to_images(inputs, params, out_path, progress=None) -> ToolOutcome:
    dpi = int(params.get("dpi", 200))
    fmt = params.get("format", "jpg")
    quality = int(params.get("quality", 90))
    if not (36 <= dpi <= 1200):
        raise ToolError("DPI harus antara 36 dan 1200.")

    doc = open_pdf(inputs[0])
    try:
        # Tool ini multi-output: `out_path` yang diberikan adalah folder tujuan.
        out_dir = params.get("out_dir") or out_path or "."
        os.makedirs(out_dir, exist_ok=True)
        stem = safe_stem(inputs[0])
        total = doc.page_count
        created: list[str] = []

        for number, page in enumerate(doc, start=1):
            pixmap = page.get_pixmap(dpi=dpi, alpha=False)
            if fmt == "png":
                path = os.path.join(out_dir, f"{stem}_hal{number:03d}.png")
                pixmap.save(path)
            else:
                path = os.path.join(out_dir, f"{stem}_hal{number:03d}.jpg")
                pixmap.pil_save(path, format="JPEG", quality=quality, optimize=True)
            created.append(path)
            report(progress, int(number / total * 100), f"Halaman {number}/{total}")

        return ToolOutcome(
            output=f"{len(created)} berkas di {out_dir}",
            summary=f"{total} halaman diubah ke {fmt.upper()} pada {dpi} DPI.",
            items=created,
        )
    finally:
        doc.close()


# ---------------------------------------------------------------- pdf to word

def pdf_to_word(inputs, params, out_path, progress=None) -> ToolOutcome:
    """PDF→DOCX memakai pdf2docx yang menjaga paragraf, tabel, dan gambar."""
    try:
        from pdf2docx import Converter
    except ImportError as exc:  # pragma: no cover
        raise ToolError(
            "pdf2docx belum terpasang.\n    pip install pdf2docx"
        ) from exc

    doc = open_pdf(inputs[0])
    try:
        pages = doc.page_count
    finally:
        doc.close()

    report(progress, 15, "Menganalisis struktur halaman…")
    try:
        converter = Converter(inputs[0])
    except Exception as exc:  # noqa: BLE001
        raise ToolError(f"Gagal membaca PDF: {exc}") from exc

    try:
        report(progress, 40, "Menyusun dokumen Word…")
        converter.convert(out_path, start=0, end=pages - 1)
    except Exception as exc:  # noqa: BLE001
        raise ToolError(f"Konversi ke Word gagal: {exc}") from exc
    finally:
        try:
            converter.close()
        except Exception:
            pass

    report(progress, 100)
    if not os.path.exists(out_path):
        raise ToolError("Berkas DOCX tidak terbentuk.")

    return ToolOutcome(
        output=out_path,
        summary=f"{pages} halaman dikonversi ke Word (DOCX).",
        warnings=["Layout di dalam PDF bisa sangat kompleks; "
                  "hasilnya perlu diperiksa bila dokumennya rumit."],
    )


# ------------------------------------------------------------- pdf to powerpoint

def pdf_to_powerpoint(inputs, params, out_path, progress=None) -> ToolOutcome:
    """Setiap halaman PDF menjadi satu slide berisi gambar penuh.

    Tampilan 100% sama dengan PDF, tetapi teks tidak bisa diedit — PowerPoint
    tidak punya representasi untuk posisi teks persis seperti di PDF.
    """
    try:
        from pptx import Presentation
        from pptx.util import Emu
    except ImportError as exc:  # pragma: no cover
        raise ToolError("python-pptx belum terpasang.\n    pip install python-pptx") from exc

    doc = open_pdf(inputs[0])
    try:
        total = doc.page_count
        presentation = Presentation()
        # Slide kosong dipakai lalu dihapus agar presentasi mulai kosong.
        slide_layout = presentation.slide_layouts[6]

        width_pt, height_pt = doc[0].rect.width, doc[0].rect.height
        presentation.slide_width = Emu(int(width_pt * 12700))
        presentation.slide_height = Emu(int(height_pt * 12700))

        with tempfile.TemporaryDirectory(prefix="pdf2ppt_") as work:
            for number, page in enumerate(doc, start=1):
                png = os.path.join(work, f"s{number:04d}.png")
                page.get_pixmap(dpi=150, alpha=False).save(png)
                slide = presentation.slides.add_slide(slide_layout)
                slide.shapes.add_picture(
                    png, 0, 0, width=presentation.slide_width, height=presentation.slide_height
                )
                report(progress, int(number / total * 100), f"Slide {number}/{total}")

        presentation.save(out_path)
    finally:
        doc.close()

    return ToolOutcome(
        output=out_path,
        summary=f"{total} halaman menjadi {total} slide.",
        warnings=["Setiap slide berisi gambar penuh — teks tidak bisa diedit."],
    )


# ----------------------------------------------------------------- pdf to excel

def pdf_to_excel(inputs, params, out_path, progress=None) -> ToolOutcome:
    """Ekstrak tabel PDF ke Excel memakai pdfplumber."""
    try:
        import pdfplumber
    except ImportError as exc:  # pragma: no cover
        raise ToolError(
            "pdfplumber belum terpasang.\n    pip install pdfplumber"
        ) from exc

    try:
        from openpyxl import Workbook
    except ImportError as exc:  # pragma: no cover
        raise ToolError("openpyxl belum terpasang.\n    pip install openpyxl") from exc

    strategy = params.get("mode") or "lines"
    plumber_settings: dict = {"vertical_strategy": strategy}
    tolerance = str(params.get("text_tolerance", "") or "").strip()
    if tolerance:
        try:
            plumber_settings["text_tolerance"] = float(tolerance)
        except ValueError as exc:
            raise ToolError("Toleransi jarak teks harus berupa angka.") from exc
    if strategy == "text":
        plumber_settings["horizontal_strategy"] = "text"

    report(progress, 10, "Membaca tabel…")
    workbook = Workbook()
    workbook.remove(workbook.active)
    total_tables = 0

    try:
        with pdfplumber.open(inputs[0]) as plumber_pdf:
            pages = len(plumber_pdf.pages)
            for index, page in enumerate(plumber_pdf.pages, start=1):
                try:
                    tables = page.extract_tables(plumber_settings) or []
                except Exception:  # noqa: BLE001
                    tables = []
                for table in tables:
                    if not table:
                        continue
                    sheet = workbook.create_sheet(title=f"Hal{index}")
                    for row in table:
                        sheet.append(["" if cell is None else str(cell) for cell in row])
                    total_tables += 1
                report(progress, int(index / pages * 100), f"Halaman {index}/{pages}")
    except ToolError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise ToolError(f"Gagal membaca tabel: {exc}") from exc

    if total_tables == 0:
        sheet = workbook.create_sheet(title="Teks")
        sheet.append(["Halaman", "Teks"])
        doc = open_pdf(inputs[0])
        try:
            for index, page in enumerate(doc, start=1):
                sheet.append([index, page.get_text().strip()])
        finally:
            doc.close()
        note = "Tidak ada tabel yang terdeteksi; isi sheet 'Teks' berisi teks per halaman."
    else:
        note = f"{total_tables} tabel berhasil diekstrak."

    workbook.save(out_path)
    return ToolOutcome(output=out_path, summary="Konversi ke Excel selesai. " + note)


# ----------------------------------------------------------------- pdf to pdfa

def pdf_to_pdfa(inputs, params, out_path, progress=None) -> ToolOutcome:
    """Konversi ke PDF/A memakai Ghostscript.

    Ghostscript memerlukan file definisi `PDFA_def.ps` (bukan ICC langsung) dan
    pada GS >= 10 SecurityLevel tinggi menolak membaca berkas profil tanpa
    `--permit-file-read`. Berkas def bawaan juga memakai path relatif untuk ICC,
    jadi disalin ke folder sementara dengan path absolut.
    """
    import re

    gs = shutil.which("gs")
    if not gs:
        raise ToolError("Ghostscript tidak terpasang.\n    sudo apt install ghostscript")
    if not os.path.exists(PDFA_PROFILE):
        raise ToolError(
            f"Profil warna Ghostscript tidak ditemukan:\n{PDFA_PROFILE}\n"
            "Install dengan:\n    sudo apt install icc-profiles-free"
        )
    gs_def = _find_gs_pdfa_def()
    if not gs_def:
        raise ToolError(
            "Berkas definisi PDF/A milik Ghostscript tidak ditemukan.\n"
            "Cari manual: PDFA_def.ps di /usr/share/ghostscript/*/lib/"
        )

    flavour = str(params.get("flavour", "2"))

    with open(gs_def, "r", encoding="latin-1") as handle:
        def_text = handle.read()
    # Ganti nama profil relatif dengan path absolut.
    def_text = re.sub(
        r"/ICCProfile\s*\([^)]*\)",
        f"/ICCProfile ({PDFA_PROFILE})",
        def_text,
        count=1,
    )

    report(progress, 20, "Menjalankan Ghostscript…")
    with tempfile.TemporaryDirectory(prefix="pdfa_") as work:
        local_def = os.path.join(work, "PDFA_def.ps")
        with open(local_def, "w", encoding="latin-1") as handle:
            handle.write(def_text)

        cmd = [
            gs,
            "-dPDFA=" + flavour,
            "-dBATCH", "-dNOPAUSE", "-dNOOUTERSAVE",
            "-sColorConversionStrategy=RGB",
            "-sDEVICE=pdfwrite",
            "-dPDFACompatibilityPolicy=1",
            f"-sOutputFile={out_path}",
            f"--permit-file-read={local_def}",
            f"--permit-file-read={PDFA_PROFILE}",
            local_def,
            inputs[0],
        ]
        try:
            proc = subprocess.run(cmd, capture_output=True, timeout=600)
        except subprocess.TimeoutExpired as exc:
            raise ToolError("Ghostscript terlalu lama merespons (timeout).") from exc

    stderr = proc.stderr.decode(errors="replace")
    if proc.returncode != 0 or not os.path.exists(out_path):
        raise ToolError("Konversi PDF/A gagal.\n" + stderr[:800])

    report(progress, 90, "Memvalidasi hasil…")
    doc = open_pdf(out_path)
    try:
        pages = doc.page_count
        xml = doc.get_xml_metadata() or ""
    finally:
        doc.close()

    part = re.search(r"pdfaid:part=[\"']?(\w+)", xml)
    conf = re.search(r"pdfaid:conformance=[\"']?(\w+)", xml)
    if not part:
        raise ToolError(
            "Ghostscript selesai tetapi metadata PDF/A tidak ditemukan.\n" + stderr[:400]
        )

    report(progress, 100)
    return ToolOutcome(
        output=out_path,
        summary=(
            f"{pages} halaman dikonversi ke PDF/A-{part.group(1)}"
            f"{conf.group(1) if conf else ''}."
        ),
    )


# ------------------------------------------------------------------ registry

SPECS: list[ToolSpec] = [
    ToolSpec(
        id="pdf2jpg",
        label="PDF to JPG",
        group="Convert From PDF",
        description="Ubah setiap halaman PDF menjadi gambar.",
        input_kind=INPUT_PDF_MULTI,
        extension="",
        multi_output=True,
        run=pdf_to_images,
        params=(
            Param("format", "Format", "choice", "jpg",
                  choices=("jpg", "png"), labels=("JPG", "PNG")),
            Param("dpi", "DPI", "int", "200"),
            Param("quality", "Kualitas JPG", "int", "90"),
        ),
    ),
    ToolSpec(
        id="pdf2word",
        label="PDF to WORD",
        group="Convert From PDF",
        description="Ubah PDF ke Word (DOCX), menjaga paragraf dan tabel.",
        input_kind=INPUT_PDF_MULTI,
        extension=".docx",
        run=pdf_to_word,
    ),
    ToolSpec(
        id="pdf2ppt",
        label="PDF to POWERPOINT",
        group="Convert From PDF",
        description="Ubah PDF ke PowerPoint — satu gambar penuh per slide.",
        input_kind=INPUT_PDF_MULTI,
        extension=".pptx",
        run=pdf_to_powerpoint,
    ),
    ToolSpec(
        id="pdf2xls",
        label="PDF to EXCEL",
        group="Convert From PDF",
        description="Ekstrak tabel PDF ke Excel.",
        input_kind=INPUT_PDF_MULTI,
        extension=".xlsx",
        run=pdf_to_excel,
        params=(
            Param("mode", "Deteksi tabel", "choice", "lines",
                  choices=("lines", "text"),
                  labels=("Tabel bergaris (lattice)", "Tanpa garis (stream)")),
            Param("text_tolerance", "Toleransi jarak teks", "text", "",
                  help="Kosongkan = bawaan. Naikkan bila kolom tercampur."),
        ),
    ),
    ToolSpec(
        id="pdf2pdfa",
        label="PDF to PDF/A",
        group="Convert From PDF",
        description="Konversi ke standar arsip PDF/A.",
        input_kind=INPUT_PDF_MULTI,
        run=pdf_to_pdfa,
        params=(
            Param("flavour", "Varian PDF/A", "choice", "2",
                  choices=("1", "2", "3"), labels=("PDF/A-1b", "PDF/A-2b", "PDF/A-3b")),
        ),
    ),
]
