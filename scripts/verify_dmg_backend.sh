#!/bin/bash
# Verify a DMG contains a runnable Netfix.app bundled backend.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VERSION="$(python3 "${REPO_ROOT}/scripts/release_manifest.py" version --repo-root "${REPO_ROOT}")"
DMG_PATH="${1:-${REPO_ROOT}/gui/macos/.build/Netfix-${VERSION}.dmg}"

if [[ ! -f "${DMG_PATH}" ]]; then
    echo "DMG not found: ${DMG_PATH}" >&2
    exit 2
fi

MNT="$(mktemp -d /tmp/netfix-dmg-backend.XXXXXX)"
SERVER_PID=""
SERVER_LOG="$(mktemp /tmp/netfix-dmg-backend-log.XXXXXX)"
RUNTIME_HOME="$(mktemp -d /tmp/netfix-dmg-backend-home.XXXXXX)"

cleanup() {
    if [[ -n "${SERVER_PID}" ]]; then
        kill -INT "${SERVER_PID}" >/dev/null 2>&1 || true
        for _ in $(seq 1 20); do
            if ! kill -0 "${SERVER_PID}" >/dev/null 2>&1; then
                break
            fi
            sleep 0.2
        done
        if kill -0 "${SERVER_PID}" >/dev/null 2>&1; then
            kill -TERM "${SERVER_PID}" >/dev/null 2>&1 || true
            sleep 0.5
        fi
        if kill -0 "${SERVER_PID}" >/dev/null 2>&1; then
            kill -KILL "${SERVER_PID}" >/dev/null 2>&1 || true
        fi
        wait "${SERVER_PID}" >/dev/null 2>&1 || true
    fi
    for _ in $(seq 1 10); do
        if hdiutil detach "${MNT}" >/dev/null 2>&1; then
            break
        fi
        sleep 0.5
    done
    if hdiutil info | grep -F "${MNT}" >/dev/null 2>&1; then
        hdiutil detach -force "${MNT}" >/dev/null 2>&1 || true
    fi
    rmdir "${MNT}" >/dev/null 2>&1 || true
    rm -f "${SERVER_LOG}"
    rm -rf "${RUNTIME_HOME}"
}
trap cleanup EXIT

hdiutil attach -nobrowse -readonly -mountpoint "${MNT}" "${DMG_PATH}" >/dev/null

APP="${MNT}/Netfix.app"
MANIFEST="${APP}/Contents/Resources/release-manifest.json"
BACKEND="${APP}/Contents/MacOS/netfix-backend"
MCP_SERVER="${APP}/Contents/Resources/netfix/mcp_server.py"

test -d "${APP}/Contents"
test -f "${MANIFEST}"
test -f "${MCP_SERVER}"
test -x "${BACKEND}"

python3 "${REPO_ROOT}/scripts/release_manifest.py" verify \
    --app-bundle "${APP}" \
    --manifest "${MANIFEST}"

MCP_JSON="$(cd /tmp && printf '%s\n' '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"dmg-smoke","version":"1.0"}}}' | python3 "${MCP_SERVER}")"
MCP_JSON="${MCP_JSON}" python3 - <<'PY'
import json
import os

lines = [line for line in os.environ["MCP_JSON"].splitlines() if line.strip()]
if not lines:
    raise SystemExit("bundled MCP server did not return a JSON-RPC response")
data = json.loads(lines[-1])
result = data.get("result") or {}
server = result.get("serverInfo") or {}
if server.get("name") != "netfix":
    raise SystemExit("bundled MCP server did not initialize as netfix")
print(json.dumps({"ok": True, "bundled_mcp_server": server.get("name")}, ensure_ascii=False))
PY

if [[ -x "${BACKEND}" ]]; then
    "${BACKEND}" --version >/dev/null
    HOME="${RUNTIME_HOME}" "${BACKEND}" server --host 127.0.0.1 --port 0 --timeout 30 >"${SERVER_LOG}" 2>&1 &
    SERVER_PID="$!"
    PORT=""
    TOKEN=""
    for _ in $(seq 1 80); do
        if ! kill -0 "${SERVER_PID}" >/dev/null 2>&1; then
            cat "${SERVER_LOG}" >&2 || true
            echo "bundled backend exited before listening" >&2
            exit 1
        fi
read -r PORT TOKEN < <(python3 - "${SERVER_LOG}" <<'PY'
import re
import sys
from pathlib import Path
text = Path(sys.argv[1]).read_text(errors="replace") if Path(sys.argv[1]).exists() else ""
port = re.search(r"http://127\.0\.0\.1:(\d+)", text)
token_file = re.search(r"token_file=(\S+)", text)
token = ""
if token_file:
    path = Path(token_file.group(1))
    if path.exists():
        token = path.read_text(errors="replace").strip()
print((port.group(1) if port else "") + " " + token)
PY
)
        if [[ -n "${PORT}" && -n "${TOKEN}" ]]; then
            break
        fi
        sleep 0.5
    done
    if [[ -z "${PORT}" || -z "${TOKEN}" ]]; then
        cat "${SERVER_LOG}" >&2 || true
        echo "bundled backend did not print a listening port and readable token_file" >&2
        exit 1
    fi
    curl -fsS "http://127.0.0.1:${PORT}/health" >/dev/null
    RUN_JSON="$(curl -fsS "http://127.0.0.1:${PORT}/run" \
        -H "Content-Type: application/json" \
        -H "X-Netfix-Token: ${TOKEN}" \
        -d '{"command":["services","--group","ai"],"timeout":120,"async":false}')"
    RUN_JSON="${RUN_JSON}" python3 - <<'PY'
import json
import os

data = json.loads(os.environ["RUN_JSON"])
if not data.get("ok"):
    raise SystemExit(f"bundled backend /run failed: {data.get('error') or data}")
report = data.get("result") or {}
if not isinstance(report, dict) or not report.get("diagnostics"):
    raise SystemExit("bundled backend /run did not return a diagnostic report")
errors = [str(item.get("error")) for item in report.get("diagnostics", []) if item.get("error")]
if any("netfix.cli" in item for item in errors):
    raise SystemExit("bundled backend /run still invoked netfix.cli as a CLI argument")
if any(item == "unknown encoding: idna" for item in errors):
    raise SystemExit("bundled backend /run is missing the idna codec")
print(json.dumps({
    "ok": True,
    "run_services_ai": report.get("explanation", {}).get("headline") or report.get("meta", {}).get("version"),
    "diagnostics": len(report.get("diagnostics", [])),
}, ensure_ascii=False))
PY
    WEB_HTML="$(curl -fsS "http://127.0.0.1:${PORT}/")"
    [[ "${WEB_HTML}" == *"btn-open-logs"* ]]
    [[ "${WEB_HTML}" == *"openLogs()"* ]]
    [[ "${WEB_HTML}" == *"copySupportBundle"* ]]
    [[ "${WEB_HTML}" == *"/support/bundle"* ]]
    [[ "${WEB_HTML}" == *"recovery-panel"* ]]
    [[ "${WEB_HTML}" == *"renderProxyBridgeLifecycle"* ]]
    [[ "${WEB_HTML}" == *"renderProxyBridgeStartupCheck"* ]]
    [[ "${WEB_HTML}" == *"proxy-bridge-auto-restart"* ]]
    [[ "${WEB_HTML}" == *"importProxyPreview"* ]]
    [[ "${WEB_HTML}" == *"netfix_proxy_import_preview.v1"* ]]
    [[ "${WEB_HTML}" == *"renderLLMChainReadiness"* ]]
    [[ "${WEB_HTML}" == *"netfix_llm_chain_readiness.v1"* ]]
    [[ "${WEB_HTML}" == *"testLLMChain"* ]]
    [[ "${WEB_HTML}" == *"TEST_LLM_CHAIN"* ]]
    [[ "${WEB_HTML}" == *"/llm/chain-test"* ]]
    curl -fsS -H "X-Netfix-Token: ${TOKEN}" "http://127.0.0.1:${PORT}/llm/providers" >/dev/null
    SUPPORT_JSON="$(curl -fsS -H "X-Netfix-Token: ${TOKEN}" "http://127.0.0.1:${PORT}/support/bundle")"
    SUPPORT_JSON="${SUPPORT_JSON}" python3 - <<'PY'
import json
import os

raw = os.environ["SUPPORT_JSON"]
data = json.loads(raw)
if data.get("schema_version") != "netfix_support_bundle.v1":
    raise SystemExit("support bundle schema missing from bundled backend")
if not data.get("ok") or "support_text" not in data:
    raise SystemExit("support bundle endpoint did not return a copyable bundle")
if "X-Netfix-Token" in raw or "__NETFIX_API_TOKEN__" in raw:
    raise SystemExit("support bundle leaked local API token markers")
print(json.dumps({"ok": True, "support_bundle": data.get("schema_version")}, ensure_ascii=False))
PY
    LLM_CHAIN_JSON="$(curl -fsS -H "X-Netfix-Token: ${TOKEN}" "http://127.0.0.1:${PORT}/llm/chain-readiness")"
    LLM_CHAIN_JSON="${LLM_CHAIN_JSON}" python3 - <<'PY'
import json
import os

data = json.loads(os.environ["LLM_CHAIN_JSON"])
chains = data.get("chains") or []
if data.get("schema_version") != "netfix_llm_chain_readiness.v1":
    raise SystemExit("LLM chain readiness schema missing from bundled backend")
ids = {item.get("id") for item in chains}
if not {"text", "image_question"}.issubset(ids):
    raise SystemExit("LLM chain readiness did not expose text and image chains")
print(json.dumps({"ok": True, "llm_chain_readiness": sorted(ids)}, ensure_ascii=False))
PY
    curl -fsS -H "X-Netfix-Token: ${TOKEN}" "http://127.0.0.1:${PORT}/proxy/monitor" >/dev/null
    BRIDGE_SETTINGS_JSON="$(curl -fsS -H "X-Netfix-Token: ${TOKEN}" "http://127.0.0.1:${PORT}/settings/proxy-bridge")"
    BRIDGE_SETTINGS_JSON="${BRIDGE_SETTINGS_JSON}" python3 - <<'PY'
import json
import os

data = json.loads(os.environ["BRIDGE_SETTINGS_JSON"])
settings = data.get("settings") or {}
if not data.get("ok") or "auto_restart_enabled" not in settings:
    raise SystemExit("proxy bridge settings endpoint missing from bundled backend")
if settings.get("auto_restart_enabled") is not False:
    raise SystemExit("proxy bridge auto restart should default to false")
print(json.dumps({"ok": True, "proxy_bridge_auto_restart_default": settings.get("auto_restart_enabled")}, ensure_ascii=False))
PY
    IMPORT_JSON="$(curl -fsS -H "X-Netfix-Token: ${TOKEN}" -H "Content-Type: application/json" \
        -d '{"input":"host,port,user,password\nproxy.example.com,8000,user,real-secret-123\ndirect.miyaip.online:8001:demo-user:miya-demo-secret"}' \
        "http://127.0.0.1:${PORT}/proxy/import-preview")"
    IMPORT_JSON="${IMPORT_JSON}" python3 - <<'PY'
import json
import os

raw = os.environ["IMPORT_JSON"]
data = json.loads(raw)
if data.get("schema_version") != "netfix_proxy_import_preview.v1":
    raise SystemExit("proxy import preview schema missing from bundled backend")
if data.get("summary", {}).get("valid_count") != 2:
    raise SystemExit("proxy import preview did not parse the provider table row and host:port:user:pass row")
if "real-secret-123" in raw:
    raise SystemExit("proxy import preview leaked the provider password")
if "miya-demo-secret" in raw:
    raise SystemExit("proxy import preview leaked the host:port:user:pass password")
print(json.dumps({"ok": True, "proxy_import_preview": data.get("summary", {})}, ensure_ascii=False))
PY
    FIX_DRY_RUN_JSON="$(curl -fsS -H "X-Netfix-Token: ${TOKEN}" -H "Content-Type: application/json" \
        -d '{"fix_id":"disable-ipv6","dry_run":true}' \
        "http://127.0.0.1:${PORT}/fixes/execute")"
    FIX_DRY_RUN_JSON="${FIX_DRY_RUN_JSON}" python3 - <<'PY'
import json
import os

data = json.loads(os.environ["FIX_DRY_RUN_JSON"])
if data.get("fix_id") != "disable-ipv6" or data.get("status") != "dry-run":
    raise SystemExit("confirmed fix endpoint did not expose disable-ipv6 dry-run")
if data.get("executed"):
    raise SystemExit("disable-ipv6 dry-run executed commands")
print(json.dumps({"ok": True, "disable_ipv6_dry_run": data.get("status")}, ensure_ascii=False))
PY
    PROFILE_JSON="$(curl -fsS -H "X-Netfix-Token: ${TOKEN}" -H "Content-Type: application/json" \
        -d '{"input":"socks5h://proxy.example.com:1080"}' \
        "http://127.0.0.1:${PORT}/proxy/profiles")"
    PROFILE_ID="$(PROFILE_JSON="${PROFILE_JSON}" python3 - <<'PY'
import json
import os

data = json.loads(os.environ["PROFILE_JSON"])
profile = data.get("profile") or {}
if not data.get("ok") or not profile.get("id"):
    raise SystemExit("failed to create temporary proxy profile for export smoke")
print(profile["id"])
PY
)"
    APPLY_DRY_RUN_JSON="$(curl -fsS -H "X-Netfix-Token: ${TOKEN}" -H "Content-Type: application/json" \
        -d '{"mode":"system"}' \
        "http://127.0.0.1:${PORT}/proxy/profiles/${PROFILE_ID}/apply-dry-run")"
    APPLY_DRY_RUN_JSON="${APPLY_DRY_RUN_JSON}" python3 - <<'PY'
import json
import os

data = json.loads(os.environ["APPLY_DRY_RUN_JSON"])
steps = data.get("steps") or []
labels = " ".join(str(step.get("label") or "") for step in steps)
if data.get("status") != "dry_run" or not data.get("requires_confirmation"):
    raise SystemExit("proxy apply dry-run did not require confirmation")
if "IPv6" not in labels:
    raise SystemExit("proxy apply dry-run did not include IPv6 protection step")
print(json.dumps({"ok": True, "proxy_apply_dry_run_ipv6": True}, ensure_ascii=False))
PY
    REPLACE_JSON="$(curl -fsS -H "X-Netfix-Token: ${TOKEN}" -H "Content-Type: application/json" \
        -d '{"input":"socks5h://new.proxy.example.com:1081"}' \
        "http://127.0.0.1:${PORT}/proxy/profiles/${PROFILE_ID}/replace")"
    REPLACE_JSON="${REPLACE_JSON}" PROFILE_ID="${PROFILE_ID}" python3 - <<'PY'
import json
import os

raw = os.environ["REPLACE_JSON"]
data = json.loads(raw)
profile = data.get("profile") or {}
new_endpoint = data.get("new_endpoint") or {}
previous_endpoint = data.get("previous_endpoint") or {}
if not data.get("ok"):
    raise SystemExit("proxy profile replace endpoint failed in bundled backend")
if data.get("profile_id") != os.environ["PROFILE_ID"] or profile.get("id") != os.environ["PROFILE_ID"]:
    raise SystemExit("proxy profile replace did not preserve the local profile id")
if previous_endpoint.get("host") != "proxy.example.com" or new_endpoint.get("host") != "new.proxy.example.com":
    raise SystemExit("proxy profile replace did not rotate the endpoint")
if "real-secret" in raw:
    raise SystemExit("proxy profile replace leaked a provider password")
print(json.dumps({"ok": True, "proxy_profile_replace": new_endpoint}, ensure_ascii=False))
PY
    EXPORT_JSON="$(curl -fsS -H "X-Netfix-Token: ${TOKEN}" -H "Content-Type: application/json" \
        -d '{"format":"all"}' \
        "http://127.0.0.1:${PORT}/proxy/profiles/${PROFILE_ID}/export")"
    EXPORT_JSON="${EXPORT_JSON}" python3 - <<'PY'
import json
import os

raw = os.environ["EXPORT_JSON"]
data = json.loads(raw)
package = data.get("package") or {}
files = package.get("files") or []
if package.get("schema_version") != "netfix_proxy_client_package.v1":
    raise SystemExit("proxy client package schema missing from bundled backend")
if not any(item.get("path") == "README.md" for item in files):
    raise SystemExit("proxy client package README missing")
if not any(str(item.get("path", "")).endswith(".sing-box.json") for item in files):
    raise SystemExit("proxy client package sing-box file missing")
if "real-secret" in raw:
    raise SystemExit("proxy client package leaked a provider password")
print(json.dumps({"ok": True, "proxy_client_package": package.get("recommended_format")}, ensure_ascii=False))
PY
    BRIDGE_JSON="$(curl -fsS -H "X-Netfix-Token: ${TOKEN}" "http://127.0.0.1:${PORT}/proxy/bridge")"
    BRIDGE_JSON="${BRIDGE_JSON}" python3 - <<'PY'
import json
import os
import sys

data = json.loads(os.environ["BRIDGE_JSON"])
if not data.get("ok"):
    raise SystemExit("proxy bridge status did not return ok")
lifecycle = data.get("lifecycle") or {}
if lifecycle.get("schema_version") != "netfix_proxy_bridge_lifecycle.v1":
    raise SystemExit("proxy bridge lifecycle schema missing from bundled backend")
if not lifecycle.get("status"):
    raise SystemExit("proxy bridge lifecycle status missing from bundled backend")
startup = data.get("startup_check") or {}
if startup.get("schema_version") != "netfix_proxy_bridge_startup_check.v1":
    raise SystemExit("proxy bridge startup_check schema missing from bundled backend")
if not isinstance(startup.get("lifecycle"), dict):
    raise SystemExit("proxy bridge startup_check lifecycle missing from bundled backend")
print(json.dumps({
    "ok": True,
    "bridge_lifecycle": lifecycle.get("status"),
    "startup_checked": bool(startup.get("checked_at")),
}, ensure_ascii=False))
PY
    ROLLBACK_RESPONSE="$(curl -sS -w '\n%{http_code}' -H "X-Netfix-Token: ${TOKEN}" -H "Content-Type: application/json" \
        -d '{"confirmed":true,"confirmation":"ROLLBACK_PROXY_PROFILE"}' \
        "http://127.0.0.1:${PORT}/proxy/profiles/rollback")"
    ROLLBACK_STATUS="${ROLLBACK_RESPONSE##*$'\n'}"
    ROLLBACK_JSON="${ROLLBACK_RESPONSE%$'\n'*}"
    ROLLBACK_JSON="${ROLLBACK_JSON}" ROLLBACK_STATUS="${ROLLBACK_STATUS}" python3 - <<'PY'
import json
import os

status = int(os.environ["ROLLBACK_STATUS"])
data = json.loads(os.environ["ROLLBACK_JSON"])
if status not in {200, 404}:
    raise SystemExit(f"proxy rollback endpoint returned unexpected HTTP {status}: {data}")
if status == 404 and data.get("status") != "no_journal":
    raise SystemExit("proxy rollback endpoint did not explain missing restore journal")
if status == 200 and not data.get("ok"):
    raise SystemExit("proxy rollback endpoint returned 200 without ok=true")
print(json.dumps({
    "ok": True,
    "proxy_rollback_endpoint": data.get("status"),
    "http_status": status,
}, ensure_ascii=False))
PY
fi

echo "DMG backend verification passed: ${DMG_PATH}"
