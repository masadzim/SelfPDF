#!/usr/bin/env bash
# Build binary mandiri SelfPDF dengan PyInstaller.
#
# PENTING: PyInstaller tidak bisa lintas-platform. `SelfPDF.exe` untuk Windows
# hanya bisa dihasilkan di Windows (atau lewat GitHub Actions di
# `.github/workflows/build.yml`). Script ini dipakai apa adanya di Linux/macOS
# untuk menghasilkan binary mandiri di Linux/macOS, dan .exe di Windows.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "${HERE}/.." && pwd)"
cd "${ROOT}"

PY="${PY:-}"
if [ -z "${PY}" ]; then
    if [ -x .venv/bin/python ]; then PY=".venv/bin/python"; else PY="python3"; fi
fi

"${PY}" -m pip install --quiet --upgrade pyinstaller

OUT="${ROOT}/dist"
"${PY}" -m PyInstaller \
    --noconfirm --clean \
    --distpath "${OUT}" \
    --workpath "${ROOT}/build/pyinstaller" \
    SelfPDF.spec

echo
echo "Selesai. Hasil:"
ls -lh "${OUT}"