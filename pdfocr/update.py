"""Jalur pembaruan SelfPDF.

Aplikasi memeriksa rilis terbaru di GitHub (`masadzim/SelfPDF`), lalu
membandingkan tag rilisnya dengan versi yang sedang berjalan. Pemeriksaan
memakai modul bawaan Python (`urllib`, `json`) sehingga tidak menambah
dependensi apa pun ke `requirements.txt` maupun bundel PyInstaller.

Prinsip: **gagal ke "tanpa kabar"**. Tanpa jaringan, kena rate-limit, atau
respons bukan JSON — semua dianggap `STATUS_UNAVAILABLE` dan aplikasi tetap
berjalan normal. Tidak ada pengecualian yang merambat ke GUI.

Pemakaian: jalankan `check_for_updates()` dari thread non-GUI, lalu teruskan
hasilnya ke GUI lewat queue (lihat `MainWindow._update_worker` di
`pdfocr/gui/app.py`).
"""

from __future__ import annotations

import fnmatch
import json
import os
import re
import urllib.request
from typing import NamedTuple, Optional

# Repositori tempat rilis dipublikasikan. Workflow
# `.github/workflows/build.yml` membuat GitHub Release (beserta
# SelfPDF-Windows.exe dan SelfPDF-Linux.deb) untuk tiap tag `v*`.
GITHUB_REPO = "masadzim/SelfPDF"
RELEASES_API = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
RELEASES_PAGE = f"https://github.com/{GITHUB_REPO}/releases"

# GitHub menolak permintaan tanpa User-Agent.
USER_AGENT = "SelfPDF-Updater"
TIMEOUT = 8.0

# Hasil pemeriksaan.
STATUS_UPDATE = "update"            # ada rilis lebih baru
STATUS_CURRENT = "current"          # sudah versi terbaru
STATUS_UNAVAILABLE = "unavailable"  # tidak bisa memeriksa (offline, dll)

# Nama berkas yang diunggah job `release` di workflow rilis. Pola diformat
# `fnmatch` supaya nama paket .deb hasil `build_deb.sh` (selfpdf_<ver>_<arch>)
# tetap cocok walau penamaannya berubah sedikit.
if os.name == "nt":
    _ASSET_PATTERNS = ("SelfPDF-Windows.exe", "*.exe")
else:
    _ASSET_PATTERNS = ("SelfPDF-Linux.deb", "selfpdf_*.deb", "*.deb")


class UpdateInfo(NamedTuple):
    """Detail satu rilis yang lebih baru dari versi berjalan."""

    version: str       # tag rilis, mis. "v1.2.0"
    page_url: str      # halaman rilis di GitHub
    download_url: str  # unduhan untuk platform ini, atau halaman rilis bila tidak ada
    notes: str         # ringkasan perubahan (badan catatan rilis)


_VERSION_RE = re.compile(r"(\d+(?:\.\d+)*)")


def parse_version(text: str) -> tuple[int, ...]:
    """Tuple angka dari string versi: `"v1.2.0"` -> `(1, 2, 0)`.

    Teks bebas diperbolehkan (`"SelfPDF 1.2"` -> `(1, 2)`); bagian yang bukan
    angka dibuang. Versi yang tidak punya angka sama sekali menghasilkan `()`.
    """
    match = _VERSION_RE.search(text or "")
    if not match:
        return ()
    return tuple(int(part) for part in match.group(1).split("."))


def is_newer(latest: str, current: str) -> bool:
    """True bila `latest` lebih baru dari `current`.

    Dibandingkan per bagian numerik, bukan string — `1.10.0` lebih baru dari
    `1.9.0` meski secara leksikografis `"1.10.0" < "1.9.0"`. Versi dengan
    jumlah bagian berbeda disamakan panjangnya dengan nol (`1.2 == 1.2.0`).
    """
    new, old = parse_version(latest), parse_version(current)
    if not new or not old:
        return False
    width = max(len(new), len(old))
    new += (0,) * (width - len(new))
    old += (0,) * (width - len(old))
    return new > old


def _pick_asset(assets: list) -> Optional[str]:
    """URL unduhan berkas yang paling pas untuk platform berjalan."""
    for pattern in _ASSET_PATTERNS:
        for asset in assets:
            if not isinstance(asset, dict):
                continue
            name = str(asset.get("name") or "")
            url = str(asset.get("browser_download_url") or "")
            if url and fnmatch.fnmatch(name, pattern):
                return url
    return None


def _fetch_json(url: str) -> dict:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/vnd.github+json",
        },
    )
    with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
        data = json.loads(response.read().decode("utf-8"))
    if not isinstance(data, dict):
        raise ValueError("respons bukan objek JSON")
    return data


def check_for_updates(current_version: str) -> tuple[str, Optional[UpdateInfo]]:
    """Cek rilis terbaru terhadap `current_version`.

    Mengembalikan `(status, info)`:

    * `STATUS_UPDATE`  — ada rilis lebih baru; `info` berisi detailnya.
    * `STATUS_CURRENT` — sudah yang terbaru; `info` selalu `None`.
    * `STATUS_UNAVAILABLE` — tidak bisa dipastikan (offline, rate-limit,
      respons rusak); `info` selalu `None`. Bukan kesalahan pemanggil.
    """
    try:
        release = _fetch_json(RELEASES_API)
    except Exception:  # noqa: BLE001 - semua kegagalan jaringan/parse = "tidak pasti"
        return STATUS_UNAVAILABLE, None

    tag = str(release.get("tag_name") or "")
    if not tag or not is_newer(tag, current_version):
        return STATUS_CURRENT, None

    page = str(release.get("html_url") or "") or RELEASES_PAGE
    download = _pick_asset(release.get("assets") or []) or page
    notes = str(release.get("body") or "").strip()
    return STATUS_UPDATE, UpdateInfo(
        version=tag, page_url=page, download_url=download, notes=notes
    )
