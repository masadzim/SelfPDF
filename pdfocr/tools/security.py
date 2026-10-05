"""Security PDF: unlock, protect, sign, redact, compare."""

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

# Bit izin enkripsi PDF (ISO 32000-1, table 22)
PERM_PRINT = 1 << 2
PERM_MODIFY = 1 << 3
PERM_COPY = 1 << 4
PERM_ANNOTATE = 1 << 5


# -------------------------------------------------------------------- unlock

def unlock_pdf(inputs, params, out_path, progress=None) -> ToolOutcome:
    password = params.get("password", "")
    doc = pymupdf.open(inputs[0])
    try:
        if not doc.needs_pass:
            # Bukan terenkripsi — tetap tulis ulang tanpa password agar bersih.
            report(progress, 60, "Menulis ulang tanpa enkripsi…")
            save_pdf(doc, out_path)
            return ToolOutcome(
                output=out_path, summary="PDF tidak terenkripsi; disalin tanpa password."
            )

        report(progress, 40, "Mencoba password…")
        if not doc.authenticate(password):
            doc.close()
            raise ToolError("Password salah.")

        report(progress, 80)
        save_pdf(doc, out_path)
        return ToolOutcome(
            output=out_path,
            summary="Password diterima; enkripsi dihapus.",
        )
    finally:
        try:
            doc.close()
        except Exception:
            pass


# ------------------------------------------------------------------ protect

def protect_pdf(inputs, params, out_path, progress=None) -> ToolOutcome:
    owner_pw = params.get("owner_password", "")
    user_pw = params.get("user_password", "")
    if not owner_pw and not user_pw:
        raise ToolError("Isi minimal satu password.")

    permissions = 0
    if params.get("allow_print"):
        permissions |= PERM_PRINT
    if params.get("allow_modify"):
        permissions |= PERM_MODIFY
    if params.get("allow_copy"):
        permissions |= PERM_COPY
    if params.get("allow_annotate"):
        permissions |= PERM_ANNOTATE

    doc = open_pdf(inputs[0])
    try:
        report(progress, 60, "Menerapkan enkripsi…")
        doc.save(
            out_path,
            encryption=pymupdf.PDF_ENCRYPT_AES_256,
            owner_pw=owner_pw or user_pw,
            user_pw=user_pw,
            permissions=int(permissions),
        )
    finally:
        doc.close()

    return ToolOutcome(
        output=out_path,
        summary="Enkripsi AES-256 diterapkan.",
        warnings=(
            ["Izin: pengguna tanpa password bisa membuka tanpa batasan."]
            if not user_pw
            else ["Izin: buka dengan 'user password' dibatasi sesuai centang di atas."]
        ),
    )


# ---------------------------------------------------------------------- sign

def sign_pdf(inputs, params, out_path, progress=None) -> ToolOutcome:
    """Tambahkan tanda tangan.

    Dua mode: gambar (cap visual) atau sertifikat digital (PAdES). Sertifikat
    harus berupa file .pfx/.p12.
    """
    mode = params.get("mode", "image")
    doc = open_pdf(inputs[0])
    try:
        from .base import parse_page_range

        total = doc.page_count
        pages = parse_page_range(params.get("ranges", ""), total)
        page_no = int(params.get("page", total))

        if mode == "image":
            image_path = params.get("image", "")
            if not image_path or not os.path.exists(image_path):
                raise ToolError("Pilih berkas gambar tanda tangan (PNG/JPG).")

            stamp = pymupdf.open(image_path)
            try:
                if stamp.page_count == 0 or stamp[0].get_images():
                    stamp.close()
                    raise ToolError(
                        "Berkas tanda tangan bukan gambar. Gunakan PNG atau JPG."
                    )
                rect_img = stamp[0].rect
                width = float(params.get("width", 160))
                height = width * rect_img.height / rect_img.width
                pos = params.get("position", "bottom-right")

                for number in pages:
                    page = doc[number]
                    rect = page.rect
                    if "top" in pos:
                        top = 30.0
                    else:
                        top = rect.height - height - 30.0
                    if "left" in pos:
                        left = 30.0
                    elif "center" in pos:
                        left = (rect.width - width) / 2
                    else:
                        left = rect.width - width - 30.0

                    page.insert_image(
                        pymupdf.Rect(left, top, left + width, top + height),
                        filename=image_path, keep_proportion=True,
                    )
                    report(progress, int((number + 1) / len(pages) * 100))
            finally:
                stamp.close()

            save_pdf(doc, out_path)
            return ToolOutcome(
                output=out_path,
                summary=f"Tanda tangan gambar disisipkan pada {len(pages)} halaman.",
                warnings=["Ini tanda tangan visual, bukan sertifikat kriptografis."],
            )

        # Mode sertifikat digital
        cert_path = params.get("cert", "")
        if not cert_path or not os.path.exists(cert_path):
            raise ToolError("Pilih berkas sertifikat (.pfx/.p12).")
        try:
            from endesive import ec
        except ImportError as exc:  # pragma: no cover
            raise ToolError(
                "endesive belum terpasang.\n    pip install endesive"
            ) from exc

        password = params.get("cert_password", "")
        field_name = params.get("field", "Signature1")

        form_pages, form_widgets = collect_widgets(doc)
        field_names = {w.field_name for w in form_widgets if w.field_name}
        if not doc.is_form_pdf or field_name not in field_names:
            raise ToolError(
                f'PDF harus punya field tanda tangan bernama "{field_name}".\n'
                "Buat field-nya lebih dulu di aplikasi pengolah PDF."
            )

        report(progress, 50, "Menandatangani dengan sertifikat…")
        try:
            with open(cert_path, "rb") as handle:
                pkcs12_load(handle.read(), password)
        except Exception as exc:  # noqa: BLE001
            raise ToolError(f"Sertifikat tidak bisa dibaca: {exc}") from exc

        try:
            from endesive import ec

            pdfsig = ec.PdfSignature(pdf=inputs[0])
            pdfsig.sign(
                field_name,
                reason=params.get("reason", "Disetujui"),
                location=params.get("location", ""),
                certify=True,
            )
            out_bytes = pdfsig.write()
        except ImportError as exc:  # pragma: no cover
            raise ToolError("endesive belum terpasang.\n    pip install endesive") from exc
        except Exception as exc:  # noqa: BLE001
            raise ToolError(f"Penandatanganan gagal: {exc}") from exc

        with open(out_path, "wb") as handle:
            handle.write(out_bytes)

        return ToolOutcome(
            output=out_path,
            summary=f"PDF ditandatangani secara kriptografis ({field_name}).",
        )
    finally:
        try:
            doc.close()
        except Exception:
            pass


def pkcs12_load(data: bytes, password: str):
    """Baca PKCS#12 tanpa dependensi eksternal bila cryptography tersedia."""
    from cryptography.hazmat.primitives.serialization import pkcs12

    key, cert, extra = pkcs12.load_key_and_certificates(data, password.encode() or None)
    if key is None or cert is None:
        raise ValueError("Sertifikat atau kunci privat tidak ditemukan di berkas .pfx")
    return key, [cert], extra


# -------------------------------------------------------------------- redact

def redact_pdf(inputs, params, out_path, progress=None) -> ToolOutcome:
    """Hapus teks secara permanen: kotak hitam + buang karakter di bawahnya."""
    terms = [t.strip() for t in (params.get("terms", "") or "").split(",") if t.strip()]
    mode = params.get("mode", "terms")
    page_no = int(params.get("page", 0))

    doc = open_pdf(inputs[0])
    try:
        from .base import parse_page_range

        total = doc.page_count
        ranges = (params.get("ranges", "") or "").strip()
        if mode == "rects":
            # `page` berlaku di mode koordinat; `ranges` menggantikannya bila
            # diisi supaya beberapa halaman bisa disensor sekaligus.
            if ranges:
                pages = parse_page_range(ranges, total)
            elif 1 <= page_no <= total:
                pages = [page_no - 1]
            else:
                raise ToolError(f"Nomor halaman harus 1–{total}.")
        else:
            pages = parse_page_range(ranges, total)

        removed = 0
        for number in pages:
            page = doc[number]
            rects = []
            if mode == "rects":
                for item in (params.get("rects", "") or "").split(";"):
                    parts = [p.strip() for p in item.split(",") if p.strip()]
                    if len(parts) != 4:
                        continue
                    try:
                        x0, y0, x1, y1 = (float(p) for p in parts)
                    except ValueError:
                        continue
                    if x1 <= x0 or y1 <= y0:
                        continue
                    rects.append(pymupdf.Rect(x0, y0, x1, y1))
                if not rects:
                    raise ToolError(
                        "Masukkan koordinat: x0,y0,x1,y1;x0,y0,x1,y1"
                    )
            else:
                for term in terms:
                    rects.extend(page.search_for(term))

            for rect in rects:
                # 1) Bersihkan karakter yang jatuh di dalam kotak.
                page.add_redact_annot(rect, fill=(0, 0, 0))
                removed += 1
            if rects:
                page.apply_redactions(images=pymupdf.PDF_REDACT_IMAGE_PIXELS)
            report(progress, int((number + 1) / len(pages) * 100))

        if removed == 0:
            raise ToolError(
                "Tidak ada yang ditemukan untuk disensor.\n"
                "Cek ejaan kata kunci, atau pakai mode koordinat."
            )

        save_pdf(doc, out_path)
    finally:
        try:
            doc.close()
        except Exception:
            pass

    # Verifikasi dengan membuka ulang: kata kunci yang masih ada berarti
    # ada kotak yang tidak menutupi seluruh glyph-nya.
    leftover_terms: list[str] = []
    if terms:
        check = open_pdf(out_path)
        try:
            for term in terms:
                for page in check:
                    if page.search_for(term):
                        leftover_terms.append(term)
                        break
        finally:
            check.close()

    notes = []
    if leftover_terms:
        notes.append(
            "Kata kunci masih terdeteksi setelah disensor: "
            + ", ".join(sorted(set(leftover_terms))[:8])
            + ". Periksa apakah teksnya terpotong antar-karakter."
        )

    return ToolOutcome(
        output=out_path,
        summary=f"{removed} area disensor pada {len(pages)} halaman.",
        warnings=notes,
    )


# ------------------------------------------------------------------- compare

def compare_pdf(inputs, params, out_path, progress=None) -> ToolOutcome:
    """Bandingkan dua PDF berdasarkan isi teksnya."""
    if len(inputs) < 2:
        raise ToolError("Pilih dua PDF untuk dibandingkan (Urutan: lama, lalu baru).")

    import difflib

    def text_of(path: str) -> list[str]:
        doc = open_pdf(path)
        try:
            return [
                " ".join(page.get_text().split())
                for page in doc
            ]
        finally:
            doc.close()

    report(progress, 25, "Membaca dokumen…")
    old_pages = text_of(inputs[0])
    report(progress, 60, "Membandingkan…")
    new_pages = text_of(inputs[1])

    out = pymupdf.open()
    added = removed = changed = same = 0
    detail: list[str] = []

    for index in range(max(len(old_pages), len(new_pages))):
        old = old_pages[index] if index < len(old_pages) else ""
        new = new_pages[index] if index < len(new_pages) else ""
        page = out.new_page(width=595, height=842)

        if old == new:
            same += 1
            _write_diff_page(page, index, "SAMA", (0.1, 0.5, 0.2),
                             _wrap(new), [])
            continue

        if not old:
            added += 1
            label = "DITAMBAHKAN"
            color = (0.1, 0.35, 0.7)
        elif not new:
            removed += 1
            label = "DIHAPUS"
            color = (0.7, 0.15, 0.1)
        else:
            changed += 1
            label = "BERUBAH"
            color = (0.75, 0.5, 0.05)

        delta = list(difflib.ndiff(_wrap(old), _wrap(new)))
        removed_lines = [d[2:] for d in delta if d.startswith("- ")]
        added_lines = [d[2:] for d in delta if d.startswith("+ ")]
        detail.append(f"Hal {index + 1}: {label}")

        _write_diff_page(page, index, label, color, _wrap(new), removed_lines)

    save_pdf(out, out_path)
    summary = (
        f"{same} halaman sama, {changed} berubah, {added} ditambah, {removed} dihapus."
    )
    return ToolOutcome(
        output=out_path,
        summary=summary + "\n" + "\n".join(detail[:12]),
    )


def _wrap(text: str, width: int = 88) -> list[str]:
    lines: list[str] = []
    for paragraph in (text or "").split("\n"):
        current = ""
        for word in paragraph.split():
            if len(current) + len(word) + 1 > width:
                lines.append(current)
                current = word
            else:
                current = f"{current} {word}".strip()
        lines.append(current)
    return lines


def _write_diff_page(page, index, label, color, new_lines, removed_lines) -> None:
    page.insert_text((50, 60), f"Halaman {index + 1} — {label}", fontsize=16,
                     fontname="hebo", color=color)
    y = 92
    if removed_lines:
        page.insert_text((50, y), "Dihapus:", fontsize=11, fontname="hebo", color=(0.7, 0.15, 0.1))
        y += 18
        for line in removed_lines[:28]:
            page.insert_text((60, y), line, fontsize=9, fontname="cour", color=(0.6, 0.15, 0.1))
            y += 13
        y += 10

    page.insert_text((50, y), "Isi baru:", fontsize=11, fontname="hebo",
                     color=(0.1, 0.35, 0.6))
    y += 18
    for line in new_lines[:34]:
        if y > 790:
            break
        page.insert_text((60, y), line, fontsize=9, fontname="cour", color=(0.15, 0.15, 0.15))
        y += 13


# ------------------------------------------------------------------ registry

SPECS: list[ToolSpec] = [
    ToolSpec(
        id="unlock",
        label="Unlock PDF",
        group="PDF Security",
        description="Buka PDF berpassword lalu simpan tanpa password.",
        input_kind=INPUT_PDF_MULTI,
        run=unlock_pdf,
        params=(Param("password", "Password", "text", ""),),
    ),
    ToolSpec(
        id="protect",
        label="Protect PDF",
        group="PDF Security",
        description="Kunci PDF dengan password dan batasi izin.",
        input_kind=INPUT_PDF_MULTI,
        run=protect_pdf,
        params=(
            Param("user_password", "Password pembuka", "text", "",
                  help="Kosongkan = siapa pun bisa membuka, tapi izin tetap dibatasi."),
            Param("owner_password", "Password pemilik", "text", ""),
            Param("allow_print", "Boleh cetak", "bool", "1"),
            Param("allow_copy", "Boleh salin teks", "bool", "0"),
            Param("allow_modify", "Boleh ubah", "bool", "0"),
            Param("allow_annotate", "Boleh anotasi", "bool", "0"),
        ),
    ),
    ToolSpec(
        id="sign",
        label="Sign PDF",
        group="PDF Security",
        description="Tambahkan tanda tangan gambar atau sertifikat digital.",
        input_kind=INPUT_PDF_MULTI,
        run=sign_pdf,
        params=(
            Param("mode", "Jenis", "choice", "image",
                  choices=("image", "certificate"),
                  labels=("Gambar (cap visual)", "Sertifikat digital (.pfx/.p12)")),
            Param("image", "Berkas gambar", "file", "",
                  help="PNG/JPG, sebaiknya transparan."),
            Param("width", "Lebar (pt)", "float", "160"),
            Param("position", "Posisi", "choice", "bottom-right",
                  choices=("bottom-right", "bottom-left", "bottom-center",
                           "top-right", "top-left"),
                  labels=("Kanan bawah", "Kiri bawah", "Tengah bawah",
                          "Kanan atas", "Kiri atas")),
            Param("cert", "Berkas sertifikat", "file", ""),
            Param("cert_password", "Password sertifikat", "text", ""),
            Param("field", "Nama field signature", "text", "Signature1"),
            Param("reason", "Alasan", "text", "Disetujui"),
            Param("ranges", "Halaman (mode gambar)", "text", ""),
            Param("page", "Halaman (mode sertifikat)", "int", "1"),
        ),
    ),
    ToolSpec(
        id="redact",
        label="Redact PDF",
        group="PDF Security",
        description="Hapus teks permanen dengan kotak hitam.",
        input_kind=INPUT_PDF_MULTI,
        run=redact_pdf,
        params=(
            Param("mode", "Cara menentukan area", "choice", "terms",
                  choices=("terms", "rects"),
                  labels=("Cari kata kunci", "Koordinat (x0,y0,x1,y1;…)")),
            Param("terms", "Kata kunci (pisahkan dengan koma)", "text", ""),
            Param("rects", "Kotak", "text", "",
                  help="Contoh: 50,60,300,90;50,120,320,150"),
            Param("page", "Halaman (mode koordinat)", "int", "1",
                  help="Dipakai kalau kolom Halaman (mode kata kunci) kosong."),
            Param("ranges", "Halaman (mode kata kunci)", "text", "",
                  help="Kosongkan = semua halaman. Di mode koordinat, isi untuk "
                       "menyensor beberapa halaman sekaligus."),
        ),
    ),
    ToolSpec(
        id="compare",
        label="Compare PDF",
        group="PDF Security",
        description="Bandingkan isi teks dua PDF dan hasilkan laporan.",
        input_kind=INPUT_PDF_MULTI,
        run=compare_pdf,
    ),
]
