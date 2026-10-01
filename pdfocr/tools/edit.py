"""Edit PDF: putar, nomor halaman, watermark, crop, anotasi, form."""

from __future__ import annotations

import os

import pymupdf

from .base import (
    INPUT_PDF_MULTI,
    Param,
    Progress,
    ToolError,
    ToolOutcome,
    ToolSpec,
    collect_widgets,
    open_pdf,
    report,
    save_pdf,
)

FONTS = {
    "helv": pymupdf.Font("helv"),
    "tiro": pymupdf.Font("tiro"),
    "cour": pymupdf.Font("cour"),
    "times": pymupdf.Font("tiro"),
}


def _font(name: str) -> pymupdf.Font:
    return FONTS.get(name, FONTS["helv"])


def _color(value: str) -> tuple[float, float, float]:
    """Terima "merah", "#ff0000", atau "1 0 0"."""
    text = (value or "").strip().lower()
    named = {
        "merah": (0.8, 0.1, 0.1), "red": (0.8, 0.1, 0.1),
        "biru": (0.1, 0.25, 0.75), "blue": (0.1, 0.25, 0.75),
        "hijau": (0.1, 0.5, 0.2), "green": (0.1, 0.5, 0.2),
        "hitam": (0, 0, 0), "black": (0, 0, 0),
        "putih": (1, 1, 1), "white": (1, 1, 1),
        "abu": (0.5, 0.5, 0.5), "grey": (0.5, 0.5, 0.5),
        "kuning": (0.85, 0.75, 0.1), "yellow": (0.85, 0.75, 0.1),
    }
    if text in named:
        return named[text]
    if text.startswith("#") and len(text) == 7:
        try:
            return tuple(int(text[i:i + 2], 16) / 255 for i in (1, 3, 5))  # type: ignore[return-value]
        except ValueError:
            pass
    parts = text.replace(",", " ").split()
    if len(parts) == 3:
        try:
            return tuple(float(p) for p in parts)  # type: ignore[return-value]
        except ValueError:
            pass
    return (0.5, 0.5, 0.5)


# -------------------------------------------------------------------- rotate

def rotate_pdf(inputs, params, out_path, progress=None) -> ToolOutcome:
    angle = int(params.get("angle", 90)) % 360
    if angle not in (90, 180, 270):
        raise ToolError("Sudut harus 90, 180, atau 270 derajat.")

    doc = open_pdf(inputs[0])
    try:
        from .base import parse_page_range

        total = doc.page_count
        pages = set(parse_page_range(params.get("ranges", ""), total))
        for number, page in enumerate(doc, start=1):
            if (number - 1) in pages:
                page.set_rotation((page.rotation + angle) % 360)
            report(progress, int(number / total * 100))
    finally:
        pass

    save_pdf(doc, out_path)
    return ToolOutcome(output=out_path, summary=f"{len(pages)} halaman diputar {angle}°.")


# --------------------------------------------------------------- page numbers

def add_page_numbers(inputs, params, out_path, progress=None) -> ToolOutcome:
    doc = open_pdf(inputs[0])
    try:
        total = doc.page_count
        position = params.get("position", "bottom-center")
        fmt = params.get("format", "{n} / {total}")
        size = float(params.get("size", 10))
        color = _color(params.get("color", "abu"))
        start_at = int(params.get("start", 1))
        margin = float(params.get("margin", 18))

        font = _font(params.get("font", "helv"))
        for number, page in enumerate(doc, start=1):
            rect = page.rect
            label = fmt.format(n=number + start_at - 1, total=total + start_at - 1)
            width = font.text_length(label, size)

            if "top" in position:
                y = margin + size
            else:
                y = rect.height - margin
            if "left" in position:
                x = margin
            elif "right" in position:
                x = rect.width - margin - width
            else:
                x = (rect.width - width) / 2

            page.insert_text(
                (x, y), label, fontname=params.get("font", "helv"),
                fontsize=size, color=color,
            )
            report(progress, int(number / total * 100))

        save_pdf(doc, out_path)
        return ToolOutcome(output=out_path, summary=f"Penomoran ditambahkan pada {total} halaman.")
    finally:
        try:
            doc.close()
        except Exception:
            pass


# ----------------------------------------------------------------- watermark

def add_watermark(inputs, params, out_path, progress=None) -> ToolOutcome:
    """Tambahkan watermark teks. `TextWriter` dipakai agar sudut bebas
    (insert_text hanya menerima 0/90/180/270) dan opacity benar-benar dipakai.
    """
    doc = open_pdf(inputs[0])
    try:
        total = doc.page_count
        text = params.get("text", "RAHASIA")
        if not text.strip():
            raise ToolError("Teks watermark tidak boleh kosong.")
        size = float(params.get("size", 48))
        opacity = min(1.0, max(0.0, float(params.get("opacity", 0.18))))
        rotation = float(params.get("rotation", 45))
        color = _color(params.get("color", "abu"))
        layout = params.get("layout", "tile")
        font = _font(params.get("font", "helv"))

        from .base import parse_page_range

        pages = set(parse_page_range(params.get("ranges", ""), total))
        matrix = pymupdf.Matrix(rotation)

        for number, page in enumerate(doc, start=1):
            if (number - 1) in pages:
                rect = page.rect
                writer = pymupdf.TextWriter(page.rect)
                width = font.text_length(text, size)

                if layout == "tile":
                    # Somegaris diagonal berulang, dirotasi di sekitar pusat.
                    for row in range(-1, 4):
                        for col in range(-1, 4):
                            cx = (col + 0.5) * rect.width / 2 + row * rect.height / 8
                            cy = (row + 0.5) * rect.height / 2 + col * rect.width / 8
                            writer.append(
                                (cx - width / 2, cy + size / 3),
                                text, font=font, fontsize=size,
                            )
                            writer.write_text(
                                page, color=color, opacity=opacity,
                                morph=(pymupdf.Point(cx, cy), matrix),
                            )
                else:  # diagonal tunggal di tengah halaman
                    cx, cy = rect.width / 2, rect.height / 2
                    writer.append(
                        (cx - width / 2, cy + size / 3), text,
                        font=font, fontsize=size,
                    )
                    writer.write_text(
                        page, color=color, opacity=opacity,
                        morph=(pymupdf.Point(cx, cy), matrix),
                    )

            report(progress, int(number / total * 100))

        save_pdf(doc, out_path)
        return ToolOutcome(
            output=out_path,
            summary=(
                f"Watermark '{text}' ditambahkan pada {len(pages)} halaman "
                f"({size:.0f} pt, {rotation:.0f}°, opacity {opacity:.0%})."
            ),
        )
    finally:
        try:
            doc.close()
        except Exception:
            pass


# ---------------------------------------------------------------------- crop

def crop_pdf(inputs, params, out_path, progress=None) -> ToolOutcome:
    doc = open_pdf(inputs[0])
    try:
        total = doc.page_count
        mode = params.get("mode", "margin")
        from .base import parse_page_range

        pages = set(parse_page_range(params.get("ranges", ""), total))

        for number, page in enumerate(doc, start=1):
            if (number - 1) not in pages:
                report(progress, int(number / total * 100))
                continue

            rect = page.rect
            if mode == "margin":
                left = right = top = bottom = float(params.get("margin", 36))
            elif mode == "absolute":
                left = float(params.get("left", 0))
                right = float(params.get("right", 0))
                top = float(params.get("top", 0))
                bottom = float(params.get("bottom", 0))
            else:  # box manual dalam pt
                x0 = float(params.get("x0", 0))
                y0 = float(params.get("y0", 0))
                x1 = float(params.get("x1", rect.width))
                y1 = float(params.get("y1", rect.height))
                left, top = x0, y0
                right, bottom = rect.width - x1, rect.height - y1

            new_rect = pymupdf.Rect(
                rect.x0 + left, rect.y0 + top,
                rect.x1 - right, rect.y1 - bottom,
            )
            if new_rect.width < 20 or new_rect.height < 20:
                raise ToolError(
                    f"Hasil crop halaman {number} terlalu kecil ({new_rect.width:.0f}×"
                    f"{new_rect.height:.0f} pt). Kurangi margin."
                )
            page.set_cropbox(new_rect)
            report(progress, int(number / total * 100))

        save_pdf(doc, out_path)
        return ToolOutcome(output=out_path, summary=f"{len(pages)} halaman di-crop.")
    finally:
        try:
            doc.close()
        except Exception:
            pass


# ------------------------------------------------------------------- annotate

def annotate_pdf(inputs, params, out_path, progress=None) -> ToolOutcome:
    """Tambah catatan, sorotan, atau stempel teks ke halaman tertentu."""
    doc = open_pdf(inputs[0])
    try:
        total = doc.page_count
        kind = params.get("kind", "note")
        text = params.get("text", "")
        page_no = int(params.get("page", 1))
        if not (1 <= page_no <= total):
            raise ToolError(f"Nomor halaman harus 1–{total}.")

        page = doc[page_no - 1]
        rect = page.rect
        color = _color(params.get("color", "kuning"))
        size = float(params.get("size", 14))

        if kind == "note":
            if not text.strip():
                raise ToolError("Isi catatan tidak boleh kosong.")
            box = pymupdf.Rect(
                rect.x0 + 36, rect.y0 + 36,
                rect.x0 + 36 + max(160, len(text) * size * 0.55), rect.y0 + 36 + size * 3
            )
            annot = page.add_text_annot(box, text, icon="Note")
            annot.set_colors(stroke=color)
            annot.update()
            summary = f"Catatan ditambahkan di halaman {page_no}."
        elif kind == "highlight":
            text_page = doc[page_no - 1]
            hits = text_page.search_for(text) if text.strip() else []
            if not hits:
                raise ToolError(
                    f'Teks "{text}" tidak ditemukan di halaman {page_no}.'
                )
            annot = text_page.add_highlight_annot(hits)
            annot.set_colors(stroke=color)
            annot.update()
            summary = f"{len(hits)} bagian disorot di halaman {page_no}."
        elif kind == "stamp":
            if not text.strip():
                raise ToolError("Teks stempel tidak boleh kosong.")
            lines = max(1, len(text) // 18 + 1)
            box = pymupdf.Rect(
                rect.x1 - 240, rect.y0 + 30,
                rect.x1 - 40, rect.y0 + 40 + lines * size * 1.35
            )
            # FreeText, bukan sticky note: stempel harus terlihat dicetak di
            # halaman, bukan hanya jadi ikon komentar.
            annot = page.add_freetext_annot(
                box,
                text,
                fontsize=size,
                fontname="helv",
                text_color=color,
                fill_color=(1, 1, 1),
                align=1,
            )
            annot.set_opacity(0.85)
            annot.update()
            summary = f"Stempel '{text}' ditambahkan di halaman {page_no}."
        else:
            raise ToolError("Jenis anotasi tidak dikenal.")

        report(progress, 100)
        save_pdf(doc, out_path)
        return ToolOutcome(output=out_path, summary=summary)
    finally:
        try:
            doc.close()
        except Exception:
            pass


# --------------------------------------------------------------------- forms

def fill_forms(inputs, params, out_path, progress=None) -> ToolOutcome:
    """Isi field AcroForm dari teks "NamaField=Nilai" lalu opsionalkan (flatten)."""
    doc = open_pdf(inputs[0])
    try:
        # `form_pages` harus tetap hidup selama widget dipakai.
        form_pages, form_widgets = collect_widgets(doc)
        widgets = {w.field_name: w for w in form_widgets if w.field_name}
        if not widgets:
            raise ToolError(
                "PDF ini tidak punya field formulir (AcroForm) yang bernama.\n"
                "Formulir harus dibuat lebih dulu di aplikasi pengolah PDF."
            )

        pairs = parse_field_values(params.get("values", ""))
        unknown = sorted(set(pairs) - set(widgets))
        if unknown:
            preview = ", ".join(unknown[:8])
            raise ToolError(
                f"Field tidak ada di PDF ini: {preview}\n"
                f"Field yang tersedia: {', '.join(list(widgets)[:8])}"
            )

        filled = 0
        skipped: list[str] = []
        for name, value in pairs.items():
            widget = widgets[name]
            if widget.field_flags & 1:  # ReadOnly
                skipped.append(name)
                continue
            widget.field_value = value
            widget.update()
            filled += 1
        report(progress, 60)

        if params.get("flatten"):
            # bake() mencium widget + anotasi jadi isi halaman secara permanen.
            doc.bake(annots=False, widgets=True)
            report(progress, 85)

        save_pdf(doc, out_path)
    finally:
        try:
            doc.close()
        except Exception:
            pass

    notes = []
    if skipped:
        notes.append(
            f"{len(skipped)} field read-only dilewati: {', '.join(skipped[:6])}"
        )
    if not pairs:
        notes.append(
            "Tidak ada nilai yang diisi. Isi kolom Nilai dengan "
            "format NamaField=Nilai (pisah titik koma atau baris baru). "
            f"Field tersedia: {', '.join(list(widgets)[:8])}"
        )
    if params.get("flatten"):
        notes.append("Field dipanggang ke isi halaman; isinya tidak bisa diedit lagi.")

    return ToolOutcome(
        output=out_path,
        summary=f"{filled} dari {len(pairs)} field terisi dari {len(widgets)} field yang ada.",
        warnings=notes,
    )


def parse_field_values(text: str) -> dict[str, str]:
    """Ubah "Nama=Nilai;Nama2=Nilai2" menjadi dict."""
    values: dict[str, str] = {}
    for chunk in (text or "").replace(";", "\n").split("\n"):
        chunk = chunk.strip()
        if not chunk or "=" not in chunk:
            continue
        name, _, value = chunk.partition("=")
        name = name.strip()
        if name:
            values[name] = value.strip()
    return values


# ------------------------------------------------------------------ registry

SPECS: list[ToolSpec] = [
    ToolSpec(
        id="rotate",
        label="Rotate PDF",
        group="Edit PDF",
        description="Putar seluruh halaman atau hanya halaman tertentu.",
        input_kind=INPUT_PDF_MULTI,
        run=rotate_pdf,
        params=(
            Param("angle", "Sudut", "choice", "90",
                  choices=("90", "180", "270"),
                  labels=("90° (kanan)", "180°", "270° (kiri)")),
            Param("ranges", "Halaman", "text", "", help="Kosongkan = semua halaman."),
        ),
    ),
    ToolSpec(
        id="numbers",
        label="Add Page Numbers",
        group="Edit PDF",
        description="Beri nomor pada tiap halaman.",
        input_kind=INPUT_PDF_MULTI,
        run=add_page_numbers,
        params=(
            Param("format", "Format", "text", "{n} / {total}",
                  help="Placeholder: {n} = nomor halaman ini, {total} = nomor "
                       "halaman terakhir (ikut menyesuaikan bila 'Mulai dari' diisi)."),
            Param("position", "Posisi", "choice", "bottom-center",
                  choices=("bottom-center", "bottom-right", "bottom-left",
                           "top-center", "top-right", "top-left"),
                  labels=("Bawah tengah", "Bawah kanan", "Bawah kiri",
                          "Atas tengah", "Atas kanan", "Atas kiri")),
            Param("start", "Mulai dari", "int", "1",
                  help="Nomor untuk halaman pertama. Kosongkan = 1."),
            Param("size", "Ukuran font", "float", "10"),
            Param("font", "Font", "choice", "helv",
                  choices=("helv", "tiro", "cour"),
                  labels=("Sans", "Serif", "Monospace")),
            Param("color", "Warna", "text", "abu",
                  help="merah/biru/hijau/hitam/putih/abu/kuning, #RRGGBB, atau \"1 0 0\"."),
        ),
    ),
    ToolSpec(
        id="watermark",
        label="Add Watermark",
        group="Edit PDF",
        description="Bubuhkan teks watermark ke halaman.",
        input_kind=INPUT_PDF_MULTI,
        run=add_watermark,
        params=(
            Param("text", "Teks watermark", "text", "RAHASIA"),
            Param("size", "Ukuran font", "float", "48"),
            Param("rotation", "Sudut (derajat)", "float", "45",
                  help="Sudut bebas, mis. 45 untuk diagonal."),
            Param("opacity", "Opasitas (0-1)", "float", "0.18"),
            Param("layout", "Tata letak", "choice", "tile",
                  choices=("tile", "center"),
                  labels=("Ulangi (mengganti seluruh halaman)", "Tengah, satu baris")),
            Param("font", "Font", "choice", "helv",
                  choices=("helv", "tiro", "cour"),
                  labels=("Sans", "Serif", "Monospace")),
            Param("color", "Warna", "text", "abu"),
            Param("ranges", "Halaman", "text", "", help="Kosongkan = semua halaman."),
        ),
    ),
    ToolSpec(
        id="crop",
        label="Crop PDF",
        group="Edit PDF",
        description="Potong margin atau area tertentu dari halaman.",
        input_kind=INPUT_PDF_MULTI,
        run=crop_pdf,
        params=(
            Param("mode", "Metode", "choice", "margin",
                  choices=("margin", "absolute", "box"),
                  labels=("Potong margin sama rata", "Specify tiap sisi", "Kotak (pt)")),
            Param("margin", "Margin (pt)", "float", "36"),
            Param("left", "Kiri (pt)", "float", "0"),
            Param("right", "Kanan (pt)", "float", "0"),
            Param("top", "Atas (pt)", "float", "0"),
            Param("bottom", "Bawah (pt)", "float", "0"),
            Param("x0", "x0 (pt)", "float", "0"),
            Param("y0", "y0 (pt)", "float", "0"),
            Param("x1", "x1 (pt)", "float", "0"),
            Param("y1", "y1 (pt)", "float", "0"),
            Param("ranges", "Halaman", "text", ""),
        ),
    ),
    ToolSpec(
        id="annotate",
        label="Edit PDF",
        group="Edit PDF",
        description="Tambah catatan, sorotan, atau stempel teks.",
        input_kind=INPUT_PDF_MULTI,
        run=annotate_pdf,
        params=(
            Param("kind", "Jenis", "choice", "note",
                  choices=("note", "highlight", "stamp"),
                  labels=("Catatan", "Sorot teks", "Stempel teks")),
            Param("page", "Halaman", "int", "1"),
            Param("text", "Teks", "text", "",
                  help="Untuk sorot: teks yang akan dicari di halaman itu."),
            Param("color", "Warna", "text", "kuning"),
            Param("size", "Ukuran font", "float", "14"),
        ),
    ),
    ToolSpec(
        id="forms",
        label="PDF Forms",
        group="Edit PDF",
        description="Isi lalu satukan field formulir AcroForm.",
        input_kind=INPUT_PDF_MULTI,
        run=fill_forms,
        params=(Param("flatten", "Satukan (flatten) form", "bool", ""),),
    ),
]
