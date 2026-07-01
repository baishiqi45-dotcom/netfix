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

Kimi Code CLI registration is not automated here because current Kimi Code CLI
builds may not expose an "mcp add" command. The script prints a generic MCP
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
    else
        echo "codex CLI not found; skipping Codex MCP registration." >&2
    fi
fi

if [[ "${INSTALL_KIMI}" == true ]]; then
    if command -v kimi >/dev/null 2>&1; then
        echo "kimi CLI found. Automatic Kimi MCP registration is not enabled because current Kimi Code CLI builds may not expose a stable 'mcp add' command." >&2
        echo "Use this stdio config in any MCP-capable Kimi host:" >&2
        echo "  name: netfix" >&2
        echo "  command: python3" >&2
        echo "  args: ${MCP_SERVER}" >&2
    else
        echo "kimi CLI not found; skipping Kimi MCP registration." >&2
    fi
fi

echo "Netfix MCP setup finished."
