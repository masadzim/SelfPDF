#!/usr/bin/env python3
"""Entry point SelfPDF."""

from __future__ import annotations

import sys


def main() -> int:
    try:
        import tkinter  # noqa: F401
    except ImportError:
        sys.stderr.write(
            "Tkinter tidak tersedia.\n"
            "Install dengan:\n"
            "    sudo apt install python3-tk\n"
        )
        return 1

    try:
        from pdfocr.gui.app import main as run
    except ImportError as exc:
        # `ImportError` (bukan hanya `ModuleNotFoundError`) juga menutup
        # kegagalan yang paling sering terjadi pada build beku Windows:
        # "DLL load failed while importing _pymupdf".
        name = getattr(exc, "name", None) or type(exc).__name__
        sys.stderr.write(
            f"Dependency Python belum lengkap: {name}\n"
            f"({exc})\n"
            "Install dengan:\n"
            "    pip install -r requirements.txt\n"
        )
        return 1

    try:
        run()
    except Exception as exc:  # noqa: BLE001
        # Tanpa ini, jendela beku yang gagal start hanya menampilkan traceback
        # di console yang tidak pernah terlihat pengguna.
        if "display" in str(exc).lower():
            sys.stderr.write(
                "Tidak ada display yang tersedia.\n"
                "SelfPDF adalah aplikasi GUI dan butuh lingkungan desktop.\n"
            )
            return 1
        raise
    return 0


if __name__ == "__main__":
    raise SystemExit(main())