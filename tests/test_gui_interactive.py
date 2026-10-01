"""Uji GUI interaktif: klik tombol tambah, berkas gambar, mode simpan, drag.

Butuh display. Jalankan:
    xvfb-run -a .venv/bin/python tests/test_gui_interactive.py

Melengkapi tests/test_gui.py (smoke) dengan alur yang belum tersentuh:
dialog tambah berkas sungguhan, berkas gambar, dan ketiga mode simpan.
"""

from __future__ import annotations

import os
import sys
import threading
import time
import traceback
from tkinter import filedialog, messagebox

import pymupdf
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

FAILURES: list[str] = []


def check(label, condition, detail=""):
    if condition:
        print(f"  PASS  {label}")
    else:
        print(f"  FAIL  {label} {detail}")
        FAILURES.append(label)


class FakeEvent:
    def __init__(self, widget, x_root=0, y_root=0, x=0, y=0, state=0):
        self.widget = widget
        self.x_root, self.y_root = x_root, y_root
        self.x, self.y = x, y
        self.state, self.num = state, 1


def make_pdfs(folder, names):
    paths = []
    for name, count in names:
        doc = pymupdf.open()
        for i in range(count):
            page = doc.new_page(width=595, height=842)
            page.insert_text((72, 100), f"{name} halaman {i + 1}", fontsize=24)
        path = os.path.join(folder, f"{name}.pdf")
        doc.save(path)
        doc.close()
        paths.append(path)
    return paths


def make_scan_png(path, text="HASIL SCAN DOKUMEN"):
    image = Image.new("RGB", (1240, 1754), "white")
    draw = ImageDraw.Draw(image)
    font = None
    for candidate in ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                      "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"):
        if os.path.exists(candidate):
            font = ImageFont.truetype(candidate, 54)
            break
    draw.text((90, 200), text, fill="black", font=font)
    image.save(path)
    return path


def find_button(app, prefix):
    """Tombol ada di header (Gabung & Simpan, + Tambah) dan bar aksi
    (Putar, Duplikat, Hapus)."""
    buttons = list(app.header.action_buttons) + list(app._action_bar.winfo_children())
    for button in _flatten_buttons(buttons):
        if str(button.cget("text")).startswith(prefix):
            return button
    return None


def _flatten_buttons(widgets):
    for widget in widgets:
        if widget.winfo_class() in ("TButton", "Button"):
            yield widget
        yield from _flatten_buttons(widget.winfo_children())


def badge(app, index):
    return str(app.grid._cells[index]._badge.cget("text"))


def photo(app, index):
    return app.grid._cells[index]._page_state.get("photo")


def labels_of(app):
    return [(app.project.source_label(i), app.project.pages[i].src_index)
            for i in range(len(app.project.pages))]


def pump(app, seconds=0.5):
    deadline = time.time() + seconds
    while time.time() < deadline:
        app.update()
        time.sleep(0.01)


def drag(app, from_index, to_index):
    src, dst = app.grid._cells[from_index], app.grid._cells[to_index]
    src_xy = (src.winfo_rootx() + src.winfo_width() // 2,
              src.winfo_rooty() + src.winfo_height() // 2)
    dst_xy = (dst.winfo_rootx() + dst.winfo_width() // 2,
              dst.winfo_rooty() + dst.winfo_height() // 2)
    app.grid._on_press(FakeEvent(src, *src_xy))
    app.grid._on_motion(FakeEvent(src, *dst_xy))
    app.grid._on_release(FakeEvent(src, *dst_xy))
    pump(app, 0.5)


def save_via_gui(app, out_path, label, timeout=30):
    """Klik 'Gabung & Simpan' sungguhan, tunggu worker selesai."""
    app.show_page()
    pump(app, 0.3)
    app.save_mode.set(label)
    app._sync_mode()
    filedialog.asksaveasfilename = lambda *a, **k: out_path
    real_worker = app._save_worker
    done = threading.Event()

    def wrapped(path):
        try:
            real_worker(path)
        finally:
            done.set()

    app._save_worker = wrapped
    try:
        find_button(app, "Gabung & Simpan").invoke()
        deadline = time.time() + timeout
        while not done.is_set() and time.time() < deadline:
            app.update()
            time.sleep(0.02)
        pump(app, 0.8)
        return done.is_set()
    finally:
        app._save_worker = real_worker


def inspect(path):
    doc = pymupdf.open(path)
    try:
        return {
            "pages": doc.page_count,
            "text": any(p.get_text().strip() for p in doc),
            "scan_text": any("SCAN" in p.get_text().upper() for p in doc),
            "imgs": [len(p.get_images()) for p in doc],
            "rot": [p.rotation for p in doc],
        }
    finally:
        doc.close()


def main() -> int:
    from pdfocr.core import SAVE_IMAGE, SAVE_LABELS, SAVE_RAW, SAVE_SEARCHABLE
    from pdfocr.gui.app import DEFAULT_ADD_LABEL, MainWindow
    from pdfocr.tools import get as get_tool

    work = "/tmp/opencode/gui_interactive"
    os.makedirs(work, exist_ok=True)
    for name in os.listdir(work):
        os.remove(os.path.join(work, name))

    real_open = filedialog.askopenfilenames
    real_save = filedialog.asksaveasfilename
    real_info, real_error = messagebox.showinfo, messagebox.showerror
    real_yesno = messagebox.askyesno
    messagebox.showinfo = lambda *a, **k: None
    messagebox.showerror = lambda title, *a, **k: FAILURES.append(f"pop-up error: {title}")
    messagebox.askyesno = lambda *a, **k: True

    app = MainWindow()
    pump(app, 0.6)
    print("jendela dibuat")

    try:
        # ---- klik tombol "+ Tambah" sungguhan, dialog dipalsukan ----
        pdfs = make_pdfs(work, [("satu", 2), ("dua", 3)])
        png = make_scan_png(os.path.join(work, "pindaian.png"))
        add_button = find_button(app, DEFAULT_ADD_LABEL)
        check("tombol + Tambah ada di header", add_button is not None)

        filedialog.askopenfilenames = lambda *a, **k: tuple(pdfs)
        add_button.invoke()
        pump(app, 0.8)

        check("5 halaman masuk lewat tombol", len(app.project.pages) == 5,
              len(app.project.pages))
        check("status menyebut jumlah halaman",
              "5 halaman" in app.status_var.get(), app.status_var.get())
        check("5 thumbnail ter-render", len(app.grid._cells) == 5, len(app.grid._cells))
        check("semua sel punya foto", all(photo(app, i) is not None for i in range(5)))
        check("badge sel 0", "satu.pdf" in badge(app, 0) and "[PDF]" in badge(app, 0),
              badge(app, 0))
        check("judul halaman benar di badge", "h1" in badge(app, 0), badge(app, 0))

        filedialog.askopenfilenames = lambda *a, **k: ()
        add_button.invoke()
        pump(app, 0.4)
        check("dialog batal tidak menambah berkas", len(app.project.pages) == 5,
              len(app.project.pages))

        # ---- berkas rusak dilaporkan, tidak crash ----
        broken = os.path.join(work, "rusak.pdf")
        with open(broken, "wb") as fh:
            fh.write(b"ini bukan pdf")
        filedialog.askopenfilenames = lambda *a, **k: (broken,)
        add_button.invoke()
        pump(app, 0.6)
        check("PDF rusak dilaporkan lewat status",
              "rusak.pdf" in app.status_var.get(), app.status_var.get())
        check("PDF rusak tidak jadi halaman", len(app.project.pages) == 5,
              len(app.project.pages))
        os.remove(broken)

        # ---- tombol tambah mengikuti tool aktif (butuh jenis gambar) ----
        app._open_tool(get_tool("scan"))
        pump(app, 0.5)
        check("tool aktif = scan",
              getattr(app.tools.spec, "id", None) == "scan",
              getattr(app.tools.spec, "id", None))
        add_button = find_button(app, "+ Tambah")
        label_now = str(add_button.cget("text"))
        check("label tombol menyesuaikan jenis input",
              label_now != DEFAULT_ADD_LABEL and "ambar" in label_now, label_now)

        # ---- gambar jadi halaman + thumbnail ----
        filedialog.askopenfilenames = lambda *a, **k: (png,)
        add_button.invoke()
        pump(app, 1.0)
        check("gambar jadi 1 halaman", len(app.project.pages) == 6, len(app.project.pages))
        check("gambar punya thumbnail", photo(app, 5) is not None)
        check("badge sel gambar", "[Gambar]" in badge(app, 5) and "pindaian.png" in badge(app, 5),
              badge(app, 5))

        # ---- OCR pada halaman gambar, lalu rotasi ----
        from pdfocr.ocr import run_ocr
        words = run_ocr(app.project.page_at(5), lang="eng", dpi=300)
        check("OCR menemukan kata di gambar", len(words) > 2, len(words))
        app.project.pages[5].words = words
        app.project.rotate(5, 90)
        app._refresh_thumbs()
        pump(app, 0.6)
        check("badge gambar menunjukkan rotasi", "90" in badge(app, 5), badge(app, 5))
        check("badge gambar menunjukkan OCR", "OCR" in badge(app, 5), badge(app, 5))

        # ---- ketiga mode simpan lewat tombol sungguhan ----
        seen = {}
        for key, name in ((SAVE_SEARCHABLE, "searchable.pdf"),
                          (SAVE_IMAGE, "image.pdf"),
                          (SAVE_RAW, "raw.pdf")):
            out = os.path.join(work, name)
            finished = save_via_gui(app, out, SAVE_LABELS[key])
            check(f"simpan {key}: worker selesai", finished)
            check(f"simpan {key}: berkas ada", os.path.exists(out))
            if os.path.exists(out):
                seen[key] = inspect(out)
            app._open_tool(get_tool("scan"))  # kembali ke panel tool
            pump(app, 0.3)

        check("searchable: 6 halaman", seen.get(SAVE_SEARCHABLE, {}).get("pages") == 6,
              seen.get(SAVE_SEARCHABLE))
        check("searchable: teks OCR gambar terbawa",
              seen.get(SAVE_SEARCHABLE, {}).get("scan_text"), seen.get(SAVE_SEARCHABLE))
        check("searchable: halaman gambar berisi gambar",
              seen.get(SAVE_SEARCHABLE, {}).get("imgs", [0] * 6)[5] >= 1,
              seen.get(SAVE_SEARCHABLE, {}).get("imgs"))
        check("searchable: rotasi 90 ikut tersimpan",
              seen.get(SAVE_SEARCHABLE, {}).get("rot", [0] * 6)[5] == 90,
              seen.get(SAVE_SEARCHABLE, {}).get("rot"))

        check("image: 6 halaman", seen.get(SAVE_IMAGE, {}).get("pages") == 6,
              seen.get(SAVE_IMAGE))
        check("image: semua halaman bergambar",
              all(n >= 1 for n in seen.get(SAVE_IMAGE, {}).get("imgs", [])),
              seen.get(SAVE_IMAGE, {}).get("imgs"))
        check("image: tidak ada teks", not seen.get(SAVE_IMAGE, {}).get("text"),
              seen.get(SAVE_IMAGE))

        check("raw: 6 halaman", seen.get(SAVE_RAW, {}).get("pages") == 6, seen.get(SAVE_RAW))
        check("raw: teks asli PDF tetap ada", seen.get(SAVE_RAW, {}).get("text"),
              seen.get(SAVE_RAW))

        # ---- drag reorder ----
        app.show_page()
        pump(app, 0.5)
        before = labels_of(app)
        drag(app, 0, 4)
        after = labels_of(app)
        check("drag memindahkan halaman ke posisi tujuan",
              after[4] == before[0] and after[0] != before[0], f"{before} -> {after}")
        check("drag tidak ada halaman hilang/duplikat", sorted(after) == sorted(before),
              f"{sorted(before)} vs {sorted(after)}")
        check("grid tetap 6 sel", len(app.grid._cells) == 6, len(app.grid._cells))
        check("thumbnail masih ada setelah drag",
              all(photo(app, i) is not None for i in range(6)))

        # ---- duplikat / hapus / putar lewat tombol aksi ----
        app.grid.select(0)
        pump(app, 0.3)
        find_button(app, "Duplikat").invoke()
        pump(app, 0.6)
        check("Duplikat menambah halaman", len(app.project.pages) == 7, len(app.project.pages))
        find_button(app, "Hapus").invoke()
        pump(app, 0.6)
        check("Hapus mengembalikan jumlah", len(app.project.pages) == 6, len(app.project.pages))

        # Hapus itu membersihkan seleksi, jadi Putar butuh seleksi baru.
        rot_before = app.project.effective_rotation(0)
        find_button(app, "Putar").invoke()          # tanpa seleksi: tidak apa-apa
        pump(app, 0.3)
        check("Putar tanpa seleksi tidak merusak apa pun",
              app.project.effective_rotation(0) == rot_before,
              app.project.effective_rotation(0))

        app.grid.select(0)
        pump(app, 0.3)
        find_button(app, "Putar").invoke()          # "Putar ↺" = -90
        pump(app, 0.4)
        check("tombol Putar memutar halaman terpilih",
              app.project.effective_rotation(0) == (rot_before - 90) % 360,
              f"{rot_before} -> {app.project.effective_rotation(0)}")

        # ---- Bersihkan mengosongkan proyek ----
        find_button(app, "Bersihkan").invoke()
        pump(app, 0.9)
        check("Bersihkan mengosongkan daftar",
              not app.project.pages and not app.project.files,
              (len(app.project.pages), len(app.project.files)))
        check("grid ikut kosong", len(app.grid._cells) == 0, len(app.grid._cells))

        check("semua tombol aktif sampai akhir", all(
            str(w.cget("state")) != "disabled" for w in app._lockable),
            [str(w.cget("state")) for w in app._lockable
             if str(w.cget("state")) == "disabled"])

    except Exception:
        traceback.print_exc()
        FAILURES.append("exception")
    finally:
        filedialog.askopenfilenames = real_open
        filedialog.asksaveasfilename = real_save
        messagebox.showinfo, messagebox.showerror = real_info, real_error
        messagebox.askyesno = real_yesno
        try:
            app.project.close()
            app.destroy()
        except Exception:
            pass

    print()
    if FAILURES:
        print(f"=== {len(FAILURES)} GAGAL ===")
        for item in FAILURES:
            print("  -", item)
        return 1
    print("=== SEMUA CEK GUI INTERAKTIF LULUS ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())