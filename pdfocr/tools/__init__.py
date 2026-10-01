"""Registry seluruh tool PDF.

Import modul tool di sini agar dependensi opsional (LibreOffice, pdf2docx,
dst.) hanya complained saat tool benar-benar dipakai, bukan saat aplikasi start.
"""

from __future__ import annotations

from .base import Param, ToolError, ToolOutcome, ToolSpec, parse_page_range, run_spec
from . import edit, from_pdf, intel, organize, optimize, security, to_pdf

MENU_ORDER = [
    "Organize PDF",
    "Optimize PDF",
    "Convert To PDF",
    "Convert From PDF",
    "Edit PDF",
    "PDF Security",
    "PDF Intelligence",
]

ALL_SPECS: list[ToolSpec] = [
    *organize.SPECS,
    *optimize.SPECS,
    *to_pdf.SPECS,
    *from_pdf.SPECS,
    *edit.SPECS,
    *security.SPECS,
    *intel.SPECS,
]

BY_ID: dict[str, ToolSpec] = {spec.id: spec for spec in ALL_SPECS}


def grouped() -> dict[str, list[ToolSpec]]:
    """Kembalikan tool dikelompokkan menurut urutan menubar."""
    buckets: dict[str, list[ToolSpec]] = {name: [] for name in MENU_ORDER}
    for spec in ALL_SPECS:
        buckets.setdefault(spec.group, []).append(spec)
    return buckets


def get(tool_id: str) -> ToolSpec:
    spec = BY_ID.get(tool_id)
    if spec is None:
        raise ToolError(f"Tool '{tool_id}' tidak dikenal.")
    return spec


__all__ = [
    "ALL_SPECS",
    "BY_ID",
    "MENU_ORDER",
    "Param",
    "ToolError",
    "ToolOutcome",
    "ToolSpec",
    "edit",
    "from_pdf",
    "get",
    "grouped",
    "intel",
    "optimize",
    "organize",
    "parse_page_range",
    "run_spec",
    "security",
    "to_pdf",
]
