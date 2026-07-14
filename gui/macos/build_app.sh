#!/bin/bash
# Build a self-contained, unsigned Netfix.app candidate and optional DMG.
# Usage: cd gui/macos && ./build_app.sh [--release-candidate] [--strict-workspace]
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
BUILD_DIR="${REPO_ROOT}/gui/macos/.build"
APP_NAME="Netfix"
APP_BUNDLE="${BUILD_DIR}/${APP_NAME}.app"
APP_EXECUTABLE="${BUILD_DIR}/release/${APP_NAME}"
BACKEND_BUILD="${BUILD_DIR}/backend/netfix-backend"
BACKEND_IN_BUNDLE="${APP_BUNDLE}/Contents/MacOS/netfix-backend"
MANIFEST_TOOL="${REPO_ROOT}/scripts/release_manifest.py"
VERSION="$(python3 "${MANIFEST_TOOL}" version --repo-root "${REPO_ROOT}")"
DMG_PATH="${BUILD_DIR}/${APP_NAME}-${VERSION}.dmg"
DMG_ROOT="${BUILD_DIR}/dmg-root"
MANIFEST_PATH="${APP_BUNDLE}/Contents/Resources/release-manifest.json"

RELEASE_CANDIDATE=false
STRICT_WORKSPACE=false
for arg in "$@"; do
    case "$arg" in
        --release-candidate) RELEASE_CANDIDATE=true ;;
        --strict-workspace) STRICT_WORKSPACE=true ;;
        *)
            echo "Unknown argument: $arg" >&2
            exit 2
            ;;
    esac
done

if [[ "${NETFIX_SIGN_IDENTITY:--}" != "-" || -n "${NETFIX_NOTARY_PROFILE:-}" || -n "${NETFIX_NOTARY_APPLE_ID:-}" ]]; then
    echo "This P0 pipeline produces an unsigned, unnotarized candidate only." >&2
    echo "Unset NETFIX_SIGN_IDENTITY and all NETFIX_NOTARY_* variables." >&2
    exit 2
fi

GIT_SHA_BEFORE="$(git -C "${REPO_ROOT}" rev-parse --verify HEAD)"
SOURCE_FINGERPRINT_BEFORE="$(python3 "${MANIFEST_TOOL}" fingerprint --repo-root "${REPO_ROOT}")"

echo "Auditing workspace for release blockers..."
if [[ "${STRICT_WORKSPACE}" == true ]]; then
    python3 "${REPO_ROOT}/scripts/release_audit.py" --scope workspace --root "${REPO_ROOT}"
else
    python3 "${REPO_ROOT}/scripts/release_audit.py" --scope workspace --root "${REPO_ROOT}" --warn-only || true
fi

echo "Building Swift release executable..."
cd "$(dirname "$0")"
swift build -c release

echo "Building self-contained backend with an existing local toolchain..."
"${REPO_ROOT}/scripts/build_backend_binary.sh" --output "${BACKEND_BUILD}"
if [[ ! -x "${BACKEND_BUILD}" ]]; then
    echo "Missing executable backend build: ${BACKEND_BUILD}" >&2
    exit 2
fi

echo "Creating ${APP_BUNDLE}..."
rm -rf "${APP_BUNDLE}"
mkdir -p "${APP_BUNDLE}/Contents/MacOS" "${APP_BUNDLE}/Contents/Resources"
cp "${APP_EXECUTABLE}" "${APP_BUNDLE}/Contents/MacOS/${APP_NAME}"
cp "${BACKEND_BUILD}" "${BACKEND_IN_BUNDLE}"
chmod 755 "${APP_BUNDLE}/Contents/MacOS/${APP_NAME}" "${BACKEND_IN_BUNDLE}"

cp "${REPO_ROOT}/netfix.py" "${APP_BUNDLE}/Contents/Resources/"
cp -R "${REPO_ROOT}/netfix" "${APP_BUNDLE}/Contents/Resources/"
cp -R "${REPO_ROOT}/rules" "${APP_BUNDLE}/Contents/Resources/"
mkdir -p "${APP_BUNDLE}/Contents/Resources/gui"
cp -R "${REPO_ROOT}/gui/web" "${APP_BUNDLE}/Contents/Resources/gui/"
cp -R "${REPO_ROOT}/bin" "${APP_BUNDLE}/Contents/Resources/"
cp "${REPO_ROOT}/gui/macos/PrivacyInfo.xcprivacy" "${APP_BUNDLE}/Contents/Resources/"

cat > "${APP_BUNDLE}/Contents/Info.plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleExecutable</key>
    <string>${APP_NAME}</string>
    <key>CFBundleIdentifier</key>
    <string>dev.netfix.Netfix</string>
    <key>CFBundleName</key>
    <string>${APP_NAME}</string>
    <key>CFBundleVersion</key>
    <string>${VERSION}</string>
    <key>CFBundleShortVersionString</key>
    <string>${VERSION}</string>
    <key>LSUIElement</key>
    <false/>
    <key>LSMinimumSystemVersion</key>
    <string>13.0</string>
</dict>
</plist>
EOF

echo "Skipping ad-hoc app bundle signing for local runnable candidate."
if ! "${BACKEND_IN_BUNDLE}" --version >/dev/null 2>&1; then
    echo "Re-signing bundled backend after copy..."
    codesign --force --sign - "${BACKEND_IN_BUNDLE}"
fi
"${BACKEND_IN_BUNDLE}" --version >/dev/null
codesign --verify --strict "${BACKEND_IN_BUNDLE}"
echo "Skipping app bundle code-sign verification for unsigned local candidate."

GIT_SHA_AFTER="$(git -C "${REPO_ROOT}" rev-parse --verify HEAD)"
SOURCE_FINGERPRINT_AFTER="$(python3 "${MANIFEST_TOOL}" fingerprint --repo-root "${REPO_ROOT}")"
if [[ "${SOURCE_FINGERPRINT_BEFORE}" != "${SOURCE_FINGERPRINT_AFTER}" || "${GIT_SHA_BEFORE}" != "${GIT_SHA_AFTER}" ]]; then
    echo "Release source changed during the build; refusing to write a misleading manifest." >&2
    exit 2
fi

WORKSPACE_AUDIT_JSON="$(python3 "${REPO_ROOT}/scripts/release_audit.py" --scope workspace --root "${REPO_ROOT}" --warn-only --json)"
WORKSPACE_FINDING_COUNT="$(python3 -c 'import json,sys; print(len(json.load(sys.stdin)["findings"]))' <<<"${WORKSPACE_AUDIT_JSON}")"
MANIFEST_ARGS=(
    create
    --repo-root "${REPO_ROOT}"
    --app-bundle "${APP_BUNDLE}"
    --output "${MANIFEST_PATH}"
    --workspace-audit-findings "${WORKSPACE_FINDING_COUNT}"
)
if [[ "${RELEASE_CANDIDATE}" == true ]]; then
    MANIFEST_ARGS+=(--release-candidate)
fi
python3 "${MANIFEST_TOOL}" "${MANIFEST_ARGS[@]}"
python3 "${MANIFEST_TOOL}" verify \
    --repo-root "${REPO_ROOT}" \
    --app-bundle "${APP_BUNDLE}" \
    --manifest "${MANIFEST_PATH}"

echo "Auditing app bundle..."
python3 "${REPO_ROOT}/scripts/release_audit.py" --scope bundle --root "${APP_BUNDLE}"

if [[ "${RELEASE_CANDIDATE}" == true ]]; then
    echo "Creating unsigned, unnotarized DMG candidate..."
    rm -f "${DMG_PATH}"
    rm -rf "${DMG_ROOT}"
    mkdir -p "${DMG_ROOT}"
    cp -R "${APP_BUNDLE}" "${DMG_ROOT}/"
    hdiutil create -volname "${APP_NAME}" -srcfolder "${DMG_ROOT}" -ov -format UDZO "${DMG_PATH}" >/dev/null
    hdiutil verify "${DMG_PATH}" >/dev/null
    echo "Built DMG ${DMG_PATH}"
fi

echo "Built ${APP_BUNDLE}"
echo "Candidate is not Developer ID signed and is not notarized."
echo "No application process was stopped or started; no desktop link was changed."
