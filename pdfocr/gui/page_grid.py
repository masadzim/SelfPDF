"""Widget Tkinter: grid thumbnail halaman dengan drag-reorder."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Callable


class ScrollFrame(ttk.Frame):
    """Frame yang bisa di-scroll vertikal, dengan wheel event yang mulus."""

    def __init__(self, master: tk.Misc, **kwargs) -> None:
        super().__init__(master, **kwargs)
        self.canvas = tk.Canvas(self, highlightthickness=0, bd=0)
        self.scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.body = ttk.Frame(self.canvas)

        self._window = self.canvas.create_window((0, 0), window=self.body, anchor="nw")
        self.canvas.configure(yscrollcommand=self._on_scroll)

        # Scrollbar dipasang lebih dulu supaya canvas yang memakai `expand`
        # tidak memakan seluruh lebar dan menyisakan nol piksel untuknya.
        self.scrollbar.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)

        self.body.bind("<Configure>", self._sync_scrollregion)
        self.canvas.bind("<Configure>", self._sync_width)
        self._bind_wheel(self)
        self._bind_wheel(self.canvas)
        self._bind_wheel(self.body)

    def _sync_scrollregion(self, _event: tk.Event | None = None) -> None:
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _sync_width(self, event: tk.Event) -> None:
        self.canvas.itemconfigure(self._window, width=event.width)

    def _on_scroll(self, first: str, last: str) -> None:
        # `pack_configure`, bukan `pack` ulang: urutan pack harus tetap
        # scrollbar-dulu-canvas, kalau tidak scrollbar dapat nol lebar.
        if float(first) <= 0.0 and float(last) >= 1.0:
            self.scrollbar.pack_forget()
        else:
            self.scrollbar.pack_configure(side="right", fill="y")
        self.scrollbar.set(first, last)

    def _bind_wheel(self, widget: tk.Misc) -> None:
        widget.bind_all("<MouseWheel>", self._on_wheel, add="+")
        widget.bind_all("<Button-4>", self._on_wheel, add="+")
        widget.bind_all("<Button-5>", self._on_wheel, add="+")

    def _on_wheel(self, event: tk.Event) -> None:
        if not self.scrollbar.winfo_ismapped():
            return
        # Kursor adalah penentu, bukan widget yang kebetulan ada di bawahnya:
        # binding dipasang dengan bind_all sehingga semua widget menerimanya.
        x = getattr(event, "x_root", None)
        y = getattr(event, "y_root", None)
        if x is None or y is None or not self._cursor_inside(x, y):
            return

        if event.num == 4 or getattr(event, "delta", 0) > 0:
            self.canvas.yview_scroll(-3, "units")
        elif event.num == 5 or getattr(event, "delta", 0) < 0:
            self.canvas.yview_scroll(3, "units")

    def _cursor_inside(self, x: int, y: int) -> bool:
        return (
            self.winfo_rootx() <= x <= self.winfo_rootx() + self.winfo_width()
            and self.winfo_rooty() <= y <= self.winfo_rooty() + self.winfo_height()
        )


class PageGrid(ttk.Frame):
    """Grid thumbnail yang bisa di-drag untuk mengurutkan ulang halaman.

    Callback yang dipakai:
      on_reorder(from_index, to_index)  dipanggil saat urutan berubah
      on_select(index, event)           saat thumbnail diklik / dipilih
      on_context(index, event)          saat klik-kanan
      on_activate(index)                saat double-klik
    """

    COLUMNS_MIN = 150
    COLUMNS_MAX = 8
    THUMB_HEIGHT = 190
    PAD_X = 6
    PAD_Y = 6

    def __init__(
        self,
        master: tk.Misc,
        on_reorder: Callable[[int, int], None],
        on_select: Callable[[int, tk.Event], None],
        on_context: Callable[[int, tk.Event], None],
        on_activate: Callable[[int], None],
        **kwargs,
    ) -> None:
        super().__init__(master, **kwargs)
        self.on_reorder = on_reorder
        self.on_select = on_select
        self.on_context = on_context
        self.on_activate = on_activate

        self._cells: list[tk.Frame] = []
        self._cell_index: dict[int, int] = {}
        self._columns = 4
        self._cell_width = self.COLUMNS_MIN

        self.scroller = ScrollFrame(self)
        self.scroller.pack(side="left", fill="both", expand=True)
        self.grid_frame = self.scroller.body
        self.grid_frame.configure(padding=(6, 6))

        # Configure pada canvas jauh lebih andal daripada pada PageGrid: ia
        # selalu memicu saat area terlihat berubah, termasuk saat halaman
        # ditambahkan setelah jendela selesai dirender.
        #
        # `add="+"` itu wajib: `ScrollFrame` juga memasang `<Configure>` di
        # canvas yang sama untuk menyamakan lebar frame isi. Bind tanpa `+`
        # akan menggantikannya, sehingga `grid_frame` tidak pernah dipaksa
        # selebar area tampilan dan kolom paling kanan terpotong.
        self.scroller.canvas.bind("<Configure>", self._on_resize, add="+")
        self.bind("<Configure>", self._on_resize, add="+")
        self._selection: set[int] = set()
        self._thumb_height = self.THUMB_HEIGHT
        self._drag_from: int | None = None
        self._drag_to: int | None = None
        self._press_pos: tuple[int, int] = (0, 0)
        self._drag_moved = False
        self._suppress = False
        self._enabled = True

    # ------------------------------------------------------------- geometry

    def _on_resize(self, _event: tk.Event | None = None) -> None:
        self._relayout(keep_order=True)

    def _available_width(self) -> int:
        """Lebar area gambar, dikurangi ruang scrollbar."""
        width = self.scroller.canvas.winfo_width()
        if width <= 1:
            width = self.scroller.winfo_width()
        return max(width, self.COLUMNS_MIN)

    def _compute_columns(self, width: int) -> tuple[int, int]:
        usable = max(width - 24, self.COLUMNS_MIN)
        columns = int(usable // self.COLUMNS_MIN)
        columns = max(1, min(self.COLUMNS_MAX, columns))
        cell_width = usable // columns
        return columns, cell_width

    def _relayout(self, keep_order: bool = False) -> None:
        if self._suppress:
            return
        columns, cell_width = self._compute_columns(self._available_width())
        if columns == self._columns and cell_width == self._cell_width and keep_order:
            return

        self._columns = columns
        self._cell_width = cell_width

        for index, cell in enumerate(self._cells):
            row, col = divmod(index, columns)
            cell.grid(row=row, column=col, padx=self.PAD_X, pady=self.PAD_Y, sticky="nsew")

        # Hanya kolom yang benar-benar dipakai yang boleh dikonfigurasi.
        # Kalau seluruh `COLUMNS_MAX` diberi `uniform` + `minsize`, frame jadi
        # lebih lebar daripada area tampilan, dan karena tidak ada scrollbar
        # horizontal, sel di kolom paling kanan terpotong tanpa jalan scrolling.
        for col in range(self.COLUMNS_MAX):
            self.grid_frame.columnconfigure(col, weight=0, minsize=0, uniform="")
        for col in range(columns):
            self.grid_frame.columnconfigure(col, weight=1, uniform="cols", minsize=cell_width)
        for row in range((len(self._cells) + columns - 1) // columns):
            self.grid_frame.rowconfigure(row, weight=0)

        self.scroller._sync_scrollregion()

    # -------------------------------------------------------------- content

    def set_cells(self, count: int) -> None:
        """Samakan jumlah sel thumbnail dengan jumlah halaman."""
        self._suppress = True
        while len(self._cells) > count:
            self._cells.pop().destroy()
        while len(self._cells) < count:
            index = len(self._cells)
            cell = self._make_cell(index)
            self._cells.append(cell)
        self._suppress = False
        self._reindex()
        self._relayout()

    def _make_cell(self, index: int) -> tk.Frame:
        outer = tk.Frame(
            self.grid_frame,
            bg="#2f3542",
            highlightthickness=2,
            highlightbackground="#2f3542",
        )

        # Label hanya memasang gambar; opsi width/height pada Label dinyatakan
        # dalam jumlah baris teks, bukan piksel, jadi harus dibiarkan otomatis.
        photo_slot = tk.Label(
            outer,
            bg="#ffffff",
            image=None,
            cursor="fleur",
        )
        photo_slot.pack(fill="both", expand=True, padx=4, pady=(4, 0))

        badge = tk.Label(
            outer,
            text="",
            bg="#2f3542",
            fg="#ffffff",
            font=("TkDefaultFont", 9),
            anchor="w",
        )
        badge.pack(fill="x", padx=6, pady=(2, 4))

        state = {"index": index, "photo": None}

        outer._page_state = state  # type: ignore[attr-defined]
        outer._photo_label = photo_slot  # type: ignore[attr-defined]
        outer._badge = badge  # type: ignore[attr-defined]

        outer.bind("<ButtonPress-1>", self._on_press)
        outer.bind("<B1-Motion>", self._on_motion)
        outer.bind("<ButtonRelease-1>", self._on_release)
        outer.bind("<Button-3>", self._on_right)
        outer.bind("<Double-Button-1>", self._on_double)
        photo_slot.bind("<ButtonPress-1>", self._on_press)
        photo_slot.bind("<B1-Motion>", self._on_motion)
        photo_slot.bind("<ButtonRelease-1>", self._on_release)
        photo_slot.bind("<Button-3>", self._on_right)
        # `photo_slot` dan `badge` menutupi seluruh isi sel, jadi event klik
        # tidak pernah sampai ke `outer`. Tanpa binding yang sama di sini,
        # klik ganda di area thumbnail tidak akan pernah memanggil
        # `on_activate`.
        photo_slot.bind("<Double-Button-1>", self._on_double)
        badge.bind("<ButtonPress-1>", self._on_press)
        badge.bind("<B1-Motion>", self._on_motion)
        badge.bind("<ButtonRelease-1>", self._on_release)
        badge.bind("<Button-3>", self._on_right)
        badge.bind("<Double-Button-1>", self._on_double)

        return outer

    def _reindex(self) -> None:
        for index, cell in enumerate(self._cells):
            cell._page_state["index"] = index  # type: ignore[attr-defined]

    def update_cell(
        self,
        index: int,
        image,
        title: str,
        ocr_done: bool,
        selected: bool,
    ) -> None:
        """Segarkan isi satu sel: gambar thumbnail, judul, badge status."""
        if not (0 <= index < len(self._cells)):
            return
        cell = self._cells[index]
        state = cell._page_state  # type: ignore[attr-defined]
        label = cell._photo_label  # type: ignore[attr-defined]
        badge = cell._badge  # type: ignore[attr-defined]

        if image is not None:
            label.configure(image=image)
            state["photo"] = image
        else:
            # Render gagal: gambar lama harus dibuang, kalau tidak sel ini
            # masih menampilkan isi halaman sebelumnya.
            label.configure(image=None)
            state["photo"] = None

        marks = []
        if selected:
            marks.append("•")
        if ocr_done:
            marks.append("OCR")
        badge.configure(text="   ".join([title, " ".join(marks)]).strip())

        if selected:
            bg, border = "#1f6feb", "#58a6ff"
        elif ocr_done:
            bg, border = "#24303f", "#3fb950"
        else:
            bg, border = "#2f3542", "#2f3542"
        cell.configure(bg=bg, highlightbackground=border)

    def resize_thumbs(self, height: int) -> None:
        """Minta thumbnail baru pada tinggi tertentu (dipanggil app)."""
        self._thumb_height = height
        self.scroller._sync_scrollregion()

    # ----------------------------------------------------------------- drag

    def _cell_at(self, x: int, y: int) -> tk.Frame | None:
        for cell in self._cells:
            if (
                cell.winfo_rootx() <= x <= cell.winfo_rootx() + cell.winfo_width()
                and cell.winfo_rooty() <= y <= cell.winfo_rooty() + cell.winfo_height()
            ):
                return cell
        return None

    def _target_index(self, x: int, y: int) -> int | None:
        """Index posisi sisip berdasarkan titik tengah sel terdekat."""
        best: int | None = None
        best_dist = float("inf")
        for index, cell in enumerate(self._cells):
            cx = cell.winfo_rootx() + cell.winfo_width() / 2
            cy = cell.winfo_rooty() + cell.winfo_height() / 2
            dist = (x - cx) ** 2 + (y - cy) ** 2
            if dist < best_dist:
                best_dist = dist
                best = index
        if best is None:
            return None
        if x > self.grid_frame.winfo_rootx() + self.grid_frame.winfo_width():
            return min(best + 1, len(self._cells) - 1)
        return best

    def _on_press(self, event: tk.Event) -> None:
        if not self._enabled:
            return
        cell = self._event_cell(event)
        if cell is None:
            return
        self._press_pos = (event.x_root, event.y_root)
        self._drag_moved = False
        self._drag_from = cell._page_state["index"]  # type: ignore[attr-defined]
        self._drag_to = self._drag_from

    def _event_cell(self, event: tk.Event) -> tk.Frame | None:
        widget = event.widget
        while widget is not None and not hasattr(widget, "_page_state"):
            try:
                widget = widget.master  # type: ignore[attr-defined]
            except AttributeError:
                return None
        if widget is None or not hasattr(widget, "_page_state"):
            return None
        return widget  # type: ignore[return-value]

    def _on_motion(self, event: tk.Event) -> None:
        if not self._enabled or self._drag_from is None:
            return
        dx = event.x_root - self._press_pos[0]
        dy = event.y_root - self._press_pos[1]
        if not self._drag_moved and (abs(dx) > 6 or abs(dy) > 6):
            self._drag_moved = True
        if not self._drag_moved:
            return

        target = self._target_index(event.x_root, event.y_root)
        if target is None or target == self._drag_from:
            return
        if self._drag_to == target:
            return

        self._drag_to = target
        self.on_reorder(self._drag_from, target)

    def _on_release(self, event: tk.Event) -> None:
        if self._drag_from is None:
            return
        was_drag = self._drag_moved
        source_index = self._drag_from
        self._drag_from = None
        self._drag_to = None
        self._drag_moved = False
        if not was_drag:
            cell = self._event_cell(event)
            if cell is not None:
                self.on_select(cell._page_state["index"], event)  # type: ignore[attr-defined]

    def _on_double(self, event: tk.Event) -> None:
        if not self._enabled:
            return
        cell = self._event_cell(event)
        if cell is not None:
            self.on_activate(cell._page_state["index"])  # type: ignore[attr-defined]

    def _on_right(self, event: tk.Event) -> None:
        if not self._enabled:
            return
        cell = self._event_cell(event)
        if cell is not None:
            self.on_context(cell._page_state["index"], event)  # type: ignore[attr-defined]

    # -------------------------------------------------------------- status

    def set_enabled(self, enabled: bool) -> None:
        """Aktif/nonaktifkan seluruh interaksi grid.

        Ini bukan sekadar retval visual: worker OCR dan simpan membaca
        `pymupdf.Document` milik proyek dari thread lain, sedangkan menghapus
        halaman bisa menutup dokumen itu lewat `Project._prune_sources()`.
        Menonaktifkan grid mencegah use-after-free di libmupdf selama proses
        background berjalan.
        """
        self._enabled = enabled
        self.configure(cursor="" if enabled else "watch")
        for cell in self._cells:
            try:
                cell.configure(cursor="fleur" if enabled else "watch")
                cell._photo_label.configure(  # type: ignore[attr-defined]
                    cursor="fleur" if enabled else "watch"
                )
            except tk.TclError:
                pass

    # ------------------------------------------------------------ selection

    def clear_selection(self) -> None:
        self._selection.clear()

    def select(self, index: int, extend: bool = False) -> int:
        """Pilih satu halaman, atau rentang dengan shift."""
        if extend and self._selection:
            anchor = min(self._selection)
            self._selection = set(range(min(anchor, index), max(anchor, index) + 1))
        else:
            self._selection = {index}
        return index

    def select_all(self) -> None:
        self._selection = set(range(len(self._cells)))

    @property
    def selection(self) -> list[int]:
        return sorted(self._selection)

    def scroll_to_index(self, index: int) -> None:
        """Gulir secukupnya agar sel `index` masuk area terlihat.

        Posisi dihitung dari layout grid (jumlah kolom & tinggi sel), bukan dari
        `winfo_rooty()`. Widget di dalam canvas yang sudah digulir melaporkan
        posisi layar basi sampai idle cycle berikutnya, sehingga pengukuran
        berbasis koordinat window tidak bisa diandalkan di sini.
        """
        if not (0 <= index < len(self._cells)):
            return

        self.update_idletasks()

        canvas = self.scroller.canvas
        canvas_height = canvas.winfo_height()
        cell_height = self._cells[0].winfo_height() or self.THUMB_HEIGHT + 40
        row_height = cell_height + 2 * self.PAD_Y

        bbox = canvas.bbox("all")
        total = bbox[3] if bbox else canvas_height

        top = row_height * (index // self._columns)

        # yview()[0] adalah fraksi dari seluruh dokumen, bukan dari rentang
        # scroll: offset = yview()[0] * total.
        offset = canvas.yview()[0] * total
        if offset - 1 <= top and top + cell_height <= offset + canvas_height + 1:
            return  # sudah terlihat

        # Baris target harus terlihat **utuh**. Kalau muat, sisakan ruang di
        # atas sebobot seperempat area tapi jangan sampai barisnya keluar di
        # bawah — itulah yang membuat halaman target tak pernah bisa dibaca
        # penuh di jendela pendek.
        if cell_height <= canvas_height:
            room = canvas_height - cell_height
            desired = top - min(room, max(room // 3, 0))
        else:
            # Area lebih pendek dari satu baris: tidak ada posisi yang
            # menampilkan seluruh baris, jadi cukupkan bagian atasnya.
            desired = top - canvas_height // 4
        canvas.yview_moveto(max(0.0, min(1.0, desired / max(1, total))))