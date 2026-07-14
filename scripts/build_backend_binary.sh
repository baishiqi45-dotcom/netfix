#!/bin/bash
# Build the standalone backend with an already-available local PyInstaller.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
NAME="netfix-backend"
OUTPUT="${REPO_ROOT}/gui/macos/.build/backend/${NAME}"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --output)
            [[ $# -ge 2 ]] || { echo "--output requires a path" >&2; exit 2; }
            OUTPUT="$2"
            shift 2
            ;;
        *)
            echo "Unknown argument: $1" >&2
            exit 2
            ;;
    esac
done

case "${OUTPUT}" in
    /*) ;;
    *) OUTPUT="${PWD}/${OUTPUT}" ;;
esac

PYI_PYTHON=""
CANDIDATES=()
if [[ -n "${PYINSTALLER_PYTHON:-}" ]]; then
    CANDIDATES+=("${PYINSTALLER_PYTHON}")
fi
CANDIDATES+=(
    "${REPO_ROOT}/.venv/bin/python"
    "${REPO_ROOT}/gui/macos/.build/pyinstaller-venv/bin/python"
    "python3"
)

for candidate in "${CANDIDATES[@]}"; do
    resolved="${candidate}"
    if [[ "${resolved}" != */* ]]; then
        resolved="$(command -v "${resolved}" 2>/dev/null || true)"
    fi
    if [[ -n "${resolved}" && -x "${resolved}" ]] && "${resolved}" -m PyInstaller --version >/dev/null 2>&1; then
        PYI_PYTHON="${resolved}"
        break
    fi
done

if [[ -z "${PYI_PYTHON}" ]]; then
    echo "No existing PyInstaller environment can build ${NAME}." >&2
    echo "Checked PYINSTALLER_PYTHON, .venv, gui/macos/.build/pyinstaller-venv, and python3." >&2
    echo "This release script never installs build dependencies." >&2
    exit 2
fi

OUTPUT_DIR="$(dirname "${OUTPUT}")"
WORK_ROOT="${OUTPUT_DIR}/pyinstaller"
DIST_DIR="${WORK_ROOT}/dist"
WORK_DIR="${WORK_ROOT}/work"
SPEC_DIR="${WORK_ROOT}/spec"
rm -rf "${WORK_ROOT}" "${OUTPUT}"
mkdir -p "${DIST_DIR}" "${WORK_DIR}" "${SPEC_DIR}" "${OUTPUT_DIR}"

cd "${REPO_ROOT}"
"${PYI_PYTHON}" -m PyInstaller \
    --noconfirm \
    --clean \
    --onefile \
    --name "${NAME}" \
    --distpath "${DIST_DIR}" \
    --workpath "${WORK_DIR}" \
    --specpath "${SPEC_DIR}" \
    --add-data "${REPO_ROOT}/rules:rules" \
    --add-data "${REPO_ROOT}/bin:bin" \
    --add-data "${REPO_ROOT}/gui/web:gui/web" \
    --hidden-import "encodings.idna" \
    --collect-submodules netfix \
    netfix.py

BUILT_BINARY="${DIST_DIR}/${NAME}"
if [[ ! -x "${BUILT_BINARY}" ]]; then
    echo "PyInstaller did not produce an executable backend: ${BUILT_BINARY}" >&2
    exit 2
fi
cp "${BUILT_BINARY}" "${OUTPUT}"
chmod 755 "${OUTPUT}"
"${OUTPUT}" --version >/dev/null

echo "Built ${OUTPUT}"
echo "SHA256 $(shasum -a 256 "${OUTPUT}" | awk '{print $1}')"
