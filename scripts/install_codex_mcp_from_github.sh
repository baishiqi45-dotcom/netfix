#!/bin/bash
# One-line installer for registering Netfix as a Codex MCP server.
set -euo pipefail
IFS=$'\n\t'

REPO_SLUG="${NETFIX_REPO_SLUG:-baishiqi45-dotcom/netfix}"
REF="${NETFIX_REF:-main}"
REF_KIND="${NETFIX_REF_KIND:-heads}"
INSTALL_DIR="${NETFIX_INSTALL_DIR:-${HOME}/.netfix/netfix-codex-mcp-source}"
if [[ -n "${NETFIX_ARCHIVE_URL:-}" ]]; then
    ARCHIVE_URL="${NETFIX_ARCHIVE_URL}"
elif [[ "${REF_KIND}" == "heads" ]]; then
    ARCHIVE_URL="https://github.com/${REPO_SLUG}/archive/refs/heads/${REF}.zip"
else
    ARCHIVE_URL="https://github.com/${REPO_SLUG}/archive/refs/tags/${REF}.zip"
fi
REGISTER_CODEX=true
DRY_RUN=false
UNINSTALL=false

usage() {
    cat <<'USAGE'
Usage: install_codex_mcp_from_github.sh [--no-register] [--dry-run] [--uninstall]

Environment overrides:
  NETFIX_REPO_SLUG      GitHub owner/repo, default: baishiqi45-dotcom/netfix
  NETFIX_REF            Git ref to download, default: main
  NETFIX_REF_KIND       refs namespace, default: heads; use tags for a pinned release
  NETFIX_ARCHIVE_URL    Explicit source zip URL, useful for releases or tests
  NETFIX_INSTALL_DIR    Install directory, default: ~/.netfix/netfix-codex-mcp-source

One-line public install, after the repository has been pushed:
  curl -fsSL https://raw.githubusercontent.com/baishiqi45-dotcom/netfix/main/scripts/install_codex_mcp_from_github.sh | bash

This installs source files for local MCP use and registers:
  codex mcp add netfix -- python3 <install-dir>/netfix/mcp_server.py

Safety:
  - Will write Netfix source under ~/.netfix/netfix-codex-mcp-source by default.
  - May run 'codex mcp add netfix ...' when the Codex CLI is installed.
  - Will not read or send proxy passwords, API keys, browser data, or shell history.
  - Run with --dry-run to preview actions, or --uninstall to remove the MCP entry and local source.
USAGE
}

for arg in "$@"; do
    case "$arg" in
        --no-register) REGISTER_CODEX=false ;;
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

MCP_SERVER="${INSTALL_DIR}/netfix/mcp_server.py"

if [[ "${DRY_RUN}" == true ]]; then
    if [[ "${UNINSTALL}" == true ]]; then
        echo "Dry run: would remove Codex MCP entry named 'netfix' if present."
        echo "Dry run: would remove local source at: ${INSTALL_DIR}"
    else
        echo "Dry run: would download Netfix source from:"
        echo "  ${ARCHIVE_URL}"
        echo "Dry run: would install source to:"
        echo "  ${INSTALL_DIR}"
        if [[ "${REGISTER_CODEX}" == true ]]; then
            echo "Dry run: would register Codex MCP:"
            echo "  codex mcp add netfix -- python3 '${MCP_SERVER}'"
        else
            echo "Dry run: would skip Codex registration."
        fi
    fi
    exit 0
fi

if [[ "${UNINSTALL}" == true ]]; then
    if command -v codex >/dev/null 2>&1 && codex mcp get netfix >/dev/null 2>&1; then
        codex mcp remove netfix >/dev/null 2>&1 || true
        echo "Removed Codex MCP entry: netfix"
    else
        echo "Codex MCP entry was not found or codex CLI is not installed."
    fi
    if [[ -e "${INSTALL_DIR}" ]]; then
        rm -rf "${INSTALL_DIR}"
        echo "Removed local Netfix MCP source:"
        echo "  ${INSTALL_DIR}"
    else
        echo "Local Netfix MCP source was not found:"
        echo "  ${INSTALL_DIR}"
    fi
    echo "Netfix Codex MCP uninstall finished. Local logs/settings are kept under ~/.netfix."
    exit 0
fi

need_cmd() {
    if ! command -v "$1" >/dev/null 2>&1; then
        echo "Missing required command: $1" >&2
        exit 1
    fi
}

need_cmd python3
need_cmd curl

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
python3 - "${ARCHIVE}" "${UNPACK_DIR}" <<'PY'
from pathlib import Path
import sys
import zipfile

archive = Path(sys.argv[1])
destination = Path(sys.argv[2])
root = destination.resolve()

with zipfile.ZipFile(archive) as zip_file:
    for member in zip_file.infolist():
        target = (destination / member.filename).resolve()
        if target != root and root not in target.parents:
            raise SystemExit(f"Unsafe archive path: {member.filename}")
    zip_file.extractall(destination)
PY

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
