#!/usr/bin/env python3
"""Entry point SelfPDF."""

from __future__ import annotations

import sys


def main() -> int:
    try:
        import tkinter  # noqa: F401
    except ModuleNotFoundError:
        sys.stderr.write(
            "Tkinter tidak tersedia.\n"
            "Install dengan:\n"
            "    sudo apt install python3-tk\n"
        )
        return 1

    try:
        from pdfocr.gui.app import main as run
    except ModuleNotFoundError as exc:
        sys.stderr.write(
            f"Dependency Python belum lengkap: {exc.name}\n"
            "Install dengan:\n"
            "    pip install -r requirements.txt\n"
        )
        return 1

    run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())