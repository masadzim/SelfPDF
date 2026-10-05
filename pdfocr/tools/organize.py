"""Organize PDF: merge, split, hapus, ekstrak, scan ke PDF."""

from __future__ import annotations

import os

import pymupdf
from PIL import Image

from .base import (
    INPUT_IMAGE,
    INPUT_PDF_MULTI,
    Param,
    Progress,
    ToolError,
    ToolOutcome,
    ToolSpec,
    open_pdf,
    report,
    require_inputs,
    resolve_output_file,
    safe_stem,
    save_pdf,
)

MARGIN = 12.0


# --------------------------------------------------------------------- merge

def merge_pdfs(inputs, params, out_path, progress=None) -> ToolOutcome:
    out = pymupdf.open()
    total = len(inputs)
    for index, path in enumerate(inputs):
        doc = open_pdf(path)
        try:
            out.insert_pdf(doc)
        finally:
            doc.close()
        report(progress, int((index + 1) / total * 100), f"{os.path.basename(path)}")
    count = out.page_count
    save_pdf(out, out_path)
    return ToolOutcome(output=out_path, summary=f"{count} halaman digabung dari {total} berkas.")


# --------------------------------------------------------------------- split

def split_pdf(inputs, params, out_path, progress=None) -> ToolOutcome:
    doc = open_pdf(inputs[0])
    mode = params.get("mode", "ranges")
    out_dir = params.get("out_dir") or out_path
    os.makedirs(out_dir, exist_ok=True)
    stem = safe_stem(inputs[0])
    created: list[str] = []

    try:
        if mode == "every":
            step = max(1, int(params.get("step", 1)))
            groups = [list(range(i, min(i + step, doc.page_count)))
                      for i in range(0, doc.page_count, step)]
        elif mode == "each":
            groups = [[i] for i in range(doc.page_count)]
        else:
            from .base import parse_page_range

            groups = []
            for chunk in (params.get("ranges") or "all").replace(";", ",").split(","):
                chunk = chunk.strip()
                if chunk:
                    groups.append(parse_page_range(chunk, doc.page_count))

        total = max(1, len(groups))
        for number, pages in enumerate(groups, start=1):
            if not pages:
                continue
            part = pymupdf.open()
            part.insert_pdf(doc, from_page=pages[0], to_page=pages[-1])
            path = os.path.join(out_dir, f"{stem}_part{number:02d}.pdf")
            part.save(path, garbage=4, deflate=True)
            part.close()
            created.append(path)
            report(progress, int(number / total * 100), f"Bagian {number}/{len(groups)}")

        return ToolOutcome(
            output=f"{len(created)} berkas di {out_dir}",
            summary=f"{len(created)} berkas dibuat dari {doc.page_count} halaman.",
            items=created,
        )
    finally:
        doc.close()


# --------------------------------------------------------------- remove pages

def remove_pages(inputs, params, out_path, progress=None) -> ToolOutcome:
    from .base import parse_page_range

    doc = open_pdf(inputs[0])
    try:
        # Unlike other tools, an empty range here must NOT mean "all pages".
        # Remove Pages is destructive, and its field help says empty = nothing
        # removed; letting it mean "all pages" deletes the whole document.
        # So: empty = no-op with an explanation, not an error.
        text = (params.get("ranges", "") or "").strip()
        if not text:
            return ToolOutcome(
                output="",
                summary="Tidak ada halaman yang dihapus.",
                warnings=[
                    "Rentang halaman masih kosong, jadi tidak ada yang dihapus.\n"
                    "Tulis halaman yang mau dibuang, contoh: 1, 3-5 atau 2-4, 7."
                ],
            )

        pages = parse_page_range(text, doc.page_count)
        keep = [i for i in range(doc.page_count) if i not in set(pages)]
        if not keep:
            raise ToolError(
                "Semua halaman akan dihapus, jadi tidak ada yang tersisa.\n"
                "Kurangi halaman yang dihapus, contoh: 1, 3-5."
            )

        out = pymupdf.open()
        first = 0
        for number in keep:
            out.insert_pdf(doc, from_page=number, to_page=number)
            first += 1
            report(progress, int(first / len(keep) * 100))

        removed = doc.page_count - len(keep)
        save_pdf(out, out_path)
        return ToolOutcome(
            output=out_path,
            summary=f"{removed} halaman dihapus, {len(keep)} halaman tersisa.",
        )
    finally:
        doc.close()


# -------------------------------------------------------------- extract pages

def extract_pages(inputs, params, out_path, progress=None) -> ToolOutcome:
    from .base import parse_page_range

    doc = open_pdf(inputs[0])
    try:
        pages = parse_page_range(params.get("ranges", ""), doc.page_count)
        out = pymupdf.open()
        for number, page in enumerate(pages, start=1):
            out.insert_pdf(doc, from_page=page, to_page=page)
            report(progress, int(number / len(pages) * 100))

        out_dir = params.get("out_dir") or out_path
        single_path = resolve_output_file(out_dir, inputs[0], "_extract")
        if params.get("separate"):
            os.makedirs(out_dir, exist_ok=True)
            stem = safe_stem(inputs[0])
            created = []
            for number, page in enumerate(pages, start=1):
                single = pymupdf.open()
                single.insert_pdf(doc, from_page=page, to_page=page)
                path = os.path.join(out_dir, f"{stem}_hal{page + 1:03d}.pdf")
                single.save(path, deflate=True)
                single.close()
                created.append(path)
            out.close()
            return ToolOutcome(
                output=f"{len(created)} berkas di {out_dir}",
                summary=f"{len(created)} berkas diekstrak (satu berkas per halaman).",
                items=created,
            )

        os.makedirs(os.path.dirname(os.path.abspath(single_path)), exist_ok=True)
        save_pdf(out, single_path)
        return ToolOutcome(output=single_path, summary=f"{len(pages)} halaman diekstrak.")
    finally:
        doc.close()


# -------------------------------------------------------------- scan to PDF

def scan_to_pdf(inputs, params, out_path, progress=None) -> ToolOutcome:
    """Gabungkan foto/scan jadi satu PDF, opsional autorek straighten."""
    dpi = int(params.get("dpi", 200))
    jpeg_quality = int(params.get("quality", 80))
    total = len(inputs)
    out = pymupdf.open()

    for index, path in enumerate(inputs, start=1):
        try:
            image = Image.open(path)
            image.load()
        except Exception as exc:
            raise ToolError(f"Gambar tidak bisa dibaca: {os.path.basename(path)} ({exc})") from exc

        if image.mode not in ("RGB", "L"):
            image = image.convert("RGB")
        if params.get("grayscale"):
            image = image.convert("L")

        import io

        buffer = io.BytesIO()
        image.save(buffer, format="JPEG", quality=jpeg_quality, optimize=True)
        rect_w = image.width * 72.0 / dpi
        rect_h = image.height * 72.0 / dpi
        page = out.new_page(width=rect_w, height=rect_h)
        page.insert_image(page.rect, stream=buffer.getvalue())
        report(progress, int(index / total * 100), os.path.basename(path))

    save_pdf(out, out_path)
    return ToolOutcome(
        output=out_path,
        summary=f"{total} gambar dijadikan PDF pada resolusi {dpi} DPI.",
    )


# ------------------------------------------------------------------- registry

SPECS: list[ToolSpec] = [
    ToolSpec(
        id="merge",
        label="Merge PDF",
        group="Organize PDF",
        description="Gabungkan beberapa PDF menjadi satu, berurutan sesuai pilihan.",
        input_kind=INPUT_PDF_MULTI,
        run=merge_pdfs,
    ),
    ToolSpec(
        id="split",
        label="Split PDF",
        group="Organize PDF",
        description="Pecah satu PDF menjadi beberapa berkas.",
        input_kind=INPUT_PDF_MULTI,
        extension="",
        multi_output=True,
        run=split_pdf,
        params=(
            Param("mode", "Metode", "choice", "ranges",
                  choices=("ranges", "every", "each"),
                  labels=("Rentang halaman", "Setiap N halaman", "Satu berkas per halaman")),
            Param("ranges", "Rentang", "text", "1-2, 3-4",
                  help="Contoh: 1-3, 5, 8-10. Kosongkan = semua halaman."),
            Param("step", "Setiap N halaman", "int", "1"),
        ),
    ),
    ToolSpec(
        id="remove",
        label="Remove Pages",
        group="Organize PDF",
        description="Hapus halaman tertentu dari PDF.",
        input_kind=INPUT_PDF_MULTI,
        run=remove_pages,
        params=(
            Param("ranges", "Halaman yang dihapus", "text", "",
                  help="Contoh: 1, 3-5. Kosongkan = tidak ada yang dihapus."),
        ),
    ),
    ToolSpec(
        id="extract",
        label="Extract Pages",
        group="Organize PDF",
        description="Ambil halaman tertentu menjadi PDF baru.",
        input_kind=INPUT_PDF_MULTI,
        multi_output=True,
        run=extract_pages,
        params=(
            Param("ranges", "Halaman yang diambil", "text", "",
                  help="Contoh: 1-3, 7. Kosongkan = semua halaman."),
            Param("separate", "Satu berkas per halaman", "bool", "",
                  help="Jika tidak dicentang, semua halaman digabung ke satu PDF."),
        ),
    ),
    ToolSpec(
        id="scan",
        label="Scan to PDF",
        group="Organize PDF",
        description="Ubah foto atau hasil scan menjadi satu PDF.",
        input_kind=INPUT_IMAGE,
        run=scan_to_pdf,
        params=(
            Param("dpi", "Resolusi (DPI)", "int", "200"),
            Param("quality", "Kualitas JPEG (1-95)", "int", "80"),
            Param("grayscale", "Ubah ke skala abu-abu", "bool", ""),
        ),
    ),
]
