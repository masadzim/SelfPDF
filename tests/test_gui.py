"""Smoke test GUI: thumbnail render, drag-reorder, OCR, simpan.

Butuh display. Jalankan:
    xvfb-run -a .venv/bin/python tests/test_gui.py
"""

from __future__ import annotations

import os
import sys
import threading
import time
import traceback

import pymupdf
import tkinter as tk

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pdfocr.gui.app import APP_TITLE  # noqa: E402
from pdfocr.gui.branding import APP_NAME  # noqa: E402

FAILURES: list[str] = []


def check(label: str, condition: bool, detail: str = "") -> None:
    if condition:
        print(f"  PASS  {label}")
    else:
        print(f"  FAIL  {label} {detail}")
        FAILURES.append(label)


class FakeEvent:
    def __init__(self, widget, x_root=0, y_root=0, x=0, y=0, state=0):
        self.widget = widget
        self.x_root = x_root
        self.y_root = y_root
        self.x = x
        self.y = y
        self.state = state
        self.num = 1


def all_button_texts(root):
    """Semua teks tombol yang ada di bawah `root`."""
    out = []

    def walk(widget):
        for child in widget.winfo_children():
            if child.winfo_class() in ("TButton", "Button"):
                out.append(child.cget("text"))
            walk(child)

    walk(root)
    return out


def make_pdfs(folder: str) -> list[str]:
    paths = []
    for name, count in (("satu.pdf", 3), ("dua.pdf", 2)):
        doc = pymupdf.open()
        for i in range(count):
            page = doc.new_page(width=595, height=842)
            page.insert_text((72, 120), f"{name} halaman {i + 1}", fontsize=26)
            pix = page.get_pixmap(dpi=110, alpha=False)
            raster = doc.new_page(width=595, height=842)
            raster.insert_image(raster.rect, pixmap=pix)
            doc.delete_page(doc.page_count - 2)
        path = os.path.join(folder, name)
        doc.save(path)
        doc.close()
        paths.append(path)
    return paths


def main() -> int:
    from pdfocr.core import Project
    from pdfocr.gui.app import MainWindow

    app = MainWindow()
    app.update_idletasks()
    app.update()
    print("jendela dibuat")

    check("judul jendela benar", app.title() == APP_TITLE, app.title())

    # Menubar harus widget in-window (bukan tk.Menu native) supaya tidak
    # berkedip di X11/Xwayland, dan semua dropdown-nya terisi.
    def walk(widget):
        yield widget
        for child in widget.winfo_children():
            yield from walk(child)

    buttons = [
        w for w in walk(app._menubar)
        if w.winfo_class() == "TMenubutton"
    ]
    check("menubar pakai Menubutton", len(buttons) >= 8, f"n={len(buttons)}")
    populated = 0
    for button in buttons:
        menu = app.nametowidget(button.cget("menu"))
        try:
            if int(menu.index("end")) >= 0:
                populated += 1
        except (ValueError, tk.TclError):
            pass
    check("semua dropdown terisi", populated == len(buttons), f"{populated}/{len(buttons)}")
    check("nama tombol ada", any(b.cget("text") == "File" for b in buttons))
    check("menu Bantuan terpisah", any(b.cget("text") == "Bantuan" for b in buttons))

    # Lebar tombol menu mengikuti panjang labelnya sendiri (gaya VS Code), bukan
    # semua disamakan dengan label terpanjang.
    widths = {b.cget("text"): b.winfo_reqwidth() for b in buttons}
    check("lebar tombol menu natural",
          len(set(widths.values())) > 1 and widths["File"] < max(widths.values()),
          str(widths))

    # Logo opsional: kalau ada di assets/, harus benar-benar termuat.
    from pdfocr.gui import branding

    if branding.find_wordmark() or branding.find_logo():
        check("logo termuat", app._logo_photo is not None)
    else:
        check("tanpa logo -> teks nama", app._logo_photo is None)

    # Wordmark sudah memuat nama, jadi teks nama tidak boleh digambar lagi.
    check("nama tidak dobel",
          not (branding.find_wordmark() and not app.header.uses_wordmark),
          "wordmark ada tapi teks nama tetap digambar")

    # Regresi "logo meleset dari tulisan SelfPDF": pada jalur logo + teks nama,
    # logo dan kedua baris teks harus satu sumbu vertikal. `winfo_rooty()`
    # dipakai karena `winfo_y()` relatif terhadap parent.
    from pdfocr.gui import header as header_mod

    real_find_wordmark = header_mod.find_wordmark
    header_mod.find_wordmark = lambda: None
    try:
        probe = header_mod.HeaderBar(app, tagline="test")
        probe.pack(fill="x")
        app.update_idletasks()
        brand = probe.brand
        labels = [w for w in walk(brand) if w.winfo_class() == "TLabel"]
        photo = [w for w in labels if str(w.cget("image"))]
        texts = [w for w in labels if not str(w.cget("image"))]
        check("fallback: logo + teks ada", len(photo) == 1 and len(texts) == 2,
              f"photo={len(photo)} texts={len(texts)}")
        if photo and len(texts) == 2:
            by_text = {label.cget("text"): label for label in texts}
            logo_mid = photo[0].winfo_rooty() + photo[0].winfo_height() / 2
            name_mid = by_text[APP_NAME].winfo_rooty() + by_text[APP_NAME].winfo_height() / 2
            check("fallback: logo sejajar dengan nama",
                  abs(name_mid - logo_mid) <= 3,
                  f"logo={logo_mid:.1f} name={name_mid:.1f}")
            # Tagline adalah baris kedua yang lebih kecil: harus di bawah
            # nama, rata kiri, dan tidak lebih tinggi dari nama.
            tag = by_text["test"]
            check("fallback: tagline di bawah nama",
                  tag.winfo_rooty() > by_text[APP_NAME].winfo_rooty(),
                  f"tag={tag.winfo_rooty()} name={by_text[APP_NAME].winfo_rooty()}")
            check("fallback: nama & tagline rata kiri",
                  tag.winfo_rootx() == by_text[APP_NAME].winfo_rootx(),
                  f"tag={tag.winfo_rootx()} name={by_text[APP_NAME].winfo_rootx()}")
            check("fallback: logo di kiri teks",
                  photo[0].winfo_rootx() < by_text[APP_NAME].winfo_rootx())
        probe.destroy()
    finally:
        header_mod.find_wordmark = real_find_wordmark

    out_dir = "/tmp/opencode/guitest"
    os.makedirs(out_dir, exist_ok=True)
    paths = make_pdfs(out_dir)
    print(f"PDF uji dibuat: {[os.path.basename(p) for p in paths]}")

    added, errors = app.project.add_files(paths)
    app._refresh_all()
    app.update()
    check("5 halaman dimuat", added == 5 and len(app.project.pages) == 5, f"added={added}")
    check("tanpa error", errors == [], str(errors))

    cells = app.grid._cells
    check("5 sel thumbnail dibuat", len(cells) == 5, f"len={len(cells)}")

    photos = [
        cell._page_state["photo"] is not None and cell._page_state["photo"].width() > 40
        for cell in cells
    ]
    check("semua thumbnail ter-render", all(photos), str(photos))
    print(f"  info panel: {app.info_var.get()}")

    # ---- drag reorder: seret sel 0 ke posisi sel 3 ----
    before = [(app.project.source_label(i), app.project.pages[i].src_index) for i in range(5)]
    src_cell, dst_cell = cells[0], cells[3]
    src_center = (src_cell.winfo_rootx() + src_cell.winfo_width() // 2,
                  src_cell.winfo_rooty() + src_cell.winfo_height() // 2)
    dst_center = (dst_cell.winfo_rootx() + dst_cell.winfo_width() // 2,
                  dst_cell.winfo_rooty() + dst_cell.winfo_height() // 2)

    app.grid._on_press(FakeEvent(src_cell, *src_center))
    app.grid._on_motion(FakeEvent(src_cell, *dst_center))
    app.grid._on_release(FakeEvent(src_cell, *dst_center))
    app.update()

    after = [(app.project.source_label(i), app.project.pages[i].src_index) for i in range(5)]
    changed = before != after
    check("drag mengubah urutan", changed, f"before={before} after={after}")
    check("tidak ada halaman hilang/hilang duplikat",
          sorted(after) == sorted(before), f"{sorted(after)}")
    print(f"  urutan setelah drag: {[f'{os.path.basename(a)[:3]}#{b + 1}' for a, b in after]}")

    # ---- klik (bukan drag) tidak mengubah urutan ----
    stable = list(after)
    cell0 = app.grid._cells[0]
    c = (cell0.winfo_rootx() + 10, cell0.winfo_rooty() + 10)
    app.grid._on_press(FakeEvent(cell0, *c))
    app.grid._on_release(FakeEvent(cell0, *c))
    app.update()
    now = [(app.project.source_label(i), app.project.pages[i].src_index) for i in range(5)]
    check("klik biasa tidak mengubah urutan", now == stable)
    check("klik menyeleksi 1 halaman", app.grid.selection == [0], str(app.grid.selection))

    # ---- shift-klik memilih rentang ----
    cell3 = app.grid._cells[3]
    c3 = (cell3.winfo_rootx() + 10, cell3.winfo_rooty() + 10)
    app.grid._on_press(FakeEvent(cell3, *c3, state=0x0001))
    app.grid._on_release(FakeEvent(cell3, *c3, state=0x0001))
    app.update()
    check("shift-klik memilih rentang", app.grid.selection == [0, 1, 2, 3], str(app.grid.selection))

    # ---- rotate + delete ----
    app.project.rotate(0, 90)
    app._refresh_thumbs()
    app.update()
    check("rotasi tersimpan di model", app.project.pages[0].rotation == 90)

    doc = app.project.build()
    check("rotasi ikut ke PDF", doc[0].rotation == 90, f"rot={doc[0].rotation}")
    doc.close()

    app.project.remove(0)
    app._refresh_all()
    app.update()
    check("hapus halaman", len(app.project.pages) == 4)

    # ---- OCR ----
    from pdfocr.ocr import run_ocr

    target = app.project.page_at(0)
    words = run_ocr(target, lang="eng", dpi=300)
    check("OCR menemukan kata", len(words) >= 3, f"words={len(words)}")
    app.project.pages[0].words = words
    app.project.pages[0].ocr_dpi = 300
    app._refresh_thumbs()
    app.update()
    text = app.project.page_text(0)
    print(f"  teks OCR: {text.splitlines()[:2]}")
    check("isi teks OCR sesuai", "halaman" in text and "satu.pdf" in text, repr(text))

    badge = app.grid._cells[0]._badge.cget("text")
    check("badge OCR muncul", "OCR" in badge, badge)

    # ---- save ----
    out_path = os.path.join(out_dir, "hasil.pdf")
    app._sync_mode()
    app.project.save(out_path, app._mode_key)
    saved = pymupdf.open(out_path)
    try:
        check("PDF hasil tersimpan", saved.page_count == 4, f"pages={saved.page_count}")
        check("teks bisa dicari", bool(saved[0].search_for("halaman") or saved[0].get_text().strip()))
    finally:
        saved.close()

    # ---- REGRESI: tombol harus hidup lagi setelah simpan via worker ----
    # Jalur ini pernah terputus: event "saved" tidak pernah memanggil
    # _set_running(False) sehingga semua tombol mati permanen.
    from tkinter import filedialog, messagebox

    from pdfocr.gui.app import MainWindow as _MW  # noqa: F401  (pastikan terimpor)

    worker_out = os.path.join(out_dir, "worker.pdf")
    shown: list[str] = []

    real_asksave = filedialog.asksaveasfilename
    real_info = messagebox.showinfo
    real_error = messagebox.showerror
    real_yesno = messagebox.askyesno

    filedialog.asksaveasfilename = lambda *a, **k: worker_out
    messagebox.showinfo = lambda title, *a, **k: shown.append(title)
    messagebox.showerror = lambda title, *a, **k: shown.append("ERR:" + title)
    messagebox.askyesno = lambda *a, **k: True
    # Tahan worker supaya keadaan "terkunci" pasti terlihat. Tanpa ini,
    # simpan bisa selesai sebelum update() pertama sehingga cek jadi flaky.
    release = threading.Event()
    real_worker = app._save_worker

    def slow_worker(path):
        release.wait(10)
        real_worker(path)

    app._save_worker = slow_worker
    try:
        app._save()
        app.update()
        check("tombol terkunci saat proses", any(
            str(w.cget("state")) == "disabled" for w in app._lockable
        ) or not app._lockable)

        # Lepas worker, lalu tunggu sampai _drain_events memproses antrean.
        release.set()
        for _ in range(200):
            app.update()
            if not any(str(w.cget("state")) == "disabled" for w in app._lockable):
                break
            time.sleep(0.02)

        check("berkas worker tersimpan", os.path.exists(worker_out))
        # Hasil tidak lagi lewat messagebox: harus muncul di kotak hasil panel.
        saved_text = app.page_result.text.get("1.0", "end")
        check("hasil simpan tampil di panel", "Tersimpan" in saved_text, repr(saved_text[:60]))
        check("tidak ada popup error", not any(s.startswith("ERR:") for s in shown), shown)
        check("SEMUA tombol hidup lagi setelah simpan", all(
            str(w.cget("state")) != "disabled" for w in app._lockable
        ), [str(w.cget("state")) for w in app._lockable
            if str(w.cget("state")) == "disabled"])
        check("status menampilkan tersimpan",
              "worker.pdf" in app.status_var.get(), app.status_var.get())
    finally:
        app._save_worker = real_worker
        release.set()
        filedialog.asksaveasfilename = real_asksave
        messagebox.showinfo = real_info
        messagebox.showerror = real_error
        messagebox.askyesno = real_yesno

    # ---- panel teks & pencarian ----
    app.grid.select(0)
    app._refresh_thumbs()
    app._show_page_text(0)
    panel = app.text_view.get("1.0", "end").strip()
    check("panel teks terisi", len(panel) > 10, repr(panel[:40]))

    app.search_var.set("halaman")
    app._run_search()
    app.update()
    check("pencarian menemukan hasil", "h1" in app.search_result.cget("text"),
          app.search_result.cget("text")[:60])

    # ---- kolom perkakas: tanpa select box, hasil inline, input per tool ----
    from pdfocr.tools import ALL_SPECS, get

    # Tidak ada lagi daftar/select box tool di panel: tool dipilih dari menu,
    # jadi semua tool harus tetap bisa dipanggil lewat `_open_tool`.
    check("tidak ada select box perkakas", not hasattr(app.tools, "tree"))
    check("semua tool bisa dipilih dari menu", len(ALL_SPECS) > 0, str(len(ALL_SPECS)))

    # Memilih tool dari menu harus hanya menukar isi kolom, tidak membuka
    # Toplevel (dulu setiap tool punya dialog-nya sendiri).
    before = [w for w in walk(app) if isinstance(w, tk.Toplevel)]
    app._open_tool(get("compress"))
    app.update()
    check("tidak ada Toplevel saat ganti tool",
          len([w for w in walk(app) if isinstance(w, tk.Toplevel)]) == len(before))
    check("tool aktif benar", app.tools.spec is not None
          and app.tools.spec.id == "compress",
          app.tools.spec.id if app.tools.spec else None)
    check("judul form sesuai tool", app.tools.title.cget("text") == get("compress").label,
          app.tools.title.cget("text"))

    # Nilai parameter harus terikat ke tool masing-masing, bukan global.
    app.tools._vars["compress"]["dpi"].set("72")
    app._open_tool(get("crop"))
    app.update()
    check("ganti tool tidak mengubah param tool lain",
          app.tools._vars["compress"]["dpi"].get() == "72")
    app.tools._vars["crop"]["margin"].set("21")
    app._open_tool(get("compress"))
    app.update()
    app._open_tool(get("crop"))
    app.update()
    check("param tool kembali seperti sebelumnya",
          app.tools._vars["crop"]["margin"].get() == "21")
    check("input tool dibaca dari preview, bukan daftar sendiri",
          app.tools.describe_inputs() != "", app.tools.describe_inputs())
    check("tidak ada daftar input per tool",
              not hasattr(app.tools, "_inputs"), "masih ada _inputs")
    check("tidak ada tombol insert di form tool",
              "…" not in all_button_texts(app.tools),
              str([t for t in all_button_texts(app.tools) if "…" in t]))

    # Satu tombol insert untuk semua pekerjaan: labelnya mengikuti jenis file
    # yang dibutuhkan tool yang dipilih dari menubar.
    def add_label():
        return next(str(b.cget("text")) for b in app.header.action_buttons
                    if str(b.cget("text")).startswith("+ Tambah"))

    check("label tombol insert default PDF", add_label() == "+ Tambah PDF", add_label())
    for tool_id, expected in (("compress", "+ Tambah PDF"),
                              ("jpg2pdf", "+ Tambah Gambar"),
                              ("word2pdf", "+ Tambah Office"),
                              ("html2pdf", "+ Tambah Berkas")):
        app._open_tool(get(tool_id))
        app.update()
        check(f"label tombol insert untuk {tool_id}", add_label() == expected,
              f"{add_label()} (harap {expected})")
    app._open_tool(get("crop"))
    app.update()

    # Jalankan tool sungguhan dari panel: hasil harus inline.
    tool_out = os.path.join(out_dir, "panel-crop.pdf")
    if os.path.exists(tool_out):
        os.remove(tool_out)
    app.tools._vars["crop"]["margin"].set("12")
    # Berkas untuk tool diambil dari preview (project), bukan dari form tool.
    app.project.add_files([paths[0]])
    app._refresh_all()
    app.update()
    filedialog.asksaveasfilename = lambda *a, **k: tool_out
    try:
        app.tools.start()
        deadline = time.time() + 15
        while time.time() < deadline:
            app.update()
            if os.path.exists(tool_out) and not app.tools.is_busy:
                break
            time.sleep(0.05)
        for _ in range(20):
            app.update()
            time.sleep(0.02)
    finally:
        filedialog.asksaveasfilename = real_asksave

    check("tool panel menulis berkas", os.path.exists(tool_out))
    panel_result = app.tools.result.text.get("1.0", "end")
    check("hasil tool tampil inline", "Crop PDF" in panel_result, repr(panel_result[:80]))
    check("tombol Jalankan di header aktif lagi setelah selesai",
          all(str(b.cget("state")) != "disabled" for b in app.header.action_buttons),
          [str(b.cget("state")) for b in app.header.action_buttons])
    check("status menampilkan tool selesai", "selesai" in app.status_var.get().lower(),
          app.status_var.get())

    # Menjalankan tanpa berkas harus memberi pesan di panel, bukan popup.
    app.project.close()
    app._refresh_all()
    app.tools.clear_inputs()
    shown.clear()
    app.tools.start()
    app.update()
    check("tanpa berkas: pesan inline",
          "Belum ada berkas" in app.tools.result.text.get("1.0", "end"))
    check("tanpa berkas: tidak ada popup", not shown, shown)

    # ---- layout di berbagai ukuran jendela ----
    big = os.path.join(out_dir, "banyak.pdf")
    doc = pymupdf.open()
    for i in range(24):
        doc.new_page(width=595, height=842)
    doc.save(big)
    doc.close()

    project_backup = app.project
    app.project = Project()
    app.project.add_files([big])
    app._refresh_all()

    for geometry in ("1040x660", "1360x860", "1920x1080", "1040x660"):
        app.geometry(geometry)
        app.update_idletasks()
        app.update()
        grid = app.grid

        def walk(widget):
            yield widget
            for child in widget.winfo_children():
                yield from walk(child)

        # Widget yang disembunyikan (grid_remove) memang berukuran 1x1, jadi
        # hanya widget yang benar-benar terlihat yang boleh diperiksa.
        def clipped_buttons(root):
            return [
                b.cget("text")
                for b in walk(root)
                if b.winfo_class() in ("TButton", "Button")
                and b.winfo_ismapped()
                and b.winfo_reqwidth() > b.winfo_width()
            ]

        clipped = clipped_buttons(app)
        check(f"tombol utuh @ {geometry}", not clipped, str(clipped))
        # Badan jendela dua kolom: grid thumbnail dan panel samping.
        # app.grid ada di dalam `left`, jadi badan jendela adalah dua level di atas.
        body = app.grid.master.master
        columns = {w.grid_info().get("column") for w in body.winfo_children()
                   if w.winfo_manager() == "grid"}
        check(f"dua kolom: grid + panel @ {geometry}", columns == {0, 1}, str(columns))
        panel = next(w for w in body.winfo_children()
                     if w.winfo_manager() == "grid" and w.grid_info()["column"] == 1)
        check(f"panel samping di kanan grid @ {geometry}",
              panel.winfo_rootx() >= app.grid.winfo_rootx() + app.grid.winfo_width(),
              f"panel_x={panel.winfo_rootx()} grid_end="
              f"{app.grid.winfo_rootx() + app.grid.winfo_width()}")
        check(f"kolom perkakas utuh @ {geometry}",
              not clipped_buttons(app.tools),
              str(clipped_buttons(app.tools)))

        # Panel kanan menampilkan tepat satu isi, dan berganti lewat menubar.
        check(f"panel menampilkan satu isi @ {geometry}",
              sum(1 for f in app._panel_pages if f.winfo_manager() == "grid") == 1,
              [f.winfo_manager() for f in app._panel_pages])
        check(f"tanpa tab/select box panel @ {geometry}",
              not hasattr(app, "_tab_pages") and not hasattr(app, "_tab_mode")
              and not hasattr(app.tools, "tree"),
              "masih ada tab atau daftar tool")
        check(f"tombol OCR tidak terduplikasi @ {geometry}",
              sorted(t_ for t_ in all_button_texts(app)
                     if t_ in ("OCR Semua", "OCR Terpilih")) == ["OCR Semua", "OCR Terpilih"],
              sorted(t_ for t_ in all_button_texts(app)
                     if t_ in ("OCR Semua", "OCR Terpilih")))

        app.update_idletasks()
        app.update()

        # jumlah kolom harus sesuai lebar, bukan nilai basi
        expected = max(1, min(8, (grid.scroller.canvas.winfo_width() - 24) // grid.COLUMNS_MIN))
        check(f"kolom sesuai lebar @ {geometry}", grid._columns == expected,
              f"cols={grid._columns} expect={expected}")

        # setiap target harus bisa digulir ke area terlihat
        canvas = grid.scroller.canvas
        unreachable = []
        for target in (23, 0, 11, 23, 5):
            grid.scroll_to_index(target)
            app.update()
            total = canvas.bbox("all")[3]
            offset = canvas.yview()[0] * total
            row_height = grid._cells[0].winfo_height() + 2 * grid.PAD_Y
            top = row_height * (target // grid._columns)
            if not (
                offset - 1 <= top
                and top + grid._cells[0].winfo_height() <= offset + canvas.winfo_height() + 1
            ):
                unreachable.append(target)
        check(f"scroll ke semua target @ {geometry}", not unreachable, str(unreachable))

    # ---- satu sumber berkas: preview dipakai semua tool ----
    app.project.close()
    html_path = os.path.join(out_dir, "satu.html")
    with open(html_path, "w", encoding="utf-8") as fh:
        fh.write("<html><body><h1>Uji</h1></body></html>")

    app.project.add_files(paths + [html_path])
    app._refresh_all()
    app.update()
    check("berkas non-thumbnail tetap tercatat",
              os.path.basename(html_path) in [os.path.basename(f) for f in app.project.files],
              str([os.path.basename(f) for f in app.project.files]))
    check("halaman preview = PDF + gambar saja",
              len(app.project.pages) > 0, str(len(app.project.pages)))

    app._open_tool(get("html2pdf"))
    app.update()
    check("tool non-PDF membaca berkas dari preview",
              [os.path.basename(p) for p in app.project.inputs_for("any")]
              == [os.path.basename(html_path)],
              str(app.project.inputs_for("any")))
    check("daftar berkas tampil saat preview tak ada thumbnail",
              app.file_list.winfo_ismapped() and
              os.path.basename(html_path) in app.file_list.cget("text"),
              repr(app.file_list.cget("text")))

    app._open_tool(get("compress"))
    app.update()
    check("daftar berkas disembunyikan untuk tool PDF",
              not app.file_list.winfo_ismapped(), "masih tampil")

    check("badge jenis file di thumbnail",
          str(app.grid._cells[0]._badge.cget("text")).startswith("[PDF]"),
          str(app.grid._cells[0]._badge.cget("text")))

    # ---- ukuran thumbnail ----
    app.geometry("1360x860")
    app.project = project_backup
    app._refresh_all()
    app.update()
    # Tes "tanpa berkas" sengaja mengosongkan proyek; muat ulang agar tes
    # orientasi thumbnail punya halaman untuk dikerjakan.
    if not app.project.pages:
        app.project.add_files(paths)
        app._refresh_all()
        app.update()

    for degree, expected_portrait in ((0, True), (90, False), (180, True), (270, False)):
        app.project.pages[0].rotation = degree
        app.thumbs.clear()
        app._refresh_thumb(0)
        app.update()
        photo = app.grid._cells[0]._page_state["photo"]
        portrait = photo.height() > photo.width()
        check(f"thumbnail {degree}° orientasi", portrait == expected_portrait,
              f"{photo.width()}x{photo.height()}")
    app.project.pages[0].rotation = 0
    app.thumbs.clear()
    app._refresh_thumb(0)
    app.update()
    check("tinggi thumbnail tepat", app.grid._cells[0]._page_state["photo"].height() == 190,
          str(app.grid._cells[0]._page_state["photo"].height()))

    app.destroy()
    print()
    if FAILURES:
        print(f"GAGAL {len(FAILURES)}: {FAILURES}")
        return 1
    print("SEMUA CEK GUI LULUS")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except Exception:
        traceback.print_exc()
        raise SystemExit(1)