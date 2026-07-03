#!/bin/bash
# One-line installer for the Netfix macOS app, with optional local-agent MCP setup.
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
  NETFIX_REGISTER_CODEX  Register Codex MCP if codex CLI exists and bundled MCP is healthy, default: true

QA install, after the v0.2.0-qa.1 DMG release asset has been published:
  curl -fsSL https://raw.githubusercontent.com/baishiqi45-dotcom/netfix/main/scripts/install_mac_app_from_github.sh | bash

This installs Netfix.app locally, prints local-agent MCP config, and does not
copy proxy credentials or API keys.
The default QA DMG is unsigned; macOS may require right-click -> Open.

Safety:
  - Will install Netfix.app to ~/Applications by default.
  - May run 'codex mcp add netfix ...' when the Codex CLI is installed.
  - Prints copy/paste MCP config for Kimi, Claude Desktop, Cursor, MiniMax-compatible agents, and other MCP stdio hosts.
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
            echo "Dry run: would smoke-check bundled MCP, register Codex if codex CLI exists, and print generic MCP config."
        else
            echo "Dry run: would smoke-check bundled MCP and print generic MCP config, but skip Codex MCP registration."
        fi
    fi
    exit 0
fi

if [[ "$(uname -s)" != "Darwin" ]]; then
    echo "Netfix.app installer requires macOS." >&2
    exit 1
fi

if [[ "${UNINSTALL}" == true ]]; then
    if [[ "${REGISTER_CODEX}" == true ]] && command -v codex >/dev/null 2>&1 && codex mcp get netfix >/dev/null 2>&1; then
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

smoke_check_bundled_mcp() {
    if [[ ! -f "${MCP_SERVER}" ]]; then
        echo "Bundled MCP server was not found:"
        echo "  ${MCP_SERVER}"
        return 1
    fi
    if ! command -v python3 >/dev/null 2>&1; then
        echo "python3 was not found, so local-agent MCP setup was skipped."
        echo "Netfix.app is installed and can still be opened; install Python 3 before using MCP hosts."
        return 1
    fi
    if (cd /tmp && printf '%s\n' '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}' | python3 "${MCP_SERVER}" | grep -q '"name": "netfix"'); then
        echo "Bundled Netfix MCP smoke check passed."
        return 0
    fi
    echo "Bundled Netfix MCP smoke check failed:"
    echo "  python3 ${MCP_SERVER}"
    return 1
}

print_agent_mcp_config() {
    cat <<AGENT_MCP

🤖 本地智能体接入（可选，但装完就能复制）

   Codex：
      如果本机有 codex CLI，安装脚本会自动注册。
      手动命令：codex mcp add netfix -- python3 "${MCP_SERVER}"

   Kimi / Claude Desktop / Cursor / MiniMax-compatible 本地智能体：
      把下面这段复制到支持 MCP stdio 的宿主配置里。MiniMax 目前按
      “兼容 MCP stdio 的本地智能体/壳”处理，不假设它一定有官方 MCP client。

   ----- start of MCP config -----
   {
     "mcpServers": {
       "netfix": {
         "command": "python3",
         "args": ["${MCP_SERVER}"]
       }
     }
   }
   ----- end of MCP config -----

   常见粘贴位置：
      Kimi Code CLI / Kimi Desktop: ~/.kimi/mcp.json
      Claude Desktop: ~/Library/Application Support/Claude/claude_desktop_config.json
      Cursor: ~/.cursor/mcp.json 或项目根目录 .cursor/mcp.json
      其他本地智能体：找 MCP / Tools / stdio server 设置，填 command 和 args。
AGENT_MCP
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
MCP_READY=false
if smoke_check_bundled_mcp; then
    MCP_READY=true
    print_agent_mcp_config
fi

if [[ "${REGISTER_CODEX}" == true && "${MCP_READY}" == true ]]; then
    if command -v codex >/dev/null 2>&1; then
        if codex mcp get netfix >/dev/null 2>&1; then
            codex mcp remove netfix >/dev/null 2>&1 || true
        fi
        codex mcp add netfix -- python3 "${MCP_SERVER}"
        echo "Registered Netfix MCP for Codex. Restart Codex or open a new thread."
    else
        echo "codex CLI not found; skipped Codex MCP registration."
    fi
elif [[ "${REGISTER_CODEX}" == true ]]; then
    echo "Skipped Codex MCP registration because bundled MCP is not ready."
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

🧭 代理下一步（不懂网络也按这个走）：
   1. 打开 Netfix.app。
   2. 进入「设置 → 代理」。
   3. 粘贴服务商给你的整行连接参数，例如 host:port:用户名:密码、
      http://user:pass@host:port 或 socks5h://user:pass@host:port。
   4. 点「检查并保存到这台 Mac」。
   5. 检查通过后点「开始使用这台 Mac 上网」。
   6. 不用了或失败了，点「恢复原来的网络设置」。

   不要复制“当前出口 IP”。那只是检测结果，不能拿来连接。
   暂不支持 ss://、vmess://、Clash/sing-box 订阅链接；请去服务商后台
   复制 HTTP/SOCKS5 的 host、port、用户名、密码。

⚠️  这是 v0.2.0-qa.1 预览版 DMG（未签名未公证），仅适合技术测试用户，
   不要把它宣传成「普通用户正式版」。
FINISHED
