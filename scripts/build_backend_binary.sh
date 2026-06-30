#!/bin/bash
# Build a standalone netfix backend binary for the macOS app bundle.
# Requires: python3 -m pip install pyinstaller
# Optional: PYINSTALLER_PYTHON=/path/to/python ./scripts/build_backend_binary.sh
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DIST_DIR="${REPO_ROOT}/dist"
NAME="netfix-backend"
PYI_PYTHON="${PYINSTALLER_PYTHON:-python3}"

if ! "${PYI_PYTHON}" -m PyInstaller --version >/dev/null 2>&1; then
    echo "PyInstaller is required to build ${NAME}." >&2
    echo "Install it in a build environment, then rerun:" >&2
    echo "  python3 -m pip install pyinstaller" >&2
    echo "or pass PYINSTALLER_PYTHON=/path/to/build-venv/bin/python" >&2
    exit 2
fi

rm -rf "${REPO_ROOT}/build/${NAME}" "${DIST_DIR}/${NAME}"
mkdir -p "${DIST_DIR}"

cd "${REPO_ROOT}"
"${PYI_PYTHON}" -m PyInstaller \
    --clean \
    --onefile \
    --name "${NAME}" \
    --add-data "rules:rules" \
    --add-data "bin:bin" \
    --add-data "gui/web:gui/web" \
    --hidden-import "encodings.idna" \
    --collect-submodules netfix \
    netfix.py

"${DIST_DIR}/${NAME}" --version >/dev/null
rm -f "${REPO_ROOT}/${NAME}.spec"
echo "Built ${DIST_DIR}/${NAME}"
echo "Use with: NETFIX_BACKEND_BIN='${DIST_DIR}/${NAME}' gui/macos/build_app.sh --release-candidate"
