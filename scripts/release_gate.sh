#!/bin/bash
# Run the local release-candidate verification gate.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
STRICT_WORKSPACE=false
SKIP_PYTEST=false
WITH_BACKEND_BINARY=false
REQUIRE_RUNTIME=false

for arg in "$@"; do
    case "$arg" in
        --strict-workspace) STRICT_WORKSPACE=true ;;
        --skip-pytest) SKIP_PYTEST=true ;;
        --with-backend-binary) WITH_BACKEND_BINARY=true; REQUIRE_RUNTIME=true ;;
        --require-runtime) REQUIRE_RUNTIME=true ;;
        *)
            echo "Unknown argument: $arg" >&2
            exit 2
            ;;
    esac
done

echo "== Python syntax =="
cd "${ROOT}"
python3 -m py_compile scripts/release_audit.py scripts/release_readiness.py scripts/release_export.py scripts/release_preflight.py scripts/release_evidence.py scripts/clean_machine_qa.py scripts/legal_release_review.py scripts/marketing_claims_check.py scripts/provider_contract_check.py scripts/provider_smoke_check.py netfix/*.py

echo "== Provider contracts =="
python3 scripts/provider_contract_check.py

echo "== Provider fixture smoke =="
python3 scripts/provider_smoke_check.py

echo "== Marketing claims =="
python3 scripts/marketing_claims_check.py

echo "== Python unittest =="
python3 -m unittest discover tests -v

if [[ "${SKIP_PYTEST}" != true ]]; then
    echo "== Python pytest =="
    python3 -m pytest -q
fi

echo "== Swift build =="
cd "${ROOT}/gui/macos"
swift build

BUILD_ENV=()
if [[ "${WITH_BACKEND_BINARY}" == true ]]; then
    echo "== Build standalone backend =="
    cd "${ROOT}"
    ./scripts/build_backend_binary.sh
    BUILD_ENV+=("NETFIX_BACKEND_BIN=${ROOT}/dist/netfix-backend")
fi
if [[ "${REQUIRE_RUNTIME}" == true ]]; then
    BUILD_ENV+=("NETFIX_REQUIRE_BUNDLED_RUNTIME=true")
fi

echo "== Build release candidate =="
cd "${ROOT}/gui/macos"
BUILD_ARGS=(--release-candidate)
if [[ "${STRICT_WORKSPACE}" == true ]]; then
    BUILD_ARGS+=(--strict-workspace)
fi
if [[ "${#BUILD_ENV[@]}" -gt 0 ]]; then
    env "${BUILD_ENV[@]}" ./build_app.sh "${BUILD_ARGS[@]}"
else
    ./build_app.sh "${BUILD_ARGS[@]}"
fi

echo "== Bundle audit =="
cd "${ROOT}"
python3 scripts/release_audit.py --scope bundle --root gui/macos/.build/Netfix.app

echo "== DMG verify =="
hdiutil verify gui/macos/.build/Netfix-0.2.0.dmg >/dev/null

echo "== DMG mount check =="
MNT="$(mktemp -d /tmp/netfix-dmg-check.XXXXXX)"
cleanup() {
    hdiutil detach "${MNT}" >/dev/null 2>&1 || true
    rmdir "${MNT}" >/dev/null 2>&1 || true
}
trap cleanup EXIT
hdiutil attach -nobrowse -readonly -mountpoint "${MNT}" gui/macos/.build/Netfix-0.2.0.dmg >/dev/null
test -d "${MNT}/Netfix.app/Contents"
hdiutil detach "${MNT}" >/dev/null
rmdir "${MNT}" >/dev/null 2>&1 || true
trap - EXIT

if [[ "${REQUIRE_RUNTIME}" == true ]]; then
    echo "== DMG bundled backend smoke =="
    NETFIX_REQUIRE_BUNDLED_RUNTIME=true ./scripts/verify_dmg_backend.sh gui/macos/.build/Netfix-0.2.0.dmg
fi

echo "release gate passed"
