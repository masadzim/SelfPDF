# -*- mode: python ; coding: utf-8 -*-
"""Spec PyInstaller untuk SelfPDF.

Dipakai oleh `packaging/build_exe.sh` dan workflow GitHub Actions untuk
menghasilkan `SelfPDF.exe` (Windows) serta binary mandiri di Linux/macOS.

Catatan penting:
  * `assets/` dibundel sebagai data. `pdfocr.gui.branding.assets_dir()` mencari
    `sys._MEIPASS` lebih dulu, jadi logo & ikon tetap ditemukan saat beku.
  * `console=False` supaya tidak ada jendela hitam di belakang GUI.
  * Modul di bawah `collect_all` adalah yang dibaca lewat import dinamis
    (LibreOffice/uno, certifikat, font internal PyMuPDF) sehingga tidak
    terdeteksi analisis statis PyInstaller.
"""

import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_submodules

block_cipher = None

PROJECT_ROOT = Path(SPECPATH).resolve()
ASSETS = PROJECT_ROOT / "assets"


def _app_icon():
    """Ikon untuk bootloader.

    Windows hanya menerima `.ico`. Workflow build membuat `assets/icon.ico`
    dari `assets/icon.png` lebih dulu; kalau tidak ada, pakai PNG apa adanya
    (PyInstaller mengabaikannya di Linux/macOS, bukan error).
    """
    for name in ("icon.ico", "icon.png"):
        candidate = ASSETS / name
        if candidate.is_file():
            return str(candidate)
    return None


APP_ICON = _app_icon()

# Modul yang di-import lewat `import` di dalam fungsi, jadi tidak terlihat
# oleh analisis dependensi PyInstaller.
HIDDEN_MODULES = [
    "pdfocr",
    "pdfocr.core",
    "pdfocr.ocr",
    "pdfocr.tools",
    "pdfocr.gui",
    "pdfocr.gui.app",
    "PIL.ImageTk",
    "pytesseract",
]

# Paket yang benar-benar dipakai tapi sering terlewat.
DATABASES = []
for _pkg in ("pdfplumber", "pdf2docx", "openpyxl", "docx", "pptx", "markdown"):
    try:
        _datas, _binaries, _hidden = collect_all(_pkg)
    except Exception:
        continue
    DATABASES += _datas
    HIDDEN_MODULES += _hidden

a = Analysis(
    ["main.py"],
    pathex=[str(PROJECT_ROOT)],
    binaries=[],
    datas=[("assets", "assets")] if ASSETS.is_dir() else [],
    hiddenimports=HIDDEN_MODULES,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # Modul bawaan interpreter tidak ikut dibundel.
    excludes=[
        "tkinter.test", "test", "unittest", "pydoc_data",
        "matplotlib", "numpy", "pandas", "IPython", "notebook",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="SelfPDF",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    # One-file: satu berkas .exe yang bisa langsung dijalankan/didistribusikan.
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=APP_ICON,
)