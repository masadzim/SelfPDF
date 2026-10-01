"""PDF Intelligence: PDF ke Markdown."""

from __future__ import annotations

import os
import re

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
)

HEADING_SIZES = {28: 1, 22: 2, 16: 3}
BULLETS = {"\uf0b7", "\u2022", "-", "\u25cf", "\u25aa", "\u2023"}
CODE_HINTS = ("monospace", "courier", "consolas")


def _heading_level(size: float) -> int | None:
    for threshold, level in sorted(HEADING_SIZES.items(), reverse=True):
        if size >= threshold:
            return level
    return None


def _looks_like_heading(text: str, size: float) -> bool:
    if not text.strip() or size < 14:
        return False
    if len(text) > 120:
        return False
    stripped = text.strip()
    # Judul seldom berakhir dengan titik dan tidak berisi kalimat panjang.
    return not stripped.endswith((".", ",", ";", ":", "!", "?")) or len(stripped) < 60


def pdf_to_markdown(inputs, params, out_path, progress=None) -> ToolOutcome:
    include_images = params.get("images", False)
    doc = open_pdf(inputs[0])
    try:
        total = doc.page_count
        chunks: list[str] = []
        images_dir = None
        if include_images:
            images_dir = os.path.join(
                os.path.dirname(os.path.abspath(out_path)),
                os.path.splitext(os.path.basename(out_path))[0] + "_images",
            )
            os.makedirs(images_dir, exist_ok=True)

        extracted_images = 0

        for number, page in enumerate(doc, start=1):
            report(progress, int(number / total * 100), f"Halaman {number}/{total}")
            blocks = page.get_text("dict")
            lines: list[str] = []

            for block in blocks.get("blocks", []):
                if block.get("type") == 1:  # gambar
                    if include_images:
                        name = f"hal{number:03d}_gambar{extracted_images + 1}.png"
                        try:
                            pix = pymupdf.Pixmap(doc, block["number"])
                            if pix.colorspace and pix.colorspace.n == 4:
                                pix = pymupdf.Pixmap(pymupdf.csRGB, pix)
                            pix.save(os.path.join(images_dir, name))
                            lines.append(f"![{name}]({os.path.basename(images_dir)}/{name})")
                            extracted_images += 1
                        except Exception:
                            pass
                    continue

                previous_size = None
                for line in block.get("lines", []):
                    spans = line.get("spans", [])
                    if not spans:
                        continue
                    text = "".join(s.get("text", "") for s in spans).strip()
                    if not text:
                        lines.append("")
                        continue

                    size = max(s.get("size", 0) for s in spans)
                    font = " ".join(str(s.get("font", "")) for s in spans).lower()
                    bold = any("bold" in str(s.get("font", "")).lower() for s in spans)
                    mono = any(hint in font for hint in CODE_HINTS)

                    if mono:
                        lines.append(f"    {text}")
                    else:
                        level = _heading_level(size)
                        if level and _looks_like_heading(text, size):
                            lines.append(f"{'#' * level} {text}")
                        elif bold and len(text) < 90 and not text.endswith("."):
                            lines.append(f"**{text}**")
                        else:
                            lines.append(text)
                    previous_size = size

            # Deteksi baris berulang sebagai header/footer lalu buang.
            body = "\n".join(lines)
            body = _strip_repeating_edges(body)
            chunks.append(body)

        markdown = _join_pages(chunks)

        directory = os.path.dirname(os.path.abspath(out_path))
        if directory:
            os.makedirs(directory, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as handle:
            handle.write(markdown)

    finally:
        try:
            doc.close()
        except Exception:
            pass

    notes = []
    if not extracted_images and include_images:
        notes.append("Tidak ada gambar yang berhasil diekstrak.")
    if not markdown.strip():
        raise ToolError(
            "PDF ini tidak punya layer teks.\n"
            "Jalankan OCR PDF lebih dulu, lalu konversi ulang."
        )

    return ToolOutcome(
        output=out_path,
        summary=f"{total} halaman diubah ke Markdown ({len(markdown)} karakter).",
        warnings=notes,
    )


def _strip_repeating_edges(body: str) -> str:
    """Buang baris yang sama persis di atas dan bawah tiap halaman."""
    lines = body.split("\n")
    if len(lines) < 5:
        return body
    head = lines[0].strip()
    tail = lines[-1].strip()
    if head and head == tail:
        lines = lines[1:-1]
    return "\n".join(lines)


def _join_pages(chunks: list[str]) -> str:
    out: list[str] = []
    for index, chunk in enumerate(chunks, start=1):
        out.append(chunk.strip())
        out.append("\n\n---\n")
    text = "".join(out)
    return re.sub(r"\n{3,}", "\n\n", text).strip() + "\n"


def ext(name: str) -> str:  # pragma: no cover
    return os.path.splitext(name)[1]


SPECS: list[ToolSpec] = [
    ToolSpec(
        id="pdf2md",
        label="PDF to Markdown",
        group="PDF Intelligence",
        description="Ubah PDF berbasis teks ke Markdown (heading, tebal, kode, gambar).",
        input_kind=INPUT_PDF_MULTI,
        extension=".md",
        run=pdf_to_markdown,
        params=(Param("images", "Sertakan gambar", "bool", ""),),
    ),
]
