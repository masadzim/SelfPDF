"""Jendela utama aplikasi SelfPDF.

Tata letak (dari atas ke bawah):

* **Header**  — logo + tombol aksi utama.
* **Menubar** — File / Edit / kategori tool / Bantuan, menyatu dengan jendela.
* **Badan**   — kolom kiri grid thumbnail halaman, kolom kanan panel samping
                yang berganti antara tab **Halaman** dan **Perkakas**.
* **Footer**  — progres + status.

Kolom kanan hanya punya satu panel. Tidak ada `Toplevel` per tool: memilih
perkakas hanya menukar isi panel, sehingga tidak ada lagi dialog popup yang
saling menimpa.
"""

from __future__ import annotations

import os
import queue
import threading
import traceback
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import webbrowser

from ..core import (
    KIND_LABELS,
    RENDERABLE_KINDS,
    SAVE_LABELS,
    SAVE_RAW,
    SAVE_SEARCHABLE,
    OCR_DPI,
    Project,
    kind_of,
)
from ..ocr import DEFAULT_LANG, OcrUnavailable, check_available, run_ocr
from ..tools.base import (
    INPUT_ANY,
    INPUT_IMAGE,
    INPUT_IMAGE_ONE,
    INPUT_OFFICE,
    INPUT_PDF,
    INPUT_PDF_MULTI,
)
from .app_colors import (
    ACCENT, BG, BG_PANEL, FG, FG_DIM, OK, WARN,
    get_theme,
    SPACE_4, SPACE_5,
    TOOLBAR_HEIGHT,
    HEADER_HEIGHT,
    RADIUS_MD,
)
from .header import HeaderBar, setup_header_styles
from .branding import (
    APP_NAME,
    APP_TAGLINE,
    DONATION_URL,
    SUPPORT_EMAIL,
    apply_window_icon,
)
from .feedback import ResultView
from .menubar import MenuBar, menubar_divider, setup_menubar_styles, CommandPalette
from .page_grid import PageGrid
from .thumbs import ThumbCache
from .tool_panel import ToolPanel

APP_TITLE = f"{APP_NAME} - {APP_TAGLINE}"
THUMB_HEIGHT = 190

# Lebar panel samping. Cukup untuk form param tanpa membuat grid thumbnail
# terlalu sempit pada lebar jendela minimum.
PANEL_WIDTH = 372

# Label tombol insert saat belum ada tool yang dipilih. Begitu perkakas diklik
# di menubar, labelnya menyesuaikan jenis file yang tool itu butuhkan.
DEFAULT_ADD_LABEL = "+ Tambah PDF"

# Tombol insert hanya perlu menerima jenis file yang sedang dibutuhkan, jadi
# dialognya tidak pernah dibuka tanpa alasan.
ADD_LABELS = {
    INPUT_PDF_MULTI: "+ Tambah PDF",
    INPUT_PDF: "+ Tambah PDF",
    INPUT_IMAGE: "+ Tambah Gambar",
    INPUT_IMAGE_ONE: "+ Tambah Gambar",
    INPUT_OFFICE: "+ Tambah Office",
    INPUT_ANY: "+ Tambah Berkas",
}

ADD_FILETYPES = {
    INPUT_PDF_MULTI: (("PDF", "*.pdf"),),
    INPUT_PDF: (("PDF", "*.pdf"),),
    INPUT_IMAGE: (("Gambar", "*.png *.jpg *.jpeg *.tif *.tiff *.bmp *.webp"),),
    INPUT_IMAGE_ONE: (("Gambar", "*.png *.jpg *.jpeg *.tif *.tiff *.bmp *.webp"),),
    INPUT_OFFICE: (
        ("Word", "*.docx *.doc"),
        ("PowerPoint", "*.pptx *.ppt"),
        ("Excel", "*.xlsx *.xls"),
        ("Semua", "*"),
    ),
    INPUT_ANY: (("Semua", "*"),),
}

__all__ = ["ACCENT", "APP_TITLE", "BG", "BG_PANEL", "DONATION_URL", "FG", "FG_DIM",
           "MainWindow", "OK", "SUPPORT_EMAIL", "WARN"]


def _configure_styles(root: tk.Tk) -> ttk.Style:
    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except tk.TclError:
        pass

    setup_header_styles(style)
    setup_menubar_styles(style)

    style.configure("App.TFrame", background=BG)
    style.configure("Panel.TFrame", background=BG_PANEL)
    style.configure("App.TLabel", background=BG, foreground=FG)
    style.configure("Dim.TLabel", background=BG, foreground=FG_DIM)
    style.configure("Panel.TLabel", background=BG_PANEL, foreground=FG)
    style.configure("DimOnPanel.TLabel", background=BG_PANEL, foreground=FG_DIM)
    style.configure("Title.TLabel", background=BG, foreground=FG,
                    font=("TkDefaultFont", 15, "bold"))
    style.configure("HeaderTag.TLabel", background=BG, foreground=FG_DIM,
                    font=("TkDefaultFont", 9))
    style.configure("SectionTitle.TLabel", background=BG_PANEL, foreground=FG,
                    font=("TkDefaultFont", 10, "bold"))
    style.configure("ToolTitle.TLabel", background=BG_PANEL, foreground=FG,
                    font=("TkDefaultFont", 11, "bold"))
    style.configure("Field.TLabel", background=BG_PANEL, foreground=FG_DIM,
                    font=("TkDefaultFont", 9))

    style.configure("App.TButton", padding=(10, 5))
    style.configure("Accent.TButton", padding=(10, 7), background=ACCENT, foreground="#ffffff")
    style.map("Accent.TButton", background=[("active", "#2f81f7")])
    style.configure("Ok.TButton", padding=(10, 6), background=OK, foreground="#04210a")
    style.map("Ok.TButton", background=[("active", "#4cc761")])
    style.configure("Panel.TButton", background=BG_PANEL, foreground=FG, padding=(8, 4))
    style.map("Panel.TButton",
              background=[("active", "#363c4a"), ("pressed", "#3d4453")],
              foreground=[("active", "#ffffff")])

    style.configure("TProgressbar", troughcolor=BG_PANEL, background=ACCENT,
                    bordercolor=BG_PANEL, lightcolor=ACCENT, darkcolor=ACCENT)
    style.configure("Treeview", background=BG_PANEL, fieldbackground=BG_PANEL,
                    foreground=FG, borderwidth=0, rowheight=24)
    style.configure("Treeview.Heading", background=BG, foreground=FG_DIM, borderwidth=0)
    style.map("Treeview", background=[("selected", ACCENT)])

    style.configure("ToolTree.Treeview", background=BG_PANEL, fieldbackground=BG_PANEL,
                    foreground=FG, bordercolor="#3a4250", lightcolor="#3a4250",
                    darkcolor="#3a4250", rowheight=23, relief="flat")
    style.map("ToolTree.Treeview",
              background=[("selected", ACCENT)],
              foreground=[("selected", "#ffffff")])

    return style


class OcrJob:
    """Satu pekerjaan OCR untuk halaman tertentu, dijalankan di thread."""

    def __init__(self, index: int, page: object, lang: str) -> None:
        self.index = index
        self.page = page
        self.lang = lang


class MainWindow(tk.Tk):
    def __init__(self) -> None:
        super().__init__(className=APP_TITLE)
        self.title(APP_TITLE)
        self.geometry("1360x860")
        self.minsize(1040, 660)
        self.configure(bg=BG, highlightthickness=0, highlightbackground=BG)
        apply_window_icon(self)

        _configure_styles(self)

        self.project = Project()
        self.thumbs = ThumbCache()
        self.events: queue.Queue = queue.Queue()
        self._worker: threading.Thread | None = None
        self._jobs: list[OcrJob] = []
        self._lockable: list[tk.Misc] = []
        self._update_busy = False

        self.status_var = tk.StringVar(value="Siap. Tambahkan file PDF untuk mulai.")
        self._mode_key = SAVE_SEARCHABLE
        self.save_mode = tk.StringVar(value=SAVE_LABELS[SAVE_SEARCHABLE])
        self.lang_var = tk.StringVar(value=DEFAULT_LANG)
        self.search_var = tk.StringVar()
        self.search_entry: ttk.Entry | None = None

        self._build_header()
        self._build_menubar()
        self._build_ui()
        self._bind_shortcuts()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(80, self._drain_events)
        self.after(120, self._check_tesseract)
        # Pemeriksaan pembaruan diam-diam: cukup satu kali per sesi, di thread
        # terpisah, jadi startup tidak menunggu jaringan.
        self.after(2500, self._check_updates_on_start)

    # ------------------------------------------------------------------ header

    def _build_header(self) -> None:
        """Build modern header with toolbar: identity left, actions right."""
        self.header = HeaderBar(
            self,
            actions=[
                ("Gabung & Simpan", self._save, "Primary.TButton", "Ctrl+S", "Simpan hasil sebagai PDF"),
                ("Jalankan", self._run_active_tool, "Primary.TButton", "Ctrl+R", "Jalankan tool aktif"),
                ("Bersihkan", self._clear_all, "Ghost.TButton", "Ctrl+Delete", "Hapus semua berkas dari preview"),
                (DEFAULT_ADD_LABEL, self._add_files, "Ghost.TButton", "Ctrl+O", "Tambah berkas ke preview"),
            ],
            tagline=APP_TAGLINE,
        )
        self.header.pack(fill="x")
        for button in self.header.action_buttons:
            self._register_lockable(button)
        self._logo_photo = self.header.logo_photo

    # ---------------------------------------------------------------- menubar

    def _build_menubar(self) -> None:
        from ..tools import MENU_ORDER, grouped

        # Modern in-window menubar with command palette support
        bar = MenuBar(self)
        bar.pack(fill="x")
        menubar_divider(self)
        self._menubar = bar

        # File menu
        file_menu = bar.add_menu("File")
        file_menu.add_command("Tambah Berkas…", self._add_files, "Ctrl+O")
        file_menu.add_command("Gabung & Simpan…", self._save, "Ctrl+S")
        file_menu.add_separator()
        file_menu.add_command("Kosongkan Proyek", self._clear_all, "Ctrl+Delete")
        file_menu.add_separator()
        file_menu.add_command("Keluar", self._on_close, "Ctrl+Q")

        bar.register_command("File", "Tambah Berkas…", self._add_files, "Ctrl+O", "file-plus")
        bar.register_command("File", "Gabung & Simpan…", self._save, "Ctrl+S", "file-save")
        bar.register_command("File", "Kosongkan Proyek", self._clear_all, "Ctrl+Delete", "trash")
        bar.register_command("File", "Keluar", self._on_close, "Ctrl+Q", "log-out")

        # Edit menu
        edit_menu = bar.add_menu("Edit")
        edit_menu.add_command("Putar 90° Kiri", lambda: self._rotate_selected(-90), "Ctrl+[")
        edit_menu.add_command("Putar 90° Kanan", lambda: self._rotate_selected(90), "Ctrl+]")
        edit_menu.add_separator()
        edit_menu.add_command("Duplikat Halaman", self._duplicate_selected, "Ctrl+D")
        edit_menu.add_command("Hapus Halaman Terpilih", self._delete_selected, "Delete")
        edit_menu.add_separator()
        edit_menu.add_command("OCR Semua Halaman", lambda: self._start_ocr(None), "Ctrl+Shift+O")
        edit_menu.add_command("OCR Halaman Terpilih", lambda: self._start_ocr("selected"),
                              "Ctrl+Shift+E")

        bar.register_command("Edit", "Putar Kiri", lambda: self._rotate_selected(-90), "Ctrl+[", "rotate-ccw")
        bar.register_command("Edit", "Putar Kanan", lambda: self._rotate_selected(90), "Ctrl+]", "rotate-cw")
        bar.register_command("Edit", "Duplikat Halaman", self._duplicate_selected, "Ctrl+D", "copy")
        bar.register_command("Edit", "Hapus Halaman", self._delete_selected, "Delete", "trash-2")
        bar.register_command("Edit", "OCR Semua", lambda: self._start_ocr(None), "Ctrl+Shift+O", "scan-text")
        bar.register_command("Edit", "OCR Terpilih", lambda: self._start_ocr("selected"), "Ctrl+O", "scan-text")

        # Tool categories from grouped()
        groups = grouped()
        for name in MENU_ORDER:
            specs = groups.get(name, [])
            if not specs:
                continue
            menu = bar.add_menu(name)
            for spec in specs:
                menu.add_command(spec.label, lambda s=spec: self._open_tool(s))
                bar.register_command(name, spec.label, lambda s=spec: self._open_tool(s), "", spec.icon_name if hasattr(spec, 'icon_name') else "")

        # Help menu
        help_menu = bar.add_menu("Bantuan")
        help_menu.add_command("Cara Pakai", self._show_help, "F1")
        help_menu.add_command("Periksa Pembaruan…", self._check_updates_manual)
        help_menu.add_command("Tentang", self._show_about)

        bar.register_command("Bantuan", "Cara Pakai", self._show_help, "F1", "help-circle")
        bar.register_command("Bantuan", "Periksa Pembaruan…", self._check_updates_manual, "", "refresh-cw")
        bar.register_command("Bantuan", "Tentang", self._show_about, "", "info")

        self._menubar = bar

        # Command palette (Ctrl+K)
        self._command_palette = CommandPalette(
            self,
            bar.get_all_commands(),
            on_execute=lambda cmd: cmd(),
        )
        self.bind_all("<Control-k>", lambda e: self._command_palette.show(self.header))
        self.bind_all("<Control-K>", lambda e: self._command_palette.show(self.header))

    def _bind_shortcuts(self) -> None:
        """Bind global keyboard shortcuts for common actions.

        Setiap urutan tombol hanya boleh di-bind **satu kali**. `bind_all`
        tanpa `add="+"` menggantikan binding sebelumnya, jadi dua bind untuk
        `Ctrl+O` membuat yang terakhir menang dan tombol yang tampil di menu
        justru tidak bisa dipakai.
        """
        # File operations
        self.bind_all("<Control-o>", lambda e: self._add_files())
        self.bind_all("<Control-s>", lambda e: self._save())
        self.bind_all("<Control-q>", lambda e: self._on_close())
        self.bind_all("<Control-Delete>", lambda e: self._clear_all())

        # Jalankan tool aktif (sesuai pintasan yang tampil di header)
        self.bind_all("<Control-r>", lambda e: self._run_active_tool())

        # Edit operations
        self.bind_all("<Control-d>", lambda e: self._duplicate_selected())
        self.bind_all("<Delete>", lambda e: self._delete_selected())
        self.bind_all("<Control-bracketleft>", lambda e: self._rotate_selected(-90))
        self.bind_all("<Control-bracketright>", lambda e: self._rotate_selected(90))

        # OCR — Ctrl+Shift+O untuk semua halaman. OCR halaman terpilih memakai
        # Ctrl+Shift+E karena `Ctrl+O` sudah dipakai "Tambah Berkas".
        self.bind_all("<Control-Shift-O>", lambda e: self._start_ocr(None))
        self.bind_all("<Control-Shift-E>", lambda e: self._start_ocr("selected"))

        # Help
        self.bind_all("<F1>", lambda e: self._show_help())

        # Theme toggle
        self.bind_all("<Control-t>", lambda e: self._toggle_theme())

        # Command palette
        self.bind_all("<Control-k>", lambda e: self._command_palette.show(self.header))

        # Navigation
        self.bind_all("<Escape>", lambda e: self._escape_pressed())

    def _escape_pressed(self) -> None:
        """Handle Escape key - close dialogs, clear selection, hide palettes."""
        # Hide command palette
        if hasattr(self, '_command_palette') and self._command_palette.winfo_exists():
            self._command_palette.hide()
        # Clear grid selection
        if hasattr(self, 'grid') and self.grid.selection:
            self.grid.clear_selection()
            self._refresh_thumbs()
        # If tool panel is active, go back to page view
        if hasattr(self, 'tools') and self.tools.spec is not None:
            self.show_page()
            self._refresh_file_list()

    def _toggle_theme(self) -> None:
        """Toggle between light and dark theme."""
        from .app_colors import toggle_theme
        new_theme = toggle_theme()
        # Re-apply styles
        _configure_styles(self)
        # Refresh header theme
        from .app_colors import get_theme
        self.header._theme = get_theme()
        # Update all widgets that need theme refresh
        self._apply_theme_to_children(self)
        self.set_status(f"Tema: {'Gelap' if new_theme == 'dark' else 'Terang'}")

    def _apply_theme_to_children(self, widget: tk.Misc) -> None:
        """Recursively apply theme to all children that have update_theme method."""
        for child in widget.winfo_children():
            if hasattr(child, 'update_theme'):
                child.update_theme()
            self._apply_theme_to_children(child)

    def _open_tool(self, spec) -> None:
        """Dipanggil hanya dari menubar.

        Panel kanan bertukar dari tampilan halaman/OCR ke form perkakas ini.
        Tidak membuka jendela baru, dan tidak ada daftar tool yang perlu
        dipilih lebih dulu.
        """
        self._show_tool()
        self.tools.set_spec(spec)
        self._refresh_add_label()
        # Preview ikut diperbarui karena jenis input tool berubah: PDF dan
        # gambar tetap jadi thumbnail, Office/HTML jadi daftar nama berkas.
        self._refresh_file_list()

    def _run_active_tool(self) -> None:
        """Tombol 'Jalankan' di header: jalankan tool yang sedang dipilih."""
        if self.tools.spec is None:
            self._show_tool()
            self.tools.report(
                "Belum ada perkakas dipilih",
                "Pilih satu perkakas dari menu di atas — misalnya Konversi, Edit,\n"
                "atau Keamanan — untuk mengisi parameternya.",
                tone="warn",
            )
            self.set_status("Pilih perkakas dari menu dulu.")
            return
        self.tools.start()

    def _show_help(self) -> None:
        messagebox.showinfo(
            "Cara Pakai",
            "1. '+ Tambah PDF' untuk menggabungkan beberapa file, lalu seret thumbnail\n"
            "   untuk mengurutkan halaman.\n"
            "2. Baris tombol di atas grid: putar, duplikat, hapus, dan OCR.\n"
            "3. Pilih perkakas dari menu di atas. Isi parameternya di kolom\n"
            "   Perkakas, lalu tekan 'Jalankan' di baris atas.\n"
            "4. Simpan lewat 'Gabung & Simpan'.\n\n"
            "Rentang halaman ditulis seperti: 1-3, 5, 8- (kosong = semua).",
            parent=self,
        )

    def _show_about(self) -> None:
        from .. import __version__

        dialog = tk.Toplevel(self)
        dialog.withdraw()
        dialog.title(f"Tentang {APP_NAME}")
        dialog.transient(self)
        dialog.resizable(False, False)

        outer = ttk.Frame(dialog, style="Panel.TFrame", padding=18)
        outer.pack(fill="both", expand=True)
        outer.columnconfigure(0, weight=1)

        if self._logo_photo is not None:
            logo = ttk.Label(outer, image=self._logo_photo, style="Panel.TLabel")
            logo.image = self._logo_photo  # type: ignore[attr-defined]
            logo.grid(row=0, column=0, sticky="w", pady=(0, 8))

        ttk.Label(outer, text=APP_TITLE, style="ToolTitle.TLabel").grid(
            row=1, column=0, sticky="w"
        )
        ttk.Label(outer, text=f"Versi {__version__}", style="DimOnPanel.TLabel").grid(
            row=2, column=0, sticky="w", pady=(2, 0)
        )
        ttk.Label(
            outer,
            text="OCR, merge, dan Perkakas PDF berbasis PyMuPDF, Tesseract,\n"
                 "Ghostscript, dan LibreOffice. Tanpa iklan, tanpa pelacak.",
            style="Panel.TLabel",
            justify="left",
        ).grid(row=3, column=0, sticky="w", pady=(10, 0))

        ttk.Label(
            outer, text="Dukung pengembangan SelfPDF", style="SectionTitle.TLabel"
        ).grid(row=4, column=0, sticky="w", pady=(14, 2))
        ttk.Label(outer, text=DONATION_URL, style="DimOnPanel.TLabel").grid(
            row=5, column=0, sticky="w"
        )
        ttk.Label(outer, text=f"Lapor bug: {SUPPORT_EMAIL}", style="DimOnPanel.TLabel").grid(
            row=6, column=0, sticky="w"
        )

        buttons = ttk.Frame(outer, style="Panel.TFrame")
        buttons.grid(row=7, column=0, sticky="ew", pady=(16, 0))
        buttons.columnconfigure(0, weight=1)

        def close() -> None:
            dialog.destroy()

        ttk.Button(buttons, text="Donasi", width=0, style="Accent.TButton",
                   command=self._open_donation).grid(row=0, column=0, sticky="w")
        ttk.Button(buttons, text="Salin Email Support", width=0, style="Panel.TButton",
                   command=self._copy_support_email).grid(row=0, column=1, padx=(6, 0))
        ttk.Button(buttons, text="Tutup", width=0, style="Panel.TButton",
                   command=close).grid(row=0, column=2, padx=(6, 0))

        dialog.protocol("WM_DELETE_WINDOW", close)
        dialog.update_idletasks()
        x = self.winfo_rootx() + (self.winfo_width() - dialog.winfo_width()) // 2
        y = self.winfo_rooty() + (self.winfo_height() - dialog.winfo_height()) // 2
        dialog.geometry(f"+{max(0, x)}+{max(0, y)}")
        dialog.deiconify()
        dialog.grab_set()

    def _open_donation(self) -> None:
        """Buka halaman donasi di browser (link dari SUPPORT.md BisikChat)."""
        try:
            opened = webbrowser.open_new_tab(DONATION_URL)
        except Exception:  # noqa: BLE001
            opened = False
        if not opened:
            messagebox.showinfo("Donasi", DONATION_URL, parent=self)

    def _copy_support_email(self) -> None:
        self.clipboard_clear()
        self.clipboard_append(SUPPORT_EMAIL)
        self.set_status(f"Email support disalin: {SUPPORT_EMAIL}")

    # ------------------------------------------------------------- pembaruan

    def _check_updates_on_start(self) -> None:
        """Pemeriksaan diam-diam saat aplikasi dibuka.

        Hasilnya lewat queue (bukan `messagebox` langsung dari thread) supaya
        hanya dialog versi lebih baru yang muncul; kalau sudah terbaru atau
        jaringan mati, tidak ada apa-apa.
        """
        if self._update_busy:
            return
        threading.Thread(
            target=self._update_worker, args=(False,), daemon=True
        ).start()

    def _check_updates_manual(self) -> None:
        """Menu Bantuan → Periksa Pembaruan: selalu memberi umpan balik."""
        if self._update_busy:
            self.set_status("Pemeriksaan pembaruan sedang berjalan…")
            return
        self.set_status("Memeriksa pembaruan…")
        threading.Thread(
            target=self._update_worker, args=(True,), daemon=True
        ).start()

    def _update_worker(self, manual: bool) -> None:
        from .. import __version__
        from ..update import check_for_updates

        self._update_busy = True
        try:
            status, info = check_for_updates(__version__)
        except Exception:  # noqa: BLE001 - jaringan bisa mati kapan saja
            from ..update import STATUS_UNAVAILABLE

            status, info = STATUS_UNAVAILABLE, None
        finally:
            self._update_busy = False
        self.events.put(("update", manual, status, info))

    # ------------------------------------------------------------------- body

    def _build_ui(self) -> None:
        """Badan jendela: grid thumbnail di kiri, panel di kanan.

        Panel kanan **tidak** punya tab "Halaman / Perkakas". Isinya hanya satu
        pada satu waktu:

        * saat aplikasi dibuka — tampilan halaman/OCR,
        * setelah perkakas diklik di menubar — form perkakas itu.

        Jadi tidak ada tombol/tab pilihan ganda, dan tidak ada input yang
        muncul dua kali.
        """
        body = ttk.Frame(self, style="App.TFrame")
        body.pack(fill="both", expand=True, padx=12, pady=10)
        body.columnconfigure(0, weight=1, minsize=420)
        body.columnconfigure(1, weight=0, minsize=PANEL_WIDTH)
        body.rowconfigure(0, weight=1)

        left = ttk.Frame(body, style="App.TFrame")
        left.grid(row=0, column=0, sticky="nsew")
        left.columnconfigure(0, weight=1)
        left.rowconfigure(1, weight=1)
        # Grid tetap merebut ruang; daftar berkas hanya muncul saat dibutuhkan.

        self._build_action_bar(left)

        # Daftar berkas yang tidak bisa jadi thumbnail (Office, HTML, dll).
        # Kalau tool aktif memang butuh jenis itu, daftar ini menggantikan
        # preview yang kosong — user tetap tahu file-nya sudah masuk.
        self.file_list = tk.Label(
            left, text="", bg=BG_PANEL, fg=FG_DIM, anchor="nw", justify="left",
            font=("TkFixedFont", 9), padx=8, pady=6,
        )
        self.file_list.grid(row=2, column=0, sticky="ew", pady=(6, 0))
        self.file_list.grid_remove()

        self.grid = PageGrid(
            left,
            on_reorder=self._on_reorder,
            on_select=self._on_select,
            on_context=self._on_context_menu,
            on_activate=self._on_activate,
            style="App.TFrame",
        )
        self.grid.grid(row=1, column=0, sticky="nsew")

        self._build_side_panel(body)

        footer = ttk.Frame(self, style="App.TFrame")
        footer.pack(fill="x", padx=12, pady=(0, 8))
        footer.columnconfigure(0, weight=1)

        self.progress = ttk.Progressbar(footer, mode="determinate", length=220)
        self.progress.grid(row=0, column=0, sticky="w")

        ttk.Label(footer, textvariable=self.status_var, style="Dim.TLabel").grid(
            row=0, column=1, sticky="e"
        )

    def _build_action_bar(self, parent: ttk.Frame) -> None:
        """Tombol yang bekerja pada halaman terpilih, tepat di atas grid."""
        bar = ttk.Frame(parent, style="App.TFrame")
        bar.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        self._action_bar = bar

        group = ttk.Frame(bar, style="App.TFrame")
        group.pack(side="left")
        self._register_lockable(
            ttk.Button(group, text="Putar ↺", width=0,
                         command=lambda: self._rotate_selected(-90))
        ).pack(side="left")
        self._register_lockable(
            ttk.Button(group, text="Putar ↻", width=0,
                         command=lambda: self._rotate_selected(90))
        ).pack(side="left", padx=(6, 0))
        self._register_lockable(
            ttk.Button(group, text="Duplikat", width=0, command=self._duplicate_selected)
        ).pack(side="left", padx=(6, 0))
        self._register_lockable(
            ttk.Button(group, text="Hapus", width=0, command=self._delete_selected)
        ).pack(side="left", padx=(6, 0))

        # Tombol OCR hidup di sini saja. Panel kanan tidak mengulangnya.
        ocr = ttk.Frame(bar, style="App.TFrame")
        ocr.pack(side="left", padx=(14, 0))
        self._register_lockable(
            ttk.Button(ocr, text="OCR Semua", width=0, style="Ok.TButton",
                       command=lambda: self._start_ocr(None))
        ).pack(side="left")
        self._register_lockable(
            ttk.Button(ocr, text="OCR Terpilih", width=0,
                       command=lambda: self._start_ocr("selected"))
        ).pack(side="left", padx=(6, 0))

        self.info_var = tk.StringVar(value="0 halaman")
        ttk.Label(bar, textvariable=self.info_var, style="Dim.TLabel").pack(
            side="right", padx=(0, 4)
        )

    # --------------------------------------------------------- panel samping

    def _build_side_panel(self, parent: ttk.Frame) -> None:
        panel = ttk.Frame(parent, style="Panel.TFrame", padding=12, width=PANEL_WIDTH)
        panel.grid(row=0, column=1, sticky="nsew", padx=(10, 0))
        panel.grid_propagate(False)
        panel.columnconfigure(0, weight=1)
        panel.rowconfigure(0, weight=1)

        # Dua isinya dibuat sekali; `show_page`/`_show_tool` yang menentukan mana
        # yang terlihat, jadi tidak ada "//tab" untuk dipilih pengguna.
        page_frame = ttk.Frame(panel, style="Panel.TFrame")
        tool_frame = ttk.Frame(panel, style="Panel.TFrame")
        for frame in (page_frame, tool_frame):
            frame.columnconfigure(0, weight=1)
            frame.rowconfigure(0, weight=1)
        self._panel_pages = [page_frame, tool_frame]

        self.page_frame = page_frame
        self._build_page_view(page_frame)
        self._build_tool_view(tool_frame)
        self.show_page()

    def show_page(self) -> None:
        """Tampilkan tampilan halaman/OCR (juga tampilan awal aplikasi)."""
        self._switch_panel(0)

    def _show_tool(self) -> None:
        self._switch_panel(1)

    def _switch_panel(self, index: int) -> None:
        for position, frame in enumerate(self._panel_pages):
            if position == index:
                frame.grid(row=0, column=0, sticky="nsew")
            else:
                frame.grid_forget()

    # ------------------------------------------------------- panel: halaman

    def _build_page_view(self, page: ttk.Frame) -> None:
        """Teks halaman terpilih + pengaturan OCR/simpan.

        Tombol OCR sengaja tidak diulang di sini — sudah ada satu kali di baris
        tombol di atas grid.
        """
        page.columnconfigure(0, weight=1)
        view = ttk.Frame(page, style="Panel.TFrame")
        view.grid(row=0, column=0, sticky="nsew")
        view.columnconfigure(0, weight=1)

        ttk.Label(view, text="Halaman", style="SectionTitle.TLabel").grid(
            row=0, column=0, sticky="w")

        options = ttk.Frame(view, style="Panel.TFrame")
        options.grid(row=1, column=0, sticky="ew", pady=(10, 0))
        options.columnconfigure(1, weight=1)

        ttk.Label(options, text="Bahasa OCR", style="Field.TLabel").grid(
            row=0, column=0, sticky="w", padx=(0, 6)
        )
        self.lang_box = self._register_lockable(
            ttk.Combobox(options, textvariable=self.lang_var, values=["eng"], state="readonly",
                         width=8)
        )
        self.lang_box.grid(row=0, column=1, sticky="w")

        ttk.Label(options, text="Simpan sebagai", style="Field.TLabel").grid(
            row=1, column=0, sticky="w", padx=(0, 6), pady=(8, 0)
        )
        self.mode_box = self._register_lockable(
            ttk.Combobox(options, textvariable=self.save_mode,
                         values=list(SAVE_LABELS.values()), state="readonly")
        )
        self.mode_box.grid(row=1, column=1, sticky="ew", pady=(8, 0))

        self.tesseract_note = tk.Label(
            view, text="", bg=BG_PANEL, fg=WARN, anchor="w", justify="left", wraplength=330
        )
        self.tesseract_note.grid(row=2, column=0, sticky="ew", pady=(8, 0))

        ttk.Label(view, text="Teks halaman terpilih", style="SectionTitle.TLabel").grid(
            row=3, column=0, sticky="w", pady=(14, 4)
        )
        self.text_view = tk.Text(
            view,
            wrap="word",
            bg="#161a21",
            fg=FG,
            insertbackground=FG,
            relief="flat",
            highlightthickness=1,
            highlightbackground="#3a4250",
            height=8,
            font=("TkFixedFont", 10),
            padx=8,
            pady=8,
        )
        self.text_view.grid(row=4, column=0, sticky="nsew")
        self.text_view.configure(state="disabled")
        self.text_view.bind("<Control-f>", lambda _e: self.search_entry.focus_set())
        view.rowconfigure(4, weight=1)

        search = ttk.Frame(view, style="Panel.TFrame")
        search.grid(row=5, column=0, sticky="ew", pady=(12, 0))
        search.columnconfigure(1, weight=1)
        ttk.Label(search, text="Cari", style="Field.TLabel").grid(row=0, column=0, sticky="w",
                                                                  padx=(0, 6))
        self.search_entry = self._register_lockable(
            ttk.Entry(search, textvariable=self.search_var)
        )
        self.search_entry.grid(row=0, column=1, sticky="ew")
        self.search_entry.bind("<Return>", self._run_search)

        self.search_result = tk.Label(
            view, text="", bg=BG_PANEL, fg=FG_DIM, anchor="w", justify="left", wraplength=330
        )
        self.search_result.grid(row=6, column=0, sticky="ew", pady=(4, 10))

        self.page_result = ResultView(view, height=4)
        self.page_result.grid(row=7, column=0, sticky="ew")
        self.page_result.grid_remove()

    # ------------------------------------------------------- panel: perkakas

    def _build_tool_view(self, page: ttk.Frame) -> None:
        self.tools = ToolPanel(page, host=self, on_busy=self._on_tool_busy)
        self.tools.grid(row=0, column=0, sticky="nsew")


    # --------------------------------------------------------------- sumber

    def _add_files(self) -> None:
        """Satu-satunya cara memasukkan berkas, untuk semua pekerjaan.

        Jenis file yang diterima mengikuti tool yang sedang dipilih, dan
        hasilnya langsung tampil di preview — bukan disembunyikan di form.
        """
        input_kind = self._insert_kind()
        patterns = list(ADD_FILETYPES.get(input_kind, (("Semua", "*"),)))
        paths = filedialog.askopenfilenames(
            title=f"Pilih {ADD_LABELS.get(input_kind, 'berkas').lstrip('+ ')}",
            filetypes=patterns,
            parent=self,
        )
        if not paths:
            return
        try:
            added, errors = self.project.add_files(list(paths))
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Gagal membuka berkas", str(exc), parent=self)
            return

        self._refresh_all()
        if errors:
            self.set_status("Sebagian file gagal: " + errors[0])
        elif added:
            self.set_status(f"{added} halaman ditambahkan ke preview.")
        else:
            self.set_status(f"{len(paths)} berkas ditambahkan ke preview.")

    def _insert_kind(self) -> str:
        """Jenis file yang dibutuhkan tool aktif (default PDF)."""
        spec = self.tools.spec
        return spec.input_kind if spec is not None else INPUT_PDF_MULTI

    def _refresh_add_label(self) -> None:
        """Samakan label tombol Tambah dengan kebutuhan tool yang dipilih."""
        label = ADD_LABELS.get(self._insert_kind(), DEFAULT_ADD_LABEL)
        for button in self.header.action_buttons:
            if str(button.cget("text")).startswith("+ Tambah"):
                button.configure(text=label)
                return

    def _clear_all(self) -> None:
        if self._busy_process():
            return
        if not self.project.files and not self.project.pages:
            return
        if not messagebox.askyesno("Kosongkan daftar", "Hapus semua berkas dari daftar?",
                                    parent=self):
            return
        self.project.close()
        self.thumbs.clear()
        self.grid.clear_selection()
        self._refresh_all()

    # -------------------------------------------------------------- refresh

    def _refresh_all(self) -> None:
        pages = self.project.pages
        self.grid.set_cells(len(pages))
        self._refresh_thumbs()
        self._update_info()
        self._sync_mode()
        self._refresh_file_list()

    def _refresh_thumbs(self) -> None:
        for index in range(len(self.project.pages)):
            self._refresh_thumb(index)

    def _refresh_thumb(self, index: int) -> None:
        pages = self.project.pages
        if not (0 <= index < len(pages)):
            return
        ref = pages[index]
        source = self.project.sources[ref.doc_key]
        try:
            page = source.doc[ref.src_index]
            base_rotation = page.rotation
            photo = self.thumbs.get_page(
                page, ref.doc_key, ref.src_index, ref.rotation, base_rotation,
                THUMB_HEIGHT, master=self,
            )
        except Exception:  # noqa: BLE001
            photo = None

        kind = KIND_LABELS.get(source.kind, "Berkas")
        label = f"{os.path.basename(source.path)} · h{ref.src_index + 1}"
        if ref.rotation:
            label += f"  ({ref.rotation}°)"
        # Badge jenis file: preview menampilkan PDF maupun gambar, jadi user
        # bisa melihat apa yang sudah dimasukkan tanpa membuka menubar.
        self.grid.update_cell(
            index, photo, f"[{kind}] {label}", ref.is_ocr_done, index in self.grid.selection
        )

    def _refresh_file_list(self) -> None:
        """Tampilkan daftar berkas non-thumbnail tepat di atas preview.

        PDF dan gambar sudah muncul sebagai thumbnail, jadi baris ini hanya
        dipakai untuk tool yang butuh Office/HTML/dll. Untuk tool seperti itu,
        daftar nama berkas inilah yang menggantikan preview yang kosong.
        """
        spec = self.tools.spec
        if spec is None:
            self.file_list.grid_remove()
            return

        wanted = self.project.inputs_for(spec.input_kind)
        # Yang tidak punya thumbnail = tidak bisa dirender jadi halaman.
        plain = [p for p in wanted if kind_of(p) not in RENDERABLE_KINDS]
        if not plain:
            self.file_list.grid_remove()
            return

        head = "Berkas untuk " + spec.label + ":"
        body = "\n".join(f"  - {os.path.basename(p)}" for p in plain)
        self.file_list.configure(text=f"{head}\n{body}")
        self.file_list.grid()

    def _update_info(self) -> None:
        total = len(self.project.pages)
        ocr = sum(1 for p in self.project.pages if p.is_ocr_done)
        # `files` menghitung semua yang sudah dimasukkan, termasuk yang tidak
        # jadi halaman (Office/HTML), supaya jumlahnya tidak setengah jadi.
        files = len(self.project.files)
        if total:
            self.info_var.set(f"{total} halaman · {files} file · {ocr} ber-OCR")
        elif files:
            self.info_var.set(f"0 halaman · {files} file (tanpa thumbnail)")
        else:
            self.info_var.set("0 halaman")

    # -------------------------------------------------------------- reorder

    def _on_reorder(self, old_index: int, new_index: int) -> None:
        self.project.move(old_index, new_index)
        selection = set(self.grid.selection)
        self.grid.clear_selection()
        self._refresh_thumbs()
        for item in selection:
            self.grid.select(item)
        self._update_info()

    # ------------------------------------------------------------ selection

    def _on_select(self, index: int, event: tk.Event) -> None:
        extend = bool(event.state & 0x0001)  # Shift
        index = self.grid.select(index, extend=extend)
        self._refresh_thumbs()
        self.grid.scroll_to_index(index)
        # Memilih halaman = mau lihat teksnya, jadi panel kanan kembali ke
        # tampilan halaman. Perkakas yang tadi dibuka tidak ikut hilang
        # permanen — klik lagi di menubar untuk melanjutkan.
        self.show_page()
        self._show_page_text(index)
        self._refresh_file_list()

    def _on_activate(self, index: int) -> None:
        self._run_ocr([index])

    def _on_context_menu(self, index: int, event: tk.Event) -> None:
        self.grid.select(index, extend=bool(event.state & 0x0001))
        self._refresh_thumbs()

        menu = tk.Menu(self, tearoff=0, bg=BG_PANEL, fg=FG, activebackground=ACCENT,
                       activeforeground="#ffffff")
        menu.add_command(label="OCR halaman ini", command=lambda: self._run_ocr([index]))
        menu.add_command(label="Putar kiri", command=lambda: self._rotate(index, -90))
        menu.add_command(label="Putar kanan", command=lambda: self._rotate(index, 90))
        menu.add_command(label="Duplikat", command=lambda: self._duplicate(index))
        menu.add_separator()
        menu.add_command(label="Hapus halaman", command=lambda: self._delete([index]))
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    # -------------------------------------------------------------- editing

    def _selected_or_active(self) -> list[int]:
        selection = self.grid.selection
        return selection if selection else []

    def _delete_selected(self) -> None:
        self._delete(self._selected_or_active())

    def _busy_process(self) -> bool:
        """True kalau ada proses background yang sedang memakai dokumen proyek."""
        ocr_busy = self._worker is not None and self._worker.is_alive()
        if ocr_busy:
            self.set_status("Tunggu proses yang sedang berjalan selesai.")
            return True
        if self.tools.is_busy:
            self.set_status("Perkakas sedang berjalan; tunggu selesai dulu.")
            return True
        return False

    def _delete(self, indices: list[int]) -> None:
        if not indices:
            self.set_status("Pilih halaman yang ingin dihapus lebih dulu.")
            return
        if self._busy_process():
            return
        self.project.remove_many(indices)
        self.grid.clear_selection()
        self._refresh_all()

    def _duplicate_selected(self) -> None:
        indices = self._selected_or_active()
        if not indices:
            self.set_status("Pilih halaman yang ingin diduplikat lebih dulu.")
            return
        for index in reversed(indices):
            self.project.duplicate(index)
        self._refresh_all()

    def _duplicate(self, index: int) -> None:
        self.project.duplicate(index)
        self._refresh_all()

    def _rotate_selected(self, delta: int) -> None:
        indices = self._selected_or_active()
        if not indices:
            self.set_status("Pilih halaman yang ingin diputar lebih dulu.")
            return
        for index in indices:
            self.project.rotate(index, delta)
        self._refresh_thumbs()

    def _rotate(self, index: int, delta: int) -> None:
        self.project.rotate(index, delta)
        self._refresh_all()

    # ------------------------------------------------------------------ OCR

    def _check_tesseract(self) -> None:
        try:
            check_available(self.lang_var.get())
            self.tesseract_note.configure(text="", fg=WARN)
        except OcrUnavailable as exc:
            short = str(exc).splitlines()[0]
            self.tesseract_note.configure(
                text=short + "\nJalankan: sudo apt install tesseract-ocr tesseract-ocr-eng",
                fg=WARN,
            )

    def _handle_update_result(self, manual: bool, status: str, info) -> None:
        """Terapkan hasil `check_for_updates` di thread GUI.

        Pemeriksaan otomatis (bukan dari menu) hanya memberi kabar bila memang
        ada versi lebih baru — tidak ada dialog "sudah terbaru" yang tiba-tiba
        muncul saat aplikasi dibuka.
        """
        from ..update import STATUS_CURRENT, STATUS_UNAVAILABLE, STATUS_UPDATE

        if status == STATUS_UPDATE and info is not None:
            self.set_status(f"Pembaruan tersedia: {info.version}")
            self._show_update_dialog(info)
            return
        if not manual:
            return
        if status == STATUS_CURRENT:
            messagebox.showinfo(
                "Pembaruan", "SelfPDF sudah versi terbaru.", parent=self
            )
        else:
            messagebox.showwarning(
                "Pembaruan",
                "Tidak bisa memeriksa pembaruan.\n"
                "Periksa koneksi internet, lalu coba lagi.",
                parent=self,
            )

    def _show_update_dialog(self, info) -> None:
        """Dialog non-modal: versi lebih baru sudah tersedia.

        Sengaja tanpa `grab_set` — pengguna boleh menutup, menunda, atau
        tetap bekerja dengan jendela utama sementara dialog ini terbuka.
        """
        from .. import __version__

        dialog = tk.Toplevel(self)
        dialog.title("Pembaruan Tersedia")
        dialog.transient(self)
        dialog.resizable(False, False)

        outer = ttk.Frame(dialog, style="Panel.TFrame", padding=18)
        outer.pack(fill="both", expand=True)
        outer.columnconfigure(0, weight=1)

        ttk.Label(outer, text=f"Pembaruan {info.version} tersedia",
                  style="ToolTitle.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(outer, text=f"Versi Anda: {__version__}",
                  style="DimOnPanel.TLabel").grid(row=1, column=0, sticky="w",
                                                  pady=(2, 0))

        notes = (info.notes or "").strip()
        if notes:
            body = tk.Text(
                outer, wrap="word", height=10, width=56,
                bg="#161a21", fg=FG, insertbackground=FG, relief="flat",
                highlightthickness=1, highlightbackground="#3a4250",
                font=("TkFixedFont", 9), padx=8, pady=8,
            )
            body.insert("1.0", notes[:2000])
            body.configure(state="disabled")
            body.grid(row=2, column=0, sticky="ew", pady=(12, 0))

        buttons = ttk.Frame(outer, style="Panel.TFrame")
        buttons.grid(row=3, column=0, sticky="ew", pady=(16, 0))
        ttk.Button(buttons, text="Unduh Sekarang", style="Accent.TButton",
                   command=lambda: self._open_update(info)).pack(side="left")
        ttk.Button(buttons, text="Nanti Saja", style="Panel.TButton",
                   command=dialog.destroy).pack(side="left", padx=(8, 0))

        dialog.protocol("WM_DELETE_WINDOW", dialog.destroy)
        dialog.update_idletasks()
        x = self.winfo_rootx() + (self.winfo_width() - dialog.winfo_width()) // 2
        y = self.winfo_rooty() + (self.winfo_height() - dialog.winfo_height()) // 2
        dialog.geometry(f"+{max(0, x)}+{max(0, y)}")

    def _open_update(self, info) -> None:
        """Buka halaman unduh rilis di browser default."""
        url = info.download_url or info.page_url
        try:
            opened = webbrowser.open_new_tab(url)
        except Exception:  # noqa: BLE001
            opened = False
        if not opened:
            messagebox.showinfo("Pembaruan", url, parent=self)

    def _start_ocr(self, scope: str | None) -> None:
        """Pintasan OCR dari tombol/menubar: `None` = semua, `"selected"`.

        Daftar indeks yang perlu di-OCR ditentukan di sini, lalu diserahkan ke
        `_run_ocr` — jalur yang sama dipakai klik ganda dan menu klik kanan.
        """
        if self._worker is not None and self._worker.is_alive():
            self.set_status("Proses OCR sebelumnya belum selesai.")
            return
        if self.tools.is_busy:
            self.set_status("Perkakas sedang berjalan; tunggu selesai dulu.")
            return

        if scope == "selected":
            indices = self._selected_or_active()
            if not indices:
                self.set_status("Pilih halaman yang ingin di-OCR.")
                return
        else:
            indices = [
                i
                for i, ref in enumerate(self.project.pages)
                if not ref.is_ocr_done
            ]
            if not indices:
                if not self.project.pages:
                    self.set_status("Belum ada halaman untuk di-OCR.")
                    return
                if not messagebox.askyesno(
                    "Semua sudah di-OCR", "Semua halaman sudah punya teks OCR. OCR ulang semua?",
                    parent=self,
                ):
                    return
                indices = list(range(len(self.project.pages)))

        self._run_ocr(indices)

    def _run_ocr(self, indices: list[int]) -> None:
        """Jalankan OCR pada indeks halaman tertentu.

        Dipakai tiga tempat: tombol OCR, klik ganda thumbnail, dan item menu
        "OCR halaman ini". Ketiganya memakai jalur yang sama supaya tidak ada
        pintasan OCR yang bisa gagal hanya karena tidak punya method.
        """
        if self._worker is not None and self._worker.is_alive():
            self.set_status("Proses OCR sebelumnya belum selesai.")
            return
        if self.tools.is_busy:
            self.set_status("Perkakas sedang berjalan; tunggu selesai dulu.")
            return

        wanted = [i for i in indices if 0 <= i < len(self.project.pages)]
        if not wanted:
            self.set_status("Tidak ada halaman yang bisa di-OCR.")
            return

        try:
            lang = self.lang_var.get()
            check_available(lang)
        except OcrUnavailable as exc:
            messagebox.showerror("OCR tidak tersedia", str(exc), parent=self)
            return

        # `page_at` mengembalikan objek halaman PyMuPDF milik dokumen sumber.
        # Dokumen itu dipakai worker thread, jadi halaman yang sudah ditutup
        # (mis. karena proyek dikosongkan) harus dilewati, bukan diteruskan.
        jobs: list[OcrJob] = []
        for index in wanted:
            try:
                jobs.append(OcrJob(index, self._page_for(index), lang))
            except Exception:  # noqa: BLE001 - sumber sudah tidak ada
                continue
        if not jobs:
            self.set_status("Halaman tidak tersedia untuk di-OCR.")
            return

        self._jobs = jobs
        self.progress.configure(maximum=len(self._jobs), value=0)
        self._set_running(True, "OCR berjalan…")
        self.page_result.show("OCR berjalan", f"{len(self._jobs)} halaman dikirim ke mesin OCR.")

        self._worker = threading.Thread(target=self._worker_loop, daemon=True)
        self._worker.start()

    def _page_for(self, index: int) -> object:
        return self.project.page_at(index)

    def _worker_loop(self) -> None:
        total = len(self._jobs)
        for position, job in enumerate(self._jobs):
            try:
                words = run_ocr(job.page, lang=job.lang, dpi=OCR_DPI)
                self.events.put(("ocr_done", job.index, words, position + 1, total))
            except Exception as exc:  # noqa: BLE001
                self.events.put(
                    ("ocr_error", job.index, f"{exc}\n{traceback.format_exc(limit=2)}", position + 1, total)
                )
        self.events.put(("all_done",))

    def _drain_events(self) -> None:
        try:
            while True:
                kind, *payload = self.events.get_nowait()
                if kind == "tool":
                    self.tools.handle(payload[0], payload[1])
                    continue
                if kind == "ocr_done":
                    index, words, done, total = payload
                    if 0 <= index < len(self.project.pages):
                        ref = self.project.pages[index]
                        ref.words = words
                        ref.ocr_dpi = OCR_DPI
                    self.progress.configure(value=done, maximum=total)
                    self._refresh_thumb(index)
                    self._update_info()
                    if index == (self.grid.selection or [-1])[0]:
                        self._show_page_text(index)
                elif kind == "ocr_error":
                    index, message, done, total = payload
                    self.progress.configure(value=done, maximum=total)
                    self.page_result.show(f"Halaman {index + 1} gagal", message, tone="error")
                    self.set_status(f"Halaman {index + 1}: OCR gagal.")
                elif kind == "all_done":
                    self._set_running(False)
                    ocr = sum(1 for p in self.project.pages if p.is_ocr_done)
                    self.set_status(f"Selesai. {ocr} halaman punya teks OCR.")
                    self.page_result.show("OCR selesai",
                                     f"{ocr} halaman punya teks OCR.", tone="ok")
                elif kind == "saved":
                    path, error = payload
                    # Tanpa cabang ini tombol tidak pernah dinyalakan lagi
                    # setelah menyimpan.
                    self._set_running(False)
                    if error:
                        self.page_result.show("Gagal menyimpan", error, tone="error")
                        self.set_status("Gagal menyimpan.")
                    else:
                        self.set_status(f"Tersimpan: {os.path.basename(path)}")
                        self.page_result.show(
                            "Tersimpan",
                            f"{path}\n\n{len(self.project.pages)} halaman.",
                            tone="ok",
                            outputs=[path],
                        )
                elif kind == "update":
                    manual, status, info = payload
                    self._handle_update_result(manual, status, info)
        except queue.Empty:
            pass
        self.after(80, self._drain_events)

    def _set_running(self, running: bool, note: str = "") -> None:
        """Matikan tombol, input, dan grid selama proses background berjalan.

        Combobox/entry dikembalikan ke state aslinya (bukan `normal`),
        supaya tetap `readonly`.

        Grid ikut dinonaktifkan karena worker berjalan di thread lain dan
        masih memakai dokumen sumber proyek. Menghapus halaman saat itu bisa
        menutup dokumen yang sedang dirender.
        """
        for widget in self._lockable:
            try:
                widget.configure(state="disabled" if running else self._restore_state(widget))
            except tk.TclError:
                pass
        try:
            self.grid.set_enabled(not running)
        except tk.TclError:
            pass
        if note:
            self.set_status(note)
        self.update_idletasks()

    def _on_tool_busy(self, busy: bool) -> None:
        """Dipanggil `ToolPanel` saat proses tool mulai/selesai.

        Tombol "Jalankan" kini ada di header, jadi jendela utama yang mengunci
        seluruh tombolnya sendiri selama tool berjalan.
        """
        self._set_running(busy)

    def _restore_state(self, widget: tk.Misc) -> str:
        if isinstance(widget, (ttk.Combobox, ttk.Entry)):
            return "readonly" if isinstance(widget, ttk.Combobox) else "normal"
        return "normal"

    def _register_lockable(self, widget: tk.Misc) -> tk.Misc:
        self._lockable.append(widget)
        return widget

    # ----------------------------------------------------------------- view

    def _show_page_text(self, index: int) -> None:
        text = self.project.page_text(index)
        source = self.project.source_label(index)
        header = f"── {source} · halaman {index + 1} ──\n"
        body = text if text else "Belum ada teks OCR.\nKlik kanan → OCR halaman ini."
        self.text_view.configure(state="normal")
        self.text_view.delete("1.0", "end")
        self.text_view.insert("1.0", header + body)
        self.text_view.configure(state="disabled")

    def _run_search(self, _event: tk.Event | None = None) -> None:
        query = self.search_var.get().strip()
        if not query:
            self.search_result.configure(text="")
            return
        hits = self.project.search_text(query)
        if not hits:
            self.search_result.configure(text=f'Tidak ada hasil untuk "{query}".')
            return
        shown = "\n".join(f"h{index + 1}: {line[:60]}" for index, line in hits[:6])
        extra = f"\n… +{len(hits) - 6} hasil lain" if len(hits) > 6 else ""
        self.search_result.configure(text=shown + extra)
        self.grid.select(hits[0][0])
        self._refresh_thumbs()
        self.grid.scroll_to_index(hits[0][0])
        self._show_page_text(hits[0][0])

    # ----------------------------------------------------------------- save

    def _save(self) -> None:
        if not self.project.pages:
            self.set_status("Tambahkan file PDF terlebih dahulu.")
            return
        self._sync_mode()
        path = filedialog.asksaveasfilename(
            title="Simpan PDF hasil",
            defaultextension=".pdf",
            filetypes=[("PDF", "*.pdf")],
            initialfile="merged.pdf",
            parent=self,
        )
        if not path:
            return

        ocr_pages = sum(1 for p in self.project.pages if p.is_ocr_done)
        if self._mode_key == SAVE_RAW and ocr_pages:
            if not messagebox.askyesno(
                "Mode Original",
                f"{ocr_pages} halaman punya teks OCR.\n"
                "Mode 'Original' akan membuang hasil OCR. Lanjutkan?",
                parent=self,
            ):
                return

        self._set_running(True, "Menyimpan PDF…")
        self.page_result.show("Menyimpan…", path)
        threading.Thread(target=self._save_worker, args=(path,), daemon=True).start()

    def _save_worker(self, path: str) -> None:
        try:
            self.project.save(path, self._mode_key)
            self.events.put(("saved", path, None))
        except Exception as exc:  # noqa: BLE001
            self.events.put(("saved", path, f"{exc}\n{traceback.format_exc(limit=3)}"))

    def _sync_mode(self) -> None:
        label = self.save_mode.get()
        for key, text in SAVE_LABELS.items():
            if text == label:
                self._mode_key = key
                return
        self._mode_key = SAVE_SEARCHABLE

    # ---------------------------------------------------------------- misc

    def set_status(self, message: str) -> None:
        """Tulis pesan ke bar status jendela utama.

        Dipakai juga oleh `ToolPanel`, jadi ini bagian dari antarmuka host
        yang harus tetap ada.
        """
        self.status_var.set(message)

    def _on_close(self) -> None:
        self.project.close()
        self.destroy()


def main() -> None:
    app = MainWindow()
    app.mainloop()
