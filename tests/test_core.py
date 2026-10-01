"""Tes logika inti (tanpa GUI). Jalankan: .venv/bin/python -m pytest tests/ -q"""

from __future__ import annotations

import os
import sys

import pymupdf
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pdfocr.core import (  # noqa: E402
    OCR_DPI,
    SAVE_IMAGE,
    SAVE_RAW,
    SAVE_SEARCHABLE,
    Project,
)
from pdfocr.ocr import OcrWord, words_to_text  # noqa: E402


@pytest.fixture()
def sample(tmp_path):
    paths = []
    for name, count in (("alpha.pdf", 3), ("beta.pdf", 2)):
        doc = pymupdf.open()
        for i in range(count):
            page = doc.new_page(width=595, height=842)
            page.insert_text((72, 100), f"{name} page {i + 1}", fontsize=24)
        path = tmp_path / name
        doc.save(path)
        doc.close()
        paths.append(str(path))
    return paths


@pytest.fixture()
def project(sample):
    proj = Project()
    proj.add_files(sample)
    yield proj
    proj.close()


def labels(project: Project) -> list[tuple[str, int]]:
    return [
        (os.path.basename(project.source_label(i)), project.pages[i].src_index)
        for i in range(len(project.pages))
    ]


def test_add_files_flattens_pages(project):
    assert len(project.pages) == 5
    assert labels(project) == [
        ("alpha.pdf", 0),
        ("alpha.pdf", 1),
        ("alpha.pdf", 2),
        ("beta.pdf", 0),
        ("beta.pdf", 1),
    ]


def test_move_reorders_pages(project):
    project.move(0, 4)
    assert labels(project) == [
        ("alpha.pdf", 1),
        ("alpha.pdf", 2),
        ("beta.pdf", 0),
        ("beta.pdf", 1),
        ("alpha.pdf", 0),
    ]


def test_move_ignores_out_of_range(project):
    before = labels(project)
    project.move(0, 99)
    project.move(-1, 2)
    project.move(2, 2)
    assert labels(project) == before


def test_full_reverse_preserves_all_pages(project):
    """`move` memakai semantik cabut-sisip (bukan tukar), jadi pembalikan
    dilakukan dengan memindahkan tiap elemen ke posisi akhirnya."""
    original = list(project.pages)
    before = labels(project)

    for target_index, page in enumerate(reversed(original)):
        current_index = next(
            i for i, candidate in enumerate(project.pages) if candidate is page
        )
        if current_index != target_index:
            project.move(current_index, target_index)

    assert list(project.pages) == list(reversed(original))
    assert labels(project) == list(reversed(before))


def test_duplicate_copies_content_and_ocr_state(project):
    project.duplicate(0)
    assert len(project.pages) == 6
    assert project.pages[1].src_index == project.pages[0].src_index
    assert project.pages[1].words is None


def test_remove_many_and_prune_sources(project):
    project.remove_many([0, 1, 2])
    assert len(project.pages) == 2
    assert "d1" not in project.sources  # alpha.pdf sudah tidak dipakai
    assert labels(project) == [("beta.pdf", 0), ("beta.pdf", 1)]


def test_rotate_wraps_around(project):
    project.rotate(0, 90)
    project.rotate(0, 90)
    project.rotate(0, 90)
    project.rotate(0, 90)
    assert project.pages[0].rotation == 0


def test_effective_rotation_adds_source_rotation(tmp_path):
    rotated = tmp_path / "rotated.pdf"
    doc = pymupdf.open()
    doc.new_page(width=595, height=842).set_rotation(90)
    doc.save(rotated)
    doc.close()

    fresh = Project()
    fresh.add_files([str(rotated)])
    try:
        assert fresh.effective_rotation(0) == 90
        fresh.rotate(0, 90)
        assert fresh.effective_rotation(0) == 180
        assert fresh.build(SAVE_RAW)[0].rotation == 180
    finally:
        fresh.close()


def test_build_preserves_order_and_count(project):
    project.move(4, 0)
    out = project.build(SAVE_RAW)
    try:
        assert out.page_count == 5
        assert "beta.pdf page 2" in out[0].get_text()
    finally:
        out.close()


def test_rotation_applied_in_output(project):
    project.rotate(0, 90)
    out = project.build(SAVE_RAW)
    try:
        assert out[0].rotation == 90
    finally:
        out.close()


def test_text_layer_is_searchable(project):
    project.pages[0].words = [
        OcrWord("Hello", 100, 200, 220, 240),
        OcrWord("World", 240, 200, 360, 240),
    ]
    out = project.build(SAVE_SEARCHABLE)
    try:
        page = out[0]
        assert "Hello World" in page.get_text()
        assert page.search_for("Hello")
    finally:
        out.close()


def test_text_layer_position_matches_ocr_pixels(project):
    """x0 piksel 300dpi harus jadi x0 PDF = px * 72/300."""
    project.pages[0].words = [OcrWord("Marker", 300, 600, 420, 640)]
    out = project.build(SAVE_SEARCHABLE)
    try:
        rect = out[0].search_for("Marker")[0]
        assert rect.x0 == pytest.approx(300 * 72 / OCR_DPI, abs=1.5)
    finally:
        out.close()


def test_text_layer_is_invisible(project):
    """Teks OCR tidak boleh muncul secara visual di halaman hasil."""
    before = project.build(SAVE_RAW)
    before_pix = before[0].get_pixmap(dpi=100)
    before.close()

    project.pages[0].words = [OcrWord("Ghost", 100, 300, 400, 360)]
    after = project.build(SAVE_SEARCHABLE)
    after_pix = after[0].get_pixmap(dpi=100)
    after.close()

    assert before_pix.width == after_pix.width
    assert before_pix.samples == after_pix.samples, "render berubah => teks tak terlihat bocor"


def test_raw_mode_ignores_ocr_words(project):
    project.pages[0].words = [OcrWord("Ghost", 100, 300, 400, 360)]
    out = project.build(SAVE_RAW)
    try:
        assert "Ghost" not in out[0].get_text()
    finally:
        out.close()


def test_image_mode_drops_text(project):
    project.pages[0].words = [OcrWord("Ghost", 100, 300, 400, 360)]
    out = project.build(SAVE_IMAGE)
    try:
        assert out.page_count == 5
        assert out[0].get_text().strip() == ""
    finally:
        out.close()


def test_save_roundtrip(project, tmp_path):
    project.move(0, 4)  # cabut-sisip: alpha.pdf h1 pindah ke posisi akhir
    path = tmp_path / "out.pdf"
    project.save(str(path), SAVE_SEARCHABLE)
    out = pymupdf.open(path)
    try:
        assert out.page_count == 5
        assert "alpha.pdf page 1" in out[4].get_text()
        assert "beta.pdf page 2" in out[3].get_text()
    finally:
        out.close()


def test_search_text_finds_matching_lines(project):
    project.pages[0].words = [OcrWord("Invoice", 72, 100, 200, 130)]
    project.pages[2].words = [OcrWord("Invoice", 72, 100, 200, 130)]
    hits = project.search_text("invoice")
    assert [i for i, _ in hits] == [0, 2]
    assert project.search_text("tidak-ada") == []


def test_search_text_respects_new_order(project):
    project.pages[0].words = [OcrWord("ZebraDoc", 72, 100, 200, 130)]
    project.pages[4].words = [OcrWord("Invoice", 72, 100, 200, 130)]
    assert [i for i, _ in project.search_text("invoice")] == [4]

    project.move(4, 0)
    assert [i for i, _ in project.search_text("invoice")] == [0]


def test_page_text_reads_back(project):
    project.pages[0].words = [
        OcrWord("Hello", 100, 200, 220, 240),
        OcrWord("World", 240, 200, 360, 240),
    ]
    assert project.page_text(0).strip() == "Hello World"
    assert project.page_text(4) == ""


def test_words_to_text_groups_lines():
    words = [
        OcrWord("satu", 100, 100, 200, 130),
        OcrWord("dua", 210, 102, 300, 132),
        OcrWord("tiga", 100, 300, 200, 330),
    ]
    assert words_to_text(words).splitlines() == ["satu dua", "tiga"]


def test_words_to_text_keeps_descenders_on_same_line():
    """Kata ber-descender ('you') punya y0 lebih rendah dari kata sebaris.

    Pengelompokan harus pakai titik tengah vertikal, bukan y0, agar
    'Thank you for your business.' tidak terpecah jadi beberapa baris.
    """
    words = [
        OcrWord("Thank", 301, 909, 485, 960),
        OcrWord("for", 631, 909, 706, 960),
        OcrWord("business.", 877, 909, 1150, 960),
        OcrWord("you", 506, 922, 606, 972),
        OcrWord("your", 728, 922, 855, 972),
    ]
    assert words_to_text(words).splitlines() == ["Thank you for your business."]


def test_words_to_text_orders_columns_left_to_right():
    words = [
        OcrWord("kanan", 800, 100, 900, 130),
        OcrWord("kiri", 100, 102, 200, 132),
    ]
    assert words_to_text(words).splitlines() == ["kiri kanan"]


def test_group_lines_orders_top_to_bottom():
    from pdfocr.ocr import group_lines

    words = [
        OcrWord("bawah", 100, 500, 200, 530),
        OcrWord("atas", 100, 100, 200, 130),
    ]
    groups = group_lines(words)
    assert [[w.text for w in g] for g in groups] == [["atas"], ["bawah"]]


def test_text_layer_line_order_survives_descenders(project):
    """Baris dengan kata ber-descender harus tetap satu baris di PDF hasil."""
    project.pages[0].words = [
        OcrWord("Thank", 301, 909, 485, 960),
        OcrWord("you", 506, 922, 606, 972),
        OcrWord("business.", 877, 909, 1150, 960),
    ]
    out = project.build(SAVE_SEARCHABLE)
    try:
        lines = out[0].get_text().strip().splitlines()
        assert lines[-1] == "Thank you business."
    finally:
        out.close()


def test_empty_project_builds_empty_doc():
    proj = Project()
    out = proj.build()
    try:
        assert out.page_count == 0
    finally:
        out.close()
        proj.close()


def test_add_files_reports_broken_pdf(tmp_path, sample):
    broken = tmp_path / "broken.pdf"
    broken.write_bytes(b"bukan pdf sama sekali")
    proj = Project()
    added, errors = proj.add_files(sample[:1] + [str(broken)])
    try:
        assert added == 3
        assert len(errors) == 1
        assert "broken.pdf" in errors[0]
    finally:
        proj.close()

# ------------------------------------------------------------- berkas gambar
#
# Gambar bisa di-insert dan jadi halaman di preview (RENDERABLE_KINDS), tapi
# dokumen gambarnya non-PDF sehingga `insert_pdf` pernah melempar
# "source or target not a PDF" saat proyek disimpan.

@pytest.fixture()
def scan(tmp_path):
    from PIL import Image, ImageDraw

    path = tmp_path / "scan.png"
    image = Image.new("RGB", (1240, 1754), "white")
    ImageDraw.Draw(image).text((90, 120), "HASIL SCAN", fill="black")
    image.save(path)
    return str(path)


def test_image_file_becomes_a_page(tmp_path, scan):
    proj = Project()
    try:
        added, errors = proj.add_files([scan])
        assert added == 1
        assert errors == []
        assert len(proj.pages) == 1
        assert proj.sources[proj.pages[0].doc_key].kind == "image"
    finally:
        proj.close()


def test_build_saves_image_source(tmp_path, scan, sample):
    proj = Project()
    proj.add_files([scan] + sample[:1])
    out = tmp_path / "gabung.pdf"
    try:
        proj.save(str(out), SAVE_SEARCHABLE)
        doc = pymupdf.open(out)
        try:
            assert doc.page_count == len(proj.pages) == 4
            assert doc[0].get_images(), "halaman gambar harus berisi gambar"
            assert not doc[1].get_images(), "halaman PDF asli tetap utuh"
            assert doc[1].get_text().strip()
        finally:
            doc.close()
    finally:
        proj.close()


def test_image_source_saves_in_every_mode(tmp_path, scan):
    proj = Project()
    proj.add_files([scan])
    try:
        for mode in (SAVE_SEARCHABLE, SAVE_IMAGE, SAVE_RAW):
            out = tmp_path / f"{mode}.pdf"
            proj.save(str(out), mode)
            doc = pymupdf.open(out)
            try:
                assert doc.page_count == 1
                assert doc[0].get_images(), f"{mode} kehilangan gambar"
            finally:
                doc.close()
    finally:
        proj.close()


def test_image_page_keeps_source_geometry(tmp_path, scan):
    """Halaman hasil harus seukuran `page.rect` sumber agar teks OCR pas."""
    proj = Project()
    proj.add_files([scan])
    try:
        expected = proj.page_at(0).rect
        doc = proj.build(SAVE_SEARCHABLE)
        try:
            got = doc[0].rect
            assert (round(got.width), round(got.height)) == (
                round(expected.width),
                round(expected.height),
            )
        finally:
            doc.close()
    finally:
        proj.close()


def test_image_source_rotate_and_ocr(tmp_path, scan):
    from pdfocr.ocr import run_ocr

    proj = Project()
    proj.add_files([scan])
    try:
        words = run_ocr(proj.page_at(0), lang="eng", dpi=OCR_DPI)
        proj.pages[0].words = words
        proj.rotate(0, 90)

        out = tmp_path / "rotasi.pdf"
        proj.save(str(out), SAVE_SEARCHABLE)
        doc = pymupdf.open(out)
        try:
            assert doc[0].rotation == 90
            assert doc[0].search_for("SCAN"), "teks OCR harus bisa dicari"
        finally:
            doc.close()
    finally:
        proj.close()
