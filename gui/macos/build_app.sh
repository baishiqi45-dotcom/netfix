#!/bin/bash
# Build a minimal Netfix.app bundle from the SwiftUI menu bar target.
# Usage: cd gui/macos && ./build_app.sh [--install] [--release-candidate] [--strict-workspace]
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
BUILD_DIR="${REPO_ROOT}/gui/macos/.build"
APP_NAME="Netfix"
APP_BUNDLE="${BUILD_DIR}/${APP_NAME}.app"
BINARY="${BUILD_DIR}/release/${APP_NAME}"
DMG_PATH="${BUILD_DIR}/${APP_NAME}-0.2.0.dmg"
DMG_ROOT="${BUILD_DIR}/dmg-root"
NOTARIZATION_RECEIPT_PATH="${BUILD_DIR}/${APP_NAME}-0.2.0.notarization.json"
MANIFEST_PATH="${APP_BUNDLE}/Contents/Resources/release-manifest.json"
SIGN_IDENTITY="${NETFIX_SIGN_IDENTITY:--}"
REQUIRE_BUNDLED_RUNTIME="${NETFIX_REQUIRE_BUNDLED_RUNTIME:-false}"
NOTARIZE=false
if [[ -n "${NETFIX_NOTARY_PROFILE:-}" || -n "${NETFIX_NOTARY_APPLE_ID:-}" ]]; then
    NOTARIZE=true
fi

INSTALL=false
RELEASE_CANDIDATE=false
STRICT_WORKSPACE=false
for arg in "$@"; do
    case "$arg" in
        --install) INSTALL=true ;;
        --release-candidate) RELEASE_CANDIDATE=true ;;
        --strict-workspace) STRICT_WORKSPACE=true ;;
        *)
            echo "Unknown argument: $arg" >&2
            exit 2
            ;;
    esac
done

if [[ "${NOTARIZE}" == true && "${SIGN_IDENTITY}" == "-" ]]; then
    echo "NETFIX_SIGN_IDENTITY must be a Developer ID Application identity when notarization is enabled" >&2
    exit 2
fi

echo "Auditing workspace for release blockers..."
if [[ "$STRICT_WORKSPACE" == true ]]; then
    python3 "${REPO_ROOT}/scripts/release_audit.py" --scope workspace --root "${REPO_ROOT}"
else
    python3 "${REPO_ROOT}/scripts/release_audit.py" --scope workspace --root "${REPO_ROOT}" --warn-only || true
fi

echo "Building release binary..."
cd "$(dirname "$0")"
swift build -c release

echo "Creating ${APP_BUNDLE}..."
rm -rf "${APP_BUNDLE}"
mkdir -p "${APP_BUNDLE}/Contents/MacOS"
mkdir -p "${APP_BUNDLE}/Contents/Resources"

cp "${BINARY}" "${APP_BUNDLE}/Contents/MacOS/${APP_NAME}"
if [[ -n "${NETFIX_BACKEND_BIN:-}" ]]; then
    if [[ ! -x "${NETFIX_BACKEND_BIN}" ]]; then
        echo "NETFIX_BACKEND_BIN must point to an executable backend binary" >&2
        exit 2
    fi
    cp "${NETFIX_BACKEND_BIN}" "${APP_BUNDLE}/Contents/MacOS/netfix-backend"
fi
cp "${REPO_ROOT}/netfix.py" "${APP_BUNDLE}/Contents/Resources/"
cp -R "${REPO_ROOT}/netfix" "${APP_BUNDLE}/Contents/Resources/"
cp -R "${REPO_ROOT}/rules" "${APP_BUNDLE}/Contents/Resources/"
mkdir -p "${APP_BUNDLE}/Contents/Resources/gui"
cp -R "${REPO_ROOT}/gui/web" "${APP_BUNDLE}/Contents/Resources/gui/"
cp -R "${REPO_ROOT}/bin" "${APP_BUNDLE}/Contents/Resources/"
cp "${REPO_ROOT}/gui/macos/PrivacyInfo.xcprivacy" "${APP_BUNDLE}/Contents/Resources/"

WORKSPACE_AUDIT_JSON="$(python3 "${REPO_ROOT}/scripts/release_audit.py" --scope workspace --root "${REPO_ROOT}" --warn-only --json)"
WORKSPACE_FINDING_COUNT="$(python3 -c 'import json,sys; print(len(json.load(sys.stdin)["findings"]))' <<<"${WORKSPACE_AUDIT_JSON}")"
DEVELOPER_ID_SIGNED=false
if [[ "${SIGN_IDENTITY}" != "-" ]]; then
    DEVELOPER_ID_SIGNED=true
fi
BUNDLED_BACKEND=false
if [[ -x "${APP_BUNDLE}/Contents/MacOS/netfix-backend" ]]; then
    BUNDLED_BACKEND=true
fi
BUNDLED_PYTHON=false
if [[ -x "${APP_BUNDLE}/Contents/Resources/python/bin/python3" ]]; then
    BUNDLED_PYTHON=true
fi
if [[ "${REQUIRE_BUNDLED_RUNTIME}" == "1" || "${REQUIRE_BUNDLED_RUNTIME}" == "true" ]]; then
    if [[ "${BUNDLED_BACKEND}" != true && "${BUNDLED_PYTHON}" != true ]]; then
        echo "Bundled runtime is required, but no netfix-backend or Resources/python/bin/python3 exists in the app bundle." >&2
        echo "Build with NETFIX_BACKEND_BIN=/path/to/netfix-backend or include a bundled Python runtime." >&2
        exit 2
    fi
fi
python3 - <<PY
import json
from datetime import datetime, timezone
from pathlib import Path

manifest = {
    "name": "${APP_NAME}",
    "version": "0.2.0",
    "bundle_id": "dev.netfix.Netfix",
    "build_time": datetime.now(timezone.utc).isoformat(),
    "release_candidate": "${RELEASE_CANDIDATE}" == "true",
    "artifact_scope": "binary-app-bundle",
    "workspace_audit_findings": int("${WORKSPACE_FINDING_COUNT}"),
    "workspace_audit_note": "Workspace findings are excluded from the binary artifact by allowlisted bundle copy; use --strict-workspace for source release gating.",
    "backend_runtime": {
        "bundled_backend": "${BUNDLED_BACKEND}" == "true",
        "bundled_python": "${BUNDLED_PYTHON}" == "true",
        "bundled_runtime_required": "${REQUIRE_BUNDLED_RUNTIME}" in {"1", "true"},
        "system_python_fallback": True
    },
    "distribution": {
        "developer_id_signed": "${DEVELOPER_ID_SIGNED}" == "true",
        "notarization_requested": "${NOTARIZE}" == "true",
        "notarized": False,
        "notarization_receipt": "${NOTARIZATION_RECEIPT_PATH}" if "${NOTARIZE}" == "true" else None,
        "dmg_created": "${RELEASE_CANDIDATE}" == "true"
    }
}
Path("${MANIFEST_PATH}").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
PY

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
    <string>0.2.0</string>
    <key>CFBundleShortVersionString</key>
    <string>0.2.0</string>
    <key>LSUIElement</key>
    <false/>
    <key>LSMinimumSystemVersion</key>
    <string>13.0</string>
</dict>
</plist>
EOF

BACKEND_IN_BUNDLE="${APP_BUNDLE}/Contents/MacOS/netfix-backend"
if [[ "${SIGN_IDENTITY}" == "-" ]]; then
    if [[ -x "${BACKEND_IN_BUNDLE}" ]]; then
        echo "Ad-hoc signing bundled backend..."
        codesign --force --sign - "${BACKEND_IN_BUNDLE}"
    fi
    echo "Skipping ad-hoc app bundle signing for local runnable candidate."
else
    if [[ -x "${BACKEND_IN_BUNDLE}" ]]; then
        echo "Developer ID signing bundled backend with ${SIGN_IDENTITY}..."
        codesign --force --options runtime --timestamp --sign "${SIGN_IDENTITY}" "${BACKEND_IN_BUNDLE}"
    fi
    echo "Developer ID signing app bundle with ${SIGN_IDENTITY}..."
    codesign --force --options runtime --timestamp --sign "${SIGN_IDENTITY}" "${APP_BUNDLE}"
fi

if [[ -x "${BACKEND_IN_BUNDLE}" ]]; then
    if ! "${BACKEND_IN_BUNDLE}" --version >/dev/null 2>&1; then
        if [[ "${SIGN_IDENTITY}" == "-" ]]; then
            echo "Re-signing bundled backend after copy..."
            codesign --force --sign - "${BACKEND_IN_BUNDLE}"
        else
            echo "Re-signing bundled backend after app signing with ${SIGN_IDENTITY}..."
            codesign --force --options runtime --timestamp --sign "${SIGN_IDENTITY}" "${BACKEND_IN_BUNDLE}"
        fi
    fi
    "${BACKEND_IN_BUNDLE}" --version >/dev/null
fi

echo "Auditing app bundle..."
python3 "${REPO_ROOT}/scripts/release_audit.py" --scope bundle --root "${APP_BUNDLE}"
if [[ "${SIGN_IDENTITY}" == "-" ]]; then
    echo "Skipping app bundle code-sign verification for unsigned local candidate."
else
    codesign --verify --deep --strict "${APP_BUNDLE}"
fi

if [[ "$RELEASE_CANDIDATE" == true ]]; then
    echo "Creating local DMG candidate..."
    rm -f "${DMG_PATH}"
    rm -f "${NOTARIZATION_RECEIPT_PATH}"
    rm -rf "${DMG_ROOT}"
    mkdir -p "${DMG_ROOT}"
    cp -R "${APP_BUNDLE}" "${DMG_ROOT}/"
    hdiutil create -volname "${APP_NAME}" -srcfolder "${DMG_ROOT}" -ov -format UDZO "${DMG_PATH}" >/dev/null
    if [[ "${SIGN_IDENTITY}" != "-" ]]; then
        echo "Signing DMG with ${SIGN_IDENTITY}..."
        codesign --force --timestamp --sign "${SIGN_IDENTITY}" "${DMG_PATH}"
    fi
    if [[ "${NOTARIZE}" == true ]]; then
        echo "Submitting DMG for notarization..."
        if [[ -n "${NETFIX_NOTARY_PROFILE:-}" ]]; then
            xcrun notarytool submit "${DMG_PATH}" --keychain-profile "${NETFIX_NOTARY_PROFILE}" --wait
        else
            : "${NETFIX_NOTARY_APPLE_ID:?NETFIX_NOTARY_APPLE_ID required when NETFIX_NOTARY_PROFILE is not set}"
            : "${NETFIX_NOTARY_TEAM_ID:?NETFIX_NOTARY_TEAM_ID required when NETFIX_NOTARY_PROFILE is not set}"
            : "${NETFIX_NOTARY_PASSWORD:?NETFIX_NOTARY_PASSWORD required when NETFIX_NOTARY_PROFILE is not set}"
            xcrun notarytool submit "${DMG_PATH}" \
                --apple-id "${NETFIX_NOTARY_APPLE_ID}" \
                --team-id "${NETFIX_NOTARY_TEAM_ID}" \
                --password "${NETFIX_NOTARY_PASSWORD}" \
                --wait
        fi
        xcrun stapler staple "${DMG_PATH}"
        python3 - <<PY
import json
from datetime import datetime, timezone
from pathlib import Path

receipt = {
    "name": "${APP_NAME}",
    "version": "0.2.0",
    "artifact": "${DMG_PATH}",
    "developer_id_signed": "${DEVELOPER_ID_SIGNED}" == "true",
    "notarized": True,
    "stapled": True,
    "completed_at": datetime.now(timezone.utc).isoformat(),
}
Path("${NOTARIZATION_RECEIPT_PATH}").write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding="utf-8")
PY
    fi
    hdiutil verify "${DMG_PATH}" >/dev/null
    echo "Built DMG ${DMG_PATH}"
fi

if [[ "$INSTALL" == true ]]; then
    rm -rf "/Applications/${APP_NAME}.app"
    cp -R "${APP_BUNDLE}" "/Applications/${APP_NAME}.app"
    echo "Installed to /Applications/${APP_NAME}.app"
fi

echo "Built ${APP_BUNDLE}"
echo "Run: open '${APP_BUNDLE}'"
