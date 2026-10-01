"""Palet warna bersama untuk seluruh jendela GUI.

Dipisah dari `app.py` supaya modul lain (mis. `tool_panel`) bisa memakai
warna yang sama tanpa import melingkar.
"""

BG = "#20242c"
BG_PANEL = "#2b303b"
FG = "#e6edf3"
FG_DIM = "#9aa4b2"
ACCENT = "#1f6feb"
OK = "#3fb950"
WARN = "#d29922"

# Latar dialog mengikuti panel agar menapak dengan jendela utama.
DIALOG_BG = BG
