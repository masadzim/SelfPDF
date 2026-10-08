"""Tes jalur pembaruan (tanpa jaringan). Jalankan: .venv/bin/python -m pytest tests/ -q"""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pdfocr import update  # noqa: E402


def release(tag: str, assets=None, body: str = "", html_url: str = "") -> dict:
    return {
        "tag_name": tag,
        "html_url": html_url or f"https://github.com/{update.GITHUB_REPO}/releases/tag/{tag}",
        "body": body,
        "assets": assets if assets is not None else [],
    }


def asset(name: str, url: str = "") -> dict:
    return {
        "name": name,
        "browser_download_url": url or f"https://example.invalid/{name}",
    }


# ------------------------------------------------------------- parse_version


def test_parse_version_kotor():
    assert update.parse_version("v1.2.3") == (1, 2, 3)
    assert update.parse_version("1.2") == (1, 2)
    assert update.parse_version("SelfPDF 1.10.0 rilis") == (1, 10, 0)


def test_parse_version_tanpa_angka():
    assert update.parse_version("") == ()
    assert update.parse_version("tanpa-versi") == ()


# ---------------------------------------------------------------- is_newer


def test_is_newer_numerik_bukan_leksikografis():
    # "1.10.0" < "1.9.0" secara string, tapi lebih baru secara numerik.
    assert update.is_newer("v1.10.0", "1.9.0") is True
    assert update.is_newer("1.9.0", "v1.10.0") is False


def test_is_newer_sama_dan_lebih_lama():
    assert update.is_newer("1.2.0", "1.2.0") is False
    assert update.is_newer("v1.0.9", "1.1.0") is False
    # Jumlah bagian beda disamakan dengan nol.
    assert update.is_newer("1.2", "1.2.0") is False
    assert update.is_newer("1.2.1", "1.2") is True


def test_is_newer_versi_rusak():
    assert update.is_newer("", "1.0.0") is False
    assert update.is_newer("1.0.0", "") is False


# --------------------------------------------------------- check_for_updates


def test_update_tersedia(monkeypatch):
    rel = release(
        "v9.9.9",
        assets=[asset("SelfPDF-Linux.deb"), asset("SelfPDF-Windows.exe")],
        body="Rilis uji",
    )
    monkeypatch.setattr(update, "_fetch_json", lambda url: rel)

    status, info = update.check_for_updates("1.2.0")

    assert status == update.STATUS_UPDATE
    assert info is not None
    assert info.version == "v9.9.9"
    assert info.notes == "Rilis uji"
    assert info.page_url.endswith("/tag/v9.9.9")
    # Unduhan yang dipilih harus cocok dengan platform yang menjalankan tes.
    expected = (
        "SelfPDF-Windows.exe" if os.name == "nt" else "SelfPDF-Linux.deb"
    )
    assert expected in info.download_url


def test_sudah_terbaru(monkeypatch):
    monkeypatch.setattr(update, "_fetch_json", lambda url: release("v1.0.0"))

    status, info = update.check_for_updates("1.2.0")

    assert status == update.STATUS_CURRENT
    assert info is None


def test_tanpa_tag(monkeypatch):
    monkeypatch.setattr(update, "_fetch_json", lambda url: {"tag_name": ""})

    status, info = update.check_for_updates("1.0.0")

    assert status == update.STATUS_CURRENT
    assert info is None


def test_jaringan_mati(monkeypatch):
    def boom(url):
        raise OSError("tidak ada jaringan")

    monkeypatch.setattr(update, "_fetch_json", boom)

    status, info = update.check_for_updates("1.0.0")

    assert status == update.STATUS_UNAVAILABLE
    assert info is None


def test_unduhan_jatuh_ke_halaman_rilis(monkeypatch):
    # Rilis tanpa berkas yang cocok: tombol Unduh membuka halaman rilis.
    monkeypatch.setattr(
        update,
        "_fetch_json",
        lambda url: release("v2.0.0", assets=[asset("sumber.zip")]),
    )

    status, info = update.check_for_updates("1.0.0")

    assert status == update.STATUS_UPDATE
    assert info is not None
    assert info.download_url == info.page_url


def test_assets_bukan_list_dict(monkeypatch):
    monkeypatch.setattr(
        update, "_fetch_json", lambda url: release("v2.0.0", assets=["aneh"])
    )

    status, info = update.check_for_updates("1.0.0")

    assert status == update.STATUS_UPDATE
    assert info is not None
    assert info.download_url == info.page_url
