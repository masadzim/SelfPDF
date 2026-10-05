"""Identitas aplikasi: nama, logo, wordmark, dan ikon jendela.

Semua gambar dibaca dari folder `assets/`. Kalau berkasnya tidak ada, aplikasi
tetap jalan dan hanya menampilkan teks nama — tidak ada yang wajib di folder
aset.

Dua jenis gambar yang dikenali:

* **logo** — lambang, biasanya bujur sangkar. Ditampilkan berdampingan dengan
  teks nama aplikasi.
* **wordmark** — lambang + nama yang sudah menyatu dalam satu gambar, mis.
  `LogoSelfPDFull.jpeg`. Kalau ini ada, teks nama tidak lagi digambar supaya
  nama tidak muncul dua kali.

Berkas asli boleh dipakai apa adanya. `prepare_image()` memangkas bingkai
putih/transparan yang sering ditinggalkan desainer, menyetel ukuran supaya pas
di kotak yang ditentukan, dan membungkus gambar yang tidak transparan dengan
latar membulat agar tidak terlihat seperti kotak putih yang menempel di
jendela gelap.
"""

from __future__ import annotations

import os
import sys
import tempfile
import tkinter as tk
from typing import Optional

APP_NAME = "SelfPDF"
APP_TAGLINE = "Make simple to use"
APP_VERSION = "1.1.0"

# Tautan donasi & dukungan. Satu sumber kebenaran untuk dialog Tentang.
# Nilai diambil dari SUPPORT.md proyek BisikChat (project selftdev/bisikchat).
DONATION_URL = "https://saweria.co/selftdev"
SUPPORT_EMAIL = "support@adzim.my.id"
SUPPORT_PAGE = "https://adzim.my.id/support"

_IMAGE_EXT = (".png", ".jpg", ".jpeg", ".webp", ".gif")

LOGO_NAMES = ("logo.png", "logo.jpg", "logo.jpeg", "logo.webp", "logo.gif")
WORDMARK_NAMES = (
    "LogoSelfPDFull.png",
    "LogoSelfPDFull.jpg",
    "LogoSelfPDFull.jpeg",
    "logo_full.png",
    "logo-full.png",
    "wordmark.png",
    "wordmark.jpg",
    "wordmark.jpeg",
)
ICON_NAMES = ("icon.png", "icon.jpg", "icon.jpeg", "icon.webp", "icon.ico", "icon.gif")

# Sisi kanvas ikon jendela. Ikon taskbar besar-besar perlu ukuran ini supaya
# tidak pecah saat diskalakan.
ICON_CANVAS = 256

# Batas ukuran gambar di header. Wordmark dibuat lebih rendah supaya tidak
# terlalu mendominasi baris judul.
LOGO_MAX_H = 30
WORDMARK_MAX_H = 32
WORDMARK_MAX_W = 260

# Kalau logo sudah membawa nama sendiri (wordmark), teks nama disembunyikan.
# Bisa dipaksa lewat variabel ini kalau logo ternyata tidak memuat nama.
SHOW_NAME_WITH_LOGO = True

ICON_SIZES = (16, 24, 32, 48, 64, 128, 256)

# Toleransi trimming bingkai: piksel yang bedanya <= nilai ini dianggap bingkai.
TRIM_TOLERANCE = 18
# Persentase sisi yang dibiarkan kosong di sekeliling gambar hasil potong.
TRIM_MARGIN_RATIO = 0.02
# Seberapa jauh sebuah piksel boleh beda dari warna latar sebelum ikut di-alpha-kan.
KEY_TOLERANCE = 34
# Porsi minimum piksel yang harus tersisa setelah latar dipisah; di bawah ini
# gambar dianggap bukan logo di atas latar polos, jadi tidak diubah.
KEY_MIN_KEEP = 0.01


def assets_dir() -> str:
    """Folder aset.

    Urutan: folder bundel PyInstaller (`sys._MEIPASS`), folder `assets/` di
    samping paket, lalu yang di dalam paket.

    `sys._MEIPASS` harus diperiksa lebih dulu: saat beku, `__file__` menunjuk
    ke direktori sementara PyInstaller, bukan ke folder proyek. Kandidat
    `sys.prefix` sengaja tidak dipakai — itu prefix interpreter/venv, bukan
    lokasi yang pernah diisi PyInstaller, sehingga bisa diam-diam menunjuk ke
    folder `assets` milik program lain.
    """
    here = os.path.dirname(os.path.abspath(__file__))          # pdfocr/gui
    pkg = os.path.dirname(os.path.dirname(here))                # pdfocr
    root = os.path.dirname(pkg)                                 # akar proyek

    candidates = []
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidates.append(os.path.join(meipass, "assets"))
    candidates += [
        os.path.join(root, "assets"),
        os.path.join(pkg, "assets"),
        os.path.join(os.path.dirname(sys.executable), "assets"),
    ]
    for candidate in candidates:
        if os.path.isdir(candidate):
            return candidate
    return candidates[0] if meipass else os.path.join(root, "assets")


def _asset_index() -> dict[str, str]:
    """`nama_kecil` -> path, untuk seluruh gambar di folder aset.

    Pencocokan dilakukan case-insensitive supaya `LogoSelfPDFull.jpeg` tetap
    ketemu meski huruf besarnya beda.
    """
    folder = assets_dir()
    index: dict[str, str] = {}
    try:
        entries = os.listdir(folder)
    except OSError:
        return index
    for entry in entries:
        if os.path.splitext(entry)[1].lower() not in _IMAGE_EXT:
            continue
        index.setdefault(entry.lower(), os.path.join(folder, entry))
    return index


def find_asset(names=LOGO_NAMES) -> Optional[str]:
    """Path berkas pertama yang ada, atau None.

    Dicoba persis seperti tertulis dulu, lalu diulang tanpa membedakan huruf
    besar-kecil supaya `LogoSelfPDFull.jpeg` tetap ditemukan.
    """
    folder = assets_dir()
    for name in names:
        path = os.path.join(folder, name)
        if os.path.isfile(path):
            return path
    index = _asset_index()
    for name in names:
        path = index.get(name.lower())
        if path:
            return path
    return None


def find_logo() -> Optional[str]:
    return find_asset(LOGO_NAMES)


def find_wordmark() -> Optional[str]:
    """Gambar yang sudah memuat lambang + nama, atau None."""
    found = find_asset(WORDMARK_NAMES)
    if found:
        return found
    # Fallback: berkas apa pun yang namanya menyiratkan "utuh"/"wordmark",
    # supaya aset buatan sendiri tetap kepakai.
    for lowered, path in _asset_index().items():
        stem = os.path.splitext(lowered)[0]
        if "wordmark" in stem or "full" in stem:
            return path
    return None


def find_icon() -> Optional[str]:
    return find_asset(ICON_NAMES)


# ------------------------------------------------------------------ gambar


def _has_transparency(image) -> bool:
    return image.mode in ("RGBA", "LA", "PA") and image.getchannel("A").getextrema()[0] < 250


def _corner_color(image) -> tuple[int, int, int]:
    """Warna yang dianggap latar: modus dari titik-titik tepi."""
    from collections import Counter

    width, height = image.size
    points = [
        (0, 0), (width - 1, 0), (0, height - 1), (width - 1, height - 1),
        (width // 2, 0), (width // 2, height - 1), (0, height // 2), (width - 1, height // 2),
    ]
    counter = Counter(image.convert("RGB").getpixel(p) for p in points)
    return counter.most_common(1)[0][0]


def _content_box(image):
    """Kotak berisi isi gambar, tanpa bingkai yang seragam."""
    if _has_transparency(image):
        alpha = image.getchannel("A")
        box = alpha.point(lambda v: 255 if v > 8 else 0).getbbox()
        return box

    from PIL import Image, ImageChops

    flat = image.convert("RGB")
    background = Image.new("RGB", flat.size, _corner_color(flat))
    diff = ImageChops.difference(flat, background).convert("L")
    return diff.point(lambda v: 255 if v > TRIM_TOLERANCE else 0).getbbox()


def _trim(image):
    """Pangkas bingkai polos di sekeliling gambar."""
    box = _content_box(image)
    if not box:
        return image
    left, top, right, bottom = box
    margin = max(1, int(min(image.size) * TRIM_MARGIN_RATIO))
    return image.crop((
        max(0, left - margin),
        max(0, top - margin),
        min(image.width, right + margin),
        min(image.height, bottom + margin),
    ))


def _fit(image, max_w: int, max_h: int):
    """Skala gambar supaya muat di (max_w x max_h) tanpa mengubah rasio."""
    from PIL import Image

    scale = min(max_w / image.width, max_h / image.height, 1.0)
    if scale >= 1.0:
        return image
    return image.resize(
        (max(1, round(image.width * scale)), max(1, round(image.height * scale))),
        Image.LANCZOS,
    )


def _key_background(image, tolerance: int = KEY_TOLERANCE):
    """Jadikan warna latar gambar menjadi transparan.

    Logo buatan sendiri sering berupa gambar mewarna di atas latar polos (putih).
    Kalau dibiarkan apa adanya, logonya tampil sebagai kotak putih di jendela
    gelap. Pisahkan warnanya: piksel yang mirip sudut gambar menjadi transparan
    dengan tepi yang melandai supaya tidak bergerigi.

    Dilewati bila gambar sudah punya alpha, atau bila setelah dipisah hampir
    tidak ada yang tersisa (artinya gambar memang bukan logo di atas latar).
    """
    if _has_transparency(image):
        return image

    from PIL import Image, ImageChops

    flat = image.convert("RGB")
    background = Image.new("RGB", flat.size, _corner_color(flat))
    diff = ImageChops.difference(flat, background).convert("L")

    edge = tolerance * 3

    def fade(value: int) -> int:
        if value <= tolerance:
            return 0
        if value >= edge:
            return 255
        return int((value - tolerance) * 255 / (edge - tolerance))

    alpha = diff.point(fade)
    box = alpha.getbbox()
    if not box:
        return image

    kept = sum(alpha.histogram()[1:])
    if kept < image.width * image.height * KEY_MIN_KEEP:
        return image

    result = flat.convert("RGBA")
    result.putalpha(alpha)
    return result


def _plate(image):
    """Bungkus gambar buram dalam kotak bersudut membulat.

    Logo JPEG/PNG tanpa alpha punya latar sendiri (biasanya putih). Di jendela
    gelap, kotak putih mentah terlihat seperti tambalan; memberinya tepian
    membulat dengan warna latar yang sama membuatnya terbaca sebagai plat logo.
    """
    from PIL import Image, ImageDraw

    width, height = image.size
    radius = max(2, int(min(width, height) * 0.16))
    mask = Image.new("L", (width, height), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, width - 1, height - 1), radius=radius, fill=255)

    base = Image.new("RGBA", (width, height), _corner_color(image) + (255,))
    base.paste(image.convert("RGBA"), (0, 0), mask)
    return base


def prepare_image(path: str, max_w: int, max_h: int, plate: bool = True,
                  key_background: bool = True):
    """Baca gambar, pangkas bingkai, pisahkan latar, skala ke kotak tujuan.

    Mengembalikan objek PIL RGBA atau None.
    """
    if not path or not os.path.isfile(path):
        return None
    try:
        from PIL import Image
    except ImportError:  # pragma: no cover
        return None

    try:
        with Image.open(path) as source:
            image = source.convert("RGBA")
    except Exception:
        return None

    try:
        image = _trim(image)
        if key_background:
            image = _key_background(image)
        image = _fit(image, max_w, max_h)
        if plate and not _has_transparency(image):
            image = _plate(image)
    except Exception:
        pass
    return image


def load_photo(master: tk.Misc, path: str, max_h: int = LOGO_MAX_H,
               max_w: int | None = None, plate: bool = True) -> Optional[tk.PhotoImage]:
    """Muat gambar dari `path` jadi PhotoImage yang sudah dipangkas & diskalakan."""
    width = max_w if max_w is not None else max_h * 6
    image = prepare_image(path, width, max_h, plate=plate)
    if image is None:
        return None
    try:
        from PIL import ImageTk

        photo = ImageTk.PhotoImage(image, master=master)
        # Jaga referensi agar tidak di-GC oleh Tk.
        photo._selfref = image  # type: ignore[attr-defined]
        return photo
    except Exception:
        return None


def load_wordmark(master: tk.Misc, path: str) -> Optional[tk.PhotoImage]:
    """Wordmark = lambang + nama; teks nama tidak perlu digambar lagi."""
    return load_photo(master, path, max_h=WORDMARK_MAX_H, max_w=WORDMARK_MAX_W, plate=False)


def load_logo(master: tk.Misc, path: str) -> Optional[tk.PhotoImage]:
    """Lambang bujur sangkar untuk diletakkan berdampingan teks nama."""
    return load_photo(master, path, max_h=LOGO_MAX_H, max_w=LOGO_MAX_H * 2, plate=True)


# -------------------------------------------------------------------- ikon


def _icon_image(path: str):
    """Siapkan gambar aset jadi ikon bujur sangkar dengan latar transparan.

    Berkas di `assets/` sering berupa gambar mewarn di atas latar putih. Kalau
    dipakai apa adanya, ikon taskbar tampil sebagai kotak putih di panel gelap.
    Karena itu bingkai dipangkas dan warnanya dijadikan transparan lebih dulu,
    lalu dipusatkan di kanvas persegi agar tidak gepeng.
    """
    from PIL import Image

    try:
        with Image.open(path) as source:
            image = source.convert("RGBA")
    except Exception:
        return None

    try:
        image = _trim(image)
        image = _key_background(image)
    except Exception:
        return image

    side = max(image.size)
    square = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    square.paste(image, ((side - image.width) // 2, (side - image.height) // 2), image)
    if side > ICON_CANVAS:
        square = square.resize((ICON_CANVAS, ICON_CANVAS), Image.LANCZOS)
    return square


def apply_window_icon(root: tk.Misc) -> bool:
    """Pasang ikon jendela + taskbar dari berkas di `assets/`.

    Prioritas: `iconphoto` (X11/Wayland) dengan gambar yang sudah disiapkan
    `_icon_image`. `iconbitmap` dicoba sebagai tambahan untuk Windows,
    diabaikan diam-diam bila format tidak cocok.
    """
    path = find_icon()
    if not path:
        return False
    try:
        from PIL import ImageTk
    except ImportError:  # pragma: no cover
        return False

    image = _icon_image(path)
    if image is None:
        return False

    try:
        photo = ImageTk.PhotoImage(image, master=root)
        # Jaga referensi agar tidak di-GC oleh Tk.
        photo._selfref = image  # type: ignore[attr-defined]
        root.iconphoto(True, photo)
        root._icon_photo = photo  # type: ignore[attr-defined]

        # `iconbitmap` hanya berguna di Windows, dan file .ico harus tetap ada
        # selama jendela hidup. Folder sementara karena itu tidak boleh dihapus
        # di akhir blok `with`.
        if os.name == "nt":
            try:
                tmp = tempfile.mkdtemp(prefix="selfpdf_icon_")
                ico = os.path.join(tmp, "icon.ico")
                keep = sorted({s for s in ICON_SIZES if s <= max(image.size)} | {max(image.size)})
                image.save(ico, format="ICO", sizes=[(s, s) for s in keep])
                root.iconbitmap(ico)
                root._icon_ico_dir = tmp  # type: ignore[attr-defined]
            except Exception:
                pass
        return True
    except Exception:
        return False
