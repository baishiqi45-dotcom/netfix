#!/bin/bash
# One-line installer for the Netfix macOS app, with optional Codex MCP registration.
set -euo pipefail
IFS=$'\n\t'

VERSION="${NETFIX_VERSION:-0.2.0}"
REPO_SLUG="${NETFIX_REPO_SLUG:-baishiqi45-dotcom/netfix}"
RELEASE_TAG="${NETFIX_RELEASE_TAG:-v${VERSION}-qa.1}"
DEFAULT_DMG_SHA256="82815efd5888e60b914a1da303e2d42835a03b6b588f87d515346426eb57183b"
if [[ -n "${NETFIX_DMG_URL:-}" ]]; then
    DMG_URL="${NETFIX_DMG_URL}"
    DMG_SHA256="${NETFIX_DMG_SHA256:-}"
else
    DMG_URL="https://github.com/${REPO_SLUG}/releases/download/${RELEASE_TAG}/Netfix-${VERSION}.dmg"
    DMG_SHA256="${NETFIX_DMG_SHA256:-${DEFAULT_DMG_SHA256}}"
fi
INSTALL_TARGET="${NETFIX_INSTALL_TARGET:-${HOME}/Applications}"
APP_DEST="${INSTALL_TARGET}/Netfix.app"
OPEN_APP="${NETFIX_OPEN_APP:-true}"
REGISTER_CODEX="${NETFIX_REGISTER_CODEX:-true}"
DRY_RUN=false
UNINSTALL=false

usage() {
    cat <<'USAGE'
Usage: install_mac_app_from_github.sh [--no-open] [--no-codex] [--dry-run] [--uninstall]

Environment overrides:
  NETFIX_VERSION          App version, default: 0.2.0
  NETFIX_REPO_SLUG       GitHub owner/repo, default: baishiqi45-dotcom/netfix
  NETFIX_RELEASE_TAG      GitHub release tag, default: v0.2.0-qa.1
  NETFIX_DMG_URL         Explicit DMG URL, useful for a fixed release asset
  NETFIX_DMG_SHA256      Optional SHA256 expected for the DMG
  NETFIX_INSTALL_TARGET  Install folder, default: ~/Applications
  NETFIX_OPEN_APP        Open app after install, default: true
  NETFIX_REGISTER_CODEX  Register Codex MCP if codex CLI exists, default: true

QA install, after the v0.2.0-qa.1 DMG release asset has been published:
  curl -fsSL https://raw.githubusercontent.com/baishiqi45-dotcom/netfix/main/scripts/install_mac_app_from_github.sh | bash

This installs Netfix.app locally. It does not copy proxy credentials or API keys.
The default QA DMG is unsigned; macOS may require right-click -> Open.

Safety:
  - Will install Netfix.app to ~/Applications by default.
  - May run 'codex mcp add netfix ...' when the Codex CLI is installed.
  - Will not read or send proxy passwords, API keys, browser data, or shell history.
  - Run with --dry-run to preview actions, or --uninstall to remove only the app/MCP entry.
USAGE
}

for arg in "$@"; do
    case "$arg" in
        --no-open) OPEN_APP=false ;;
        --no-codex) REGISTER_CODEX=false ;;
        --dry-run) DRY_RUN=true ;;
        --uninstall|--remove) UNINSTALL=true ;;
        -h|--help) usage; exit 0 ;;
        *)
            echo "Unknown argument: $arg" >&2
            usage >&2
            exit 2
            ;;
    esac
done

if [[ "${DRY_RUN}" == true ]]; then
    if [[ "${UNINSTALL}" == true ]]; then
        echo "Dry run: would remove app at:"
        echo "  ${APP_DEST}"
        if [[ "${REGISTER_CODEX}" == true ]]; then
            echo "Dry run: would remove Codex MCP entry named 'netfix' if present."
        fi
    else
        echo "Dry run: would download Netfix DMG from:"
        echo "  ${DMG_URL}"
        if [[ -n "${DMG_SHA256}" ]]; then
            echo "Dry run: would verify DMG SHA256:"
            echo "  ${DMG_SHA256}"
        fi
        echo "Dry run: would install Netfix.app to:"
        echo "  ${APP_DEST}"
        if [[ "${REGISTER_CODEX}" == true ]]; then
            echo "Dry run: would register bundled MCP for Codex if codex CLI exists."
        else
            echo "Dry run: would skip Codex MCP registration."
        fi
    fi
    exit 0
fi

if [[ "$(uname -s)" != "Darwin" ]]; then
    echo "Netfix.app installer requires macOS." >&2
    exit 1
fi

if [[ "${UNINSTALL}" == true ]]; then
    if [[ "${REGISTER_CODEX}" == true && command -v codex >/dev/null 2>&1 && codex mcp get netfix >/dev/null 2>&1 ]]; then
        codex mcp remove netfix >/dev/null 2>&1 || true
        echo "Removed Codex MCP entry: netfix"
    fi
    if [[ -e "${APP_DEST}" ]]; then
        rm -rf "${APP_DEST}"
        echo "Removed Netfix.app:"
        echo "  ${APP_DEST}"
    else
        echo "Netfix.app was not found:"
        echo "  ${APP_DEST}"
    fi
    echo "Netfix macOS app uninstall finished. Local logs/settings are kept under ~/.netfix."
    exit 0
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
BACKUP_DEST=""
INSTALL_IN_PROGRESS=false
INSTALL_COMPLETE=false

rollback_failed_install() {
    if [[ "${INSTALL_IN_PROGRESS}" != true || "${INSTALL_COMPLETE}" == true ]]; then
        return
    fi
    if [[ -e "${APP_DEST}" ]]; then
        rm -rf "${APP_DEST}" || true
    fi
    if [[ -n "${BACKUP_DEST}" && -e "${BACKUP_DEST}" ]]; then
        mv "${BACKUP_DEST}" "${APP_DEST}" || true
        echo "Restored previous Netfix.app after failed install:"
        echo "  ${APP_DEST}"
    fi
}

cleanup() {
    local status=$?
    if [[ "${ATTACHED}" == true ]]; then
        hdiutil detach "${MOUNT_POINT}" -quiet >/dev/null 2>&1 || true
    fi
    if [[ "${status}" -ne 0 ]]; then
        rollback_failed_install
    fi
    rm -rf "${TMP_DIR}"
    exit "${status}"
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
if [[ -e "${APP_DEST}" ]]; then
    BACKUP_DEST="${APP_DEST}.backup.$(date +%Y%m%d-%H%M%S)"
    mv "${APP_DEST}" "${BACKUP_DEST}"
    echo "Existing app moved to: ${BACKUP_DEST}"
fi

INSTALL_IN_PROGRESS=true
ditto "${APP_IN_DMG}" "${APP_DEST}"

if [[ ! -x "${APP_DEST}/Contents/MacOS/Netfix" ]]; then
    echo "Installed app is missing executable: ${APP_DEST}/Contents/MacOS/Netfix" >&2
    exit 1
fi
INSTALL_COMPLETE=true

echo "Installed Netfix.app:"
echo "  ${APP_DEST}"
open -R "${APP_DEST}" >/dev/null 2>&1 || true

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

cat <<FINISHED

✅ Netfix 安装完成

📦 App 位置：
   ${APP_DEST}

🍎 首次打开提示（QA 版 DMG 未签名）：
   1. 双击 Netfix.app，如果 macOS 提示「无法验证开发者」，
      打开「系统设置 → 隐私与安全性」，滚到最下面点击「仍要打开」。
   2. 以后双击即可直接打开。

🧹 卸载命令（后悔了随时跑）：
   curl -fsSL https://raw.githubusercontent.com/${REPO_SLUG}/main/scripts/install_mac_app_from_github.sh | bash -s -- --uninstall

⚠️  这是 v0.2.0-qa.1 预览版 DMG（未签名未公证），仅适合技术测试用户，
   不要把它宣传成「普通用户正式版」。
FINISHED
