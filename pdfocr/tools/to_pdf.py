"""Convert To PDF: gambar, Word, PowerPoint, Excel, HTML."""

from __future__ import annotations

import io
import os
import shutil
import subprocess
import tempfile

import pymupdf
from PIL import Image

from .base import (
    INPUT_ANY,
    INPUT_IMAGE,
    INPUT_OFFICE,
    Param,
    Progress,
    ToolError,
    ToolOutcome,
    ToolSpec,
    report,
    save_pdf,
)

OFFICE_TIMEOUT = 180


def libreoffice_path() -> str:
    path = shutil.which("soffice") or shutil.which("libreoffice")
    if not path:
        raise ToolError(
            "LibreOffice tidak ditemukan.\n"
            "Install dengan:\n    sudo apt install libreoffice-writer libreoffice-calc libreoffice-impress"
        )
    return path


def convert_office(inputs, out_dir, profile=None, progress=None, label="berkas") -> list[str]:
    """Konversi dokumen Office ke PDF lewat LibreOffice headless."""
    exe = libreoffice_path()
    os.makedirs(out_dir, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="lo_profile_") as profile_dir:
        cmd = [
            exe,
            "--headless", "--norestore", "--invisible", "--nolockcheck",
            f"-env:UserInstallation=file://{profile_dir}",
            "--convert-to", _filter_for(inputs),
            "--outdir", out_dir,
            *inputs,
        ]

        report(progress, 20, "Menjalankan LibreOffice…")
        try:
            proc = subprocess.run(cmd, capture_output=True, timeout=OFFICE_TIMEOUT)
        except subprocess.TimeoutExpired as exc:
            raise ToolError("LibreOffice terlalu lama merespons (timeout).") from exc

    created = []
    for path in inputs:
        stem = os.path.splitext(os.path.basename(path))[0]
        produced = os.path.join(out_dir, stem + ".pdf")
        if os.path.exists(produced):
            created.append(produced)

    if not created:
        stderr = proc.stderr.decode(errors="replace")[:400]
        raise ToolError(f"LibreOffice tidak menghasilkan PDF.\n{stderr}")

    return created


def _filter_for(paths: list[str]) -> str:
    """Pilih filter ekspor sesuai jenis dokumen (jika campur, pakai writer)."""
    exts = {os.path.splitext(p)[1].lower() for p in paths}
    if exts <= {".pptx", ".ppt", ".odp"}:
        return "pdf:impress_pdf_Export"
    if exts <= {".xlsx", ".xls", ".ods", ".csv"}:
        return "pdf:calc_pdf_Export"
    return "pdf:writer_pdf_Export"


# ------------------------------------------------------------------- images

def images_to_pdf(inputs, params, out_path, progress=None) -> ToolOutcome:
    dpi = int(params.get("dpi", 200))
    quality = int(params.get("quality", 85))
    page_size = params.get("page_size", "fit")

    out = pymupdf.open()
    total = len(inputs)

    for index, path in enumerate(inputs, start=1):
        try:
            image = Image.open(path)
            image.load()
        except Exception as exc:
            raise ToolError(
                f"Gambar tidak bisa dibaca: {os.path.basename(path)} ({exc})"
            ) from exc
        if image.mode not in ("RGB", "L"):
            image = image.convert("RGB")

        buffer = io.BytesIO()
        image.save(buffer, format="JPEG", quality=quality, optimize=True)
        data = buffer.getvalue()

        if page_size == "a4":
            doc_w, doc_h = 595.28, 841.89
            if image.height > image.width:
                doc_w, doc_h = doc_h, doc_w
            page = out.new_page(width=doc_w, height=doc_h)
            margin = 24.0
            avail_w, avail_h = doc_w - 2 * margin, doc_h - 2 * margin
            scale = min(avail_w / image.width, avail_h / image.height)
            width, height = image.width * scale, image.height * scale
            rect = pymupdf.Rect(
                (doc_w - width) / 2, (doc_h - height) / 2,
                (doc_w + width) / 2, (doc_h + height) / 2,
            )
            page.insert_image(rect, stream=data)
        else:
            page = out.new_page(
                width=image.width * 72.0 / dpi, height=image.height * 72.0 / dpi
            )
            page.insert_image(page.rect, stream=data)

        report(progress, int(index / total * 100), os.path.basename(path))

    save_pdf(out, out_path)
    return ToolOutcome(
        output=out_path, summary=f"{total} gambar dijadikan PDF ({dpi} DPI)."
    )


# ----------------------------------------------------------------- office

def office_to_pdf(inputs, params, out_path, progress=None) -> ToolOutcome:
    """Konversi dokumen Office ke PDF. `out_path` adalah folder tujuan."""
    out_dir = params.get("out_dir") or out_path
    created = convert_office(inputs, out_dir, None, progress, label="Office")
    if not created:
        raise ToolError(
            "LibreOffice tidak menghasilkan PDF.\n"
            "Cek berkas tidak sedang terbuka di aplikasi lain."
        )

    return ToolOutcome(
        output=f"{len(created)} berkas di {out_dir}",
        summary=f"{len(created)} dokumen diubah ke PDF.",
        items=created,
    )


def word_to_pdf(inputs, params, out_path, progress=None):
    return _office(inputs, params, out_path, progress, ".docx,.doc")


def powerpoint_to_pdf(inputs, params, out_path, progress=None):
    return _office(inputs, params, out_path, progress, ".pptx,.ppt,.odp")


def excel_to_pdf(inputs, params, out_path, progress=None):
    return _office(inputs, params, out_path, progress, ".xlsx,.xls,.ods,.csv")


def _office(inputs, params, out_path, progress, extensions) -> ToolOutcome:
    allowed = {e for e in extensions.split(",")}
    for path in inputs:
        if os.path.splitext(path)[1].lower() not in allowed:
            raise ToolError(
                f"{os.path.basename(path)} bukan format yang didukung "
                f"({', '.join(sorted(allowed))})."
            )
    return office_to_pdf(inputs, params, out_path, progress)


# --------------------------------------------------------------------- html

def html_to_pdf(inputs, params, out_path, progress=None) -> ToolOutcome:
    exe = libreoffice_path()
    out_dir = os.path.dirname(os.path.abspath(out_path)) or "."
    os.makedirs(out_dir, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="lo_html_") as work:
        staged: list[str] = []
        for index, path in enumerate(inputs):
            ext = os.path.splitext(path)[1].lower()
            if ext in (".html", ".htm"):
                staged.append(path)
            elif ext in (".txt", ".md", ".markdown"):
                target = os.path.join(work, os.path.splitext(os.path.basename(path))[0] + ".html")
                _markdown_to_html(path, target)
                staged.append(target)
            else:
                raise ToolError(
                    f"{os.path.basename(path)} bukan HTML/teks. "
                    "Simpan halaman web sebagai .html lebih dulu."
                )

        report(progress, 25, "Menjalankan LibreOffice…")
        with tempfile.TemporaryDirectory(prefix="lo_profile_") as profile_dir:
            cmd = [
                exe, "--headless", "--norestore", "--invisible", "--nolockcheck",
                f"-env:UserInstallation=file://{profile_dir}",
                "--convert-to", "pdf:writer_pdf_Export",
                "--outdir", out_dir,
                *staged,
            ]
            try:
                proc = subprocess.run(cmd, capture_output=True, timeout=OFFICE_TIMEOUT)
            except subprocess.TimeoutExpired as exc:
                raise ToolError("LibreOffice terlalu lama merespons (timeout).") from exc

        created = []
        for path in staged:
            produced = os.path.join(
                out_dir, os.path.splitext(os.path.basename(path))[0] + ".pdf"
            )
            if os.path.exists(produced):
                if len(staged) == 1:
                    shutil.move(produced, out_path)
                    produced = out_path
                created.append(produced)

    if not created:
        raise ToolError(f"LibreOffice tidak menghasilkan PDF.\n{proc.stderr.decode(errors='replace')[:300]}")

    return ToolOutcome(
        output=out_path if len(created) == 1 else f"{len(created)} berkas di {out_dir}",
        summary=f"{len(created)} halaman HTML diubah ke PDF.",
        items=created,
    )


def _markdown_to_html(src: str, dst: str) -> None:
    try:
        import markdown as md
    except ImportError:  # pragma: no cover
        import html as html_mod

        text = open(src, encoding="utf-8", errors="replace").read()
        open(dst, "w", encoding="utf-8").write(
            f"<html><body><pre>{html_mod.escape(text)}</pre></body></html>"
        )
        return

    text = open(src, encoding="utf-8", errors="replace").read()
    body = md.markdown(text, extensions=["tables", "fenced_code", "toc"])
    open(dst, "w", encoding="utf-8").write(
        f"<html><head><meta charset='utf-8'><style>"
        "body{font-family:sans-serif;margin:2cm;line-height:1.5}"
        "table{border-collapse:collapse}td,th{border:1px solid #999;padding:4px 8px}"
        "</style></head><body>{body}</body></html>"
    )


# ------------------------------------------------------------------ registry

SPECS: list[ToolSpec] = [
    ToolSpec(
        id="jpg2pdf",
        label="JPG to PDF",
        group="Convert To PDF",
        description="Ubah gambar JPG/PNG menjadi PDF.",
        input_kind=INPUT_IMAGE,
        run=images_to_pdf,
        params=(
            Param("page_size", "Ukuran halaman", "choice", "fit",
                  choices=("fit", "a4"), labels=("Ikuti ukuran gambar", "A4 (dengan margin)")),
            Param("dpi", "DPI", "int", "200"),
            Param("quality", "Kualitas JPEG", "int", "85"),
        ),
    ),
    ToolSpec(
        id="word2pdf",
        label="WORD to PDF",
        group="Convert To PDF",
        description="Ubah Word ke PDF lewat LibreOffice.",
        input_kind=INPUT_OFFICE,
        multi_output=True,
        run=word_to_pdf,
    ),
    ToolSpec(
        id="ppt2pdf",
        label="POWERPOINT to PDF",
        group="Convert To PDF",
        description="Ubah PowerPoint ke PDF lewat LibreOffice.",
        input_kind=INPUT_OFFICE,
        multi_output=True,
        run=powerpoint_to_pdf,
    ),
    ToolSpec(
        id="xls2pdf",
        label="EXCEL to PDF",
        group="Convert To PDF",
        description="Ubah Excel/CSV ke PDF lewat LibreOffice.",
        input_kind=INPUT_OFFICE,
        multi_output=True,
        run=excel_to_pdf,
    ),
    ToolSpec(
        id="html2pdf",
        label="HTML to PDF",
        group="Convert To PDF",
        description="Ubah berkas HTML/Markdown ke PDF.",
        input_kind=INPUT_ANY,
        run=html_to_pdf,
    ),
]
