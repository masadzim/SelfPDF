"""Kolom perkakas: form parameternya saja, tampil inline di jendela utama.

Kenapa tidak ada daftar/select box di sini? Semua tool sudah punya tempat di
menubar (File / Edit / kategori / Bantuan). Kalau daftar tool juga ditampilkan
di panel, muncul dua cara memilih tool yang isinya sama persis — itu-lah
duplikasi yang dikeluhkan. Sekarang tool dipilih **dari menu**, dan panel ini
hanya menampilkan parameternya.

Tidak ada dialog `Toplevel` per tool: memilih tool dari menu hanya mengganti
isi kolom ini, sehingga tidak ada popup yang saling menimpa. Nilai yang sudah
diisi disimpan per tool, jadi bolak-balik antar tool tidak menghapus pekerjaan
yang sedang disusun.

Tombol Jalankan tidak lagi ada di bawah kolom ini — ia dipindah ke baris atas
jendela bersama tombol lain (lihat `MainWindow._build_header`).
"""

from __future__ import annotations

import os
import threading
import traceback
import tkinter as tk
from tkinter import filedialog, ttk
from typing import Optional

from ..tools.base import (
    FILE_DIALOG,
    INPUT_ANY,
    INPUT_NONE,
    Param,
    ToolError,
    ToolSpec,
    ToolOutcome,
    run_spec,
)
from .app_colors import BG_PANEL, FG, FG_DIM, OK, WARN
from .feedback import ResultView

INPUT_LABELS = {
    "pdf": "Berkas PDF",
    "pdf_multi": "PDF (boleh banyak)",
    "image": "Gambar (boleh banyak)",
    "image_one": "Berkas gambar",
    "office": "Dokumen Office",
    "any": "Berkas",
}

_OUTPUT_TYPES = {
    ".md": ("Markdown", "*.md"),
    ".docx": ("Word", "*.docx"),
    ".pptx": ("PowerPoint", "*.pptx"),
    ".xlsx": ("Excel", "*.xlsx"),
    ".pdf": ("PDF", "*.pdf"),
}

# Lebar panel samping; label dibuat tetap sempit supaya entry parameter
# mendapat ruang yang panjang.
LABEL_COLUMN_WIDTH = 128
# Batas panjang baris teks panjang (judul tool, bantuan param, pesan status).
WRAP_WIDTH = 320


class _VScroll(ttk.Frame):
    """Area yang bisa digulir vertikal; event roda hanya berlaku di dalamnya."""

    def __init__(self, master: tk.Misc) -> None:
        super().__init__(master, style="Panel.TFrame")
        self.canvas = tk.Canvas(self, highlightthickness=0, bd=0, bg=BG_PANEL)
        self.bar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.body = ttk.Frame(self.canvas, style="Panel.TFrame")

        self._window = self.canvas.create_window((0, 0), window=self.body, anchor="nw")
        self.canvas.configure(yscrollcommand=self.bar.set)

        # Scrollbar dipasang lebih dulu. Kalau canvas (yang memakai `expand`)
        # dipaket lebih awal, ia memakan seluruh lebar dan scrollbar tidak
        # mendapat ruang sama sekali.
        self.bar.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)

        self.body.configure(padding=(0, 0, 2, 0))
        self.body.bind("<Configure>", self._sync_region)
        self.canvas.bind("<Configure>", self._sync_width)
        # Satu binding global saja; memasang di beberapa widget akan membuat
        # satu gesekan roda digulirkan berkali-kali.
        self.bind_all("<MouseWheel>", self._on_wheel, add="+")
        self.bind_all("<Button-4>", self._on_wheel, add="+")
        self.bind_all("<Button-5>", self._on_wheel, add="+")

    def _sync_region(self, _event: tk.Event | None = None) -> None:
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _sync_width(self, event: tk.Event) -> None:
        self.canvas.itemconfigure(self._window, width=event.width)

    def _inside(self, event: tk.Event) -> bool:
        x, y = getattr(event, "x_root", 0), getattr(event, "y_root", 0)
        return (
            self.winfo_rootx() <= x <= self.winfo_rootx() + self.winfo_width()
            and self.winfo_rooty() <= y <= self.winfo_rooty() + self.winfo_height()
        )

    def _on_wheel(self, event: tk.Event) -> None:
        if not self.bar.winfo_ismapped() or not self._inside(event):
            return
        if event.num == 4 or getattr(event, "delta", 0) > 0:
            self.canvas.yview_scroll(-3, "units")
        elif event.num == 5 or getattr(event, "delta", 0) < 0:
            self.canvas.yview_scroll(3, "units")


class ToolPanel(ttk.Frame):
    """Kolom perkakas: judul tool, form parameter, progres, dan hasil.

    `host` harus menyediakan:
      * `events`           — `queue.Queue` tempat event proses dikirim
      * `set_status(text)` — untuk bar status jendela utama

    `on_busy(bool)` dipanggil saat proses mulai/selesai supaya jendela utama
    bisa mengunci tombol "Jalankan" yang ada di header.

    Widget panel ini mengurus enable/disable form-nya sendiri lewat
    `_set_running`, jadi tidak perlu didaftarkan ke daftar lockable jendela
    utama.
    """

    def __init__(self, master: tk.Misc, host, on_busy=None) -> None:
        super().__init__(master, style="Panel.TFrame")
        self.host = host
        self.on_busy = on_busy
        self.columnconfigure(0, weight=1)

        self.spec: Optional[ToolSpec] = None
        self.worker: Optional[threading.Thread] = None
        self._finished = False

        # Nilai per tool supaya tidak hilang saat berpindah tool. Daftar berkas
        # tidak ada di sini — semua tool membaca dari preview.
        self._vars: dict[str, dict[str, tk.StringVar]] = {}
        self._widgets: list[tk.Misc] = []
        self._help_labels: list[ttk.Label] = []

        self._build_form_host()

        # Progres hanya muncul saat tool berjalan. Diam-diam ia masih memakan
        # tinggi jendela yang precious, padahal isinya selalu 0.
        self.progress = ttk.Progressbar(self, mode="determinate", maximum=100)
        self.progress.grid(row=2, column=0, sticky="ew", pady=(8, 0))
        self.progress.grid_remove()

        self.status = tk.Label(
            self, text="", bg=BG_PANEL, fg=FG_DIM, anchor="w", justify="left",
            wraplength=WRAP_WIDTH,
        )
        self.status.grid(row=3, column=0, sticky="ew", pady=(4, 0))

        self.result = ResultView(self, height=5)
        self.result.grid(row=4, column=0, sticky="ew", pady=(8, 0))
        self.result.grid_remove()

        self._show_placeholder()

    # -------------------------------------------------------------------- form

    def _build_form_host(self) -> None:
        self.head = ttk.Frame(self, style="Panel.TFrame")
        self.head.grid(row=0, column=0, sticky="ew")
        self.head.columnconfigure(0, weight=1)

        # Ditampilkan selama belum ada tool yang dipilih dari menu.
        self.placeholder = ttk.Label(
            self.head,
            text="Perkakas — belum ada yang dipilih.\n"
                 "Pilih satu perkakas dari menu di atas (mis. Konversi, Edit, "
                 "Keamanan) untuk mengisi parameternya.",
            style="DimOnPanel.TLabel",
            wraplength=WRAP_WIDTH,
            justify="left",
        )
        self.placeholder.grid(row=0, column=0, sticky="w")

        self.title = ttk.Label(self.head, text="", style="ToolTitle.TLabel",
                               wraplength=WRAP_WIDTH, justify="left")
        self.title.grid(row=0, column=0, sticky="w")

        self.hint = ttk.Label(self.head, text="", style="DimOnPanel.TLabel",
                              wraplength=WRAP_WIDTH, justify="left")
        self.hint.grid(row=1, column=0, sticky="w", pady=(2, 0))

        self.scroll = _VScroll(self)
        self.scroll.grid(row=1, column=0, sticky="nsew", pady=(8, 0))
        self.rowconfigure(1, weight=1)
        self.columnconfigure(0, weight=1)
        self.form = self.scroll.body
        self.form.columnconfigure(1, weight=1)

    def _show_placeholder(self) -> None:
        """Tampilkan placeholder, bukan form: belum ada tool yang dipilih."""
        self.spec = None
        self.title.grid_remove()
        self.hint.grid_remove()
        self.scroll.grid_remove()
        self.placeholder.grid()

    def report(self, headline: str, body: str = "", tone: str = "info") -> None:
        """Tulis pesan ke kotak hasil panel ini."""
        self.result.show(headline, body, tone=tone)

    def _show_result(self, headline: str, body: str = "", tone: str = "info",
                     outputs=()) -> None:
        self.result.show(headline, body, tone=tone, outputs=outputs)

    def set_spec(self, spec: ToolSpec) -> None:
        """Tampilkan form untuk `spec`, mempertahankan nilai yang sudah diisi."""
        if self.is_busy:
            # Ganti tool di tengah proses akan membuat hasil dilaporkan ke tool
            # yang salah, jadi tahan sampai proses selesai.
            self.status.configure(text="Tunggu proses yang sedang berjalan selesai.",
                                  fg=FG_DIM)
            return
        self.spec = spec
        self._finished = False
        for child in self.form.winfo_children():
            child.destroy()
        self._widgets = []
        self._help_labels = []

        self.placeholder.grid_remove()
        self.title.grid()
        self.hint.grid()
        self.scroll.grid()

        self.title.configure(text=spec.label)
        self.hint.configure(text=spec.description or "")
        self.status.configure(text="", fg=FG_DIM)
        self.progress.configure(value=0)

        tool_id = spec.id
        if tool_id not in self._vars:
            self._vars[tool_id] = {param.key: self._default_var(param) for param in spec.params}

        # Tidak ada baris input + tombol "…" di sini. Berkas masuk lewat satu
        # tombol Tambah di header dan langsung tampil di preview, jadi form
        # cukup berisi parameter saja.
        self.param_widgets: dict[str, tk.Misc] = {}
        row = 0
        for param in spec.params:
            row = self._build_param(param, row)

        self._set_running(False)
        self.scroll.canvas.configure(scrollregion=self.scroll.canvas.bbox("all"))
        self.scroll.canvas.yview_moveto(0.0)

    def _default_var(self, param: Param) -> tk.StringVar:
        if param.kind == "bool":
            return tk.StringVar(value="1" if param.default in ("1", True) else "")
        return tk.StringVar(value=str(param.default))

    def _build_param(self, param: Param, row: int) -> int:
        var = self._vars[self.spec.id][param.key]  # type: ignore[index]

        ttk.Label(self.form, text=param.label, style="Field.TLabel",
                  wraplength=LABEL_COLUMN_WIDTH - 8, justify="left").grid(
            row=row, column=0, sticky="nw", pady=(0, 6), padx=(0, 10))

        if param.kind == "choice":
            widget = ttk.Combobox(self.form, textvariable=var, values=param.display_choices(),
                                  state="readonly")
        elif param.kind == "bool":
            widget = ttk.Checkbutton(self.form, text="Ya", width=0, variable=var)
        elif param.kind in ("dir", "file"):
            entry = ttk.Entry(self.form, textvariable=var)
            entry.grid(row=row, column=1, sticky="ew", pady=(0, 6))
            ttk.Button(
                self.form, width=0, text="Folder…" if param.kind == "dir" else "Berkas…",
                style="Panel.TButton",
                command=lambda p=param, v=var: self._pick_path(p, v),
            ).grid(row=row, column=2, padx=(6, 0), pady=(0, 6), sticky="e")
            self.param_widgets[param.key] = entry
            self._widgets.append(entry)
            if param.help:
                row += 1
                self._help(param, row)
            return row + 1
        else:
            widget = ttk.Entry(self.form, textvariable=var)

        widget.grid(row=row, column=1, columnspan=2, sticky="ew", pady=(0, 6))
        self.param_widgets[param.key] = widget
        self._widgets.append(widget)

        if param.help:
            row += 1
            self._help(param, row)
        return row + 1

    def _help(self, param: Param, row: int) -> None:
        label = ttk.Label(self.form, text=param.help, style="DimOnPanel.TLabel",
                          wraplength=WRAP_WIDTH - 40, justify="left")
        label.grid(row=row, column=0, columnspan=3, sticky="w", pady=(0, 6))
        self._help_labels.append(label)


    # ------------------------------------------------------------------ berkas

    def describe_inputs(self) -> str:
        """Ringkasan berkas yang akan dipakai tool ini, dibaca dari preview."""
        spec = self.spec
        if spec is None:
            return ""
        paths = self.host.project.inputs_for(spec.input_kind)
        if not paths:
            wanted = INPUT_LABELS.get(spec.input_kind, "berkas")
            return f"Belum ada {wanted.lower()} di preview"
        if len(paths) == 1:
            return os.path.basename(paths[0])
        return f"{len(paths)} berkas di preview"

    def _pick_path(self, param: Param, var: tk.StringVar) -> None:
        if param.kind == "dir":
            chosen = filedialog.askdirectory(title="Pilih folder", parent=self)
        else:
            chosen = filedialog.askopenfilename(title="Pilih berkas", parent=self)
        if chosen:
            var.set(chosen)

    def clear_inputs(self) -> None:
        if self.spec is None:
            return
        for param in self.spec.params:
            self._vars[self.spec.id][param.key].set(self._default_var(param).get())
        self.status.configure(text="Parameter tool dikosongkan.", fg=FG_DIM)

    # ------------------------------------------------------------------ proses

    @property
    def is_busy(self) -> bool:
        return self.worker is not None and self.worker.is_alive()

    def _collect(self) -> dict:
        params: dict = {}
        for param in self.spec.params:  # type: ignore[union-attr]
            raw = self._vars[self.spec.id][param.key].get()  # type: ignore[index]
            params[param.key] = (
                param.internal_value(raw) if param.kind == "choice" else param.parse(raw)
            )
        return params

    def start(self) -> None:
        spec = self.spec
        if spec is None or self.is_busy:
            return

        # Sumber berkas tunggal: preview di panel kiri. Tidak ada daftar input
        # sendiri per tool, jadi `+ Tambah PDF` berlaku untuk semua pekerjaan.
        inputs = self.host.project.inputs_for(spec.input_kind)
        if not inputs:
            wanted = INPUT_LABELS.get(spec.input_kind, "berkas").lower()
            self._show_result(
                "Belum ada berkas",
                f"Tambahkan {wanted} dulu lewat tombol Tambah di baris atas — "
                f"filenya akan muncul di preview.",
                tone="warn",
            )
            self.host.set_status(f"{spec.label}: belum ada {wanted} di preview.")
            return

        try:
            params = self._collect()
        except ToolError as exc:
            self._show_result("Parameter tidak valid", str(exc), tone="error")
            return

        out_path = self._choose_output(inputs)
        if not out_path:
            return

        self._finished = False
        self._show_result("Sedang berjalan…", f"{spec.label} — {self.describe_inputs()}")
        self._set_running(True, f"{spec.label} berjalan…")
        self.host.set_status(f"{spec.label} sedang berjalan…")

        self.worker = threading.Thread(
            target=self._worker, args=(spec, list(inputs), params, out_path), daemon=True
        )
        self.worker.start()

    def _choose_output(self, inputs: list[str]) -> str:
        spec = self.spec
        assert spec is not None
        if spec.multi_output or not spec.extension:
            return filedialog.askdirectory(title="Pilih folder tujuan", parent=self) or ""
        label, pattern = _OUTPUT_TYPES.get(spec.extension, ("PDF", "*.pdf"))
        return filedialog.asksaveasfilename(
            title="Simpan hasil",
            defaultextension=spec.extension,
            filetypes=[(label, pattern)],
            initialfile=spec.suggested_name(inputs[0]),
            parent=self,
        )

    def _worker(self, spec: ToolSpec, inputs: list[str], params: dict, out_path: str) -> None:
        def progress(percent: int, message: str) -> None:
            self.host.events.put(("tool", "progress", (percent, message)))

        try:
            outcome: ToolOutcome = run_spec(spec, inputs=inputs, params=params,
                                            out_path=out_path, progress=progress)
            self.host.events.put(("tool", "done", (spec.id, outcome)))
        except ToolError as exc:
            self.host.events.put(("tool", "error", (spec.id, str(exc))))
        except Exception as exc:  # noqa: BLE001
            self.host.events.put(
                ("tool", "error",
                 (spec.id, f"{type(exc).__name__}: {exc}\n\n{traceback.format_exc(limit=3)}"))
            )

    def handle(self, kind: str, payload) -> None:
        """Dipanggil dari loop event jendela utama."""
        if kind == "progress":
            percent, message = payload
            self.progress.configure(value=max(0, min(100, int(percent))))
            if message:
                self.status.configure(text=message, fg=FG_DIM)
            return

        self._set_running(False)
        if self._finished:
            return
        self._finished = True
        self.progress.configure(value=100 if kind == "done" else 0)

        tool_id, data = payload
        label = self.spec.label if self.spec else tool_id  # type: ignore[union-attr]

        if kind == "done":
            outcome: ToolOutcome = data
            outputs = [outcome.output] if outcome.output else list(outcome.items)
            body = outcome.message()
            tone = "warn" if outcome.warnings else "ok"
            self.status.configure(text="Selesai.", fg=OK)
            self.host.set_status(f"{label} selesai.")
        else:
            outputs = []
            body = str(data)
            tone = "error"
            self.status.configure(text="Gagal.", fg=WARN)
            self.host.set_status(f"{label} gagal.")

        self._show_result(f"{'Selesai' if kind == 'done' else 'Gagal'} — {label}", body,
                          tone=tone, outputs=outputs)

    # ------------------------------------------------------------------ status

    def _set_running(self, running: bool, note: str = "") -> None:
        state = "disabled" if running else "normal"
        if running:
            self.progress.grid()
        else:
            self.progress.grid_remove()
        for widget in self._widgets:
            try:
                if isinstance(widget, ttk.Combobox):
                    widget.configure(state="disabled" if running else "readonly")
                else:
                    widget.configure(state=state)
            except tk.TclError:
                pass
        if running:
            self.status.configure(text=note, fg=FG_DIM)
        # Jendela utama mengunci tombolnya sendiri (termasuk "Jalankan" yang
        # kini ada di header) melalui `on_busy`.
        if self.on_busy is not None:
            self.on_busy(running)

    def widgets(self) -> list[tk.Misc]:
        """Widget yang harus ikut terkunci selama proses tool berjalan."""
        return list(self._widgets)
