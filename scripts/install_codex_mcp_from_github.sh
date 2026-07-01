#!/bin/bash
# One-line installer for registering Netfix as a Codex MCP server.
set -euo pipefail

REPO_SLUG="${NETFIX_REPO_SLUG:-baishiqi45-dotcom/netfix}"
REF="${NETFIX_REF:-main}"
INSTALL_DIR="${NETFIX_INSTALL_DIR:-${HOME}/.netfix/netfix-codex-mcp-source}"
ARCHIVE_URL="${NETFIX_ARCHIVE_URL:-https://github.com/${REPO_SLUG}/archive/refs/heads/${REF}.zip}"
REGISTER_CODEX=true

usage() {
    cat <<'USAGE'
Usage: install_codex_mcp_from_github.sh [--no-register]

Environment overrides:
  NETFIX_REPO_SLUG      GitHub owner/repo, default: baishiqi45-dotcom/netfix
  NETFIX_REF            Git ref to download, default: main
  NETFIX_ARCHIVE_URL    Explicit source zip URL, useful for releases or tests
  NETFIX_INSTALL_DIR    Install directory, default: ~/.netfix/netfix-codex-mcp-source

One-line public install, after the repository has been pushed:
  curl -fsSL https://raw.githubusercontent.com/baishiqi45-dotcom/netfix/main/scripts/install_codex_mcp_from_github.sh | bash

This installs source files for local MCP use and registers:
  codex mcp add netfix -- python3 <install-dir>/netfix/mcp_server.py

No proxy credentials or API keys are copied.
USAGE
}

for arg in "$@"; do
    case "$arg" in
        --no-register) REGISTER_CODEX=false ;;
        -h|--help) usage; exit 0 ;;
        *)
            echo "Unknown argument: $arg" >&2
            usage >&2
            exit 2
            ;;
    esac
done

need_cmd() {
    if ! command -v "$1" >/dev/null 2>&1; then
        echo "Missing required command: $1" >&2
        exit 1
    fi
}

need_cmd python3
need_cmd curl
need_cmd unzip

TMP_DIR="$(mktemp -d)"
cleanup() {
    rm -rf "${TMP_DIR}"
}
trap cleanup EXIT

ARCHIVE="${TMP_DIR}/netfix-source.zip"
UNPACK_DIR="${TMP_DIR}/unpack"
TMP_INSTALL="${TMP_DIR}/install"

echo "Downloading Netfix source:"
echo "  ${ARCHIVE_URL}"
curl -fsSL "${ARCHIVE_URL}" -o "${ARCHIVE}"

mkdir -p "${UNPACK_DIR}" "${TMP_INSTALL}"
unzip -q "${ARCHIVE}" -d "${UNPACK_DIR}"

SRC_DIR="$(find "${UNPACK_DIR}" -mindepth 1 -maxdepth 1 -type d | head -n 1)"
if [[ -z "${SRC_DIR}" || ! -d "${SRC_DIR}" ]]; then
    echo "Downloaded archive did not contain a source directory." >&2
    exit 1
fi

if [[ ! -f "${SRC_DIR}/netfix/mcp_server.py" ]]; then
    echo "Downloaded archive is missing netfix/mcp_server.py." >&2
    exit 1
fi

cp -R "${SRC_DIR}/." "${TMP_INSTALL}/"

MCP_SERVER="${INSTALL_DIR}/netfix/mcp_server.py"
mkdir -p "$(dirname "${INSTALL_DIR}")"
if [[ -e "${INSTALL_DIR}" ]]; then
    BACKUP_DIR="${INSTALL_DIR}.backup.$(date +%Y%m%d-%H%M%S)"
    mv "${INSTALL_DIR}" "${BACKUP_DIR}"
    echo "Existing install moved to: ${BACKUP_DIR}"
fi
mv "${TMP_INSTALL}" "${INSTALL_DIR}"

echo "Checking Netfix MCP server..."
if ! (cd /tmp && printf '%s\n' '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}' | python3 "${MCP_SERVER}" | grep -q '"name": "netfix"'); then
    echo "MCP smoke check failed: ${MCP_SERVER}" >&2
    exit 1
fi

if [[ "${REGISTER_CODEX}" == true ]]; then
    if command -v codex >/dev/null 2>&1; then
        if codex mcp get netfix >/dev/null 2>&1; then
            codex mcp remove netfix >/dev/null 2>&1 || true
        fi
        codex mcp add netfix -- python3 "${MCP_SERVER}"
        codex mcp get netfix
    else
        echo "codex CLI not found; Netfix source is installed but MCP registration was skipped." >&2
        echo "Manual command after installing Codex CLI:" >&2
        echo "  codex mcp add netfix -- python3 '${MCP_SERVER}'" >&2
    fi
else
    echo "Skipping Codex registration by request."
    echo "Manual command:"
    echo "  codex mcp add netfix -- python3 '${MCP_SERVER}'"
fi

echo "Netfix Codex MCP install finished."
echo "Restart Codex or open a new Codex thread before expecting the new MCP tools to appear."
