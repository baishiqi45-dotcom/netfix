#!/bin/bash
# Register Netfix as a local MCP server for Codex and/or Kimi.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
MCP_SERVER="${ROOT}/netfix/mcp_server.py"
INSTALL_CODEX=false
INSTALL_KIMI=false
DRY_RUN=false

usage() {
    cat <<'USAGE'
Usage: scripts/install_mcp.sh [--all] [--codex] [--kimi] [--dry-run]

Examples:
  scripts/install_mcp.sh --all
  scripts/install_mcp.sh --codex
  scripts/install_mcp.sh --kimi --dry-run

This registers the local checkout as an MCP stdio server. It does not copy
proxy credentials or API keys.

Codex CLI currently uses:
  codex mcp add netfix -- python3 /path/to/netfix/mcp_server.py

Automatic Kimi MCP registration is not enabled here because current Kimi Code CLI
builds may not expose a stable "mcp add" command. The script prints a generic MCP
stdio config for Kimi-compatible hosts instead of pretending a command worked.
USAGE
}

if [[ "$#" -eq 0 ]]; then
    INSTALL_CODEX=true
    INSTALL_KIMI=true
fi

for arg in "$@"; do
    case "$arg" in
        --all) INSTALL_CODEX=true; INSTALL_KIMI=true ;;
        --codex) INSTALL_CODEX=true ;;
        --kimi) INSTALL_KIMI=true ;;
        --dry-run) DRY_RUN=true ;;
        -h|--help) usage; exit 0 ;;
        *)
            echo "Unknown argument: $arg" >&2
            usage >&2
            exit 2
            ;;
    esac
done

if [[ ! -f "${MCP_SERVER}" ]]; then
    echo "Cannot find ${MCP_SERVER}" >&2
    exit 1
fi

echo "Checking MCP server from a different working directory..."
if ! (cd /tmp && printf '%s\n' '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}' | python3 "${MCP_SERVER}" | grep -q '"name": "netfix"'); then
    echo "MCP smoke check failed. Run: python3 ${MCP_SERVER}" >&2
    exit 1
fi

run_cmd() {
    if [[ "${DRY_RUN}" == true ]]; then
        printf '+'
        for arg in "$@"; do
            printf ' '
            if [[ -z "${arg}" || "${arg}" == *[!a-zA-Z0-9_./:=+-]* ]]; then
                printf "'%s'" "${arg//\'/\'\\\'\'}"
            else
                printf '%s' "${arg}"
            fi
        done
        printf '\n'
    else
        "$@"
    fi
}

if [[ "${INSTALL_CODEX}" == true ]]; then
    if command -v codex >/dev/null 2>&1; then
        run_cmd codex mcp add netfix -- python3 "${MCP_SERVER}"
        echo ""
        echo "Codex MCP registered. Next steps:"
        echo "  1. Restart Codex or start a new thread."
        echo "  2. Type something like 'check my network' to see Netfix tools."
        echo "  3. Verify with: codex mcp list"
    else
        echo "codex CLI not found; skipping Codex MCP registration." >&2
        echo "Install Codex CLI first, or use the manual command below." >&2
    fi
fi

if [[ "${INSTALL_KIMI}" == true ]]; then
    echo ""
    echo "=============================================="
    echo " Kimi / Claude / Cursor MCP stdio config"
    echo "=============================================="
    echo ""
    echo "  把下面这段粘到你用的 MCP 宿主配置里："
    echo ""
    echo "  ----- start of MCP config -----"
    cat <<JSON
{
  "mcpServers": {
    "netfix": {
      "command": "python3",
      "args": ["${MCP_SERVER}"]
    }
  }
}
JSON
    echo "  ----- end of MCP config -----"
    echo ""
    echo "  粘到哪个文件："
    echo "    Kimi Code CLI / Kimi Desktop:  ~/.kimi/mcp.json"
    echo "    Claude Desktop:                ~/Library/Application Support/Claude/claude_desktop_config.json"
    echo "    Cursor:                        ~/.cursor/mcp.json  或  <项目根>/.cursor/mcp.json"
    echo ""
    if command -v kimi >/dev/null 2>&1; then
        echo "  ⚠️  当前 Kimi Code CLI 版本可能不暴露 'mcp add' 命令，所以这里只给配置片段，请手动粘贴。"
        echo "  Automatic Kimi MCP registration is not enabled because current Kimi Code CLI builds may not expose a stable 'mcp add' command."
    else
        echo "  ℹ️  没找到 kimi CLI；上面配置也适用于 Kimi Desktop 等 GUI 客户端。"
    fi
fi

echo ""
echo "=============================================="
echo " ✅ Netfix MCP 配置完成"
echo "=============================================="
echo " 直接测试 MCP server：  python3 ${MCP_SERVER}"
echo " Codex 用户：           codex mcp list"
