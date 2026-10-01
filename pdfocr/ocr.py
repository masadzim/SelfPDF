"""Pembungkus mesin OCR Tesseract."""

from __future__ import annotations

import shutil
from typing import NamedTuple

import pytesseract
from PIL import Image

DEFAULT_LANG = "eng"
PREVIEW_MAX_SIDE = 1400


class OcrUnavailable(RuntimeError):
    """Tesseract atau bahasa yang diminta tidak tersedia."""


class OcrWord(NamedTuple):
    """Satu kata hasil OCR dalam koordinat piksel gambar."""

    text: str
    x0: float
    y0: float
    x1: float
    y1: float


def tesseract_path() -> str | None:
    return shutil.which("tesseract")


def check_available(lang: str = DEFAULT_LANG) -> str:
    """Pastikan Tesseract + paket bahasa siap, kembalikan nama executable."""
    exe = tesseract_path()
    if exe is None:
        raise OcrUnavailable(
            "Executable 'tesseract' tidak ditemukan.\n"
            "Install dengan:\n    sudo apt install tesseract-ocr tesseract-ocr-eng"
        )
    try:
        pytesseract.get_tesseract_version()
    except pytesseract.TesseractError as exc:  # pragma: no cover - sulit dipicu
        raise OcrUnavailable(f"Tesseract tidak bisa dijalankan: {exc}") from exc

    if lang not in available_languages():
        raise OcrUnavailable(
            f"Bahasa OCR '{lang}' belum terinstall.\n"
            f"Install dengan:\n    sudo apt install tesseract-ocr-{lang}"
        )
    return exe


def available_languages() -> list[str]:
    try:
        return sorted(pytesseract.get_languages(config=""))
    except pytesseract.TesseractError:  # pragma: no cover
        return []


def run_ocr(
    source: object,
    lang: str = DEFAULT_LANG,
    dpi: int = 300,
    psm: int = 3,
) -> list[OcrWord]:
    """Jalankan OCR pada satu halaman dan kembalikan posisi tiap kata.

    ``source`` boleh berupa ``PIL.Image`` atau ``pymupdf.Page``.
    """
    image = source if isinstance(source, Image.Image) else _render_page(source, dpi)

    data = pytesseract.image_to_data(
        image,
        lang=lang,
        config=f"--oem 1 --psm {psm}",
        output_type=pytesseract.Output.DICT,
    )

    words: list[OcrWord] = []
    texts = data["text"]
    for i, raw in enumerate(texts):
        text = raw.strip()
        if not text:
            continue
        try:
            conf = float(data["conf"][i])
        except (TypeError, ValueError):
            conf = -1.0
        if conf < 0:
            continue
        left = float(data["left"][i])
        top = float(data["top"][i])
        width = float(data["width"][i])
        height = float(data["height"][i])
        if width <= 0 or height <= 0:
            continue
        words.append(OcrWord(text, left, top, left + width, top + height))

    return words


def _render_page(page: object, dpi: int) -> Image.Image:
    pixmap = page.get_pixmap(dpi=dpi, alpha=False)
    return Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples)


def render_for_preview(source: object, dpi: int = 300) -> Image.Image:
    """Render halaman pada resolusi OCR, dibatasi agar tidak meledak di memori."""
    image = source if isinstance(source, Image.Image) else _render_page(source, dpi)
    longest = max(image.size)
    if longest <= PREVIEW_MAX_SIDE:
        return image
    ratio = PREVIEW_MAX_SIDE / longest
    return image.resize(
        (max(1, int(image.width * ratio)), max(1, int(image.height * ratio))),
        Image.LANCZOS,
    )


def group_lines(words: list[OcrWord], tolerance: float = 0.5) -> list[list[OcrWord]]:
    """Kelompokkan kata menjadi baris berdasarkan titik tengah vertikal.

    `y0` tidak bisa dipakai langsung: kata ber-descender ("you") punya y0 lebih
    rendah daripada kata sebaris ("Thank") meski sebenarnya satu baris. Yang
    stabil adalah titik tengah kotak kata.
    """
    if not words:
        return []

    heights = sorted(w.y1 - w.y0 for w in words)
    typical = heights[len(heights) // 2] or 1.0
    limit = typical * tolerance

    groups: list[list[OcrWord]] = []
    current: list[OcrWord] = []
    center = 0.0

    for word in sorted(words, key=lambda w: (w.y0 + w.y1) / 2):
        word_center = (word.y0 + word.y1) / 2
        if current and abs(word_center - center) <= limit:
            current.append(word)
            center = sum((w.y0 + w.y1) / 2 for w in current) / len(current)
        else:
            if current:
                groups.append(current)
            current = [word]
            center = word_center

    if current:
        groups.append(current)

    for group in groups:
        group.sort(key=lambda w: w.x0)
    groups.sort(key=lambda group: min(w.y0 for w in group))
    return groups


def words_to_text(words: list[OcrWord]) -> str:
    """Susun ulang kata menjadi teks yang terbaca, dikelompokkan per baris."""
    if not words:
        return ""
    heights = sorted(w.y1 - w.y0 for w in words)
    typical = heights[len(heights) // 2] or 1.0

    lines: list[str] = []
    for group in group_lines(words):
        pieces: list[str] = []
        for index, word in enumerate(group):
            # Celah antar kata pada teks normal ≈ 0.2–0.4 tinggi huruf,
            # sedangkan karakter dalam satu kata nyaris bersentuhan.
            if index and word.x0 - group[index - 1].x1 > typical * 0.2:
                pieces.append(" ")
            pieces.append(word.text)
        lines.append("".join(pieces))

    return "\n".join(lines)