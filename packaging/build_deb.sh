#!/usr/bin/env bash
# Bangun paket .deb SelfPDF untuk Debian/Ubuntu.
#
# Paket berisi aplikasi yang di-build dengan PyInstaller menjadi satu binary,
# lalu dipasang ke /opt/selfpdf dengan launcher di /usr/bin/selfpdf.
# Pendekatan ini dipakai supaya .deb tidak perlu meng drags-compile dependensi
# Python saat instalasi, dan versi yang terpasang persis sama dengan yang
# sudah dites.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "${HERE}/.." && pwd)"
cd "${ROOT}"

VERSION="$(.venv/bin/python -c 'import re,pathlib;print(re.search(r"__version__\s*=\s*\"([^\"]+)\"", pathlib.Path("pdfocr/__init__.py").read_text()).group(1))' 2>/dev/null || echo "1.1.0")"
ARCH="$(dpkg --print-architecture)"
BUILD_DIR="${ROOT}/build/deb"
STAGE="${BUILD_DIR}/stage"
PKG_ROOT="${STAGE}/opt/selfpdf"
VERSION="${1:-${VERSION}}"

echo "==> SelfPDF ${VERSION} (${ARCH})"

if [ ! -d .venv ]; then
    echo "!! .venv belum ada. Jalankan: python3 -m venv .venv && .venv/bin/pip install -r requirements.txt" >&2
    exit 1
fi

# ---------------------------------------------------------------- build binary
.venv/bin/pip install --quiet --upgrade pyinstaller
echo "==> PyInstaller (one-file)"
rm -rf "${BUILD_DIR}/pyinstaller" "${STAGE}"
.venv/bin/pyinstaller \
    --noconfirm --clean \
    --distpath "${BUILD_DIR}/pyinstaller" \
    --workpath "${BUILD_DIR}/pyinstaller-work" \
    SelfPDF.spec

BIN="${BUILD_DIR}/pyinstaller/SelfPDF"
[ -f "${BIN}" ] || { echo "!! binary tidak ditemukan: ${BIN}" >&2; exit 1; }

# ------------------------------------------------------------------ susun paket
echo "==> Menyusun paket"
install -d "${PKG_ROOT}"
install -d "${STAGE}/DEBIAN"
install -d "${STAGE}/usr/bin"
install -d "${STAGE}/usr/share/applications"
install -d "${STAGE}/usr/share/icons/hicolor/256x256/apps"
install -d "${STAGE}/usr/share/doc/selfpdf"

install -m 0755 "${BIN}" "${PKG_ROOT}/SelfPDF"
install -m 0644 assets/icon.png "${STAGE}/usr/share/icons/hicolor/256x256/apps/selfpdf.png"
install -m 0644 assets/logo.png "${STAGE}/usr/share/icons/hicolor/256x256/apps/selfpdf-logo.png"
install -m 0644 packaging/debian/selfpdf.desktop "${STAGE}/usr/share/applications/selfpdf.desktop"
install -m 0644 LICENSE "${STAGE}/usr/share/doc/selfpdf/copyright"
install -m 0644 README.md "${STAGE}/usr/share/doc/selfpdf/README.md"

cat > "${STAGE}/usr/bin/selfpdf" <<'LAUNCHER'
#!/bin/sh
# Launcher SelfPDF. HOME dipakai eksplisit supaya PyInstaller tidak salah
# menebak folder cache ketika aplikasi dijalankan dari menu.
export HOME="${HOME:-/tmp}"
exec /opt/selfpdf/SelfPDF "$@"
LAUNCHER
chmod 0755 "${STAGE}/usr/bin/selfpdf"

INSTALLED_SIZE="$(du -ks "${PKG_ROOT}" | cut -f1)"
cat > "${STAGE}/DEBIAN/control" <<CONTROL
Package: selfpdf
Version: ${VERSION}
Section: utils
Priority: optional
Architecture: ${ARCH}
Depends: libc6, libglib2.0-0, libx11-6, libtk8.6
Recommends: tesseract-ocr, tesseract-ocr-eng, ghostscript, libreoffice
Installed-Size: ${INSTALLED_SIZE}
Maintainer: SelfPDF Contributors <support@adzim.my.id>
Homepage: https://github.com/masadzim/SelfPDF-Desktop
Description: OCR, reorder visual, dan 30 perkakas PDF
 SelfPDF menggabungkan beberapa PDF secara visual (seret thumbnail untuk
 mengurutkan ulang), menjalankan OCR English, dan menyimpan hasilnya sebagai
 PDF yang bisa dicari. Bulat 30 perkakas PDF dalam satu panel in-window.
 .
 Semua proses berjalan lokal. Tanpa telemetri, iklan, atau pelacak.
CONTROL

# ------------------------------------------------------------ postinst & prerm
cat > "${STAGE}/DEBIAN/postinst" <<'POSTINST'
#!/bin/sh
set -e
if [ "$1" = "configure" ]; then
    if command -v update-desktop-database >/dev/null 2>&1; then
        update-desktop-database -q /usr/share/applications || true
    fi
    if command -v gtk-update-icon-cache >/dev/null 2>&1; then
        gtk-update-icon-cache -q -t -f /usr/share/icons/hicolor || true
    fi
fi
exit 0
POSTINST

cat > "${STAGE}/DEBIAN/prerm" <<'PRERM'
#!/bin/sh
set -e
if [ "$1" = "remove" ] || [ "$1" = "upgrade" ]; then
    if command -v update-desktop-database >/dev/null 2>&1; then
        update-desktop-database -q /usr/share/applications || true
    fi
    if command -v gtk-update-icon-cache >/dev/null 2>&1; then
        gtk-update-icon-cache -q -t -f /usr/share/icons/hicolor || true
    fi
fi
exit 0
PRERM
chmod 0755 "${STAGE}/DEBIAN/postinst" "${STAGE}/DEBIAN/prerm"

# ------------------------------------------------------------------ build .deb
DEB="${BUILD_DIR}/selfpdf_${VERSION}_${ARCH}.deb"
echo "==> dpkg-deb --build"
rm -f "${DEB}"
dpkg-deb --root-owner-group --build "${STAGE}" "${DEB}"

echo
echo "Selesai: ${DEB}"
ls -lh "${DEB}"
echo
echo "Pasang dengan:"
echo "    sudo apt install ./${DEB#"${ROOT}"/}"