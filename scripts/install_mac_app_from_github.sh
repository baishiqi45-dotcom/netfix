#!/bin/bash
# One-line installer for the Netfix macOS app, with optional Codex MCP registration.
set -euo pipefail

VERSION="${NETFIX_VERSION:-0.2.0}"
REPO_SLUG="${NETFIX_REPO_SLUG:-baishiqi45-dotcom/netfix}"
DMG_URL="${NETFIX_DMG_URL:-https://github.com/${REPO_SLUG}/releases/latest/download/Netfix-${VERSION}.dmg}"
DMG_SHA256="${NETFIX_DMG_SHA256:-}"
INSTALL_TARGET="${NETFIX_INSTALL_TARGET:-${HOME}/Applications}"
OPEN_APP="${NETFIX_OPEN_APP:-true}"
REGISTER_CODEX="${NETFIX_REGISTER_CODEX:-true}"

usage() {
    cat <<'USAGE'
Usage: install_mac_app_from_github.sh [--no-open] [--no-codex]

Environment overrides:
  NETFIX_VERSION          App version, default: 0.2.0
  NETFIX_REPO_SLUG       GitHub owner/repo, default: baishiqi45-dotcom/netfix
  NETFIX_DMG_URL         Explicit DMG URL, useful for a fixed release asset
  NETFIX_DMG_SHA256      Optional SHA256 expected for the DMG
  NETFIX_INSTALL_TARGET  Install folder, default: ~/Applications
  NETFIX_OPEN_APP        Open app after install, default: true
  NETFIX_REGISTER_CODEX  Register Codex MCP if codex CLI exists, default: true

Public install, after a signed/notarized release DMG has been published:
  curl -fsSL https://raw.githubusercontent.com/baishiqi45-dotcom/netfix/main/scripts/install_mac_app_from_github.sh | bash

This installs Netfix.app locally. It does not copy proxy credentials or API keys.
USAGE
}

for arg in "$@"; do
    case "$arg" in
        --no-open) OPEN_APP=false ;;
        --no-codex) REGISTER_CODEX=false ;;
        -h|--help) usage; exit 0 ;;
        *)
            echo "Unknown argument: $arg" >&2
            usage >&2
            exit 2
            ;;
    esac
done

if [[ "$(uname -s)" != "Darwin" ]]; then
    echo "Netfix.app installer requires macOS." >&2
    exit 1
fi

need_cmd() {
    if ! command -v "$1" >/dev/null 2>&1; then
        echo "Missing required command: $1" >&2
        exit 1
    fi
}

need_cmd curl
need_cmd hdiutil
need_cmd ditto
need_cmd shasum

TMP_DIR="$(mktemp -d)"
MOUNT_POINT="${TMP_DIR}/mnt"
DMG_PATH="${TMP_DIR}/Netfix.dmg"
ATTACHED=false

cleanup() {
    if [[ "${ATTACHED}" == true ]]; then
        hdiutil detach "${MOUNT_POINT}" -quiet >/dev/null 2>&1 || true
    fi
    rm -rf "${TMP_DIR}"
}
trap cleanup EXIT

echo "Downloading Netfix DMG:"
echo "  ${DMG_URL}"
curl -fL "${DMG_URL}" -o "${DMG_PATH}"

if [[ -n "${DMG_SHA256}" ]]; then
    ACTUAL_SHA256="$(shasum -a 256 "${DMG_PATH}" | awk '{print $1}')"
    if [[ "${ACTUAL_SHA256}" != "${DMG_SHA256}" ]]; then
        echo "DMG SHA256 mismatch." >&2
        echo "Expected: ${DMG_SHA256}" >&2
        echo "Actual:   ${ACTUAL_SHA256}" >&2
        exit 1
    fi
fi

mkdir -p "${MOUNT_POINT}"
hdiutil attach "${DMG_PATH}" -nobrowse -readonly -mountpoint "${MOUNT_POINT}" -quiet
ATTACHED=true

APP_IN_DMG="$(find "${MOUNT_POINT}" -maxdepth 2 -type d -name "Netfix.app" | head -n 1)"
if [[ -z "${APP_IN_DMG}" || ! -d "${APP_IN_DMG}" ]]; then
    echo "DMG does not contain Netfix.app." >&2
    exit 1
fi

mkdir -p "${INSTALL_TARGET}"
APP_DEST="${INSTALL_TARGET}/Netfix.app"
if [[ -e "${APP_DEST}" ]]; then
    BACKUP_DEST="${APP_DEST}.backup.$(date +%Y%m%d-%H%M%S)"
    mv "${APP_DEST}" "${BACKUP_DEST}"
    echo "Existing app moved to: ${BACKUP_DEST}"
fi

ditto "${APP_IN_DMG}" "${APP_DEST}"

if [[ ! -x "${APP_DEST}/Contents/MacOS/Netfix" ]]; then
    echo "Installed app is missing executable: ${APP_DEST}/Contents/MacOS/Netfix" >&2
    exit 1
fi

echo "Installed Netfix.app:"
echo "  ${APP_DEST}"

MCP_SERVER="${APP_DEST}/Contents/Resources/netfix/mcp_server.py"
if [[ "${REGISTER_CODEX}" == true && -f "${MCP_SERVER}" ]]; then
    if command -v codex >/dev/null 2>&1; then
        if codex mcp get netfix >/dev/null 2>&1; then
            codex mcp remove netfix >/dev/null 2>&1 || true
        fi
        codex mcp add netfix -- python3 "${MCP_SERVER}"
        echo "Registered Netfix MCP for Codex. Restart Codex or open a new thread."
    else
        echo "codex CLI not found; skipped Codex MCP registration."
    fi
fi

if [[ "${OPEN_APP}" == true ]]; then
    open "${APP_DEST}" || true
fi

echo "Netfix macOS app install finished."
echo "If macOS says the developer cannot be verified, this DMG is not ready for public non-technical distribution."
